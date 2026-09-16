export type ReliabilityFindingSource = "model" | "market";

export interface ReliabilityFindingMeasurement {
  source: ReliabilityFindingSource;
  n: number;
  brier: number;
  reliability: number;
  resolution: number;
  uncertainty: number;
  reconstructedBrier: number;
  remainder: number;
  reliabilityComparison: "smaller" | "larger" | "equal";
}

export interface ReliabilityFindingSport {
  sport: string;
  nRows: number;
  measurements: ReliabilityFindingMeasurement[];
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

function measurementFrom(value: unknown, source: ReliabilityFindingSource): ReliabilityFindingMeasurement | null {
  const entry = record(value);
  const n = count(entry?.n);
  const brier = finite(entry?.brier);
  const reliability = finite(entry?.reliability);
  const resolution = finite(entry?.resolution);
  const uncertainty = finite(entry?.uncertainty);
  const reconstructedBrier = finite(entry?.reconstructed_brier);
  if (n === null || brier === null || reliability === null || resolution === null || uncertainty === null || reconstructedBrier === null) return null;
  return {
    source, n, brier: rounded(brier), reliability: rounded(reliability), resolution: rounded(resolution), uncertainty: rounded(uncertainty), reconstructedBrier: rounded(reconstructedBrier),
    remainder: rounded(brier - reconstructedBrier),
    reliabilityComparison: reliability < resolution ? "smaller" : reliability > resolution ? "larger" : "equal",
  };
}

/** Parses the published Murphy decomposition snapshot and labels closure differences as derived values. */
export function buildReliabilityFinding(value: unknown): ReliabilityFindingSport[] {
  const sports = record(record(value)?.sports);
  if (!sports) return [];
  return Object.entries(sports).flatMap(([sport, value]) => {
    const entry = record(value);
    const nRows = count(entry?.n_rows);
    const model = measurementFrom(entry?.model_prob, "model");
    const market = measurementFrom(entry?.market_prob, "market");
    return nRows === null || !model || !market ? [] : [{ sport, nRows, measurements: [model, market] }];
  });
}
