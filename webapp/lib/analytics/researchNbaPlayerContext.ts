import { field as f, snapshot } from "./labHelpers";
import type { ResearchAnalysis, ResearchReference, ResearchRow, ResearchSource } from "./researchTypes";

type Entry = Record<string, unknown>;
type PlayerContextSources = { consistency: Entry; q4: Entry; context: Entry; onOff: Entry; atlas: Entry };
type PlayerCell = { name: string; paths: string[]; values: Record<string, number | null>; modules: Set<string> };

const REFERENCES: ResearchReference[] = [{
  title: "Published NBA player snapshot modules",
  url: "https://github.com/neeljshah/court-vision/tree/master/webapp/public/data/showcase",
}];
const finite = (value: unknown): value is number => typeof value === "number" && Number.isFinite(value);
const record = (value: unknown): Entry => value && typeof value === "object" && !Array.isArray(value) ? value as Entry : {};
const text = (value: unknown): string => typeof value === "string" ? value.trim() : "";
const playerKey = (value: unknown): string => text(value).normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase().replace(/[^a-z0-9]/g, "");
const numberAt = (value: unknown, key: string): number | null => finite(record(value)[key]) ? record(value)[key] as number : null;
const atlasAsOf = (source: Entry | undefined): string => {
  const entries = Array.isArray(source?.entries) ? source.entries : [];
  return text(record(entries[0]).as_of) || "not published";
};

function setCell(cells: Map<string, PlayerCell>, name: string, module: string, values: Record<string, number | null>, paths: string[]) {
  const key = playerKey(name);
  if (!key) return;
  const current = cells.get(key) || { name, paths: [], values: {}, modules: new Set<string>() };
  current.name = current.name || name;
  current.modules.add(module);
  Object.assign(current.values, values);
  current.paths.push(...paths);
  cells.set(key, current);
}
function q4Cells(source: Entry, cells: Map<string, PlayerCell>) {
  const definitions = [["pts_shift", "q4_points_shift"], ["reb_shift", "q4_rebounds_shift"], ["ast_shift", "q4_assists_shift"]] as const;
  for (const [section, key] of definitions) {
    for (const [list, rows] of Object.entries(record(source[section]))) {
      if (!Array.isArray(rows)) continue;
      for (const raw of rows) {
        const row = record(raw);
        const name = text(row.player_name);
        if (name) setCell(cells, name, "nba_q4_shift", { [key]: numberAt(row, "shift") }, [`nba_q4_shift.${section}.${list}[].player_name`, `nba_q4_shift.${section}.${list}[].shift`]);
      }
    }
  }
}
function onOffCells(source: Entry, cells: Map<string, PlayerCell>) {
  const seasons = Object.entries(record(source.seasons)).sort(([left], [right]) => right.localeCompare(left));
  const seen = new Set<string>();
  for (const [season, rawSeason] of seasons) {
    for (const [list, rows] of Object.entries(record(rawSeason))) {
      if (!Array.isArray(rows) || !["top_15", "bottom_15"].includes(list)) continue;
      for (const raw of rows) {
        const row = record(raw);
        const name = text(row.player_name);
        const key = playerKey(name);
        if (!name || seen.has(key)) continue;
        seen.add(key);
        setCell(cells, name, "on_off_showcase", { net_rating_delta: numberAt(row, "net_rating_delta") }, [`on_off_showcase.seasons.${season}.${list}[].player_name`, `on_off_showcase.seasons.${season}.${list}[].net_rating_delta`]);
      }
    }
  }
}
function coverage(module: string, cells: PlayerCell[], total: number): string {
  return `${module} ${cells.filter(cell => cell.modules.has(module)).length}/${total}`;
}

