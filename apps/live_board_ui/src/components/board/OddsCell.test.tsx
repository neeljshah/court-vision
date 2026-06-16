/** RTL tests for OddsCell: verifies odds+provider display and the null fallback.
 * Uses a minimal BoardRow builder so each test overrides only the fields it needs.
 */
import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { OddsCell } from "./OddsCell";
import type { BoardRow } from "@/types/board";

// ---------------------------------------------------------------------------
// Helper
// ---------------------------------------------------------------------------

function buildRow(overrides: Partial<BoardRow>): BoardRow {
  const base: BoardRow = {
    sport: "mlb",
    league: "mlb",
    state: "in",
    start_time: null,
    home: "NYY",
    away: "BOS",
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
  };
  return { ...base, ...overrides };
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("OddsCell", () => {
  it('renders "-110" and "DK" when market_odds is "-110" and provider is "DK"', () => {
    const row = buildRow({ market_odds: "-110", provider: "DK" });
    render(<OddsCell row={row} />);

    expect(screen.getByText("-110")).toBeInTheDocument();
    expect(screen.getByText("DK")).toBeInTheDocument();
  });

  it('renders a muted "--" and no provider when market_odds is null', () => {
    const row = buildRow({ market_odds: null, provider: null });
    render(<OddsCell row={row} />);

    expect(screen.getByText("--")).toBeInTheDocument();
    // Provider must not appear
    expect(screen.queryByText("DK")).not.toBeInTheDocument();
  });
});
