import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { buildNbaFormCoverage } from "./nbaFormCoverage";

const published = JSON.parse(readFileSync(join(process.cwd(), "public/data/showcase/nba_form_curves.json"), "utf8"));
const input = (unique_players: unknown, players_with_retained_window: unknown, movers_eligible: unknown) =>
  ({ input_coverage: { unique_players, players_with_retained_window, movers_eligible } });

describe("NBA form selection support", () => {
  it("reproduces the published nested player-ID counts without mixing overlapping windows", () => {
    const result = buildNbaFormCoverage(published);
    expect(result).toMatchObject({ sourcePlayers: 807, retainedPlayers: 619, eligibleMovers: 562,
      excludedBeforeWindow: 188, excludedBeforeMover: 57, pooledWindows: 61298,
      publishedMoverRows: 30, consistent: true, windowGames: 10,
      seasons: ["2023-24", "2024-25", "2025-26"], floors: published.methodology.floors });
    expect(result.retainedShare).toBeCloseTo(619 / 807, 12);
    expect(result.eligibleShare).toBeCloseTo(562 / 619, 12);
  });

  it.each([undefined, null, "807", -1, 1.5, Infinity, NaN, Number.MAX_SAFE_INTEGER + 1])(
    "keeps an invalid count unavailable and suppresses the cohort derivations: %s", value => {
      const result = buildNbaFormCoverage(input(value, 619, 562));
      expect(result.sourcePlayers).toBeNull();
      expect(result.retainedPlayers).toBe(619);
      expect(result.eligibleMovers).toBe(562);
      expect(result.consistent).toBe(false);
      expect([result.retainedShare, result.eligibleShare, result.excludedBeforeWindow, result.excludedBeforeMover]).toEqual([null, null, null, null]);
    });

  it.each([[5, 6, 4], [5, 4, 6], [0, 1, 1]])("preserves contradictory source counts %s/%s/%s without clamping rates", (raw, retained, eligible) => {
    const result = buildNbaFormCoverage(input(raw, retained, eligible));
    expect([result.sourcePlayers, result.retainedPlayers, result.eligibleMovers]).toEqual([raw, retained, eligible]);
    expect(result.consistent).toBe(false);
    expect([result.retainedShare, result.eligibleShare, result.excludedBeforeWindow, result.excludedBeforeMover]).toEqual([null, null, null, null]);
  });

  it("preserves explicit zero while leaving zero-denominator shares unavailable", () => {
    expect(buildNbaFormCoverage(input(0, 0, 0))).toMatchObject({ sourcePlayers: 0, retainedPlayers: 0,
      eligibleMovers: 0, consistent: true, retainedShare: null, eligibleShare: null,
      excludedBeforeWindow: 0, excludedBeforeMover: 0 });
    expect(buildNbaFormCoverage(input(5, 0, 0))).toMatchObject({ retainedShare: 0, eligibleShare: null });
  });

  it("keeps missing metadata unknown rather than inferring a date or window", () => {
    expect(buildNbaFormCoverage(null)).toMatchObject({ seasons: [], windowGames: null, floors: null,
      pooledWindows: null, publishedMoverRows: null });
    expect(buildNbaFormCoverage({ methodology: { window_games: 0, seasons_pooled: [2024, "bad", "2024-25", "2024-25"] } })).toMatchObject({ windowGames: null, seasons: ["2024-25"] });
  });

  it("counts published entries without pretending names identify unique people", () => {
    expect(buildNbaFormCoverage({ top_movers_risers: [{ player_name: "Same" }], top_movers_fallers: [{ player_name: "Same" }] }).publishedMoverRows).toBe(2);
    expect(buildNbaFormCoverage({ top_movers_risers: [], top_movers_fallers: [] }).publishedMoverRows).toBe(0);
    expect(buildNbaFormCoverage({ top_movers_risers: [null], top_movers_fallers: [] }).publishedMoverRows).toBeNull();
  });
});
