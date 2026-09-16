export type StatePopulation = {
  time: string;
  probabilityBand: string;
  meanOutcomeFrequency: number;
  n: number;
};

export type StateContrast = {
  sport: string;
  from: StatePopulation;
  to: StatePopulation;
  winprobDelta: number;
  minSupportN: number;
};

export type AdjacentTimePair = {
  id: string;
  fromTime: string;
  toTime: string;
};

export type StateContrastSport = {
  sport: string;
  contrasts: StateContrast[];
  adjacentTimePairs: AdjacentTimePair[];
};

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

function populationFrom(value: unknown): StatePopulation | null {
  const source = record(value);
  const time = text(source?.time);
  const probabilityBand = text(source?.prob);
  const meanOutcomeFrequency = finite(source?.mean_y);
  const n = count(source?.n);
  if (!time || !probabilityBand || meanOutcomeFrequency === null || n === null) return null;
  return { time, probabilityBand, meanOutcomeFrequency: rounded(meanOutcomeFrequency), n };
}

function contrastFrom(sport: string, value: unknown): StateContrast | null {
  const source = record(value);
  const from = populationFrom(source?.from);
  const to = populationFrom(source?.to);
  const winprobDelta = finite(source?.winprob_delta);
  const minSupportN = count(source?.min_support_n);
  if (!from || !to || winprobDelta === null || minSupportN === null) return null;
  return { sport, from, to, winprobDelta: rounded(winprobDelta), minSupportN };
}

function timePair(contrast: StateContrast): AdjacentTimePair {
  return {
    id: `${contrast.from.time}__${contrast.to.time}`,
    fromTime: contrast.from.time,
    toTime: contrast.to.time,
  };
}

function uniquePairs(contrasts: StateContrast[]): AdjacentTimePair[] {
  const seen = new Set<string>();
  return contrasts.flatMap(contrast => {
    const pair = timePair(contrast);
    if (seen.has(pair.id)) return [];
    seen.add(pair.id);
    return [pair];
  });
}

/** Parses the committed state-bucket snapshot without treating rows as game-level movements. */
export function buildStateContrasts(value: unknown): StateContrastSport[] {
  const root = record(value);
  const sports = record(root?.sports);
  if (!sports) return [];
  return Object.entries(sports).flatMap(([sport, entry]) => {
    const source = record(entry);
    const contrasts = Array.isArray(source?.transitions)
      ? source.transitions.flatMap(item => {
        const parsed = contrastFrom(sport, item);
        return parsed ? [parsed] : [];
      })
      : [];
    return contrasts.length ? [{ sport, contrasts, adjacentTimePairs: uniquePairs(contrasts) }] : [];
  });
}

export function contrastsForPair(sports: StateContrastSport[], sport: string, pairId: string): StateContrast[] {
  return sports.find(item => item.sport === sport)?.contrasts.filter(contrast => timePair(contrast).id === pairId) || [];
}

export function deltaPercentagePoints(delta: number): number {
  return rounded(delta * 100);
}
