import { describe, expect, it } from "vitest";
import { buildOnOffResearch } from "./researchOnOff";

const player = (name: string, rank: number, delta: number, minutes: number) => ({ player_name: name, player_id: rank, rank, net_rating_delta: delta, min_on: minutes });

describe("on-off research", () => {
  it("builds published player measurements with source paths", () => {
    const analysis = buildOnOffResearch({ seasons: { "2024_25": { min_sample: { min_on: 500 }, top_15: [player("A Player", 1, 4.2, 800)], bottom_15: [] } } })[0];
    expect(analysis).toMatchObject({ id: "nba-on-off-net-rating-by-player", source: "on_off_showcase" });
    expect(analysis.rows[0].values).toMatchObject({ net_rating_delta: 4.2, minutes_on_court: 800, published_rank: 1 });
    expect(analysis.rows[0].sourcePaths).toContain("seasons.2024_25.top_15[].net_rating_delta");
  });

  it("orders each season by net rating delta", () => {
    const rows = buildOnOffResearch({ seasons: { "2024_25": { top_15: [player("Lower", 2, 1, 800), player("Higher", 1, 4, 900)] } } })[0].rows;
    expect(rows.map(row => row.label)).toEqual(["2024-25 | Higher", "2024-25 | Lower"]);
  });

  it("returns no rows for missing or malformed selections", () => {
    expect(buildOnOffResearch({ seasons: { "2024_25": { top_15: [{ ...player("Bad", 1, 2, 800), min_on: -1 }] } } })[0].rows).toEqual([]);
    expect(buildOnOffResearch({})[0].rows).toEqual([]);
  });
});
