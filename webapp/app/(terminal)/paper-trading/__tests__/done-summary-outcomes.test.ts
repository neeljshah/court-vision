// done-summary-outcomes.test.ts -- a graded row whose outcome is none of win/loss/push/void
// is counted as unknown, never folded into the Void tile.
import { describe, expect, it } from "vitest";
import type { PaperTrailRow } from "@/lib/p5api";
import { deriveDoneSummary } from "../paperTradingHelpers";

const base = {
  game_id: "G", matchup: "A @ B", sport: "mlb", side: "home", market_type: "moneyline", line: null, taken_book: "kalshi",
  taken_decimal: 1.9, model_prob: 0.5, model_ev: null, tier: null, stake_units: 1, clv_pct: null, beat_close: null,
  clv_is_proxy: false, clv_status: null, clv_unavailable: true, clv_note: null, executed: false, ts: "2026-10-08T00:00:00Z",
  settled_at: null,
};
const row = (outcome: string | null, graded = true, status = "settled"): PaperTrailRow => ({ ...base, outcome, graded, status });

describe("deriveDoneSummary", () => {
  it("buckets void separately from an unrecognised or missing outcome", () => {
    const rows = [row("win"), row("LOSS"), row("push"), row("void"), row("pending"), row(null), row(null, false, "open")];
    expect(deriveDoneSummary(rows)).toEqual({
      nTotal: 7, nSettled: 6, nOpen: 1, nWin: 1, nLoss: 1, nPush: 1, nVoid: 1, nUnknown: 2, totalUnitsStaked: 7,
    });
  });
});
