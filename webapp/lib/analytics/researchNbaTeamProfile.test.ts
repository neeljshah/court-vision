import { describe, expect, it } from "vitest";
import { buildNbaTeamProfileResearch } from "./researchNbaTeamProfile";

function source() {
  return {
    atlas: { entries: [
      { entity: "ATL", key_numbers: { team_full_name: "Atlanta Hawks", pace_proxy_latest_season: 101, ppg_latest_season: 114 }, as_of: "2026-04-12" },
      { entity: "BKN", key_numbers: { team_full_name: "Brooklyn Nets", pace_proxy_latest_season: 99, ppg_latest_season: 108 }, as_of: "2026-04-12" },
    ] },
    loadBearing: { as_of: { estimator_a: "2024-25", estimator_b: "2025-26" }, results: [{ team: "BRK", estimator_a_elo_onoff: { delta_winprob: 0.2 }, estimator_b_raw_withwithout: { delta_win_rate: 0.1 } }] },
    fatigue: { results: [{ team: "BKN", season: "2024-25", sft_credible_pts_per100_ortg: -0.3 }] },
    density: { per_team_season_frequencies: [{ team: "BKN", season: "2023-24", b2b_freq: 0.2 }] },
    states: { as_of: "2026-05-21", teams: [{ team: "BKN", n_games: 2, front_runner_2h_margin: 1, comeback_2h_margin: -2, masked_below_floor: true }] },
  };
}

describe("NBA team profile research", () => {
  it("joins normalized team aliases and keeps source paths", () => {
    const row = buildNbaTeamProfileResearch(source())[0].rows.find(item => item.label === "Brooklyn Nets")!;
    expect(row.values).toMatchObject({ pace_proxy: 99, fragility_delta_estimator_a: 0.2, fatigue_tax_pts_per100: -0.3, back_to_back_share: 0.2 });
    expect(row.sourcePaths).toContain("novel_load_bearing_index.results[].estimator_a_elo_onoff.delta_winprob");
  });

  it("reports unmatched keys without removing atlas teams", () => {
    const input = source();
    input.loadBearing.results.push({ team: "XXX", estimator_a_elo_onoff: { delta_winprob: 0.4 }, estimator_b_raw_withwithout: { delta_win_rate: 0.2 } });
    const analysis = buildNbaTeamProfileResearch(input)[0];
    expect(analysis.rows.map(row => row.label)).toContain("Atlanta Hawks");
    expect(analysis.caveat).toContain("source-only teams: XXX");
  });

  it("retains explicit nulls for absent joined measurements", () => {
    const row = buildNbaTeamProfileResearch(source())[0].rows.find(item => item.label === "Atlanta Hawks")!;
    expect(row.values.fragility_delta_estimator_a).toBeNull();
    expect(row.values.back_to_back_share).toBeNull();
    expect(row.note).toContain("No published halftime-state record");
  });

  it("orders team rows by the published team name", () => {
    expect(buildNbaTeamProfileResearch(source())[0].rows.map(row => row.label)).toEqual(["Atlanta Hawks", "Brooklyn Nets"]);
  });
});
