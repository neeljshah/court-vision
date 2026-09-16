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
  artifactDate: string | null;
  nForecastObservations: number;
  nSkippedNoStateField: number;
  nCells: number;
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

function probabilityLowerBound(bucket: string): number {
  const parsed = Number(bucket.split("-")[0]);
  return Number.isFinite(parsed) ? parsed : Number.POSITIVE_INFINITY;
}

function timeBucketOrder(bucket: string): number {
  if (bucket.startsWith("early")) return 0;
  if (bucket.startsWith("mid")) return 1;
  if (bucket.startsWith("late")) return 2;
  const matched = bucket.match(/^\d+(?:\.\d+)?/);
  return matched ? Number(matched[0]) : Number.POSITIVE_INFINITY;
}

function sortedProbabilityBuckets(values: string[]): string[] {
  return ordered(values).sort((left, right) => probabilityLowerBound(left) - probabilityLowerBound(right) || left.localeCompare(right));
}

function sortedTimeBuckets(values: string[]): string[] {
  return ordered(values).sort((left, right) => timeBucketOrder(left) - timeBucketOrder(right) || left.localeCompare(right));
}

/** Parses the committed state-conditioned calibration snapshot without pairing source populations. */
export function buildStateReliability(value: unknown): StateReliabilitySport[] {
  const root = record(value);
  const sports = record(root?.sports);
  if (!sports) return [];
  const parsedSports = Object.entries(sports).flatMap(([sport, value]) => {
    const entry = record(value);
    const nForecastObservations = count(entry?.n_records);
    const nSkippedNoStateField = count(entry?.n_skipped_no_state_field);
    const rows = Array.isArray(entry?.buckets) ? entry.buckets.flatMap(item => {
      const parsed = rowFrom(item);
      return parsed?.sport === sport ? [parsed] : [];
    }) : [];
    if (nForecastObservations === null || nSkippedNoStateField === null || !rows.length) return [];
    return [{ sport, nForecastObservations, nSkippedNoStateField, nCells: new Set(rows.map(row => `${row.timeBucket}|${row.probabilityBucket}`)).size, rows, timeBuckets: sortedTimeBuckets(rows.map(row => row.timeBucket)), probabilityBuckets: [] }];
  });
  const probabilityBuckets = sortedProbabilityBuckets(parsedSports.flatMap(sport => sport.rows.map(row => row.probabilityBucket)));
  const artifactDate = stateReliabilityArtifactDate(root);
  return parsedSports.map(sport => ({ ...sport, artifactDate, probabilityBuckets }));
}

/** Returns the published artifact date, or null when the snapshot does not publish one. */
export function stateReliabilityArtifactDate(value: unknown): string | null {
  const root = record(value);
  const asOf = text(root?.as_of);
  if (asOf && asOf.toLowerCase() !== "unknown") return asOf;
  const generatedAt = text(root?.generated_at);
  return generatedAt && generatedAt.toLowerCase() !== "unknown" ? generatedAt : null;
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
