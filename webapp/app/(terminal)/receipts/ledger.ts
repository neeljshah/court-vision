// ledger.ts -- /receipts/ cell helpers. receipts.json stores delta_ci as MARKET minus MODEL
// ("x [lo, hi]"), the same convention as the home scoreboard; both pages print model minus
// market through lib/scoreboardDelta.ts so the two can never disagree.
import { modelMinusMarket } from "@/lib/scoreboardDelta";
import { FIGURES } from "@/lib/figures";

export const DELTA_HEADER = "model minus market (95% CI); positive = model worse";
export const CELL_FLOOR = FIGURES.forward_cell_floor_games.value;

const fmt = (v: number) => (v >= 0 ? "+" : "") + v.toFixed(4);

/** "x [lo, hi]" (market minus model) -> "+d [+lo, +hi]" (model minus market); anything else as is. */
export function modelMinusMarketCell(deltaCi: string): string {
  const m = /^\s*(-?[\d.]+)\s*\[\s*(-?[\d.]+)\s*,\s*(-?[\d.]+)\s*\]\s*$/.exec(deltaCi);
  const d = m ? modelMinusMarket(Number(m[1]), [Number(m[2]), Number(m[3])]) : null;
  return d ? `${fmt(d.delta)} [${fmt(d.ci[0])}, ${fmt(d.ci[1])}]` : deltaCi;
}

/** A MODEL_SHARPER read on fewer games than the pre-registered cell floor is not a result. */
export function underFloor(verdict: string, n: number | string): boolean {
  return verdict.startsWith("MODEL_SHARPER") && Number(n) < CELL_FLOOR;
}
