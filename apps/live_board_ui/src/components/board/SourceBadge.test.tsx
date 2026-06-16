/** RTL tests for SourceBadge: verifies honest provenance labels per row.source.
 * No edge/profit copy is ever asserted -- this is a decision-support tool. */
import { render, screen } from "@testing-library/react";
import type { BoardRow, RowSource, Sport, GameState } from "@/types/board";
import { SourceBadge } from "./SourceBadge";

// ---------------------------------------------------------------------------
// Helper
// ---------------------------------------------------------------------------

function makeRow(
  source: RowSource,
  overrides: Partial<BoardRow> = {}
): BoardRow {
  return {
    sport: "mlb" as Sport,
    league: "MLB",
    state: "in" as GameState,
    start_time: null,
    home: "TeamA",
    away: "TeamB",
    home_score: 0,
    away_score: 0,
    clock_text: null,
    win_home: null,
    win_away: null,
    draw: null,
    total: null,
    market_odds: null,
    provider: null,
    source,
    market_implied: false,
    note: null,
    ...overrides,
  };
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("SourceBadge", () => {
  it("renders MODEL for source='model'", () => {
    render(<SourceBadge row={makeRow("model")} />);
    expect(screen.getByText("MODEL")).toBeInTheDocument();
  });

  it("renders MODEL - LIVE for source='live-model'", () => {
    render(<SourceBadge row={makeRow("live-model")} />);
    expect(screen.getByText("MODEL - LIVE")).toBeInTheDocument();
  });

  it("renders MARKET for source='market'", () => {
    render(<SourceBadge row={makeRow("market")} />);
    expect(screen.getByText("MARKET")).toBeInTheDocument();
  });

  it("renders MARKET LINE for source='unavailable' with market_odds set", () => {
    render(<SourceBadge row={makeRow("unavailable", { market_odds: "-110" })} />);
    expect(screen.getByText("MARKET LINE")).toBeInTheDocument();
  });

  it("renders SCORE ONLY for source='unavailable' with no market_odds", () => {
    render(<SourceBadge row={makeRow("unavailable", { market_odds: null })} />);
    expect(screen.getByText("SCORE ONLY")).toBeInTheDocument();
  });
});
