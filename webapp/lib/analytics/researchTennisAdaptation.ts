import { field as f, snapshot } from "./labHelpers";
import type { ResearchAnalysis, ResearchReference, ResearchRow } from "./researchTypes";

type Metric = "clay_minus_hard" | "grass_adapt";
export type TennisAdaptationEntry = {
  entity: string;
  key_numbers: Record<string, unknown>;
  floors?: string;
  as_of?: string;
  status?: string;
};
export type TennisAdaptationAtlas = { generated_at?: string; entries: TennisAdaptationEntry[] };

const REFERENCE: ResearchReference[] = [{
  title: "Published tennis surface context method",
  url: "https://github.com/neeljshah/court-vision/blob/master/scripts/platformkit/intel_validation/tennis_surface_context_claims.py",
}];
const FLOOR_SUFFIX = "(per metric, career+recent_form independently; below floor shows n/a)";
const FLOOR: Record<Metric, string> = {
  clay_minus_hard: "clay_minus_hard: clay_n>=25 & hard_n>=25",
  grass_adapt: "grass_adapt: grass_n>=15",
};

const boundedGap = (value: unknown): number | null =>
  typeof value === "number" && Number.isFinite(value) && value >= -1 && value <= 1 ? value : null;

function validStatus(status: unknown): status is string {
  return status === "complete" || (typeof status === "string" && /^partial \((?:[0-9]|10)\/10 metrics\)$/.test(status));
}

function validFloor(entry: TennisAdaptationEntry, metric: Metric): boolean {
  const declaration = FLOOR[metric];
  if (typeof entry.floors !== "string" || !entry.floors.endsWith(FLOOR_SUFFIX)) return false;
  const declarations = entry.floors.slice(0, -FLOOR_SUFFIX.length).trim().split(" | ");
  return declarations.includes(declaration);
}

function duplicateEntities(entries: TennisAdaptationEntry[]): Set<string> {
  const counts = new Map<string, number>();
  for (const entry of entries) counts.set(entry.entity, (counts.get(entry.entity) || 0) + 1);
  return new Set([...counts].filter(([, count]) => count > 1).map(([entity]) => entity));
}

function metricRows(entries: TennisAdaptationEntry[], metric: Metric): ResearchRow[] {
  const duplicates = duplicateEntities(entries);
  return entries.flatMap((entry, index) => {
    const name = entry.entity.endsWith(" (ATP)") ? entry.entity.slice(0, -6).trim() : "";
    const career = boundedGap(entry.key_numbers[`${metric}_career`]);
    const recent = boundedGap(entry.key_numbers[`${metric}_recent`]);
    if (!name || duplicates.has(entry.entity) || !validStatus(entry.status) || !validFloor(entry, metric)
      || career === null || recent === null) return [];
    return [{
      id: `${metric}-${index}`,
      label: entry.entity,
      group: metric === "clay_minus_hard" ? "Clay-hard paired windows" : "Grass-overall paired windows",
      values: { recent_minus_career: recent - career, recent_gap: recent, career_gap: career },
      sourcePaths: [`entries[${index}].key_numbers.${metric}_recent`, `entries[${index}].key_numbers.${metric}_career`],
      note: `Source floor: ${entry.floors}. Career and recent windows qualify independently. Exact match counts are not published; operands are source-rounded to four decimals. Source status: ${entry.status}. Source row as-of: ${entry.as_of || "not recorded"}.`,
    }];
  });
}

function commonAsOf(entries: TennisAdaptationEntry[], labels: Set<string>): string | undefined {
  const included = entries.filter(entry => labels.has(entry.entity));
  if (!included.length || included.some(entry => typeof entry.as_of !== "string"
    || !/^\d{4}-\d{2}-\d{2}T/.test(entry.as_of) || !Number.isFinite(Date.parse(entry.as_of)))) return undefined;
  const dates = new Set(included.map(entry => entry.as_of as string));
  return dates.size === 1 ? [...dates][0] : undefined;
}

export function buildTennisAdaptationResearch(atlas: TennisAdaptationAtlas): ResearchAnalysis[] {
  const definitions: Array<{ metric: Metric; id: string; title: string; formula: string; detail: string }> = [
    {
      metric: "clay_minus_hard", id: "tennis-clay-gap-window-shift", title: "Clay-hard gap across overlapping windows",
      formula: "displayed shift (pp) = 100 * (recent_gap - career_gap), where each source-rounded clay gap is clay win rate - hard win rate; stored values remain unscaled fractions",
      detail: "Clay gap is clay win rate minus hard win rate; each surface has at least 25 matches in its own window.",
    },
    {
      metric: "grass_adapt", id: "tennis-grass-gap-window-shift", title: "Grass-overall gap across overlapping windows",
      formula: "displayed shift (pp) = 100 * (recent_gap - career_gap), where each source-rounded grass gap is grass win rate - overall win rate; stored values remain unscaled fractions",
      detail: "Grass gap is grass win rate minus overall win rate, where overall includes grass; grass has at least 15 matches in its own window.",
    },
  ];
  return definitions.map(({ metric, id, title, formula, detail }) => {
    const rows = metricRows(atlas.entries, metric);
    return {
      id, title, sport: "tennis", category: "Surface windows", source: "atlas_tennis_manifest",
      description: `${detail} Compare source-career (available 2015-2025) with recent form on or after 2023-01-01.`,
      scope: `${rows.length} ATP players with both published gap windows independently at or above the declared source floor; source career is available 2015-2025 and recent is on or after 2023-01-01.`,
      caveat: "Recent matches overlap the available 2015-2025 career corpus. The shared source as-of is the claim-computation timestamp, not each player's latest match date. Exact match counts and unrounded operands are not published; differences use source-rounded operands. Opponent strength, age, draws, retirement endings, and tournament mix are uncontrolled. This is a descriptive historical comparison and makes no causal, skill, predictive, or market claim.",
      status: metric === "grass_adapt" ? "Descriptive sparse subset" : "Descriptive subset",
      fields: [f("recent_minus_career", "Recent minus corpus", "pp", 2), f("recent_gap", "Recent gap", "pp", 2), f("career_gap", "Corpus gap", "pp", 2)],
      rows, formula,
      interpretation: "Positive values mean the source-rounded recent gap is larger than the source-rounded career gap; negative values mean it is smaller.",
      references: REFERENCE, novelty: "Derived analysis",
      asOf: commonAsOf(atlas.entries, new Set(rows.map(row => row.label))),
    };
  });
}

export function getTennisAdaptationResearch(): ResearchAnalysis[] {
  return buildTennisAdaptationResearch(snapshot<TennisAdaptationAtlas>("atlas_tennis_manifest"));
}
