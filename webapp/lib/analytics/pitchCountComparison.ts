import type { ComparisonEntity } from "./comparisonData";

export type PitchCountCategory = "pitcher_ahead" | "even" | "pitcher_behind";
export type PitchCountEntityEvidence = {
  slug: string;
  name: string;
  nPitches: number;
  floors?: string;
  asOf?: string;
};
export type PitchCountRow = {
  key: PitchCountCategory;
  label: string;
  unit: "source_percent";
  a: number | null;
  b: number | null;
};
export type PitchCountComparison = {
  rows: PitchCountRow[];
  entities: { a: PitchCountEntityEvidence; b: PitchCountEntityEvidence };
  sameAsOf: boolean | null;
  denominator: string;
  definition: string;
  note: string;
};

const CATEGORIES: Array<[PitchCountCategory, string]> = [
  ["pitcher_ahead", "Pitcher ahead"],
  ["even", "Even count"],
  ["pitcher_behind", "Pitcher behind"],
];

function plainObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function sourcePercent(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) && value >= 0 && value <= 100 ? value : null;
}

export function isPitchTypeComparisonEntity(entity: ComparisonEntity): boolean {
  return entity.sourceEntity?.startsWith("pitch_type:") === true
    && plainObject(entity.values.count_leverage_pct)
    && typeof entity.values.n_pitches === "number"
    && Number.isFinite(entity.values.n_pitches)
    && entity.values.n_pitches >= 0;
}

function evidence(entity: ComparisonEntity): PitchCountEntityEvidence {
  return {
    slug: entity.slug,
    name: entity.name,
    nPitches: entity.values.n_pitches as number,
    floors: entity.floors,
    asOf: entity.asOf,
  };
}

export function pitchCountComparison(a: ComparisonEntity, b: ComparisonEntity): PitchCountComparison | null {
  if (!isPitchTypeComparisonEntity(a) || !isPitchTypeComparisonEntity(b)) return null;
  const aShares = a.values.count_leverage_pct as Record<string, unknown>;
  const bShares = b.values.count_leverage_pct as Record<string, unknown>;
  return {
    rows: CATEGORIES.map(([key, label]) => ({ key, label, unit: "source_percent", a: sourcePercent(aShares[key]), b: sourcePercent(bShares[key]) })),
    entities: { a: evidence(a), b: evidence(b) },
    sameAsOf: a.asOf && b.asOf ? a.asOf === b.asOf : null,
    denominator: "Each share uses all published pitches of that pitch type as its denominator.",
    definition: "Pitcher ahead means strikes > balls; pitcher behind means balls > strikes; even is the remainder.",
    note: "Historical 2025 count-state mix, not pitch efficacy, sequencing, a head-to-head result, or a forecast. Rare and unclassified pitch codes remain visible with their published support and floor text.",
  };
}
