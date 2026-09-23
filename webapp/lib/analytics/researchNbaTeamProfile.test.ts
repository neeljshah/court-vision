import { describe, expect, it } from "vitest";
import { buildNbaTeamProfileResearch, getNbaTeamProfileResearch } from "./researchNbaTeamProfile";

function source() {
  return {
    atlas: { entries: [
      { entity: "ATL", card_path: "cards/atlanta.png", key_numbers: { team_full_name: "Atlanta Hawks", pace_proxy_latest_season: 101, ppg_latest_season: 114, games_total: 239, seasons_covered: 3 }, as_of: "2026-04-12" },
      { entity: "BKN", card_path: "cards/brooklyn.png", key_numbers: { team_full_name: "Brooklyn Nets", pace_proxy_latest_season: 99, ppg_latest_season: 108, games_total: 238, seasons_covered: 3 }, as_of: "2026-04-12" },
    ] },
    loadBearing: { as_of: { estimator_a: "2024-25", estimator_b: "2025-26" }, results: [{ team: "BRK", estimator_a_elo_onoff: { player_name: "Alpha A", delta_winprob: 0.2 }, estimator_b_raw_withwithout: { player_name: "Bravo B", delta_win_rate: 0.1, n_active: 36, n_missed: 44 }, agreement_same_player: false }] },
    fatigue: { results: [{ team: "BKN", season: "2024-25", sft_credible_pts_per100_ortg: -0.3 }] },
    density: { per_team_season_frequencies: [{ team: "BKN", season: "2023-24", b2b_freq: 0.2 }] },
    states: { as_of: "2026-05-21", min_games_per_split: 2, teams: [{ team: "BKN", n_games: 2, n_led_at_half: 1, n_trailed_at_half: 1, front_runner_2h_margin: 1, comeback_2h_margin: -2, masked_below_floor: true }] },
  };
}

