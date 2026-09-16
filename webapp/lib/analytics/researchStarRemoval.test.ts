import { describe, expect, it } from "vitest";
import { buildStarRemovalResearch } from "./researchStarRemoval";

const team = (team_abbr: string, player_name: string, delta_winprob: number) => ({ team_abbr, player_name, p_win_with: 0.7, p_win_without: 0.4, delta_winprob, on_off_net_rating_delta: 12.5, min_on: 1000 });

describe("star removal research", () => {
  it("builds scenario rows with direct source measurements", () => {
    const analysis = buildStarRemovalResearch({ as_of: "2026-05-21", teams: [team("DEN", "Nikola Jokic", 0.3)] })[0];
    expect(analysis).toMatchObject({ id: "star-removal-team-win-probability", source: "cf_star_removal", asOf: "2026-05-21" });
    expect(analysis.rows[0].values).toMatchObject({ win_probability_with: 0.7, win_probability_without: 0.4, minutes_active: 1000 });
    expect(analysis.rows[0].sourcePaths).toContain("teams[].p_win_with");
  });

  it("orders rows deterministically by player and team label", () => {
    const rows = buildStarRemovalResearch({ teams: [team("BOS", "Zed Player", 0.2), team("ATL", "Ada Player", 0.1)] })[0].rows;
    expect(rows.map(row => row.label)).toEqual(["Ada Player (ATL)", "Zed Player (BOS)"]);
  });

  it("keeps the analysis shape while rejecting malformed rows", () => {
    expect(buildStarRemovalResearch({ teams: [{ ...team("DEN", "Nikola Jokic", 0.3), p_win_with: 2 }] })[0].rows).toEqual([]);
    expect(buildStarRemovalResearch({})[0].rows).toEqual([]);
  });
});