export function buildNbaPlayerContextResearch(source: PlayerContextSources): ResearchAnalysis[] {
  const cells = new Map<string, PlayerCell>();
  for (const [list, path] of [["most_consistent_top15", "most_consistent_top15"], ["least_consistent_top15", "least_consistent_top15"]] as const) {
    const rows = source?.consistency && Array.isArray(source.consistency[list]) ? source.consistency[list] : [];
    for (const raw of rows) { const row = record(raw); const name = text(row.player_name); if (name) setCell(cells, name, "nba_consistency_profiles", { consistency_cv: numberAt(row, "composite_cv_shrunk") }, [`nba_consistency_profiles.${path}[].player_name`, `nba_consistency_profiles.${path}[].composite_cv_shrunk`]); }
  }
  q4Cells(record(source?.q4), cells);
  for (const raw of Array.isArray(source?.context?.players) ? source.context.players : []) {
    const row = record(raw); const name = text(row.player_name); const homeAway = record(record(row.splits).home_away);
    if (name) setCell(cells, name, "ctx_player_splits", { context_sensitivity: numberAt(row, "context_sensitivity_score"), home_away_ts_difference: numberAt(homeAway, "delta_ts_pct") }, ["ctx_player_splits.players[].player_name", "ctx_player_splits.players[].context_sensitivity_score", "ctx_player_splits.players[].splits.home_away.delta_ts_pct"]);
  }
  onOffCells(record(source?.onOff), cells);
  for (const raw of Array.isArray(source?.atlas?.entries) ? source.atlas.entries : []) {
    const row = record(raw); const name = text(row.entity); const numbers = record(row.key_numbers);
    if (name) setCell(cells, name, "atlas_nba_manifest", { career_points_per36: numberAt(numbers, "career_pts_per36"), career_rebounds_per36: numberAt(numbers, "career_reb_per36"), career_assists_per36: numberAt(numbers, "career_ast_per36") }, ["atlas_nba_manifest.entries[].entity", "atlas_nba_manifest.entries[].key_numbers.career_pts_per36", "atlas_nba_manifest.entries[].key_numbers.career_reb_per36", "atlas_nba_manifest.entries[].key_numbers.career_ast_per36"]);
  }
  const allCells = [...cells.values()];
  const threeSourceRows = allCells.filter(cell => cell.modules.size >= 3);
  const minimumSources = threeSourceRows.length >= 40 ? 3 : 2;
  const selected = allCells.filter(cell => cell.modules.size >= minimumSources).sort((left, right) => left.name.localeCompare(right.name));
  const rows: ResearchRow[] = selected.map(cell => ({ id: `nba-player-context-${playerKey(cell.name)}`, label: cell.name, group: `${cell.modules.size} published sources`, values: { consistency_cv: null, q4_points_shift: null, q4_rebounds_shift: null, q4_assists_shift: null, context_sensitivity: null, home_away_ts_difference: null, net_rating_delta: null, career_points_per36: null, career_rebounds_per36: null, career_assists_per36: null, ...cell.values }, note: `Published in ${cell.modules.size} joined source modules. Null means that source module did not publish this measurement for the player.`, sourcePaths: [...new Set(cell.paths)] }));
  const sourceTotals = new Map<string, number>([["nba_consistency_profiles", 0], ["nba_q4_shift", 0], ["ctx_player_splits", 0], ["on_off_showcase", 0], ["atlas_nba_manifest", 0]]);
  for (const cell of allCells) for (const module of cell.modules) sourceTotals.set(module, (sourceTotals.get(module) || 0) + 1);
  const sourceCoverage = [...sourceTotals].map(([module, total]) => coverage(module, selected, total)).join("; ");
  const excludedNames = allCells.filter(cell => cell.modules.size === 1 && !cell.modules.has("atlas_nba_manifest")).map(cell => cell.name).sort((left, right) => left.localeCompare(right));
  const sources: ResearchSource[] = [
    { id: "nba_consistency_profiles", asOf: text(source?.consistency?.as_of) || "not published" }, { id: "nba_q4_shift", asOf: text(source?.q4?.generated_at) || "not published" }, { id: "ctx_player_splits", asOf: "not published" }, { id: "on_off_showcase", asOf: "not published" }, { id: "atlas_nba_manifest", asOf: atlasAsOf(source?.atlas) },
  ];
  return [{
    id: "nba-player-context-consistency-q4-venue-onoff",
    title: "NBA player context: consistency, Q4 shift, venue dispersion and on/off",
    sport: "nba",
    category: "Player context",
    source: "atlas_nba_manifest",
    sources,
    question: "Which published player consistency, Q4, venue-context, on-off, and per-36 measurements can be read together for the same names?",
    method: "Normalize player names by lower-casing and removing diacritics and punctuation; no alias map is used. Keep rows meeting the stated source-count floor and retain unavailable measurements as null.",
    description: "Published player subsets are joined by normalized name so their available consistency, late-quarter, venue-context, on-off, and per-36 values remain side by side.",
    scope: `${rows.length} player names from at least ${minimumSources} published sources. Sources: ${sources.map(item => `${item.id} (as of ${item.asOf})`).join("; ")}.`,
    caveat: `The three-source join produced ${threeSourceRows.length} names, below the 40-row floor, so this analysis uses a two-source join. Join coverage among retained names: ${sourceCoverage}. Source-only names excluded from the join: ${excludedNames.join(", ") || "none"}. No alias map was needed; source windows, populations, and definitions differ.`,
    status: "Descriptive cross-module profile",
    fields: [f("consistency_cv", "Consistency CV", "number", 4), f("q4_points_shift", "Q4 points shift per 36", "number", 2), f("q4_rebounds_shift", "Q4 rebounds shift per 36", "number", 2), f("q4_assists_shift", "Q4 assists shift per 36", "number", 2), f("context_sensitivity", "Context sensitivity", "number", 4), f("home_away_ts_difference", "Home minus away true-shooting difference", "pp", 2), f("net_rating_delta", "Net rating delta", "number", 3), f("career_points_per36", "Career points per 36", "number", 1), f("career_rebounds_per36", "Career rebounds per 36", "number", 1), f("career_assists_per36", "Career assists per 36", "number", 1)],
    rows,
    formula: "Each value is copied from its named source field. Q4 shifts are the published Q4 minus Q1-Q3 values; home-minus-away true-shooting difference and net rating delta are published source fields.",
    interpretation: "Compare each measurement within its source definition and treat missing cells as unavailable, not as zero.",
    references: REFERENCES,
    novelty: "Derived analysis",
    asOf: "2026-07-24",
  }];
}

export function getNbaPlayerContextResearch(): ResearchAnalysis[] {
  return buildNbaPlayerContextResearch({ consistency: snapshot<Entry>("nba_consistency_profiles"), q4: snapshot<Entry>("nba_q4_shift"), context: snapshot<Entry>("ctx_player_splits"), onOff: snapshot<Entry>("on_off_showcase"), atlas: snapshot<Entry>("atlas_nba_manifest") });
}
