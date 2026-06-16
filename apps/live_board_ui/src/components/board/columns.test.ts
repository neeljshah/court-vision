/**
 * Unit tests for computeColumns and rowGridClass in "@/components/board/columns".
 * Pure logic -- no DOM or React needed, so no setup import required.
 */
import { describe, it, expect } from "vitest";
import type { BoardRow } from "@/types/board";
import { computeColumns, rowGridClass } from "@/components/board/columns";

// ---------------------------------------------------------------------------
// Minimal BoardRow partial helper
// ---------------------------------------------------------------------------

function makeRow(overrides: Partial<BoardRow> = {}): BoardRow {
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
    market_implied: false,
    note: null,
    ...overrides,
  } as BoardRow;
}

// ---------------------------------------------------------------------------
// computeColumns
// ---------------------------------------------------------------------------

describe("computeColumns", () => {
  it("returns { odds: false, total: false } when all rows have null market_odds and null total", () => {
    const rows = [makeRow(), makeRow(), makeRow()];
    const result = computeColumns(rows);
    expect(result.odds).toBe(false);
    expect(result.total).toBe(false);
  });

  it("returns { odds: false, total: false } for an empty row array", () => {
    const result = computeColumns([]);
    expect(result.odds).toBe(false);
    expect(result.total).toBe(false);
  });

  it("returns total: true when at least one row has a non-null total", () => {
    const rows = [makeRow(), makeRow({ total: 7.8 }), makeRow()];
    const result = computeColumns(rows);
    expect(result.total).toBe(true);
    expect(result.odds).toBe(false);
  });

  it("returns odds: true when at least one row has a non-null market_odds string", () => {
    const rows = [makeRow(), makeRow({ market_odds: "-110" }), makeRow()];
    const result = computeColumns(rows);
    expect(result.odds).toBe(true);
    expect(result.total).toBe(false);
  });

  it("returns both true when rows include both market_odds and total", () => {
    const rows = [makeRow({ market_odds: "+105", total: 9.0 }), makeRow()];
    const result = computeColumns(rows);
    expect(result.odds).toBe(true);
    expect(result.total).toBe(true);
  });

  it("still returns odds: false when market_odds is present but is an empty string", () => {
    // The implementation trims and checks for non-empty, so "" should not count.
    const rows = [makeRow({ market_odds: "" })];
    const result = computeColumns(rows);
    expect(result.odds).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// rowGridClass
// ---------------------------------------------------------------------------

describe("rowGridClass", () => {
  it("starts with 'md:grid-cols-[110px' regardless of visibility flags", () => {
    expect(rowGridClass({ odds: false, total: false })).toMatch(
      /^md:grid-cols-\[110px/
    );
    expect(rowGridClass({ odds: true, total: true })).toMatch(
      /^md:grid-cols-\[110px/
    );
  });

  it("omits the Odds (110px, track 5) and Total (70px, track 6) segments when both are false", () => {
    const cls = rowGridClass({ odds: false, total: false });
    // The full grid when both present contains these segments after position 4
    // We verify neither the dedicated "odds" 110px track nor the 70px total track
    // are present by checking the track list does not contain _70px at all.
    expect(cls).not.toContain("_70px");
    // The grid should have exactly 6 tracks: Status Matchup Score WinProb Source Updated
    const inner = cls.replace(/^md:grid-cols-\[/, "").replace(/\]$/, "");
    const tracks = inner.split("_");
    expect(tracks).toHaveLength(6);
  });

  it("does NOT contain the 70px Total track when total is false", () => {
    const cls = rowGridClass({ odds: false, total: false });
    expect(cls).not.toContain("70px");
  });

  it("does NOT contain the dropped Odds segment (_110px after the base 110px Status track) when odds is false", () => {
    // With odds:false the only 110px tracks are Status (1st) and Source (6th of 6).
    const cls = rowGridClass({ odds: false, total: false });
    const inner = cls.replace(/^md:grid-cols-\[/, "").replace(/\]$/, "");
    const tracks = inner.split("_");
    // Two 110px tracks (Status + Source), no extra Odds track
    const count110 = tracks.filter((t) => t === "110px").length;
    expect(count110).toBe(2);
  });

  it("contains both _110px (Odds) and _70px (Total) tracks when both are true", () => {
    const cls = rowGridClass({ odds: true, total: true });
    expect(cls).toContain("70px");
    // Full 8 tracks
    const inner = cls.replace(/^md:grid-cols-\[/, "").replace(/\]$/, "");
    const tracks = inner.split("_");
    expect(tracks).toHaveLength(8);
  });

  it("includes Total (70px) but not an extra Odds track when only total is true", () => {
    const cls = rowGridClass({ odds: false, total: true });
    expect(cls).toContain("70px");
    const inner = cls.replace(/^md:grid-cols-\[/, "").replace(/\]$/, "");
    const tracks = inner.split("_");
    expect(tracks).toHaveLength(7);
    const count110 = tracks.filter((t) => t === "110px").length;
    // Status + Source only (no Odds), so 2
    expect(count110).toBe(2);
  });

  it("includes Odds (extra 110px) but not Total when only odds is true", () => {
    const cls = rowGridClass({ odds: true, total: false });
    expect(cls).not.toContain("70px");
    const inner = cls.replace(/^md:grid-cols-\[/, "").replace(/\]$/, "");
    const tracks = inner.split("_");
    expect(tracks).toHaveLength(7);
    const count110 = tracks.filter((t) => t === "110px").length;
    // Status + Odds + Source = 3
    expect(count110).toBe(3);
  });
});
