import { describe, expect, it } from "vitest";
import { ATLAS_FIELD_DEFINITIONS, atlasFieldDefinition } from "./atlasFieldDefinitions";

describe("atlas field definitions", () => {
  it("defines every published atlas key", () => {
    expect(Object.keys(ATLAS_FIELD_DEFINITIONS)).toEqual(["calibration", "mlb_batters", "mlb_pitch", "nba_players", "nba_teams", "soccer", "tennis"]);
    expect(Object.keys(ATLAS_FIELD_DEFINITIONS.mlb_pitch)).toContain("pct_of_all_pitches");
  });

  it("uses explicit percentage semantics and excludes identifiers", () => {
    expect(atlasFieldDefinition("mlb_pitch", "pct_of_all_pitches")).toMatchObject({ unit: "percent-already", decimals: 2 });
    expect(atlasFieldDefinition("tennis", "hard_wr_career")).toMatchObject({ unit: "fraction-as-percent", label: "Hard-court win rate, career" });
    expect(atlasFieldDefinition("nba_players", "player_id").isIdentifier).toBe(true);
    expect(atlasFieldDefinition("nba_players", "team_id").isIdentifier).toBe(true);
  });

  it("keeps unknown fields as plain numbers", () => {
    expect(atlasFieldDefinition("nba_players", "new_rate")).toMatchObject({ label: "New Rate", unit: "number", decimals: 3 });
  });
});
