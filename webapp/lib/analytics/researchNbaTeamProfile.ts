import { field as f, snapshot } from "./labHelpers";
import { entrySlugs, type RawEntry } from "./comparisonData";
import type { ResearchAnalysis, ResearchReference, ResearchRow, ResearchSource } from "./researchTypes";

type Entry = Record<string, unknown>;
type TeamProfileSources = { atlas: Entry; loadBearing: Entry; fatigue: Entry; density: Entry; states: Entry };
type TeamCell = { label: string; sourcePaths: string[]; values: Record<string, number | null>; bindingValues: Record<string, string | number | null>; windows: Record<string, string>; note: string };

const REFERENCES: ResearchReference[] = [{
  title: "Published NBA team snapshot modules",
  url: "https://github.com/neeljshah/court-vision/tree/master/webapp/public/data/showcase",
}];
const finite = (value: unknown): value is number => typeof value === "number" && Number.isFinite(value);
const record = (value: unknown): Entry => value && typeof value === "object" && !Array.isArray(value) ? value as Entry : {};
const text = (value: unknown): string => typeof value === "string" ? value.trim() : "";
const sourced = (sourceId: string, key: string, label: string, unit: "number" | "percent" | "pp", digits: number) => ({ ...f(key, label, unit, digits), sourceId });
const TEAM_ALIASES: Record<string, string> = { BRK: "BKN", GS: "GSW", NO: "NOP", PHO: "PHX", SA: "SAS" };

function teamKey(value: unknown): string {
  const key = text(value).toUpperCase().replace(/[^A-Z0-9]/g, "");
  return TEAM_ALIASES[key] || key;
}
function valueAt(value: unknown, key: string): number | null {
  const candidate = record(value)[key];
  return finite(candidate) ? candidate : null;
}
function latestByTeam(rows: unknown, valueKey: string): Map<string, Entry> {
  const latest = new Map<string, Entry>();
  if (!Array.isArray(rows)) return latest;
  for (const raw of rows) {
    const row = record(raw);
    const team = teamKey(row.team);
    const season = text(row.season);
    if (!team || !season || !finite(row[valueKey])) continue;
    const previous = latest.get(team);
    if (!previous || season.localeCompare(text(previous.season)) > 0) latest.set(team, row);
  }
  return latest;
}
function keyedByTeam(rows: Entry[]): Map<string, Entry> {
  const output = new Map<string, Entry>();
  for (const row of rows) {
    const team = teamKey(row.team);
    if (team) output.set(team, row);
  }
  return output;
}
function firstAsOf(source: Entry): string {
  const entries = Array.isArray(source.entries) ? source.entries : [];
  return asOf(record(entries[0]).as_of);
}
function coverage(name: string, entries: Map<string, Entry>, teams: string[]): string {
  const missing = teams.filter(team => !entries.has(team));
  const extras = [...entries.keys()].filter(team => !teams.includes(team));
  return `${name} ${teams.length - missing.length}/${teams.length}; unmatched atlas teams: ${missing.join(", ") || "none"}; source-only teams: ${extras.join(", ") || "none"}`;
}
function asOf(value: unknown): string {
  return text(value) || "not published";
}
function teamHrefs(entries: Entry[]): Map<string, string> {
  const valid = entries.flatMap((value): RawEntry[] => typeof value.entity === "string" && typeof value.card_path === "string"
    ? [{ entity: value.entity, card_path: value.card_path, key_numbers: record(value.key_numbers) }]
    : []);
  return new Map<string, string>(entrySlugs(valid).flatMap(({ slug, entry }): Array<[string, string]> => {
    const href = `/analytics/players/nba_teams/${slug}`;
    const fullName = record(entry.key_numbers).team_full_name;
    return [[teamKey(entry.entity), href], ...(typeof fullName === "string" ? [[teamKey(fullName), href] as [string, string]] : [])];
  }));
}
function rowWindows(rows: ResearchRow[], keys: string[]): Record<string, string[]> {
  return Object.fromEntries(keys.map(key => [key, [...new Set(rows.map(row => row.windows?.[key]).filter((value): value is string => Boolean(value)))]]));
}

