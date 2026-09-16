import { field as f, snapshot } from "./labHelpers";
import type { LabRow } from "./labTypes";
import type { ResearchAnalysis, ResearchReference } from "./researchTypes";

export type MlbBatterContactEntry = {
  entity: unknown;
  key_numbers?: Record<string, unknown>;
  floors?: unknown;
  as_of?: unknown;
};
export type MlbBatterContactAtlas = {
  generated_at?: unknown;
  n_entries?: unknown;
  entries: MlbBatterContactEntry[];
};

const SOURCE_FLOOR = /^pitches_faced_2025>=300(?=\s|\(|$)/;
const REFERENCES: ResearchReference[] = [{
  title: "Published MLB batter-atlas method",
  url: "https://github.com/neeljshah/court-vision/blob/master/scripts/platformkit/analytics_showcase/mlb_batter_atlas.py",
}, {
  title: "Published MLB batter atlas",
  url: "https://github.com/neeljshah/court-vision/blob/master/webapp/public/data/showcase/atlas_mlb_batters_manifest.json",
}];

const finiteNonnegative = (value: unknown): number | null =>
  typeof value === "number" && Number.isFinite(value) && value >= 0 ? value : null;
const positiveInteger = (value: unknown): number | null =>
  typeof value === "number" && Number.isInteger(value) && value > 0 ? value : null;

function contactRows(entries: MlbBatterContactEntry[]): LabRow[] {
  const idCounts = new Map<number, number>();
  for (const entry of entries) {
    const id = positiveInteger(entry.key_numbers?.batter_id);
    if (id !== null) idCounts.set(id, (idCounts.get(id) || 0) + 1);
  }
  return entries.flatMap(entry => {
    const label = typeof entry.entity === "string" ? entry.entity.trim() : "";
    const values = entry.key_numbers || {};
    const mean = finiteNonnegative(values.avg_exit_velo);
    const p90 = finiteNonnegative(values.exit_velo_p90);
    const pitches = positiveInteger(values.pitches_faced);
    const recorded = positiveInteger(values.n_batted_balls);
    const batterId = positiveInteger(values.batter_id);
    const eligible = typeof entry.floors === "string" && SOURCE_FLOOR.test(entry.floors);
    if (!label || mean === null || p90 === null || pitches === null || recorded === null ||
        batterId === null || idCounts.get(batterId) !== 1 || pitches < 300 || recorded > pitches || !eligible) return [];
    return [{
      id: `mlb-contact-${batterId}`,
      label,
      group: "Recorded exit velocity",
      values: {
        p90_minus_mean_exit_velo: p90 - mean,
        exit_velo_p90: p90,
        avg_exit_velo: mean,
        recorded_exit_velocities: recorded,
        pitches_faced: pitches,
      },
      note: `Source batter_id ${batterId}. ${recorded} rows have recorded launch_speed among ${pitches} pitches faced. Source values are rounded to 0.1 mph before this difference is derived.`,
    }];
  });
}

function exactDate(value: unknown): string | undefined {
  if (typeof value !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return undefined;
  const parsed = Date.parse(`${value}T00:00:00Z`);
  return Number.isFinite(parsed) && new Date(parsed).toISOString().slice(0, 10) === value ? value : undefined;
}

function sharedInputDate(entries: MlbBatterContactEntry[]): string | undefined {
  if (!entries.length) return undefined;
  const dates = entries.map(entry => exactDate(entry.as_of));
  if (dates.some(date => date === undefined)) return undefined;
  const unique = new Set(dates as string[]);
  return unique.size === 1 ? [...unique][0] : undefined;
}

function generatedDate(value: unknown): string | undefined {
  if (typeof value !== "string" || !Number.isFinite(Date.parse(value))) return undefined;
  return new Date(Date.parse(value)).toISOString().slice(0, 10);
}

export function buildMlbBatterContactResearch(atlas: MlbBatterContactAtlas): ResearchAnalysis[] {
  const rows = contactRows(atlas.entries);
  const inputDate = sharedInputDate(atlas.entries);
  const generated = generatedDate(atlas.generated_at);
  const publishedCount = typeof atlas.n_entries === "number" && Number.isInteger(atlas.n_entries) && atlas.n_entries >= 0
    ? atlas.n_entries : null;
  return [{
    id: "mlb-batter-p90-minus-mean-exit-velocity",
    title: "Batter exit velocity: P90 versus mean",
    sport: "mlb",
    category: "Batter contact",
    source: "atlas_mlb_batters_manifest",
    description: "Subtracts each batter's mean recorded exit velocity from the 90th percentile of that same recorded launch_speed series.",
    scope: `${rows.length} valid rows from ${publishedCount === null ? "the published batter atlas" : `${publishedCount} published batter entries`}; source eligibility is at least 300 pitches faced in 2025${inputDate ? `; latest global input date ${inputDate}` : ""}${generated ? `; public artifact generated ${generated}` : ""}.`,
    caveat: "The producer drops missing launch_speed values and does not load event, type, or description fields. The support count therefore means rows with recorded exit velocity; it does not establish balls in play, official batted-ball events, or whether fouls are included. The input cutoff is global rather than batter-specific, and no earliest-date, completeness, or game-type audit is published. Both operands are rounded to 0.1 mph, so the derived difference inherits that precision. This is a historical description, not a forecast.",
    status: "Descriptive",
    fields: [
      f("p90_minus_mean_exit_velo", "P90 minus mean exit velocity", "mph", 1),
      f("exit_velo_p90", "P90 recorded exit velocity", "mph", 1),
      f("avg_exit_velo", "Mean recorded exit velocity", "mph", 1),
      f("recorded_exit_velocities", "Recorded exit-velocity rows", "number", 0),
      f("pitches_faced", "Pitches faced", "number", 0),
    ],
    rows,
    formula: "P90-minus-mean (mph) = published exit_velo_p90 - published avg_exit_velo; both operands summarize the same non-missing launch_speed series and are published to 0.1 mph.",
    interpretation: "Positive values place the recorded 90th percentile above the recorded mean; negative values place it below. Inspect both operands and the recorded-exit-velocity row count with the difference.",
    references: REFERENCES,
    novelty: "Derived analysis",
  }];
}

export function getMlbBatterContactResearch(): ResearchAnalysis[] {
  return buildMlbBatterContactResearch(snapshot<MlbBatterContactAtlas>("atlas_mlb_batters_manifest"));
}
