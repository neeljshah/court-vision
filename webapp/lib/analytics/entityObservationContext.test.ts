import { describe, expect, it } from "vitest";
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
});
