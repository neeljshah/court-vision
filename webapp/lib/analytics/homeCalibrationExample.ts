export interface HomeCalibrationExample {
  mean_p: number;
  mean_y: number;
  n: number;
  n_games: number;
  mean_y_ci: [number, number];
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
  if (typeof value !== "string" || !value || value.toLowerCase() === "unknown") return null;
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
  const candidates = bins.flatMap((value) => {
    const bin = record(value);
    const meanP = finite(bin?.mean_p);
    const meanY = finite(bin?.mean_y);
    const n = count(bin?.n);
    const nGames = count(bin?.n_games);
    const interval = Array.isArray(bin?.mean_y_ci) ? bin.mean_y_ci.map(finite) : [];
    if (meanP === null || meanY === null || n === null || nGames === null || interval.length !== 2 || interval[0] === null || interval[1] === null) return [];
    if (meanP < 0.4 || meanP > 0.6) return [];
    return [{ mean_p: rounded(meanP), mean_y: rounded(meanY), n, n_games: nGames, mean_y_ci: [rounded(interval[0]), rounded(interval[1])] as [number, number] }];
  });
  const selected = candidates.sort((left, right) => right.n - left.n)[0];
  return selected ? { ...selected, artifact_date: artifactDate(root) } : null;
}
