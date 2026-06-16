/** RTL tests for WinProbCell: verifies home/away pct display, draw row gating
 * by sport, and the all-null "--" fallback. Uses a minimal BoardRow builder so
 * each test only overrides the fields it cares about. No snapshot tests.
 */
import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { WinProbCell } from "./WinProbCell";
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
    source: "model",
    market_implied: false,
    note: null,
  };
  return { ...base, ...overrides };
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("WinProbCell", () => {
  it("shows 61% and 39% for an mlb row with win_home=0.61 win_away=0.39", () => {
    const row = buildRow({ sport: "mlb", win_home: 0.61, win_away: 0.39 });
    render(<WinProbCell row={row} />);

    expect(screen.getByText("61%")).toBeInTheDocument();
    expect(screen.getByText("39%")).toBeInTheDocument();
  });

  it("does NOT render a Draw row for an mlb game", () => {
    const row = buildRow({ sport: "mlb", win_home: 0.61, win_away: 0.39 });
    render(<WinProbCell row={row} />);

    expect(screen.queryByText("Draw")).not.toBeInTheDocument();
  });

  it("shows a Draw row with 25% for a soccer game that has draw=0.25", () => {
    const row = buildRow({
      sport: "soccer",
      win_home: 0.45,
      win_away: 0.30,
      draw: 0.25,
    });
    render(<WinProbCell row={row} />);

    expect(screen.getByText("Draw")).toBeInTheDocument();
    expect(screen.getByText("25%")).toBeInTheDocument();
  });

  it("does NOT show a Draw row for soccer when draw is null", () => {
    const row = buildRow({
      sport: "soccer",
      win_home: 0.55,
      win_away: 0.45,
      draw: null,
    });
    render(<WinProbCell row={row} />);

    expect(screen.queryByText("Draw")).not.toBeInTheDocument();
  });

  it("renders -- when all probability fields are null", () => {
    const row = buildRow({ win_home: null, win_away: null, draw: null });
    render(<WinProbCell row={row} />);

    // The group wrapper shows "--"; no percentage bars should be rendered.
    const group = screen.getByRole("group", { name: /win probability/i });
    expect(group).toHaveTextContent("--");
    expect(screen.queryByText("Home")).not.toBeInTheDocument();
    expect(screen.queryByText("Away")).not.toBeInTheDocument();
  });

  it("ignores a non-null draw value when sport is not soccer", () => {
    // draw field present but sport=mlb -> Draw row must NOT appear.
    const row = buildRow({ sport: "mlb", win_home: 0.6, win_away: 0.4, draw: 0.1 });
    render(<WinProbCell row={row} />);

    expect(screen.queryByText("Draw")).not.toBeInTheDocument();
  });

  it("labels the container with 'Win probability' for accessibility", () => {
    const row = buildRow({ win_home: 0.5, win_away: 0.5 });
    render(<WinProbCell row={row} />);

    expect(
      screen.getByRole("group", { name: /win probability/i })
    ).toBeInTheDocument();
  });
});
