export type MovementEvidence = {
  overreaction: OverreactionEvidence;
  absorption: AbsorptionEvidence;
};

export type OverreactionEvidence = {
  rows: OverreactionRow[];
  unavailable: { dates: true; intervals: true; independentGameCounts: true };
};

export type OverreactionRow = {
  sport: string;
  bucket: string;
  n: number;
  movedToPrice: number;
  outcomeRate: number;
  derivedDifference: number;
  statedDifference: number;
};

export type AbsorptionEvidence = {
  rows: AbsorptionRow[];
  independentGameCountsUnavailable: true;
};

export type AbsorptionRow = {
  sport: string;
  availability: "published" | "unavailable";
  observationWindow: { start: string | null; end: string | null; days: number | null; files: number | null };
  intervalMinutes: { median: number | null; p90: number | null; mean: number | null };
  nPregameSnapshots: number | null;
  nMovePairs: number | null;
  nSeriesUsed: number | null;
  meanMovementPerPair: number | null;
  finalHourMovementShare: number | null;
  movementByBucket: Record<string, number | null>;
};

type RecordValue = Record<string, unknown>;
const isRecord = (value: unknown): value is RecordValue => !!value && typeof value === "object" && !Array.isArray(value);
const number = (value: unknown): number | null => typeof value === "number" && Number.isFinite(value) ? value : null;
const rounded = (value: number | null): number | null => value === null ? null : Number(value.toFixed(6));
const text = (value: unknown): string | null => typeof value === "string" && value.trim() ? value : null;
const sportLabel = (sport: string): string => sport === "soccer_intl" ? "International soccer" : sport.toUpperCase();

function windowFor(value: unknown): AbsorptionRow["observationWindow"] {
  const entry = isRecord(value) ? value : {};
  return { start: text(entry.start), end: text(entry.end), days: number(entry.days), files: number(entry.files) };
}

function cadenceFor(value: unknown): AbsorptionRow["intervalMinutes"] {
  const entry = isRecord(value) ? value : {};
  return { median: number(entry.median), p90: number(entry.p90), mean: number(entry.mean) };
}

export function buildMarketOverreactionEvidence(source: unknown): OverreactionEvidence {
  const buckets = isRecord(source) && isRecord(source.buckets) ? source.buckets : {};
  const rows = Object.entries(buckets).flatMap(([sport, values]) => isRecord(values)
    ? Object.entries(values).flatMap(([bucket, raw]) => {
      if (!isRecord(raw)) return [];
      const n = number(raw.n);
      const movedToPrice = number(raw.moved_to_price);
      const outcomeRate = number(raw.outcome_rate);
      const statedDifference = number(raw.moved_to_minus_outcome);
      if (n === null || movedToPrice === null || outcomeRate === null || statedDifference === null) return [];
      return [{ sport: sportLabel(sport), bucket, n, movedToPrice, outcomeRate, derivedDifference: rounded(movedToPrice - outcomeRate)!, statedDifference }];
    }) : []);
  return { rows, unavailable: { dates: true, intervals: true, independentGameCounts: true } };
}

export function buildMicroAbsorptionEvidence(source: unknown): AbsorptionEvidence {
  const sports = isRecord(source) && isRecord(source.sports) ? source.sports : {};
  const rows = Object.entries(sports).map(([sport, raw]) => {
    const entry = isRecord(raw) ? raw : {};
    const available = entry.status === "ok";
    const pairs = number(entry.n_move_pairs);
    const totalMovement = number(entry.total_abs_move);
    const movement = isRecord(entry.move_by_bucket) ? entry.move_by_bucket : {};
    const movementByBucket = Object.fromEntries(Object.entries(movement).map(([bucket, value]) => {
      const bucketValue = isRecord(value) ? number(value.mean_abs_move) : null;
      return [bucket, bucketValue];
    }));
    return {
      sport: sportLabel(sport),
      availability: available ? "published" : "unavailable",
      observationWindow: windowFor(entry.observation_window),
      intervalMinutes: cadenceFor(entry.interval_minutes),
      nPregameSnapshots: number(entry.n_pregame_snapshots),
      nMovePairs: pairs,
      nSeriesUsed: number(entry.n_series_used),
      meanMovementPerPair: available && pairs !== null && pairs > 0 && totalMovement !== null ? rounded(totalMovement / pairs) : null,
      finalHourMovementShare: available ? number(entry.final_hour_movement_share) : null,
      movementByBucket,
    } satisfies AbsorptionRow;
  });
  return { rows, independentGameCountsUnavailable: true };
}

export function buildMovementEvidence(overreaction: unknown, absorption: unknown): MovementEvidence {
  return { overreaction: buildMarketOverreactionEvidence(overreaction), absorption: buildMicroAbsorptionEvidence(absorption) };
}
