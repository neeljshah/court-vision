import { formatMetric, metricLabel, type ComparisonEntity, type ComparisonPack } from "@/lib/analytics/comparisonData";

export type MatchupInsight = { field: string; label: string; aValue: string; bValue: string; aPercentile: number; bPercentile: number; gap: number };

const validPercentile = (value: unknown): value is number =>
  typeof value === "number" && Number.isFinite(value) && value >= 0 && value <= 100;

export function matchupInsights(pack: ComparisonPack, a: ComparisonEntity, b: ComparisonEntity, limit = 4): MatchupInsight[] {
  return pack.metricKeys.map((field) => {
    const aPercentile = a.percentiles[field];
    const bPercentile = b.percentiles[field];
    const aValue = a.values[field];
    const bValue = b.values[field];
    if (!validPercentile(aPercentile) || !validPercentile(bPercentile)) return undefined;
    if (![aValue, bValue].every((value) => typeof value === "number" && Number.isFinite(value))) return undefined;
    return { field, label: metricLabel(field), aValue: formatMetric(aValue, field), bValue: formatMetric(bValue, field), aPercentile, bPercentile, gap: Math.abs(aPercentile - bPercentile) };
  }).filter((insight): insight is MatchupInsight => Boolean(insight)).sort((left, right) => right.gap - left.gap || left.label.localeCompare(right.label)).slice(0, limit);
}

export function sharedMeasuredAxisCount(pack: ComparisonPack, a: ComparisonEntity, b: ComparisonEntity): number {
  return matchupInsights(pack, a, b, Number.MAX_SAFE_INTEGER).length;
}
