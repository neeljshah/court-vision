/** Vitest: gameKey stability and uniqueness contract. */
import { describe, it, expect } from "vitest";
import { gameKey } from "@/lib/gameKey";
import type { BoardRow } from "@/types/board";

const base: BoardRow = {
  sport: "mlb",
  league: "MLB",
  state: "in",
  start_time: "2026-06-15T19:10:00Z",
  home: "NYY",
  away: "BOS",
  home_score: 0,
  away_score: 0,
  clock_text: "T1",
  win_home: 0.52,
  win_away: 0.48,
  draw: null,
  total: 8.5,
  market_odds: null,
  provider: null,
  source: "model",
  market_implied: false,
  note: null,
};

describe("gameKey", () => {
  it("is stable for the same game across two row objects with different scores and clock", () => {
    const rowA = { ...base, home_score: 2, away_score: 1, clock_text: "T3" } as BoardRow;
    const rowB = { ...base, home_score: 5, away_score: 4, clock_text: "T7" } as BoardRow;
    expect(gameKey(rowA)).toBe(gameKey(rowB));
  });

  it("differs for two different matchups", () => {
    const rowA = { ...base, home: "NYY", away: "BOS" } as BoardRow;
    const rowB = { ...base, home: "LAD", away: "SFG" } as BoardRow;
    expect(gameKey(rowA)).not.toBe(gameKey(rowB));
  });
});
