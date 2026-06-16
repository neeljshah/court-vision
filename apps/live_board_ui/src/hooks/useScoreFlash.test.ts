/**
 * Vitest unit tests for useScoreFlash: verifies initial-render no-flash,
 * score-change detection, 1.8s expiry, and null-score non-flash.
 */
import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { BoardRow } from "@/types/board";
import { gameKey } from "@/lib/gameKey";
import { useScoreFlash } from "./useScoreFlash";

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

/** Build a minimal in-game MLB row with controllable scores. */
function makeRow(
  overrides: Partial<Pick<BoardRow, "home_score" | "away_score" | "home" | "away" | "start_time" | "state">>,
): BoardRow {
  return {
    sport: "mlb",
    league: "MLB",
    state: "in",
    start_time: "2026-06-15T17:05:00Z",
    home: "NYY",
    away: "BOS",
    home_score: 3,
    away_score: 2,
    clock_text: "Bot 7",
    win_home: 0.58,
    win_away: 0.42,
    draw: null,
    total: 8.5,
    market_odds: null,
    provider: null,
    source: "market",
    market_implied: true,
    note: null,
    ...overrides,
  };
}

/** A pre-game row with null scores. */
function makePreRow(): BoardRow {
  return makeRow({ state: "pre", home_score: null, away_score: null });
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("useScoreFlash", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.runOnlyPendingTimers();
    vi.useRealTimers();
  });

  it("returns empty set on initial render -- no flash on first sight", () => {
    const rows = [makeRow({ home_score: 3, away_score: 2 })];
    const { result } = renderHook(() => useScoreFlash(rows));
    expect(result.current.size).toBe(0);
  });

  it("adds a gameKey to the set when the score changes on rerender", () => {
    const baseRow = makeRow({ home_score: 3, away_score: 2 });
    const { result, rerender } = renderHook(
      ({ rows }: { rows: BoardRow[] }) => useScoreFlash(rows),
      { initialProps: { rows: [baseRow] } },
    );

    // No flash after initial render.
    expect(result.current.size).toBe(0);

    // Score changes on the same game.
    const updatedRow = makeRow({ home_score: 4, away_score: 2 });
    // Wrap rerender in act so the synchronous useEffect + setState flush before assertions.
    act(() => { rerender({ rows: [updatedRow] }); });

    const key = gameKey(updatedRow);
    expect(result.current.has(key)).toBe(true);
  });

  it("removes the gameKey from the set after ~1900ms (flash window expires)", () => {
    const baseRow = makeRow({ home_score: 3, away_score: 2 });
    const { result, rerender } = renderHook(
      ({ rows }: { rows: BoardRow[] }) => useScoreFlash(rows),
      { initialProps: { rows: [baseRow] } },
    );

    // Trigger a flash.
    const updatedRow = makeRow({ home_score: 4, away_score: 2 });
    act(() => {
      rerender({ rows: [updatedRow] });
    });

    const key = gameKey(updatedRow);
    expect(result.current.has(key)).toBe(true);

    // Advance past the 1.8s flash window.
    act(() => {
      vi.advanceTimersByTime(1_900);
    });

    expect(result.current.has(key)).toBe(false);
  });

  it("does not flash when a pre-game row keeps null scores across rerenders", () => {
    const preRow = makePreRow();
    const { result, rerender } = renderHook(
      ({ rows }: { rows: BoardRow[] }) => useScoreFlash(rows),
      { initialProps: { rows: [preRow] } },
    );

    expect(result.current.size).toBe(0);

    // Same null -> null: still no flash.
    act(() => {
      rerender({ rows: [makePreRow()] });
    });

    expect(result.current.size).toBe(0);
  });

  it("does not flash when scores are unchanged across rerenders", () => {
    const row = makeRow({ home_score: 3, away_score: 2 });
    const { result, rerender } = renderHook(
      ({ rows }: { rows: BoardRow[] }) => useScoreFlash(rows),
      { initialProps: { rows: [row] } },
    );

    act(() => {
      rerender({ rows: [makeRow({ home_score: 3, away_score: 2 })] });
    });

    expect(result.current.size).toBe(0);
  });

  it("handles multiple rows and only flashes the row whose score changed", () => {
    const rowA = makeRow({ home: "NYY", away: "BOS", home_score: 1, away_score: 0, start_time: "2026-06-15T17:00:00Z" });
    const rowB = makeRow({ home: "LAD", away: "SF", home_score: 2, away_score: 2, start_time: "2026-06-15T20:00:00Z" });

    const { result, rerender } = renderHook(
      ({ rows }: { rows: BoardRow[] }) => useScoreFlash(rows),
      { initialProps: { rows: [rowA, rowB] } },
    );

    expect(result.current.size).toBe(0);

    // Only rowA's score changes.
    const rowAUpdated = makeRow({ home: "NYY", away: "BOS", home_score: 2, away_score: 0, start_time: "2026-06-15T17:00:00Z" });
    // act ensures the useEffect + setFlashing flush synchronously before assertions.
    act(() => { rerender({ rows: [rowAUpdated, rowB] }); });

    expect(result.current.has(gameKey(rowAUpdated))).toBe(true);
    expect(result.current.has(gameKey(rowB))).toBe(false);
  });
});
