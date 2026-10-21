// lib/scoreboardDelta.ts -- sign convention for the home scoreboard.
// cross_sport_scoreboard.json stores paired_delta_mean as MARKET minus MODEL
// (a MARKET_SHARPER Brier row is negative, the MODEL_SHARPER CRPS row positive).
// The page states "model minus market", so the displayed delta is the negation:
// lower Brier / CRPS is better, so a positive displayed delta = model worse.
// Rounded to 4 dp so tooltips never print 18-digit floats.

const r4 = (v: number) => Math.round(v * 1e4) / 1e4 + 0; // + 0 folds -0 to 0

// A non-finite input (a null or NaN slipped into the artifact) has no sign to flip:
// null, so the row says so, never a NaN rendered as "NaN" or folded to 0.
export function modelMinusMarket(
  marketMinusModel: number,
  ci: [number, number],
): { delta: number; ci: [number, number] } | null {
  if (!Number.isFinite(marketMinusModel) || !Array.isArray(ci) || !Number.isFinite(ci[0]) || !Number.isFinite(ci[1])) return null;
  return { delta: r4(-marketMinusModel), ci: [r4(-ci[1]), r4(-ci[0])] };
}

export const DELTA_LEGEND =
  "lower Brier is better; delta = model minus market; positive = model worse";
