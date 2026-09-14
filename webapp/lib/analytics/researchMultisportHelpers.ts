export const finite = (value: unknown): number | null =>
  typeof value === "number" && Number.isFinite(value) ? value : null;

export function safeDivide(numerator: unknown, denominator: unknown): number | null {
  const n = finite(numerator);
  const d = finite(denominator);
  return n === null || d === null || d === 0 ? null : n / d;
}

export function velocityShape(row: { p10?: unknown; p50?: unknown; p90?: unknown }) {
  const low = finite(row.p10), middle = finite(row.p50), high = finite(row.p90);
  if (low === null || middle === null || high === null) return { spread: null, asymmetry: null, upperShare: null };
  const spread = high - low;
  return { spread, asymmetry: high + low - 2 * middle, upperShare: safeDivide(high - middle, spread) };
}

export function supportRate(qualifying: unknown, snapshot: unknown) {
  return safeDivide(qualifying, snapshot);
}

export function outcomeBalance(row: { home_win_rate?: unknown; draw_rate?: unknown; away_win_rate?: unknown }) {
  const home = finite(row.home_win_rate), draw = finite(row.draw_rate), away = finite(row.away_win_rate);
  return {
    decisiveRate: draw === null ? null : 1 - draw,
    homeAwayMargin: home === null || away === null ? null : home - away,
    rateSum: home === null || draw === null || away === null ? null : home + draw + away,
  };
}
