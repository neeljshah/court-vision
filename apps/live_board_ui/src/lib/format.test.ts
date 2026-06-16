/** Vitest unit tests for @/lib/format -- pct, winnerSide, setsWon, sortRows. */
import { describe, it, expect } from "vitest";
import type { BoardRow } from "@/types/board";
import { pct, winnerSide, setsWon, sortRows } from "@/lib/format";

// Minimal partial helper -- cast so we don't repeat every field.
function row(overrides: Partial<BoardRow>): BoardRow {
  return {
    sport: "mlb",
    league: "mlb",
    state: "pre",
    start_time: null,
    home: "Home",
    away: "Away",
    home_score: null,
    away_score: null,
    clock_text: null,
    win_home: null,
    win_away: null,
    draw: null,
    total: null,
    market_odds: null,
    provider: null,
    source: "model",
    market_implied: false,
    note: null,
    ...overrides,
  } as BoardRow;
}

// ---------------------------------------------------------------------------
// pct
// ---------------------------------------------------------------------------
describe("pct", () => {
  it("rounds a 0..1 fraction to integer percent", () => {
    expect(pct(0.611)).toBe(61);
  });

  it("returns null for null input", () => {
    expect(pct(null)).toBeNull();
  });

  it("passes through an already-percent value unchanged", () => {
    expect(pct(78)).toBe(78);
  });

  it("returns null for undefined", () => {
    expect(pct(undefined)).toBeNull();
  });

  it("returns null for NaN", () => {
    expect(pct(NaN)).toBeNull();
  });

  it("handles 0 as 0%", () => {
    expect(pct(0)).toBe(0);
  });

  it("handles 1.0 as 100%", () => {
    expect(pct(1)).toBe(100);
  });
});

// ---------------------------------------------------------------------------
// winnerSide
// ---------------------------------------------------------------------------
describe("winnerSide", () => {
  it("returns 'home' when home score exceeds away score on a post mlb row", () => {
    const r = row({ state: "post", sport: "mlb", home_score: 7, away_score: 0 });
    expect(winnerSide(r)).toBe("home");
  });

  it("returns null for tied post soccer row (1-1)", () => {
    const r = row({
      state: "post",
      sport: "soccer",
      home_score: 1,
      away_score: 1,
    });
    expect(winnerSide(r)).toBeNull();
  });

  it("returns null for a non-post row regardless of scores", () => {
    const r = row({ state: "in", home_score: 5, away_score: 1 });
    expect(winnerSide(r)).toBeNull();
  });

  it("returns null for a pre row", () => {
    const r = row({ state: "pre", home_score: null, away_score: null });
    expect(winnerSide(r)).toBeNull();
  });

  it("returns 'away' when away score exceeds home on post mlb row", () => {
    const r = row({ state: "post", sport: "mlb", home_score: 2, away_score: 9 });
    expect(winnerSide(r)).toBe("away");
  });
});

// ---------------------------------------------------------------------------
// setsWon
// ---------------------------------------------------------------------------
describe("setsWon", () => {
  // awayStr, homeStr -- away won sets "6 4 7", home won sets "3 6 5"
  // Set breakdown: set1: away 6 > home 3 -> away; set2: home 6 > away 4 -> home;
  //                set3: away 7 > home 5 -> away => away wins 2-1
  it("returns 'away' when away player wins 2 of 3 sets (6 4 7 vs 3 6 5)", () => {
    expect(setsWon("6 4 7", "3 6 5")).toBe("away");
  });

  // home wins 6-4, 7-5 -> 2 sets, away wins 0 -> home
  it("returns 'home' when home player wins 2 of 2 sets (4 5 vs 6 7)", () => {
    expect(setsWon("4 5", "6 7")).toBe("home");
  });

  // Each player wins 1 set: 6-3, 3-6 -> tied 1-1
  it("returns null when each player wins one set (6 3 vs 3 6)", () => {
    expect(setsWon("6 3", "3 6")).toBeNull();
  });

  it("returns null when inputs are not strings", () => {
    expect(setsWon(null, null)).toBeNull();
    expect(setsWon(6, 3)).toBeNull();
  });

  it("handles a straight-sets away win (6 6 vs 2 1)", () => {
    expect(setsWon("6 6", "2 1")).toBe("away");
  });
});

// ---------------------------------------------------------------------------
// sortRows
// ---------------------------------------------------------------------------
describe("sortRows", () => {
  it("places live (state='in') rows before pre then post", () => {
    const a = row({ state: "post", start_time: "2026-01-01T10:00:00Z", source: "model" });
    const b = row({ state: "pre",  start_time: "2026-01-01T11:00:00Z", source: "model" });
    const c = row({ state: "in",   start_time: "2026-01-01T09:00:00Z", source: "model" });
    const sorted = sortRows([a, b, c]);
    expect(sorted[0].state).toBe("in");
    expect(sorted[1].state).toBe("pre");
    expect(sorted[2].state).toBe("post");
  });

  it("places predicted rows before unavailable rows within the same state group", () => {
    const predicted = row({ state: "pre", source: "market", start_time: "2026-01-01T12:00:00Z" });
    const unavail   = row({ state: "pre", source: "unavailable", start_time: "2026-01-01T11:00:00Z" });
    const sorted = sortRows([unavail, predicted]);
    expect(sorted[0].source).toBe("market");
    expect(sorted[1].source).toBe("unavailable");
  });

  it("orders live predicted before live unavailable", () => {
    const liveModel  = row({ state: "in", source: "live-model" });
    const liveNone   = row({ state: "in", source: "unavailable" });
    const sorted = sortRows([liveNone, liveModel]);
    expect(sorted[0].source).toBe("live-model");
    expect(sorted[1].source).toBe("unavailable");
  });

  it("sorts by start_time ascending within the same state+prediction group", () => {
    const early = row({ state: "pre", source: "model", start_time: "2026-06-15T14:00:00Z" });
    const late  = row({ state: "pre", source: "model", start_time: "2026-06-15T20:00:00Z" });
    const sorted = sortRows([late, early]);
    expect(sorted[0].start_time).toBe("2026-06-15T14:00:00Z");
    expect(sorted[1].start_time).toBe("2026-06-15T20:00:00Z");
  });

  it("handles an empty array", () => {
    expect(sortRows([])).toEqual([]);
  });

  it("does not mutate the original array", () => {
    const a = row({ state: "post" });
    const b = row({ state: "in" });
    const original = [a, b];
    sortRows(original);
    expect(original[0].state).toBe("post");
  });
});