function buildRows(source: TeamProfileSources): { rows: ResearchRow[]; coverage: string } {
  const atlas = Array.isArray(source.atlas.entries) ? source.atlas.entries.map(record) : [];
  const loadBearing = Array.isArray(source.loadBearing.results) ? source.loadBearing.results.map(record) : [];
  const fatigue = latestByTeam(source.fatigue.results, "sft_credible_pts_per100_ortg");
  const density = latestByTeam(source.density.per_team_season_frequencies, "b2b_freq");
  const states = Array.isArray(source.states.teams) ? source.states.teams.map(record) : [];
  const hrefs = teamHrefs(atlas);
  const loadMap = keyedByTeam(loadBearing);
  const stateMap = keyedByTeam(states);
  const cells: TeamCell[] = atlas.flatMap(entry => {
    const team = teamKey(entry.entity);
    if (!team) return [];
    const numbers = record(entry.key_numbers);
    const load = loadMap.get(team);
    const loadA = record(load?.estimator_a_elo_onoff);
    const loadB = record(load?.estimator_b_raw_withwithout);
    const state = stateMap.get(team);
    const sourcePaths = [
      "atlas_nba_teams_manifest.entries[].entity",
      "atlas_nba_teams_manifest.entries[].key_numbers.pace_proxy_latest_season",
      "atlas_nba_teams_manifest.entries[].key_numbers.ppg_latest_season",
    ];
    if (load) sourcePaths.push("novel_load_bearing_index.results[].estimator_a_elo_onoff.player_name", "novel_load_bearing_index.results[].estimator_a_elo_onoff.delta_winprob", "novel_load_bearing_index.results[].estimator_b_raw_withwithout.player_name", "novel_load_bearing_index.results[].estimator_b_raw_withwithout.delta_win_rate", "novel_load_bearing_index.results[].estimator_b_raw_withwithout.n_active", "novel_load_bearing_index.results[].estimator_b_raw_withwithout.n_missed", "novel_load_bearing_index.results[].agreement_same_player");
    if (fatigue.has(team)) sourcePaths.push("novel_schedule_fatigue_tax.results[].sft_credible_pts_per100_ortg");
    if (density.has(team)) sourcePaths.push("schedule_density.per_team_season_frequencies[].b2b_freq");
    if (state) sourcePaths.push("ctx_team_states.teams[].n_games", "ctx_team_states.teams[].front_runner_2h_margin", "ctx_team_states.teams[].comeback_2h_margin", "ctx_team_states.teams[].masked_below_floor");
    const masked = state?.masked_below_floor === true;
    return [{
      label: text(numbers.team_full_name) || team,
      sourcePaths,
      values: {
        pace_proxy: valueAt(numbers, "pace_proxy_latest_season"),
        points_per_game: valueAt(numbers, "ppg_latest_season"),
        fragility_delta_estimator_a: valueAt(loadA, "delta_winprob"),
        fragility_delta_estimator_b: valueAt(loadB, "delta_win_rate"),
        fragility_estimator_b_active_games: valueAt(loadB, "n_active"),
        fragility_estimator_b_missed_games: valueAt(loadB, "n_missed"),
        fatigue_tax_pts_per100: valueAt(fatigue.get(team), "sft_credible_pts_per100_ortg"),
        back_to_back_share: valueAt(density.get(team), "b2b_freq"),
        halftime_games: valueAt(state, "n_games"),
        front_runner_second_half_margin: valueAt(state, "front_runner_2h_margin"),
        comeback_second_half_margin: valueAt(state, "comeback_2h_margin"),
      },
      bindingValues: {
        fragility_estimator_a_player: text(loadA.player_name) || null,
        fragility_estimator_b_player: text(loadB.player_name) || null,
        fragility_estimators_same_player: typeof load?.agreement_same_player === "boolean" ? String(load.agreement_same_player) : null,
      },
      windows: {
        fatigue_tax_pts_per100: text(fatigue.get(team)?.season),
        back_to_back_share: text(density.get(team)?.season),
      },
      note: !state ? "No published halftime-state record matched this team." : masked ? "Small halftime sample: the source marks this team below its split floor; the displayed second-half margins are retained as flagged source values." : "Published halftime-state record cleared the source split floor.",
    }];
  });
  const teams = atlas.map(entry => teamKey(entry.entity)).filter(Boolean);
  const coverageText = [
    coverage("load-bearing index", loadMap, teams),
    coverage("fatigue tax", fatigue, teams),
    coverage("schedule density", density, teams),
    coverage("halftime states", stateMap, teams),
  ].join(". ");
  return { rows: cells.sort((left, right) => left.label.localeCompare(right.label)).map(cell => ({ id: `nba-team-profile-${cell.label.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/(^-|-$)/g, "")}`, label: cell.label, group: "NBA teams", values: cell.values, bindingValues: cell.bindingValues, windows: cell.windows, note: cell.note, href: hrefs.get(teamKey(cell.label)), sourcePaths: cell.sourcePaths })), coverage: coverageText };
}

