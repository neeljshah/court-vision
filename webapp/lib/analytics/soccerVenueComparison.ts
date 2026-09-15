import type { ComparisonEntity } from "./comparisonData";

export type SoccerVenueMetric = "ppg" | "clean_sheet_rate";
export type SoccerVenueAvailability = "published" | "missing" | "invalid";
export type SoccerVenueValue = {
  home: number | null;
  away: number | null;
  gap: number | null;
  homeAvailability: SoccerVenueAvailability;
  awayAvailability: SoccerVenueAvailability;
};
export type SoccerVenueEvidence = {
  sourceEntity: string;
  name: string;
  floors: string;
  status?: string;
  asOf: string;
  sampleCounts: { home: null; away: null };
};
export type SoccerVenueRow = {
  key: SoccerVenueMetric;
  label: string;
  unit: "points_per_game" | "percentage_points";
  a: SoccerVenueValue;
  b: SoccerVenueValue;
};
export type SoccerVenueComparison = {
  window: "trailing10_asof_corpus_end";
  rows: SoccerVenueRow[];
  entities: { a: SoccerVenueEvidence; b: SoccerVenueEvidence };
  note: string;
};

const WINDOW = "trailing10_asof_corpus_end" as const;

function bounded(value: unknown, maximum: number): { value: number | null; availability: SoccerVenueAvailability } {
  if (value === null || value === undefined) return { value: null, availability: "missing" };
  return typeof value === "number" && Number.isFinite(value) && value >= 0 && value <= maximum
    ? { value, availability: "published" }
    : { value: null, availability: "invalid" };
}

function values(entity: ComparisonEntity, key: SoccerVenueMetric): SoccerVenueValue {
  const homeResult = bounded(entity.values[key === "ppg" ? "ppg_home_l10" : "clean_sheet_rate_home"], key === "ppg" ? 3 : 1);
  const awayResult = bounded(entity.values[key === "ppg" ? "ppg_away_l10" : "clean_sheet_rate_away"], key === "ppg" ? 3 : 1);
  const { value: home, availability: homeAvailability } = homeResult;
  const { value: away, availability: awayAvailability } = awayResult;
  const scale = key === "ppg" ? 10 : 1000;
  const gap = home === null || away === null ? null : Math.round((home - away) * scale) / 10;
  return { home, away, gap, homeAvailability, awayAvailability };
}

function evidence(entity: ComparisonEntity): SoccerVenueEvidence {
  return {
    sourceEntity: entity.sourceEntity!, name: entity.name, floors: entity.floors!, status: entity.status,
    asOf: entity.asOf!, sampleCounts: { home: null, away: null },
  };
}

export function soccerVenueComparison(a: ComparisonEntity, b: ComparisonEntity): SoccerVenueComparison | null {
  const windowToken = `window=${WINDOW};`;
  if (!a.sourceEntity || !b.sourceEntity || !a.floors?.includes(windowToken) ||
      !b.floors?.includes(windowToken) || !a.asOf || a.asOf !== b.asOf) return null;
  return {
    window: WINDOW,
    rows: [
      { key: "ppg", label: "Points per game", unit: "points_per_game", a: values(a, "ppg"), b: values(b, "ppg") },
      { key: "clean_sheet_rate", label: "Clean-sheet rate", unit: "percentage_points", a: values(a, "clean_sheet_rate"), b: values(b, "clean_sheet_rate") },
    ],
    entities: { a: evidence(a), b: evidence(b) },
    note: "Each club's latest recorded match is excluded before separate trailing windows take the last 10 prior home and away matches. Those windows can cover different dates and span seasons. Source as-of is the claim-computation timestamp, not a match cutoff. Exact total prior counts and club-specific match dates are not published. Values are descriptive, not forecasts.",
  };
}
