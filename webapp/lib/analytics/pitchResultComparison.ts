import type { ComparisonEntity } from "./comparisonData";
import { mlbAtlasFamily, type MlbAtlasFamily } from "./mlbAtlasFamily";

export type PitchResultCategory = "ball" | "strike" | "in-play";
export type PitchResultValue = { value: number | null; serialized: boolean };
export type PitchResultEntityEvidence = {
  slug: string;
  name: string;
  nPitches: number | null;
  outcomeAvailable: boolean;
  floors?: string;
  asOf?: string;
};
export type PitchResultRow = {
  key: PitchResultCategory;
  label: string;
  unit: "source_percent";
  a: PitchResultValue;
  b: PitchResultValue;
};
export type PitchResultComparison = {
  family: MlbAtlasFamily;
  rows: PitchResultRow[];
  entities: { a: PitchResultEntityEvidence; b: PitchResultEntityEvidence };
  sameAsOf: boolean | null;
  denominator: string;
  definition: string;
  note: string;
};

const CATEGORIES: ReadonlyArray<readonly [PitchResultCategory, string]> = [
  ["ball", "Ball"], ["strike", "Strike"], ["in-play", "In play"],
];

function plainObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function sourcePercent(source: Record<string, unknown> | null, key: PitchResultCategory): PitchResultValue {
  if (!source || !Object.prototype.hasOwnProperty.call(source, key)) return { value: null, serialized: false };
  const value = source[key];
  return {
    value: typeof value === "number" && Number.isFinite(value) && value >= 0 && value <= 100 ? value : null,
    serialized: true,
  };
}

function evidence(entity: ComparisonEntity, outcomeAvailable: boolean): PitchResultEntityEvidence {
  const n = entity.values.n_pitches;
  return {
    slug: entity.slug,
    name: entity.name,
    nPitches: typeof n === "number" && Number.isFinite(n) && Number.isInteger(n) && n >= 0 ? n : null,
    outcomeAvailable,
    floors: entity.floors,
    asOf: entity.asOf,
  };
}

export function pitchResultComparison(a: ComparisonEntity, b: ComparisonEntity): PitchResultComparison | null {
  const family = mlbAtlasFamily(a.sourceEntity);
  if (!family || mlbAtlasFamily(b.sourceEntity) !== family) return null;
  const aMix = plainObject(a.values.outcome_mix_pct) ? a.values.outcome_mix_pct : null;
  const bMix = plainObject(b.values.outcome_mix_pct) ? b.values.outcome_mix_pct : null;
  return {
    family,
    rows: CATEGORIES.map(([key, label]) => ({ key, label, unit: "source_percent", a: sourcePercent(aMix, key), b: sourcePercent(bMix, key) })),
    entities: { a: evidence(a, aMix !== null), b: evidence(b, bMix !== null) },
    sameAsOf: a.asOf && b.asOf ? a.asOf === b.asOf : null,
    denominator: "Each percentage uses all published pitches in that entity record as its denominator.",
    definition: "Statcast type codes: B = ball, S = strike, X = in play.",
    note: "Historical pitch-result categories rounded independently to 0.1 percentage point. Source as-of is the pull's maximum game date, not an entity-specific latest date or a full-season claim. Strike is the broad Statcast S code, not a called-strike, swinging-strike, whiff, chase, or strike-zone measure. An absent nested category was not serialized and remains unavailable here.",
  };
}