describe("NBA team profile research", () => {
  it("joins normalized team aliases and keeps source paths", () => {
    const row = buildNbaTeamProfileResearch(source())[0].rows.find(item => item.label === "Brooklyn Nets")!;
    expect(row.values).toMatchObject({ pace_proxy: 99, atlas_games_total: 238, atlas_seasons_covered: 3, fragility_delta_estimator_a: 0.2, fragility_estimator_b_active_games: 36, fragility_estimator_b_missed_games: 44, fatigue_tax_pts_per100: -0.3, back_to_back_share: 0.2 });
    expect(row.windows).toMatchObject({ fatigue_tax_pts_per100: "2024-25", back_to_back_share: "2023-24" });
    expect(row.sourcePaths).toContain("novel_load_bearing_index.results[].estimator_a_elo_onoff.delta_winprob");
    expect(row.href).toBe("/analytics/players/nba_teams/brooklyn");
    expect(buildNbaTeamProfileResearch(source())[0].bindings?.every(binding => binding.valueKey in row.values || binding.valueKey in (row.bindingValues || {}))).toBe(true);
    const analysis = buildNbaTeamProfileResearch(source())[0];
    expect(analysis.fields.find(field => field.key === "fatigue_tax_pts_per100")?.sourceId).toBe("novel_schedule_fatigue_tax");
    expect(analysis.fields.slice(0, 4).map(field => [field.key, field.label, field.sourceId])).toEqual([
      ["pace_proxy", "Pace proxy", "atlas_nba_teams_manifest"],
      ["points_per_game", "Points per game", "atlas_nba_teams_manifest"],
      ["atlas_games_total", "Atlas team games, full corpus", "atlas_nba_teams_manifest"],
      ["atlas_seasons_covered", "Atlas seasons covered", "atlas_nba_teams_manifest"],
    ]);
    expect(analysis.sources?.find(item => item.id === "atlas_nba_teams_manifest")?.fields).toEqual(["pace_proxy", "points_per_game", "atlas_games_total", "atlas_seasons_covered"]);
    expect(analysis.bindings?.filter(binding => binding.operand.startsWith("atlas_")).map(binding => [binding.operand, binding.sourcePath])).toEqual([
      ["atlas_games_total", "atlas_nba_teams_manifest.entries[].key_numbers.games_total"],
      ["atlas_seasons_covered", "atlas_nba_teams_manifest.entries[].key_numbers.seasons_covered"],
    ]);
    expect(analysis.sources?.find(item => item.id === "schedule_density")?.rowWindows).toEqual({ back_to_back_share: ["2023-24"] });
  });

  it("reports unmatched keys without removing atlas teams", () => {
    const input = source();
    input.loadBearing.results.push({ team: "XXX", estimator_a_elo_onoff: { player_name: "Extra A", delta_winprob: 0.4 }, estimator_b_raw_withwithout: { player_name: "Extra B", delta_win_rate: 0.2, n_active: 1, n_missed: 1 }, agreement_same_player: false });
    const analysis = buildNbaTeamProfileResearch(input)[0];
    expect(analysis.rows.map(row => row.label)).toContain("Atlanta Hawks");
    expect(analysis.caveat).toContain("source-only teams: XXX");
  });

  it("retains explicit nulls for absent joined measurements", () => {
    const row = buildNbaTeamProfileResearch(source())[0].rows.find(item => item.label === "Atlanta Hawks")!;
    expect(row.values.fragility_delta_estimator_a).toBeNull();
    expect(row.values.back_to_back_share).toBeNull();
    expect(row.bindingValues).toMatchObject({ fragility_estimator_a_player: null, fragility_estimator_b_player: null, fragility_estimators_same_player: null });
    expect(row.note).toContain("No published halftime-state record");
  });

  it("accepts only nonnegative safe-integer atlas coverage counts without gating latest values", () => {
    const invalid = [-1, 1.5, Infinity, Number.MAX_SAFE_INTEGER + 1, "3", null];
    for (const value of invalid) {
      const input = source();
      const numbers = input.atlas.entries[0].key_numbers as Record<string, unknown>;
      numbers.games_total = value;
      numbers.seasons_covered = value;
      const row = buildNbaTeamProfileResearch(input)[0].rows.find(item => item.label === "Atlanta Hawks")!;
      expect(row.values).toMatchObject({ atlas_games_total: null, atlas_seasons_covered: null, pace_proxy: 101, points_per_game: 114 });
    }
    const input = source();
    Object.assign(input.atlas.entries[0].key_numbers, { games_total: 0, seasons_covered: 0 });
    const zero = buildNbaTeamProfileResearch(input)[0].rows.find(item => item.label === "Atlanta Hawks")!;
    expect(zero.values).toMatchObject({ atlas_games_total: 0, atlas_seasons_covered: 0 });
  });

  it("orders team rows by the published team name", () => {
    expect(buildNbaTeamProfileResearch(source())[0].rows.map(row => row.label)).toEqual(["Atlanta Hawks", "Brooklyn Nets"]);
  });

  it("keeps Denver's different estimator players and agreement flag explicit", () => {
    const input = source();
    input.atlas.entries.push({ entity: "DEN", card_path: "cards/denver.png", key_numbers: { team_full_name: "Denver Nuggets", pace_proxy_latest_season: 98, ppg_latest_season: 116 }, as_of: "2026-04-12" });
    input.loadBearing.results.push({ team: "DEN", estimator_a_elo_onoff: { player_name: "Nikola Jokic", delta_winprob: 0.5822 }, estimator_b_raw_withwithout: { player_name: "Aaron Gordon", delta_win_rate: 0.1818, n_active: 36, n_missed: 44 }, agreement_same_player: false });
    const row = buildNbaTeamProfileResearch(input)[0].rows.find(item => item.label === "Denver Nuggets")!;
    expect(row.values).toMatchObject({ fragility_delta_estimator_a: 0.5822, fragility_delta_estimator_b: 0.1818, fragility_estimator_b_active_games: 36, fragility_estimator_b_missed_games: 44 });
    expect(row.bindingValues).toMatchObject({ fragility_estimator_a_player: "Nikola Jokic", fragility_estimator_b_player: "Aaron Gordon", fragility_estimators_same_player: "false" });
  });

  it("excludes the real artifact's masked halftime margins from comparison and discloses their support", () => {
    const analysis = getNbaTeamProfileResearch()[0];
    expect(analysis.rows).toHaveLength(30);
    expect(analysis.rows.every(row => row.values.front_runner_second_half_margin === null && row.values.comeback_second_half_margin === null)).toBe(true);
    const atlanta = analysis.rows.find(row => row.label === "Atlanta Hawks")!;
    expect(atlanta.values).toMatchObject({ halftime_led_at_half_games: 1, halftime_trailed_at_half_games: 1, halftime_required_games_per_split: 2 });
    expect(atlanta.bindingValues?.halftime_source_disclosure).toContain("source masked this row below its split floor");
    expect(atlanta.bindingValues?.halftime_source_disclosure).toContain("led at half 1/2");
    expect(atlanta.bindingValues?.halftime_source_disclosure).toContain("trailed at half 1/2");
  });

  it("copies full-corpus coverage for all teams from the public atlas", () => {
    const analysis = getNbaTeamProfileResearch()[0];
    const games = analysis.rows.map(row => row.values.atlas_games_total);
    const seasons = analysis.rows.map(row => row.values.atlas_seasons_covered);
    expect(analysis.rows).toHaveLength(30);
    expect(games.every(value => value !== null && value >= 236 && value <= 246)).toBe(true);
    expect(seasons).toEqual(Array(30).fill(3));
    expect(analysis.rows.find(row => row.label === "Atlanta Hawks")?.values.atlas_games_total).toBe(239);
    expect(analysis.caveat).toContain("not denominators for latest-season pace or points per game");
    expect(analysis.caveat).toContain("not a per-team coverage endpoint");
  });

  it("does not qualify margins when split support counts are missing", () => {
    const input = source();
    const state = input.states.teams[0] as Record<string, unknown>;
    delete state.n_led_at_half;
    delete state.n_trailed_at_half;
    state.masked_below_floor = false;
    const row = buildNbaTeamProfileResearch(input)[0].rows.find(item => item.label === "Brooklyn Nets")!;
    expect(row.values.front_runner_second_half_margin).toBeNull();
    expect(row.values.comeback_second_half_margin).toBeNull();
  });

  it("keeps unmasked margins with both split counts above the published floor", () => {
    const input = source();
    const state = input.states.teams[0] as Record<string, unknown>;
    Object.assign(state, { n_led_at_half: 4, n_trailed_at_half: 3, front_runner_2h_margin: 1.5, comeback_2h_margin: -0.5, masked_below_floor: false });
    const analysis = buildNbaTeamProfileResearch(input)[0];
    const row = analysis.rows.find(item => item.label === "Brooklyn Nets")!;
    expect(row.values).toMatchObject({ halftime_led_at_half_games: 4, halftime_trailed_at_half_games: 3, halftime_required_games_per_split: 2, front_runner_second_half_margin: 1.5, comeback_second_half_margin: -0.5 });
    expect(row.bindingValues?.halftime_source_disclosure).toBeNull();
  });

  it("carries the published halftime floor and artifact date into the analysis definition", () => {
    const analysis = buildNbaTeamProfileResearch(source())[0];
    expect(analysis.method).toContain("floor of 2 games");
    expect(analysis.method).toContain("as of 2026-05-21");
    expect(analysis.formula).toContain("floor of 2 games per split");
    expect(analysis.formula).toContain("artifact as of 2026-05-21");
  });
});
