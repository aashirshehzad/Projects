import { NextResponse } from "next/server";
import { listTokenUsage, tokenUsageTotals } from "@/lib/db";
import { getDb } from "@/lib/schema";

export async function GET() {
  const usage = listTokenUsage();
  const totals = tokenUsageTotals();

  const perUser = getDb()
    .prepare(
      `SELECT u.email as email,
              COALESCE(SUM(t.tokens_in), 0) as tokensIn,
              COALESCE(SUM(t.tokens_out), 0) as tokensOut
       FROM token_usage t
       JOIN users u ON u.id = t.user_id
       GROUP BY t.user_id
       ORDER BY tokensIn + tokensOut DESC`
    )
    .all();

  const daily = getDb()
    .prepare(
      `SELECT substr(created_at, 1, 10) as day,
              COALESCE(SUM(tokens_in), 0) as tokensIn,
              COALESCE(SUM(tokens_out), 0) as tokensOut
       FROM token_usage
       GROUP BY day
       ORDER BY day DESC
       LIMIT 30`
    )
    .all();

  return NextResponse.json({ usage, totals, perUser, daily });
}
