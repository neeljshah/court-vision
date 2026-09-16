export interface HomeCalibrationExample {
  bin_lo: number;
  bin_hi: number;
  mean_p: number;
  mean_y: number;
  n: number;
  n_games: number;
  mean_y_ci: [number, number];
  gap: number;
  gap_ci: [number, number];
  ci_pct: [number, number];
  cluster_unit: string;
  n_boot: number;
  artifact_date: string | null;
}

type UnknownRecord = Record<string, unknown>;

function record(value: unknown): UnknownRecord | null {
  return value !== null && typeof value === "object" && !Array.isArray(value) ? value as UnknownRecord : null;
}

function finite(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function count(value: unknown): number | null {
  const parsed = finite(value);
  return parsed !== null && parsed >= 0 ? Math.trunc(parsed) : null;
}

function rounded(value: number): number {
  return Number(value.toFixed(6));
}

function artifactDate(root: UnknownRecord): string | null {
  const value = typeof root.as_of === "string" ? root.as_of : root.generated_at;
  if (typeof value !== "string" || !/^\d{4}-\d{2}-\d{2}(?:[ T].*)?$/.test(value)) return null;
  return value.slice(0, 10);
}

/** Selects the most-supported readable MLB model bin near an even forecast. */
export function buildHomeCalibrationExample(value: unknown): HomeCalibrationExample | null {
  const root = record(value);
  if (!root) return null;
  const sports = record(root?.sports);
  const mlb = record(sports?.mlb);
  const sides = record(mlb?.sides);
  const model = record(sides?.model_prob);
  const bins = Array.isArray(model?.bins) ? model.bins : [];
  const ciPct = Array.isArray(root.ci_pct) ? root.ci_pct.map(finite) : [];
  const nBoot = count(root.n_boot);
  const clusterUnit = typeof root.cluster_unit === "string" ? root.cluster_unit : null;
  if (ciPct.length !== 2 || ciPct[0] === null || ciPct[1] === null || nBoot === null || !clusterUnit) return null;
  const candidates = bins.flatMap((value) => {
    const bin = record(value);
    const binLo = finite(bin?.bin_lo);
    const binHi = finite(bin?.bin_hi);
    const meanP = finite(bin?.mean_p);
    const meanY = finite(bin?.mean_y);
    const n = count(bin?.n);
    const nGames = count(bin?.n_games);
    const interval = Array.isArray(bin?.mean_y_ci) ? bin.mean_y_ci.map(finite) : [];
    const gap = finite(bin?.gap);
    const gapCi = Array.isArray(bin?.gap_ci) ? bin.gap_ci.map(finite) : [];
    if (binLo === null || binHi === null || meanP === null || meanY === null || n === null || nGames === null || interval.length !== 2 || interval[0] === null || interval[1] === null || gap === null || gapCi.length !== 2 || gapCi[0] === null || gapCi[1] === null) return [];
    if (meanP < 0.4 || meanP > 0.6) return [];
    return [{ bin_lo: rounded(binLo), bin_hi: rounded(binHi), mean_p: rounded(meanP), mean_y: rounded(meanY), n, n_games: nGames, mean_y_ci: [rounded(interval[0]), rounded(interval[1])] as [number, number], gap: rounded(gap), gap_ci: [rounded(gapCi[0]), rounded(gapCi[1])] as [number, number] }];
  });
  const selected = candidates.sort((left, right) => right.n - left.n)[0];
  return selected ? { ...selected, ci_pct: [rounded(ciPct[0]), rounded(ciPct[1])], cluster_unit: clusterUnit, n_boot: nBoot, artifact_date: artifactDate(root) } : null;
}