export function buildNbaTeamProfileResearch(source: TeamProfileSources): ResearchAnalysis[] {
  const built = buildRows(source || {} as TeamProfileSources);
  const sources: ResearchSource[] = [
    { id: "atlas_nba_teams_manifest", asOf: firstAsOf(record(source?.atlas)), fields: ["pace_proxy", "points_per_game"] },
    { id: "novel_load_bearing_index", asOf: "not published", fields: ["fragility_delta_estimator_a", "fragility_delta_estimator_b", "fragility_estimator_b_active_games", "fragility_estimator_b_missed_games"] },
    { id: "novel_schedule_fatigue_tax", asOf: "not published", fields: ["fatigue_tax_pts_per100"], rowWindows: rowWindows(built.rows, ["fatigue_tax_pts_per100"]) },
    { id: "schedule_density", asOf: "not published", fields: ["back_to_back_share"], rowWindows: rowWindows(built.rows, ["back_to_back_share"]) },
    { id: "ctx_team_states", asOf: asOf(record(source?.states).as_of), fields: ["halftime_games", "front_runner_second_half_margin", "comeback_second_half_margin"] },
  ];
  return [{
    id: "nba-team-profile-pace-fragility-fatigue-halftime",
    title: "NBA team profile: pace, fragility, fatigue and half-time swing",
    sport: "nba",
    category: "Team context",
    source: "atlas_nba_teams_manifest",
    sources,
    question: "How do the published pace, fragility, schedule, and halftime-state measurements sit beside one another for each NBA team?",
    method: "Join published team records by normalized abbreviation, retain every atlas team, and show missing module values as null rather than removing a team.",
    description: "The 30-team atlas is the anchor; published load-bearing, schedule, fatigue, and halftime-state values are placed alongside its pace and scoring measurements.",
    scope: `${built.rows.length} atlas teams. Sources: ${sources.map(item => `${item.id} (as of ${item.asOf})`).join("; ")}.`,
    caveat: `Join coverage: ${built.coverage}. Estimator A and estimator B can name different players; inspect their published player names, agreement flag, and estimator B support counts before comparing the two deltas. The team atlas does not publish a defensive-identity numeric field, and the halftime source does not publish a mean halftime-margin field; its flagged front-runner and comeback second-half margins are retained with game counts instead. These modules use different windows and methods, so their values are not a common scale or a team ranking.`,
    status: "Descriptive cross-module profile",
    fields: [sourced("atlas_nba_teams_manifest", "pace_proxy", "Pace proxy", "number", 1), sourced("atlas_nba_teams_manifest", "points_per_game", "Points per game", "number", 1), sourced("novel_load_bearing_index", "fragility_delta_estimator_a", "Fragility delta, estimator A", "pp", 2), sourced("novel_load_bearing_index", "fragility_delta_estimator_b", "Fragility delta, estimator B", "pp", 2), sourced("novel_load_bearing_index", "fragility_estimator_b_active_games", "Estimator B active games", "number", 0), sourced("novel_load_bearing_index", "fragility_estimator_b_missed_games", "Estimator B missed games", "number", 0), sourced("novel_schedule_fatigue_tax", "fatigue_tax_pts_per100", "Fatigue tax, points per 100", "number", 3), sourced("schedule_density", "back_to_back_share", "Back-to-back share", "percent", 1), sourced("ctx_team_states", "halftime_games", "Halftime-state games", "number", 0), sourced("ctx_team_states", "front_runner_second_half_margin", "Front-runner second-half margin", "number", 2), sourced("ctx_team_states", "comeback_second_half_margin", "Comeback second-half margin", "number", 2)],
    rows: built.rows,
    formula: "pace_proxy, points_per_game, fragility_delta_estimator_a, fragility_delta_estimator_b, fragility_estimator_b_active_games, fragility_estimator_b_missed_games, fatigue_tax_pts_per100, back_to_back_share, halftime_games, front_runner_second_half_margin, and comeback_second_half_margin are copied from their named source fields; estimator player names and agreement are retained as published text; no values are combined or rescaled.",
    bindings: [
      { operand: "pace_proxy", sourcePath: "atlas_nba_teams_manifest.entries[].key_numbers.pace_proxy_latest_season", valueKey: "pace_proxy", label: "Pace proxy" },
      { operand: "points_per_game", sourcePath: "atlas_nba_teams_manifest.entries[].key_numbers.ppg_latest_season", valueKey: "points_per_game", label: "Points per game" },
      { operand: "fragility_delta_estimator_a", sourcePath: "novel_load_bearing_index.results[].estimator_a_elo_onoff.delta_winprob", valueKey: "fragility_delta_estimator_a", label: "Fragility delta, estimator A" },
      { operand: "fragility_delta_estimator_b", sourcePath: "novel_load_bearing_index.results[].estimator_b_raw_withwithout.delta_win_rate", valueKey: "fragility_delta_estimator_b", label: "Fragility delta, estimator B" },
      { operand: "fragility_estimator_a_player", sourcePath: "novel_load_bearing_index.results[].estimator_a_elo_onoff.player_name", valueKey: "fragility_estimator_a_player", label: "Estimator A selected player" },
      { operand: "fragility_estimator_b_player", sourcePath: "novel_load_bearing_index.results[].estimator_b_raw_withwithout.player_name", valueKey: "fragility_estimator_b_player", label: "Estimator B selected player" },
      { operand: "fragility_estimator_b_active_games", sourcePath: "novel_load_bearing_index.results[].estimator_b_raw_withwithout.n_active", valueKey: "fragility_estimator_b_active_games", label: "Estimator B active games" },
      { operand: "fragility_estimator_b_missed_games", sourcePath: "novel_load_bearing_index.results[].estimator_b_raw_withwithout.n_missed", valueKey: "fragility_estimator_b_missed_games", label: "Estimator B missed games" },
      { operand: "fragility_estimators_same_player", sourcePath: "novel_load_bearing_index.results[].agreement_same_player", valueKey: "fragility_estimators_same_player", label: "Estimators name the same player" },
      { operand: "fatigue_tax_pts_per100", sourcePath: "novel_schedule_fatigue_tax.results[].sft_credible_pts_per100_ortg", valueKey: "fatigue_tax_pts_per100", label: "Fatigue tax, points per 100" },
      { operand: "back_to_back_share", sourcePath: "schedule_density.per_team_season_frequencies[].b2b_freq", valueKey: "back_to_back_share", label: "Back-to-back share" },
      { operand: "halftime_games", sourcePath: "ctx_team_states.teams[].n_games", valueKey: "halftime_games", label: "Halftime-state games" },
      { operand: "front_runner_second_half_margin", sourcePath: "ctx_team_states.teams[].front_runner_2h_margin", valueKey: "front_runner_second_half_margin", label: "Front-runner second-half margin" },
      { operand: "comeback_second_half_margin", sourcePath: "ctx_team_states.teams[].comeback_2h_margin", valueKey: "comeback_second_half_margin", label: "Comeback second-half margin" },
    ],
    interpretation: "Compare values only within their named measurement and read the row note before using the halftime-state columns.",
    references: REFERENCES,
    novelty: "Derived analysis",
    asOf: "2026-05-21",
  }];
}

export function getNbaTeamProfileResearch(): ResearchAnalysis[] {
  return buildNbaTeamProfileResearch({
    atlas: snapshot<Entry>("atlas_nba_teams_manifest"), loadBearing: snapshot<Entry>("novel_load_bearing_index"), fatigue: snapshot<Entry>("novel_schedule_fatigue_tax"), density: snapshot<Entry>("schedule_density"), states: snapshot<Entry>("ctx_team_states"),
  });
}
