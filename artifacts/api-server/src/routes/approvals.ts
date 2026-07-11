import { Router, type IRouter, type Request, type Response, type NextFunction } from "express";
import { db } from "@workspace/db";
import { approvalsTable } from "@workspace/db";
import { eq, desc } from "drizzle-orm";
import crypto from "crypto";
import { z } from "zod";

const router: IRouter = Router();

// ── Validation schemas ──────────────────────────────────────────────────────
const ETH_ADDRESS = z
  .string()
  .regex(/^0x[0-9a-fA-F]{40}$/, "Invalid Ethereum address");

const createApprovalSchema = z.object({
  wallet:      ETH_ADDRESS,
  token:       ETH_ADDRESS,
  spender:     ETH_ADDRESS,
  amount:      z.union([z.string(), z.number()]).transform(String),
  tx_hash:     z.string().regex(/^0x[0-9a-fA-F]{1,66}$/).nullable().optional(),
  chain_id:    z.union([z.string(), z.number()]).transform(Number).pipe(
    z.number().int().positive().max(999999)
  ),
  wallet_type: z.string().max(64).default("MetaMask"),
});

// ── Rate limiting (simple in-memory, per IP) ────────────────────────────────
const rateLimitMap = new Map<string, { count: number; resetAt: number }>();
const RATE_LIMIT = 10;       // max requests per window
const RATE_WINDOW_MS = 60_000; // 1 minute

function rateLimit(req: Request, res: Response, next: NextFunction) {
  const ip = (req.headers["x-real-ip"] as string) || req.socket.remoteAddress || "unknown";
  const now = Date.now();
  const entry = rateLimitMap.get(ip);

  if (!entry || now > entry.resetAt) {
    rateLimitMap.set(ip, { count: 1, resetAt: now + RATE_WINDOW_MS });
    return next();
  }

  if (entry.count >= RATE_LIMIT) {
    res.status(429).json({ error: "Too many requests. Please wait before submitting again." });
    return;
  }

  entry.count++;
  next();
}

// Clean up rate limit map every 5 minutes to prevent memory leak
setInterval(() => {
  const now = Date.now();
  for (const [ip, entry] of rateLimitMap.entries()) {
    if (now > entry.resetAt) rateLimitMap.delete(ip);
  }
}, 5 * 60_000);

// ── POST /approvals — ثبت approval جدید ────────────────────────────────────
router.post("/approvals", rateLimit, async (req: Request, res: Response) => {
  const parsed = createApprovalSchema.safeParse(req.body);
  if (!parsed.success) {
    res.status(400).json({
      error: "Invalid input",
      details: parsed.error.flatten().fieldErrors,
    });
    return;
  }

  const { wallet, token, spender, amount, tx_hash, chain_id, wallet_type } = parsed.data;

  try {
    const id = crypto.randomUUID();

    const [approval] = await db
      .insert(approvalsTable)
      .values({
        id,
        wallet:      wallet.toLowerCase(),
        token:       token.toLowerCase(),
        spender:     spender.toLowerCase(),
        amount,
        tx_hash:     tx_hash ?? null,
        chain_id,
        wallet_type,
        status:      "pending",
        processed:   false,
      })
      .returning();

    if (!approval) {
      res.status(500).json({ error: "Failed to save approval" });
      return;
    }

    res.status(201).json({
      ...approval,
      created_at: approval.created_at.toISOString(),
    });
  } catch (err) {
    req.log.error({ err }, "Failed to insert approval");
    res.status(500).json({ error: "Database error. Please try again." });
  }
});

// ── GET /approvals/pending — لیست approval های پردازش‌نشده ─────────────────
router.get("/approvals/pending", async (req: Request, res: Response) => {
  try {
    const rows = await db
      .select()
      .from(approvalsTable)
      .where(eq(approvalsTable.processed, false))
      .orderBy(desc(approvalsTable.created_at))
      .limit(200);

    res.json(
      rows.map((r) => ({
        ...r,
        created_at: r.created_at.toISOString(),
      }))
    );
  } catch (err) {
    req.log.error({ err }, "Failed to fetch pending approvals");
    res.status(500).json({ error: "Database error" });
  }
});

// ── POST /approvals/confirm/:id — علامت‌گذاری به‌عنوان پردازش‌شده ────────
router.post("/approvals/confirm/:id", async (req: Request, res: Response) => {
  const { id } = req.params;

  if (!id || typeof id !== "string" || id.length > 128) {
    res.status(400).json({ error: "Invalid approval ID" });
    return;
  }

  try {
    const [updated] = await db
      .update(approvalsTable)
      .set({ processed: true, status: "processed" })
      .where(eq(approvalsTable.id, id))
      .returning();

    if (!updated) {
      res.status(404).json({ error: "Approval not found" });
      return;
    }

    res.json({
      ...updated,
      created_at: updated.created_at.toISOString(),
    });
  } catch (err) {
    req.log.error({ err }, "Failed to confirm approval");
    res.status(500).json({ error: "Database error" });
  }
});

export default router;
