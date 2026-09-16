import { field as f, snapshot } from "./labHelpers";
import { atlasFieldDefinition } from "./atlasFieldDefinitions";
import { getMlbPitchAtlasCohorts } from "./atlasResearchCohorts";
import { entrySlugs, entityName, type RawEntry } from "./comparisonData";
import type { LabField } from "./labTypes";
import type { ResearchAnalysis, ResearchReference, ResearchRow } from "./researchTypes";

export type AtlasManifest = { entries?: RawEntry[]; generated_at?: unknown; sourceIndexes?: number[] };
export type AtlasPack = { key: string; source: string; id: string; title: string; sport: ResearchAnalysis["sport"]; noun: string; defaultMeasurement?: string };

const PACKS: AtlasPack[] = [
  { key: "nba_players", source: "atlas_nba_manifest", id: "nba-player-atlas-measurements", title: "NBA player atlas measurements", sport: "nba", noun: "NBA players" },
  { key: "nba_teams", source: "atlas_nba_teams_manifest", id: "nba-team-atlas-measurements", title: "NBA team atlas measurements", sport: "nba", noun: "NBA teams" },
  { key: "mlb_batters", source: "atlas_mlb_batters_manifest", id: "mlb-batter-atlas-measurements", title: "MLB batter atlas measurements", sport: "mlb", noun: "MLB batters" },
  { key: "soccer", source: "atlas_soccer_manifest", id: "soccer-team-atlas-measurements", title: "Soccer team atlas measurements", sport: "soccer", noun: "soccer teams" },
  { key: "tennis", source: "atlas_tennis_manifest", id: "tennis-player-atlas-measurements", title: "Tennis player atlas measurements", sport: "tennis", noun: "tennis players" },
];

const REFERENCES: ResearchReference[] = [{
  title: "Published entity atlas manifests",
  url: "https://github.com/neeljshah/court-vision/tree/master/webapp/public/data/showcase",
}];

const finite = (value: unknown): value is number => typeof value === "number" && Number.isFinite(value);
function fieldFor(pack: string, key: string): LabField {
  const definition = atlasFieldDefinition(pack, key);
  if (definition.isDifference) return f(key, definition.label, "pp", definition.decimals);
  if (definition.unit === "percent-already" || definition.unit === "fraction-as-percent") return f(key, definition.label, "percent", definition.decimals);
  if (definition.unit === "mph") return f(key, definition.label, "mph", definition.decimals);
  return f(key, definition.label, "number", definition.decimals);
}

function displayedValue(pack: string, value: unknown, key: string): number | null {
  if (!finite(value)) return null;
  if (atlasFieldDefinition(pack, key).unit === "percent-already") return value / 100;
  return value;
}

function scalarKeys(pack: string, entries: RawEntry[], defaultMeasurement?: string): string[] {
  const keys = [...new Set(entries.flatMap((entry) => Object.entries(entry.key_numbers || {})
    .flatMap(([key, value]) => finite(value) && !atlasFieldDefinition(pack, key).isIdentifier ? [key] : [])))].sort();
  return defaultMeasurement && keys.includes(defaultMeasurement)
    ? [defaultMeasurement, ...keys.filter((key) => key !== defaultMeasurement)]
    : keys;
}

function dates(entries: RawEntry[]): string | undefined {
  const values = entries.map((entry) => typeof entry.as_of === "string" ? entry.as_of.slice(0, 10) : "");
  return values.length && values.every((value) => /^\d{4}-\d{2}-\d{2}$/.test(value)) && new Set(values).size === 1 ? values[0] : undefined;
}

function floors(entries: RawEntry[]): string {
  return [...new Set(entries.map((entry) => entry.floors).filter((value): value is string => typeof value === "string" && value.trim().length > 0))].join(" ");
}

export function buildAtlasResearch(pack: AtlasPack, manifest: AtlasManifest): ResearchAnalysis {
  const entries = manifest.entries || [];
  const keys = scalarKeys(pack.key, entries, pack.defaultMeasurement);
  const rows: ResearchRow[] = entrySlugs(entries).map(({ slug, entry }, index) => ({
    id: `${pack.id}-${slug || index + 1}`,
    label: entityName(entry),
    group: pack.noun,
    values: Object.fromEntries(keys.map((key) => [key, displayedValue(pack.key, entry.key_numbers?.[key], key)])),
    note: typeof entry.floors === "string" ? entry.floors : undefined,
    href: `/analytics/players/${pack.key}/${slug}`,
    sourcePaths: keys.map((key) => `entries[${manifest.sourceIndexes?.[index] ?? index}].key_numbers.${key}`),
  }));
  const publishedFloors = floors(entries);
  return {
    id: pack.id,
    title: pack.title,
    sport: pack.sport,
    category: "Entity atlas",
    source: pack.source,
    question: `Which published measurements are recorded for ${pack.noun}?`,
    method: "Restates every finite scalar key_numbers field from each published entity card. Nested objects remain on the entity card and are not flattened here.",
    description: `Published scalar measurements for ${pack.noun}, with one row for each committed entity card.`,
    scope: `${rows.length} published ${pack.noun} rows and ${keys.length} scalar measurement fields.`,
    caveat: publishedFloors || "The published manifest does not state a shared floor for this pack.",
    status: "Descriptive",
    fields: keys.map(key => fieldFor(pack.key, key)),
    rows,
    formula: "Displayed values restate published scalar key_numbers fields. The field definitions preserve each published unit: already-percent values are normalized for percent display, and published fractions are shown as percentages.",
    interpretation: "Sort a column to inspect the published measurements. Unavailable values remain unavailable, and a higher value is not a quality judgement.",
    references: REFERENCES,
    novelty: "Derived analysis",
    asOf: dates(entries),
  };
}

export function getAtlasPackResearch(): ResearchAnalysis[] {
  const standard = PACKS.map((pack) => buildAtlasResearch(pack, snapshot<AtlasManifest>(pack.source)));
  const mlbPitch = snapshot<AtlasManifest>("atlas_mlb_pitch_manifest");
  const cohorts = getMlbPitchAtlasCohorts(mlbPitch.entries || []).map((cohort) => buildAtlasResearch({
    key: "mlb_pitch", source: "atlas_mlb_pitch_manifest", id: cohort.id, title: cohort.title,
    sport: "mlb", noun: cohort.noun, defaultMeasurement: cohort.defaultMeasurement,
  }, { ...mlbPitch, entries: cohort.entries, sourceIndexes: cohort.sourceIndexes }));
  return [...standard, ...cohorts];
}
