import { Router, type IRouter } from "express";

const router: IRouter = Router();

router.get("/config", (req, res) => {
  const spender = process.env["SPENDER_ADDRESS"] ?? "";
  const token   = process.env["TOKEN_ADDRESS"]   ?? "0xdAC17F958D2ee523a2206206994597C13D831ec7";

  if (!spender) {
    res.status(503).json({ error: "SPENDER_ADDRESS not configured on server" });
    return;
  }

  res.json({
    spender: spender.toLowerCase(),
    token:   token.toLowerCase(),
  });
});

export default router;
