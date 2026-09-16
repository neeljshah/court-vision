import { field as f, snapshot } from "./labHelpers";
import { entrySlugs, entityName, type RawEntry } from "./comparisonData";
import type { LabField } from "./labTypes";
import type { ResearchAnalysis, ResearchReference, ResearchRow } from "./researchTypes";

export type AtlasManifest = { entries?: RawEntry[]; generated_at?: unknown };
export type AtlasPack = { key: string; source: string; id: string; title: string; sport: ResearchAnalysis["sport"]; noun: string };

const PACKS: AtlasPack[] = [
  { key: "nba_players", source: "atlas_nba_manifest", id: "nba-player-atlas-measurements", title: "NBA player atlas measurements", sport: "nba", noun: "NBA players" },
  { key: "nba_teams", source: "atlas_nba_teams_manifest", id: "nba-team-atlas-measurements", title: "NBA team atlas measurements", sport: "nba", noun: "NBA teams" },
  { key: "mlb_batters", source: "atlas_mlb_batters_manifest", id: "mlb-batter-atlas-measurements", title: "MLB batter atlas measurements", sport: "mlb", noun: "MLB batters" },
  { key: "mlb_pitch", source: "atlas_mlb_pitch_manifest", id: "mlb-pitch-atlas-measurements", title: "MLB pitch atlas measurements", sport: "mlb", noun: "MLB pitch types" },
  { key: "soccer", source: "atlas_soccer_manifest", id: "soccer-team-atlas-measurements", title: "Soccer team atlas measurements", sport: "soccer", noun: "soccer teams" },
  { key: "tennis", source: "atlas_tennis_manifest", id: "tennis-player-atlas-measurements", title: "Tennis player atlas measurements", sport: "tennis", noun: "tennis players" },
];

const REFERENCES: ResearchReference[] = [{
  title: "Published entity atlas manifests",
  url: "https://github.com/neeljshah/court-vision/tree/master/webapp/public/data/showcase",
}];

const finite = (value: unknown): value is number => typeof value === "number" && Number.isFinite(value);
const percentKey = (key: string) => /pct|rate|_wr_/.test(key);
const pointKey = (key: string) => /clay_minus_hard|grass_adapt/.test(key);

function labelFor(key: string): string {
  return key.replace(/_/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase())
    .replace(/\bPct\b/g, "Percent").replace(/\bPer36\b/g, "Per 36");
}

function fieldFor(key: string): LabField {
  if (pointKey(key)) return f(key, labelFor(key), "pp", 2);
  if (percentKey(key)) return f(key, labelFor(key), "percent", 2);
  if (/velo/.test(key)) return f(key, labelFor(key), "mph", 1);
  return f(key, labelFor(key), "number", /(^|_)(n|id|games|minutes|seasons|pitches|balls|strikes)(_|$)/.test(key) ? 0 : 2);
}

function displayedValue(value: unknown, key: string): number | null {
  if (!finite(value)) return null;
  if (pointKey(key)) return value;
  if (percentKey(key)) return /pct/.test(key) ? value / 100 : value;
  return value;
}

function scalarKeys(entries: RawEntry[]): string[] {
  return [...new Set(entries.flatMap((entry) => Object.entries(entry.key_numbers || {})
    .flatMap(([key, value]) => finite(value) ? [key] : [])))].sort();
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
  const keys = scalarKeys(entries);
  const rows: ResearchRow[] = entrySlugs(entries).map(({ slug, entry }, index) => ({
    id: `${pack.key}-${slug || index + 1}`,
    label: entityName(entry),
    group: pack.noun,
    values: Object.fromEntries(keys.map((key) => [key, displayedValue(entry.key_numbers?.[key], key)])),
    note: typeof entry.floors === "string" ? entry.floors : undefined,
    href: `/analytics/players/${pack.key}/${slug}`,
    sourcePaths: keys.map((key) => `entries[${index}].key_numbers.${key}`),
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
    fields: keys.map(fieldFor),
    rows,
    formula: "Displayed values restate published scalar key_numbers fields. Fields containing pct are divided by 100 for percent display; rate and win-rate fields are already published as proportions.",
    interpretation: "Sort a column to inspect the published measurements. Unavailable values remain unavailable, and a higher value is not a quality judgement.",
    references: REFERENCES,
    novelty: "Derived analysis",
    asOf: dates(entries),
  };
}

export function getAtlasPackResearch(): ResearchAnalysis[] {
  return PACKS.map((pack) => buildAtlasResearch(pack, snapshot<AtlasManifest>(pack.source)));
}
