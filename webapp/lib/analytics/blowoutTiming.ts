type UnknownRecord = Record<string, unknown>;

export type BlowoutTimingThreshold = {
  threshold: number;
  nGamesTotal: number;
  nGamesDecided: number;
  incidence: number | null;
  publishedIncidence: number | null;
  masked: boolean;
  maskReason: string | null;
  p25: number | null;
  median: number | null;
  p75: number | null;
};

export type BlowoutTimingSport = {
  sport: string;
  unit: string;
  clockField: string;
  thresholds: BlowoutTimingThreshold[];
};

function record(value: unknown): UnknownRecord | null {
  return value !== null && typeof value === "object" && !Array.isArray(value) ? value as UnknownRecord : null;
}

function number(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function count(value: unknown): number {
  const parsed = number(value);
  return parsed !== null && parsed >= 0 ? Math.trunc(parsed) : 0;
}

export function incidenceFraction(decided: number, total: number): number | null {
  return total > 0 ? Number((decided / total).toFixed(6)) : null;
}

function timing(value: unknown): number | null {
  const parsed = number(value);
  return parsed !== null && parsed >= 0 ? parsed : null;
}

function thresholdFrom(value: unknown, minimum: number | null): BlowoutTimingThreshold | null {
  const source = record(value);
  const threshold = number(source?.threshold);
  if (threshold === null || threshold < 0) return null;
  const nGamesTotal = count(source?.n_games_total);
  const nGamesDecided = count(source?.n_games_decided);
  const masked = source?.masked_below_floor === true;
  return {
    threshold,
    nGamesTotal,
    nGamesDecided,
    incidence: incidenceFraction(nGamesDecided, nGamesTotal),
    publishedIncidence: number(source?.decided_frac_of_games),
    masked,
    maskReason: masked ? `Below the published minimum of ${minimum ?? "the stated minimum"} decided games.` : null,
    p25: timing(source?.decided_clock_p25),
    median: timing(source?.decided_clock_median),
    p75: timing(source?.decided_clock_p75),
  };
}

/** Parses the committed blowout dynamics artifact without pooling sport clocks. */
export function buildBlowoutTiming(value: unknown): BlowoutTimingSport[] {
  const root = record(value);
  const sports = record(root?.sports);
  const floors = record(root?.floors);
  const minimum = number(floors?.min_games_per_threshold);
  if (!sports) return [];
  return Object.entries(sports).flatMap(([sport, entry]) => {
    const source = record(entry);
    const unit = typeof source?.unit === "string" ? source.unit : null;
    const clockField = typeof source?.clock_field === "string" ? source.clock_field : null;
    const rows = Array.isArray(source?.thresholds) ? source.thresholds.flatMap(row => {
      const parsed = thresholdFrom(row, minimum);
      return parsed ? [parsed] : [];
    }) : [];
    return unit && clockField && rows.length ? [{ sport, unit, clockField, thresholds: rows }] : [];
  });
}
