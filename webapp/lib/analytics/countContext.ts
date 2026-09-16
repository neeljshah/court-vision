type RecordValue = Record<string, unknown>;

export interface CountPitchMix {
  pitchType: string;
  n: number | null;
  pct: number;
}

/** Outcome rates remain source fractions; display consumers convert them to percentages. */
export interface CountOutcomeProxies {
  nType: number | null;
  strikeRate: number | null;
  ballRate: number | null;
  inplayRate: number | null;
  nZone: number | null;
  inZoneRate: number | null;
}

export interface CountContextClass {
  id: string;
  definition: string;
  overlapping: boolean;
  n: number | null;
  pitchTypeN: number | null;
  pitchMix: CountPitchMix[];
  remainderPct: number;
  outcomes: CountOutcomeProxies;
}

export interface CountContextData {
  classes: CountContextClass[];
  asOf: string | null;
}

function record(value: unknown): RecordValue | null {
  return value && typeof value === "object" && !Array.isArray(value) ? value as RecordValue : null;
}

function numberOrNull(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function outcomesFrom(value: unknown): CountOutcomeProxies {
  const raw = record(value);
  return {
    nType: numberOrNull(raw?.n_type), strikeRate: numberOrNull(raw?.strike_rate_type_S),
    ballRate: numberOrNull(raw?.ball_rate), inplayRate: numberOrNull(raw?.inplay_rate_type_X),
    nZone: numberOrNull(raw?.n_zone), inZoneRate: numberOrNull(raw?.in_zone_rate),
  };
}

function classFrom(value: unknown): CountContextClass | null {
  const raw = record(value);
  const id = typeof raw?.class === "string" ? raw.class : null;
  if (!raw || !id) return null;
  const pitchMix = Array.isArray(raw.pitch_mix_top) ? raw.pitch_mix_top.map(item => {
    const pitch = record(item);
    const pct = numberOrNull(pitch?.pct);
    return pitch && typeof pitch.pitch_type === "string" && pct !== null
      ? { pitchType: pitch.pitch_type, n: numberOrNull(pitch.n), pct } : null;
  }).filter((item): item is CountPitchMix => item !== null) : [];
  const publishedTotal = pitchMix.reduce((total, item) => total + item.pct, 0);
  return {
    id, definition: typeof raw.definition === "string" ? raw.definition : "Not published",
    overlapping: raw.overlapping === true, n: numberOrNull(raw.n), pitchTypeN: numberOrNull(raw.pitch_type_n),
    pitchMix, remainderPct: Number((100 - publishedTotal).toFixed(6)), outcomes: outcomesFrom(raw.outcome_proxies),
  };
}

/** Parses the published count-class snapshot without rescaling percentages or denominators. */
export function buildCountContext(value: unknown): CountContextData {
  const raw = record(value);
  const classes = Array.isArray(raw?.by_leverage_class)
    ? raw.by_leverage_class.map(classFrom).filter((item): item is CountContextClass => item !== null) : [];
  return { classes, asOf: typeof raw?.as_of === "string" ? raw.as_of : null };
}

export function countClassById(data: CountContextData, id: string): CountContextClass | undefined {
  return data.classes.find(item => item.id === id);
}
