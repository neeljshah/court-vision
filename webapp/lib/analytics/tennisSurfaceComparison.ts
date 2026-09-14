import type { ComparisonEntity } from "./comparisonData";

export type TennisSurface = "hard" | "clay" | "grass";
export type TennisWindow = "career" | "recent";
export type TennisSurfaceValue = { value: number | null; percentile: number | null };
export type TennisSurfaceRow = {
  key: string;
  label: string;
  kind: "surface_rate" | "within_player_delta";
  window: TennisWindow;
  unit: "percent" | "pp";
  a: TennisSurfaceValue;
  b: TennisSurfaceValue;
};
export type TennisSurfaceEntityEvidence = {
  name: string;
  floors?: string;
  status?: string;
  asOf?: string;
};
export type TennisSurfaceComparison = {
  surface: TennisSurface;
  surfaceLabel: string;
  rows: TennisSurfaceRow[];
  entities: { a: TennisSurfaceEntityEvidence; b: TennisSurfaceEntityEvidence };
  comparability: {
    windows: Record<TennisWindow, string>;
    sameAsOf: boolean | null;
    note: string;
  };
};

const LABELS: Record<TennisSurface, string> = { hard: "Hard", clay: "Clay", grass: "Grass" };
const DELTAS: Partial<Record<TennisSurface, { stem: string; label: string }>> = {
  clay: { stem: "clay_minus_hard", label: "Clay minus hard win rate" },
  grass: { stem: "grass_adapt", label: "Grass minus overall win rate" },
};
const finite = (value: unknown): number | null => typeof value === "number" && Number.isFinite(value) ? value : null;

function measurement(entity: ComparisonEntity, key: string): TennisSurfaceValue {
  const value = finite(entity.values[key]);
  return { value, percentile: value === null ? null : finite(entity.percentiles[key]) };
}

function entityEvidence(entity: ComparisonEntity): TennisSurfaceEntityEvidence {
  return { name: entity.name, floors: entity.floors, status: entity.status, asOf: entity.asOf };
}

export function tennisSurfaceComparison(
  a: ComparisonEntity,
  b: ComparisonEntity,
  surface: TennisSurface,
): TennisSurfaceComparison {
  const rows: TennisSurfaceRow[] = [];
  for (const window of ["career", "recent"] as const) {
    const rateKey = `${surface}_wr_${window}`;
    rows.push({ key: rateKey, label: `${LABELS[surface]} win rate`, kind: "surface_rate", window, unit: "percent", a: measurement(a, rateKey), b: measurement(b, rateKey) });
    const delta = DELTAS[surface];
    if (delta) {
      const deltaKey = `${delta.stem}_${window}`;
      rows.push({ key: deltaKey, label: delta.label, kind: "within_player_delta", window, unit: "pp", a: measurement(a, deltaKey), b: measurement(b, deltaKey) });
    }
  }
  const sameAsOf = a.asOf && b.asOf ? a.asOf === b.asOf : null;
  return {
    surface,
    surfaceLabel: LABELS[surface],
    rows,
    entities: { a: entityEvidence(a), b: entityEvidence(b) },
    comparability: {
      windows: { career: "2015-2025 pooled", recent: "matches on or after 2023-01-01" },
      sameAsOf,
      note: "Historical ATP rates from the same published atlas. They are not head-to-head results or forecasts. Per-metric floors apply independently in each window; null means the player did not have a published above-floor value.",
    },
  };
}
