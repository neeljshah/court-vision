import { describe, expect, it } from "vitest";
import { entityMeasurements } from "./entityMeasurements";

const pct = { n_in_pack: 69, fields: { n_pitches: { n_ranked: 61 } }, entities: { ch: { n_pitches: 82 } } };

describe("entityMeasurements", () => {
  it("keeps pitch distributions in their published order", () => {
    const result = entityMeasurements("mlb_pitch", { key_numbers: { n_pitches: 4, pct_of_all_pitches: 0, count_leverage_pct: { pitcher_ahead: 37.1, even: 40, pitcher_behind: 22.9 }, count_state_pct: { "0-0": 16.2, "0-1": 17.0 }, outcome_mix_pct: { ball: 40.7, strike: 40.1, "in-play": 19.2 } } }, "ch", pct);
    expect(result.distributions.map((item) => item.key)).toEqual(["count_leverage_pct", "count_state_pct", "outcome_mix_pct"]);
    expect(result.distributions[0].rows.map((row) => row.key)).toEqual(["pitcher_ahead", "even", "pitcher_behind"]);
  });

  it("treats zero as measured rather than unavailable", () => {
    const result = entityMeasurements("mlb_pitch", { key_numbers: { n_pitches: 0, pct_of_all_pitches: 0, velo_p10: null, velo_p50: 80, velo_p90: 90 } }, "ch", pct);
    expect(result.scalars.find((item) => item.key === "n_pitches")?.value).toBe("0");
    expect(result.unavailable.map((item) => item.key)).toContain("count_leverage_pct");
    expect(result.unavailable.map((item) => item.key)).toContain("velo_p10");
  });

  it("formats fractional win rates as percentages", () => {
    const result = entityMeasurements("tennis", { key_numbers: { hard_wr_career: 0.6906, clay_wr_career: 0.5, grass_wr_career: 0.6, hard_wr_recent: 0.7, clay_wr_recent: 0.7, grass_wr_recent: 0.7, clay_minus_hard_career: 0, clay_minus_hard_recent: 0, grass_adapt_career: 0, grass_adapt_recent: 0 } }, "zverev");
    expect(result.scalars.find((item) => item.key === "hard_wr_career")).toMatchObject({ value: "69.1%", unit: "%" });
  });

  it("keeps published percent values as percentages without scaling them again", () => {
    const result = entityMeasurements("mlb_pitch", { key_numbers: { pct_of_all_pitches: 0.06 } }, "cs");
    expect(result.scalars.find((item) => item.key === "pct_of_all_pitches")?.value).toBe("0.06%");
  });

  it("excludes identifiers and keeps unknown numeric keys as plain numbers", () => {
    const known = entityMeasurements("nba_players", { key_numbers: { player_id: 7, team_id: 8, career_games: 50 } }, "player");
    const unknown = entityMeasurements("unlisted_pack", { key_numbers: { new_rate: 0.612 } }, "player");
    expect(known.scalars.map((item) => item.key)).not.toContain("player_id");
    expect(known.scalars.map((item) => item.key)).not.toContain("team_id");
    expect(unknown.scalars[0]).toMatchObject({ label: "New Rate", value: "0.612" });
  });

  it("attaches matching floor guidance to unavailable tennis fields", () => {
    const result = entityMeasurements("tennis", { key_numbers: { hard_wr_career: null }, floors: "hard_wr: hard_n>=30 | clay_wr: clay_n>=30" }, "player");
    expect(result.unavailable.find((item) => item.key === "hard_wr_career")?.floor).toBe("hard_wr: hard_n>=30");
  });

  it("keeps new published numeric fields conservative until they receive a definition", () => {
    const result = entityMeasurements("nba_players", { key_numbers: { career_games: 50, invented_signal: 99 } }, "player");
    expect(result.scalars).toEqual(expect.arrayContaining([
      expect.objectContaining({ key: "career_games", value: "50" }),
      expect.objectContaining({ key: "invented_signal", label: "Invented Signal", value: "99" }),
    ]));
  });
});
