import { describe, expect, it } from "vitest";
import tennisAtlas from "../../public/data/showcase/atlas_tennis_manifest.json";
import { entityObservationContext } from "./entityObservationContext";

describe("entityObservationContext", () => {
  it("labels the NBA atlas sample as corpus seasons rather than a full career", () => {
    const line = entityObservationContext("nba_players", { as_of: "2026-04-12T00:00:00Z", key_numbers: { seasons_played: 3, career_games: 241, career_minutes: 7429 } });
    expect(line).toBe("Corpus measurements: 3 seasons in the snapshot, 241 games, 7,429 minutes; snapshot 2026-04-12");
    expect(line).not.toContain("career");
  });

  it("does not add an NBA corpus line to other entity packs", () => {
    expect(entityObservationContext("nba_teams", { as_of: "2026-04-12", key_numbers: { seasons_played: 3, career_games: 241, career_minutes: 7429 } })).toBeNull();
  });

  it("describes the documented tennis windows for complete and partial public entries", () => {
    const complete = tennisAtlas.entries.find(entry => entry.status === "complete")!;
    const partial = tennisAtlas.entries.find(entry => entry.key_numbers.hard_wr_recent === null)!;
    expect(complete).toBeTruthy();
    expect(partial).toBeTruthy();
    for (const entry of [complete, partial]) {
      const line = entityObservationContext("tennis", entry);
      expect(line).toContain("source corpus documented as 2015-2025");
      expect(line).toContain("career uses all dated corpus matches");
      expect(line).toContain("recent starts 2023-01-01 and overlaps the corpus");
      expect(line).toContain("Published floors apply independently for each metric and window");
      expect(line).toContain("Exact player match counts and latest match dates are not published");
      expect(line).toContain("The as-of date records claim computation, not a match cutoff");
    }
  });

  it("does not turn a tennis as-of value into an observation-window endpoint", () => {
    const line = entityObservationContext("tennis", { as_of: "2030-12-31T23:59:59Z", key_numbers: {} });
    expect(line).toContain("The as-of date records claim computation, not a match cutoff");
    expect(line).not.toContain("2030-12-31");
    expect(line).not.toContain("matches through 2030-12-31");
    expect(entityObservationContext("mlb_pitch", { as_of: "2030-12-31", key_numbers: {} })).toBeNull();
  });
});
