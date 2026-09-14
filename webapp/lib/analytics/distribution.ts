import type { LabRow } from "./labTypes";

export type DistributionBin = { low: number; high: number; count: number; includesHigh: boolean };
export type Distribution = {
  total: number; measured: number; missing: number; zero: number; negative: number; positive: number;
  min: number | null; max: number | null; mean: number | null; median: number | null;
  q1: number | null; q3: number | null; iqr: number | null; bins: DistributionBin[];
};

// Hyndman-Fan R7: interpolate at zero-based position p * (n - 1).
function quantile(sorted: number[], p: number): number | null {
  if (!sorted.length) return null;
  const position = p * (sorted.length - 1), index = Math.floor(position), fraction = position - index;
  return sorted[index] * (1 - fraction) + sorted[Math.min(index + 1, sorted.length - 1)] * fraction;
}

export function summarizeDistribution(rows: LabRow[], key: string): Distribution {
  const values = rows.map(row => row.values[key]).filter((value): value is number => typeof value === "number" && Number.isFinite(value)).sort((a, b) => a - b);
  const n = values.length, min = n ? values[0] : null, max = n ? values[n - 1] : null;
  const q1 = quantile(values, .25), q3 = quantile(values, .75);
  const bins: DistributionBin[] = [];
  if (min !== null && max !== null) {
    const count = min === max ? 1 : Math.min(8, Math.ceil(Math.sqrt(n)));
    const width = (max - min) / count;
    for (let i = 0; i < count; i++) bins.push({ low: min + width * i, high: i === count - 1 ? max : min + width * (i + 1), count: 0, includesHigh: i === count - 1 });
    for (const bin of bins) bin.count = values.filter(value => value >= bin.low && (bin.includesHigh ? value <= bin.high : value < bin.high)).length;
  }
  return {
    total: rows.length, measured: n, missing: rows.length - n,
    zero: values.filter(v => v === 0).length, negative: values.filter(v => v < 0).length, positive: values.filter(v => v > 0).length,
    min, max, mean: n ? values.reduce((sum, value) => sum + value / n, 0) : null,
    median: quantile(values, .5), q1, q3, iqr: q1 !== null && q3 !== null ? q3 - q1 : null, bins,
  };
}
