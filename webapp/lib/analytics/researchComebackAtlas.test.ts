import { describe, expect, it } from "vitest";
import { buildComebackAtlasResearch } from "./researchComebackAtlas";

const cell = (lead_band: string, time_band: string, outcome_rate: number, n_games = 40) => ({ lead_band, time_band, outcome_rate, n_games, n_ticks: 200, masked_n_lt_30: n_games < 30 });

describe("comeback atlas research", () => {
  it("builds comeback share as the complement of the leading-side outcome rate", () => {
    const analysis = buildComebackAtlasResearch({ cells: [cell("lead_+01_05", "rem_00_02", 0.8)] })[0];
    expect(analysis).toMatchObject({ id: "comeback-rates-deficit-time", source: "comeback_atlas" });
    expect(analysis.rows[0].values).toMatchObject({ comeback_share: 0.2, games: 40, ticks: 200 });
    expect(analysis.rows[0].sourcePaths).toContain("cells[].outcome_rate");
  });

  it("orders deficit-time cells deterministically and retains flagged support", () => {
    const rows = buildComebackAtlasResearch({ cells: [cell("lead_+06_10", "rem_05_12", 0.9), cell("lead_+01_05", "rem_00_02", 0.8, 20)] })[0].rows;
    expect(rows.map(row => row.label)).toEqual(["Deficit 1-5 | 0-2 remaining", "Deficit 6-10 | 5-12 remaining"]);
    expect(rows[0].note).toContain("Small-support source cell");
  });

  it("returns no rows for missing or malformed cells", () => {
    expect(buildComebackAtlasResearch({ cells: [{ ...cell("lead_+01_05", "rem_00_02", 0.8), n_games: -1 }] })[0].rows).toEqual([]);
    expect(buildComebackAtlasResearch({})[0].rows).toEqual([]);
  });
});
