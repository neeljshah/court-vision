export type ResidualMetric = "n" | "meanAbsResidual" | "totalAbsResidualMass";

export interface ResidualSegment {
  sport: string;
  timeBucket: string;
  probBucket: string;
  n: number;
  meanAbsResidual: number;
  totalAbsResidualMass: number;
}

export interface ResidualGridRow {
  timeBucket: string;
  cells: Array<ResidualSegment | null>;
}

export interface ResidualRankings {
  byVolume: ResidualSegment[];
  byPerRowError: ResidualSegment[];
}

export interface ResidualSport {
  sport: string;
  nFiles: number | null;
  nRecords: number | null;
  nSkipped: number | null;
  segments: ResidualSegment[];
  timeBuckets: string[];
  probBuckets: string[];
  grid: ResidualGridRow[];
  rankings: ResidualRankings;
}

export interface ResidualAnatomyData {
  sports: ResidualSport[];
  exclusions: Array<{ sport: string; reason: string }>;
}

type RecordValue = Record<string, unknown>;

function record(value: unknown): RecordValue | null {
  return value && typeof value === "object" && !Array.isArray(value) ? value as RecordValue : null;
}

function finite(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function text(value: unknown): string | null {
  return typeof value === "string" && value.length ? value : null;
}

function segmentFrom(value: unknown): ResidualSegment | null {
  const raw = record(value);
  if (!raw) return null;
  const sport = text(raw.sport);
  const timeBucket = text(raw.time_bucket);
  const probBucket = text(raw.prob_bucket);
  const n = finite(raw.n);
  const meanAbsResidual = finite(raw.mean_abs_residual);
  const totalAbsResidualMass = finite(raw.total_abs_residual_mass);
  if (!sport || !timeBucket || !probBucket || n === null || meanAbsResidual === null || totalAbsResidualMass === null) return null;
  return { sport, timeBucket, probBucket, n, meanAbsResidual, totalAbsResidualMass };
}

function unique(values: string[]): string[] {
  return Array.from(new Set(values));
}

function buildSport(sport: string, value: unknown): ResidualSport | null {
  const raw = record(value);
  if (!raw) return null;
  const segments = Array.isArray(raw.segments) ? raw.segments.map(segmentFrom).filter((item): item is ResidualSegment => item !== null) : [];
  const timeBuckets = unique(segments.map(item => item.timeBucket));
  const probBuckets = unique(segments.map(item => item.probBucket));
  const lookup = new Map(segments.map(item => [`${item.timeBucket}\u0000${item.probBucket}`, item]));
  const grid = timeBuckets.map(timeBucket => ({
    timeBucket,
    cells: probBuckets.map(probBucket => lookup.get(`${timeBucket}\u0000${probBucket}`) || null),
  }));
  return {
    sport,
    nFiles: finite(raw.n_files),
    nRecords: finite(raw.n_records),
    nSkipped: finite(raw.n_skipped),
    segments,
    timeBuckets,
    probBuckets,
    grid,
    rankings: {
      byVolume: [...segments].sort((left, right) => right.totalAbsResidualMass - left.totalAbsResidualMass),
      byPerRowError: [...segments].sort((left, right) => right.meanAbsResidual - left.meanAbsResidual),
    },
  };
}

/** Parses the committed residual anatomy snapshot without assigning cause to residuals. */
export function buildResidualAnatomy(value: unknown): ResidualAnatomyData {
  const root = record(value);
  const sports = record(root?.sports);
  const exclusions = Array.isArray(root?.skipped) ? root.skipped.flatMap(item => {
    const entry = record(item);
    const sport = text(entry?.sport);
    const reason = text(entry?.reason);
    return sport && reason ? [{ sport, reason }] : [];
  }) : [];
  return {
    sports: sports ? Object.entries(sports).flatMap(([sport, entry]) => {
      const parsed = buildSport(sport, entry);
      return parsed ? [parsed] : [];
    }) : [],
    exclusions,
  };
}

export function metricValue(segment: ResidualSegment, metric: ResidualMetric): number {
  if (metric === "n") return segment.n;
  if (metric === "meanAbsResidual") return segment.meanAbsResidual;
  return segment.totalAbsResidualMass;
}
