export type StateReliabilitySource = "model" | "market";
export type StateReliabilityMetric = "signed-gap" | "absolute-gap" | "support";

export interface StateReliabilityRow {
  sport: string;
  timeBucket: string;
  probabilityBucket: string;
  source: StateReliabilitySource;
  n: number;
  meanP: number;
  meanY: number;
  calibrationError: number;
}

export interface StateReliabilitySport {
  sport: string;
  nSkippedNoStateField: number;
  rows: StateReliabilityRow[];
  timeBuckets: string[];
  probabilityBuckets: string[];
}

type UnknownRecord = Record<string, unknown>;

function record(value: unknown): UnknownRecord | null {
  return value !== null && typeof value === "object" && !Array.isArray(value) ? value as UnknownRecord : null;
}

function text(value: unknown): string | null {
  return typeof value === "string" && value.length > 0 ? value : null;
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

function rowFrom(value: unknown): StateReliabilityRow | null {
  const source = record(value);
  const sport = text(source?.sport);
  const timeBucket = text(source?.time_bucket);
  const probabilityBucket = text(source?.prob_bucket);
  const side = source?.source;
  const n = count(source?.n);
  const meanP = finite(source?.mean_p);
  const meanY = finite(source?.mean_y);
  const calibrationError = finite(source?.calibration_error);
  if (!sport || !timeBucket || !probabilityBucket || (side !== "model" && side !== "market") || n === null || meanP === null || meanY === null || calibrationError === null) return null;
  return { sport, timeBucket, probabilityBucket, source: side, n, meanP: rounded(meanP), meanY: rounded(meanY), calibrationError: rounded(calibrationError) };
}

function ordered(values: string[]): string[] {
  return Array.from(new Set(values));
}

/** Parses the committed state-conditioned calibration snapshot without pairing source populations. */
export function buildStateReliability(value: unknown): StateReliabilitySport[] {
  const root = record(value);
  const sports = record(root?.sports);
  if (!sports) return [];
  return Object.entries(sports).flatMap(([sport, value]) => {
    const entry = record(value);
    const nSkippedNoStateField = count(entry?.n_skipped_no_state_field);
    const rows = Array.isArray(entry?.buckets) ? entry.buckets.flatMap(item => {
      const parsed = rowFrom(item);
      return parsed?.sport === sport ? [parsed] : [];
    }) : [];
    if (nSkippedNoStateField === null || !rows.length) return [];
    return [{ sport, nSkippedNoStateField, rows, timeBuckets: ordered(rows.map(row => row.timeBucket)), probabilityBuckets: ordered(rows.map(row => row.probabilityBucket)) }];
  });
}

export function stateReliabilityRow(sport: StateReliabilitySport, timeBucket: string, probabilityBucket: string, source: StateReliabilitySource): StateReliabilityRow | undefined {
  return sport.rows.find(row => row.timeBucket === timeBucket && row.probabilityBucket === probabilityBucket && row.source === source);
}

/** Returns source-published values in the selected display units. */
export function stateReliabilityMetricValue(row: StateReliabilityRow, metric: StateReliabilityMetric): number {
  if (metric === "support") return row.n;
  if (metric === "absolute-gap") return rounded(row.calibrationError * 100);
  return rounded((row.meanY - row.meanP) * 100);
}
