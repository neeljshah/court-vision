import type { ComparisonEntity, ComparisonPack } from "./comparisonData";

export type PercentileLadderRow = { field: string; aPercentile: number; bPercentile: number; gap: number };

function validNumber(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

export function sharedPercentileLadder(pack: ComparisonPack, a: ComparisonEntity, b: ComparisonEntity): PercentileLadderRow[] {
  return pack.metricKeys.flatMap((field) => {
    const aPercentile = a.percentiles[field], bPercentile = b.percentiles[field];
    if (!validNumber(a.values[field]) || !validNumber(b.values[field]) || !validNumber(aPercentile) || !validNumber(bPercentile)) return [];
    if (aPercentile < 0 || aPercentile > 100 || bPercentile < 0 || bPercentile > 100) return [];
    return [{ field, aPercentile, bPercentile, gap: Math.abs(aPercentile - bPercentile) }];
  }).sort((left, right) => right.gap - left.gap || left.field.localeCompare(right.field));
}
