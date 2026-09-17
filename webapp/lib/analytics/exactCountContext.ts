type RecordValue = Record<string, unknown>;

export interface ExactCountRow {
  id: string;
  balls: number;
  strikes: number;
  leverageClass: string;
  n: number | null;
  topPitchType: string | null;
  topPitchPct: number | null;
  strikeRate: number | null;
  inZoneRate: number | null;
}

export interface ExactCountData {
  rows: ExactCountRow[];
  asOf: string | null;
}

function record(value: unknown): RecordValue | null {
  return value !== null && typeof value === "object" && !Array.isArray(value)
    ? value as RecordValue : null;
}

function boundedNumber(value: unknown, minimum: number, maximum: number): number | null {
  return typeof value === "number" && Number.isFinite(value)
    && value >= minimum && value <= maximum ? value : null;
}

function sampleCount(value: unknown): number | null {
  const parsed = boundedNumber(value, 0, Number.MAX_SAFE_INTEGER);
  return parsed !== null && Number.isInteger(parsed) ? parsed : null;
}

function countCoordinate(value: unknown, maximum: number): number | null {
  const parsed = boundedNumber(value, 0, maximum);
  return parsed !== null && Number.isInteger(parsed) ? parsed : null;
}

function rowFrom(value: unknown): ExactCountRow | null {
  const raw = record(value);
  const balls = countCoordinate(raw?.balls, 3);
  const strikes = countCoordinate(raw?.strikes, 2);
  const leverageClass = typeof raw?.leverage_class === "string" && raw.leverage_class
    ? raw.leverage_class : null;
  if (!raw || balls === null || strikes === null || !leverageClass) return null;
  const expectedClass = balls === strikes ? "even" : strikes > balls ? "ahead" : "behind";
  if (leverageClass !== expectedClass) return null;
  return {
    id: `${balls}-${strikes}`,
    balls,
    strikes,
    leverageClass,
    n: sampleCount(raw.n),
    topPitchType: typeof raw.top_pitch_type === "string" && raw.top_pitch_type
      ? raw.top_pitch_type : null,
    topPitchPct: boundedNumber(raw.top_pitch_pct, 0, 100),
    strikeRate: boundedNumber(raw.strike_rate_type_S, 0, 1),
    inZoneRate: boundedNumber(raw.in_zone_rate, 0, 1),
  };
}

/** Parses only fields published on exact-count rows; class denominators are unavailable. */
export function buildExactCountContext(value: unknown): ExactCountData {
  const raw = record(value);
  const asOf = typeof raw?.as_of === "string" && raw.as_of ? raw.as_of : null;
  if (raw?.status !== "ok" || !Array.isArray(raw.by_exact_count)) return { rows: [], asOf };
  const rows: ExactCountRow[] = [];
  const ids = new Set<string>();
  for (const valueRow of raw.by_exact_count) {
    const row = rowFrom(valueRow);
    if (!row || ids.has(row.id)) return { rows: [], asOf };
    ids.add(row.id);
    rows.push(row);
  }
  rows.sort((left, right) => left.balls - right.balls || left.strikes - right.strikes);
  return { rows, asOf };
}
