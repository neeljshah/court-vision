import { describe, expect, it } from "vitest";
import { buildAtlasResearch, getAtlasPackResearch, type AtlasManifest, type AtlasPack } from "./researchAtlasPacks";

const pack: AtlasPack = {
  key: "nba_players", source: "atlas_nba_manifest", id: "nba-player-atlas-measurements",
  title: "NBA player atlas measurements", sport: "nba", noun: "NBA players",
};

describe("atlas pack research", () => {
  it("builds one descriptive row per published fixture entry", () => {
    const analysis = buildAtlasResearch(pack, { entries: [{ entity: "First Player", card_path: "cards/first.png", key_numbers: { career_games: 40, career_fg_pct: 42.5 }, floors: "minutes>=800", as_of: "2026-01-02" }] });
    expect(analysis.rows).toHaveLength(1);
    expect(analysis.rows[0]).toMatchObject({ label: "First Player", href: "/analytics/players/nba_players/first", values: { career_games: 40, career_fg_pct: 0.425 } });
    expect(analysis.rows[0].sourcePaths).toEqual(["entries[0].key_numbers.career_fg_pct", "entries[0].key_numbers.career_games"]);
    expect(analysis.asOf).toBe("2026-01-02");
  });

  it("uses the entity-page collision fallback for published card slugs", () => {
    const analysis = buildAtlasResearch(pack, { entries: [
      { entity: "First Player", card_path: "cards/shared.png", key_numbers: { career_games: 1 } },
      { entity: "Second Player!", card_path: "cards/shared.png", key_numbers: { career_games: 2 } },
    ] });
    expect(analysis.rows.map((row) => row.href)).toEqual([
      "/analytics/players/nba_players/shared", "/analytics/players/nba_players/second_player",
    ]);
  });

  it("preserves a published null for a scalar field", () => {
    const analysis = buildAtlasResearch(pack, { entries: [
      { entity: "Reported", card_path: "reported.png", key_numbers: { career_games: 10 } },
      { entity: "Unavailable", card_path: "unavailable.png", key_numbers: { career_games: null } },
    ] });
    expect(analysis.rows.map((row) => row.values.career_games)).toEqual([10, null]);
  });

  it("keeps nested measurements on the entity card rather than flattening them", () => {
    const analysis = buildAtlasResearch(pack, { entries: [{
      entity: "Pitch Type", card_path: "pitch.png", key_numbers: { n_pitches: 100, count_state_pct: { "0-0": 20 } },
    }] });
    expect(analysis.fields.map((item) => item.key)).toEqual(["n_pitches"]);
    expect(analysis.rows[0].values).toEqual({ n_pitches: 100 });
  });

  it("excludes identifiers and preserves explicit percentage definitions", () => {
    const analysis = buildAtlasResearch({ ...pack, key: "tennis" }, { entries: [{
      entity: "Player", card_path: "player.png", key_numbers: { player_id: 7, hard_wr_career: 0.612, clay_minus_hard_career: 0.06 },
    }] });
    expect(analysis.fields).toEqual(expect.arrayContaining([
      expect.objectContaining({ key: "hard_wr_career", label: "Hard-court win rate, career", unit: "percent" }),
      expect.objectContaining({ key: "clay_minus_hard_career", unit: "pp" }),
    ]));
    expect(analysis.fields.map((item) => item.key)).not.toContain("player_id");
    expect(analysis.rows[0].values).toMatchObject({ hard_wr_career: 0.612, clay_minus_hard_career: 0.06 });
  });

  it("keeps unknown values as numbers rather than inferring a percentage", () => {
    const analysis = buildAtlasResearch(pack, { entries: [{ entity: "Player", card_path: "player.png", key_numbers: { new_rate: 0.612 } }] });
    expect(analysis.fields[0]).toMatchObject({ key: "new_rate", label: "New Rate", unit: "number" });
    expect(analysis.rows[0].values.new_rate).toBe(0.612);
  });

  it("registers three non-overlapping MLB pitch atlas cohorts", () => {
    const analyses = getAtlasPackResearch().filter((analysis) => analysis.source === "atlas_mlb_pitch_manifest");
    expect(analyses.map((analysis) => [analysis.id, analysis.rows.length, analysis.fields[0].key])).toEqual([
      ["mlb-pitch-type-atlas-measurements", 19, "velo_p50"],
      ["mlb-team-pitch-atlas-measurements", 30, "n_pitches"],
      ["mlb-count-state-atlas-measurements", 12, "balls"],
    ]);
    expect(analyses[0].rows.every((row) => row.label.startsWith("pitch type "))).toBe(true);
    expect(analyses[1].rows.every((row) => row.label.startsWith("team "))).toBe(true);
    expect(analyses[2].rows.every((row) => row.label.startsWith("count:"))).toBe(true);
    expect(new Set(analyses.flatMap((analysis) => analysis.rows.map((row) => row.id))).size).toBe(61);
  });
});
