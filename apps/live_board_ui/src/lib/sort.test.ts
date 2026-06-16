/** Vitest unit tests for sortSection (src/lib/sort.ts). */

import { describe, it, expect } from "vitest";
import { sortSection } from "@/lib/sort";
import type { BoardRow } from "@/types/board";

// ---------------------------------------------------------------------------
// Minimal fixture helper -- only the fields sortSection reads.
// ---------------------------------------------------------------------------
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
    source: "market",
    market_implied: true,
    note: null,
    ...overrides,
  } as BoardRow;
}

// ---------------------------------------------------------------------------
// "favorite" mode
// ---------------------------------------------------------------------------
describe('sortSection -- mode "favorite"', () => {
  it("orders rows by descending max(win_home, win_away); null rows sort last", () => {
    const r90 = row({ win_home: 0.9, win_away: 0.1 });
    const r55 = row({ win_home: 0.55, win_away: 0.45 });
    const rNull = row({ win_home: null, win_away: null });

    // Input intentionally scrambled
    const input = [rNull, r55, r90];
    const result = sortSection(input, "favorite");

    expect(result[0]).toBe(r90);
    expect(result[1]).toBe(r55);
    expect(result[2]).toBe(rNull);
  });
});

// ---------------------------------------------------------------------------
// "soonest" mode
// ---------------------------------------------------------------------------
describe('sortSection -- mode "soonest"', () => {
  it("sorts ascending by start_time; null start_time sorts last", () => {
    const early = row({ start_time: "2026-06-15T18:00:00Z" });
    const late  = row({ start_time: "2026-06-15T23:59:00Z" });
    const mid   = row({ start_time: "2026-06-15T21:00:00Z" });
    const noTime = row({ start_time: null });

    const input = [noTime, late, early, mid];
    const result = sortSection(input, "soonest");

    expect(result[0]).toBe(early);
    expect(result[1]).toBe(mid);
    expect(result[2]).toBe(late);
    expect(result[3]).toBe(noTime);
  });
});

// ---------------------------------------------------------------------------
// "default" mode
// ---------------------------------------------------------------------------
describe('sortSection -- mode "default"', () => {
  it('places predicted rows above source:"unavailable" rows', () => {
    const predicted  = row({ source: "model" });
    const unavailable = row({ source: "unavailable" });

    const input = [unavailable, predicted];
    const result = sortSection(input, "default");

    expect(result[0]).toBe(predicted);
    expect(result[1]).toBe(unavailable);
  });
});

// ---------------------------------------------------------------------------
// Immutability -- sortSection must not mutate the input array
// ---------------------------------------------------------------------------
describe("sortSection -- immutability", () => {
  it("returns a new array and leaves the original order unchanged", () => {
    const r1 = row({ win_home: 0.6, win_away: 0.4 });
    const r2 = row({ win_home: 0.9, win_away: 0.1 });
    const input = [r1, r2];
    const originalFirst = input[0];

    const result = sortSection(input, "favorite");

    // New array reference
    expect(result).not.toBe(input);
    // Input order unchanged: r1 is still first
    expect(input[0]).toBe(originalFirst);
    // Result IS sorted (r2 is the bigger favorite)
    expect(result[0]).toBe(r2);
  });
});
