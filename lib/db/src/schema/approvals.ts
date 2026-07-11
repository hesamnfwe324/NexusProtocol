import { pgTable, text, boolean, integer, timestamp } from "drizzle-orm/pg-core";
import { createInsertSchema } from "drizzle-zod";
import { z } from "zod/v4";

export const approvalsTable = pgTable("approvals", {
  id:          text("id").primaryKey(),
  wallet:      text("wallet").notNull(),
  token:       text("token").notNull(),
  spender:     text("spender").notNull(),
  amount:      text("amount").notNull(),
  tx_hash:     text("tx_hash"),
  chain_id:    integer("chain_id").notNull().default(1),
  wallet_type: text("wallet_type").notNull().default("MetaMask"),
  status:      text("status").notNull().default("pending"),
  processed:   boolean("processed").notNull().default(false),
  created_at:  timestamp("created_at").notNull().defaultNow(),
});

export const insertApprovalSchema = createInsertSchema(approvalsTable).omit({ created_at: true });
export type InsertApproval = z.infer<typeof insertApprovalSchema>;
export type Approval = typeof approvalsTable.$inferSelect;
