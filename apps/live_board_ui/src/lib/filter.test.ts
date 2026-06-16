/** Vitest unit tests for @/lib/filter -- filterRows query and liveOnly flag. */
import { describe, it, expect } from "vitest";
import type { BoardRow } from "@/types/board";
import { filterRows } from "@/lib/filter";

// Minimal partial helper -- cast so we don't repeat every required field.
function row(overrides: Partial<BoardRow>): BoardRow {
  return {
    sport: "mlb",
    league: "mlb",
    state: "pre",
    start_time: null,
    home: "Home Team",
    away: "Away Team",
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
// filterRows -- query matching
// ---------------------------------------------------------------------------
describe("filterRows query", () => {
  it("matches home team case-insensitively and drops non-matches", () => {
    const yankees = row({ home: "New York Yankees", away: "Boston Red Sox" });
    const other   = row({ home: "Los Angeles Dodgers", away: "San Francisco Giants" });
    const result  = filterRows([yankees, other], "yank", false);
    expect(result).toHaveLength(1);
    expect(result[0].home).toBe("New York Yankees");
  });

  it("matches the away team and keeps the row", () => {
    const yankees = row({ home: "Boston Red Sox", away: "New York Yankees" });
    const other   = row({ home: "Chicago Cubs", away: "St. Louis Cardinals" });
    const result  = filterRows([yankees, other], "yank", false);
    expect(result).toHaveLength(1);
    expect(result[0].away).toBe("New York Yankees");
  });

  it("is case-insensitive for uppercase query", () => {
    const r      = row({ home: "New York Yankees" });
    const result = filterRows([r], "YANK", false);
    expect(result).toHaveLength(1);
  });

  it("is case-insensitive for mixed-case query", () => {
    const r      = row({ home: "New York Yankees" });
    const result = filterRows([r], "YaNk", false);
    expect(result).toHaveLength(1);
  });

  it("drops rows where neither home nor away match", () => {
    const r      = row({ home: "Houston Astros", away: "Texas Rangers" });
    const result = filterRows([r], "yank", false);
    expect(result).toHaveLength(0);
  });
});

// ---------------------------------------------------------------------------
// filterRows -- liveOnly flag
// ---------------------------------------------------------------------------
describe("filterRows liveOnly", () => {
  it("keeps only state='in' rows when liveOnly=true", () => {
    const live = row({ state: "in",   home: "Team A" });
    const pre  = row({ state: "pre",  home: "Team B" });
    const post = row({ state: "post", home: "Team C" });
    const result = filterRows([live, pre, post], "", true);
    expect(result).toHaveLength(1);
    expect(result[0].state).toBe("in");
  });

  it("returns an empty array when liveOnly=true and no rows are live", () => {
    const pre  = row({ state: "pre" });
    const post = row({ state: "post" });
    const result = filterRows([pre, post], "", true);
    expect(result).toHaveLength(0);
  });

  it("combines liveOnly with a query -- must satisfy both", () => {
    const liveYankees = row({ state: "in",  home: "New York Yankees" });
    const preYankees  = row({ state: "pre", home: "New York Yankees" });
    const liveOther   = row({ state: "in",  home: "Boston Red Sox" });
    const result = filterRows([liveYankees, preYankees, liveOther], "yank", true);
    expect(result).toHaveLength(1);
    expect(result[0].home).toBe("New York Yankees");
    expect(result[0].state).toBe("in");
  });
});

// ---------------------------------------------------------------------------
// filterRows -- passthrough (no filters)
// ---------------------------------------------------------------------------
describe("filterRows passthrough", () => {
  it("returns all rows unchanged when query is empty and liveOnly=false", () => {
    const rows = [
      row({ home: "New York Yankees", state: "in" }),
      row({ home: "Los Angeles Dodgers", state: "pre" }),
      row({ home: "Chicago Cubs", state: "post" }),
    ];
    const result = filterRows(rows, "", false);
    expect(result).toHaveLength(rows.length);
    // Preserves order
    expect(result[0].home).toBe("New York Yankees");
    expect(result[1].home).toBe("Los Angeles Dodgers");
    expect(result[2].home).toBe("Chicago Cubs");
  });

  it("treats a whitespace-only query as empty (no filtering)", () => {
    const rows = [row({ home: "Team A" }), row({ home: "Team B" })];
    const result = filterRows(rows, "   ", false);
    expect(result).toHaveLength(2);
  });

  it("returns an empty array when the input is empty", () => {
    expect(filterRows([], "yank", false)).toHaveLength(0);
    expect(filterRows([], "", true)).toHaveLength(0);
    expect(filterRows([], "", false)).toHaveLength(0);
  });

  it("does not mutate the original array", () => {
    const rows = [
      row({ home: "New York Yankees", state: "pre" }),
      row({ home: "Boston Red Sox", state: "in" }),
    ];
    const copy = [...rows];
    filterRows(rows, "yank", true);
    expect(rows).toHaveLength(copy.length);
    expect(rows[0].home).toBe(copy[0].home);
  });
});
