/** RTL tests for ScoreCell: mlb post, tennis in-progress, and null/null states. */
import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { ScoreCell } from "./ScoreCell";
import type { BoardRow } from "@/types/board";

// ---------------------------------------------------------------------------
// Helper: builds a minimal BoardRow with required fields only.
// ---------------------------------------------------------------------------
function makeRow(overrides: Partial<BoardRow>): BoardRow {
  return {
    sport: "mlb",
    league: "MLB",
    state: "pre",
    start_time: null,
    home: "Team A",
    away: "Team B",
    home_score: null,
    away_score: null,
    clock_text: null,
    win_home: null,
    win_away: null,
    draw: null,
    total: null,
    market_odds: null,
    provider: null,
    source: "unavailable",
    market_implied: false,
    note: null,
    ...overrides,
  };
}

// ---------------------------------------------------------------------------
// MLB post game: away 4, home 2
// ---------------------------------------------------------------------------
describe("ScoreCell - MLB post game", () => {
  it('renders away score "4" and home score "2"', () => {
    const row = makeRow({
      sport: "mlb",
      state: "post",
      away_score: 4,
      home_score: 2,
    });
    const { container } = render(<ScoreCell row={row} />);
    // Both digit strings must appear somewhere in the rendered output
    expect(container.textContent).toContain("4");
    expect(container.textContent).toContain("2");
  });

  it("marks the away team bold when away wins (away 4 > home 2)", () => {
    const row = makeRow({
      sport: "mlb",
      state: "post",
      away_score: 4,
      home_score: 2,
      win_away: 1,
      win_home: 0,
    });
    const { container } = render(<ScoreCell row={row} />);
    // The away score span carries font-bold class when away wins
    const awaySpan = container.querySelector("span.font-bold");
    expect(awaySpan).not.toBeNull();
    expect(awaySpan?.textContent).toBe("4");
  });
});

// ---------------------------------------------------------------------------
// Tennis: away "6 4", home "3 6" (in-progress, e.g. one set each)
// ---------------------------------------------------------------------------
describe("ScoreCell - Tennis in-progress", () => {
  it('renders away set string "6 4" and home set string "3 6"', () => {
    const row = makeRow({
      sport: "tennis",
      state: "in",
      away_score: "6 4",
      home_score: "3 6",
    });
    const { container } = render(<ScoreCell row={row} />);
    expect(container.textContent).toContain("6 4");
    expect(container.textContent).toContain("3 6");
  });

  it("renders both set strings without mangling spacing", () => {
    const row = makeRow({
      sport: "tennis",
      state: "in",
      away_score: "6 4",
      home_score: "3 6",
    });
    render(<ScoreCell row={row} />);
    // sr-only text also contains the values; just confirm both substrings exist
    const srNode = document.querySelector(".sr-only");
    expect(srNode?.textContent).toMatch(/6 4/);
    expect(srNode?.textContent).toMatch(/3 6/);
  });

  it("marks the winner bold in a completed tennis match (away wins 6-4 6-3)", () => {
    const row = makeRow({
      sport: "tennis",
      state: "post",
      away_score: "6 4 6 3",
      home_score: "4 6 3 6",
      win_away: 1,
      win_home: 0,
    });
    const { container } = render(<ScoreCell row={row} />);
    const boldSpan = container.querySelector("span.font-bold");
    expect(boldSpan).not.toBeNull();
    expect(boldSpan?.textContent).toContain("6");
  });
});

// ---------------------------------------------------------------------------
// Null / null: no scores available
// ---------------------------------------------------------------------------
describe("ScoreCell - null scores", () => {
  it('renders "--" when both scores are null', () => {
    const row = makeRow({
      sport: "mlb",
      state: "pre",
      away_score: null,
      home_score: null,
    });
    render(<ScoreCell row={row} />);
    expect(screen.getByText("--")).toBeTruthy();
  });

  it('has aria-label "Score unavailable" when both scores are null', () => {
    const row = makeRow({
      sport: "soccer",
      state: "pre",
      away_score: null,
      home_score: null,
    });
    render(<ScoreCell row={row} />);
    expect(
      screen.getByLabelText("Score unavailable")
    ).toBeTruthy();
  });
});

// ---------------------------------------------------------------------------
// Soccer: away 1, home 0 (in-game)
// ---------------------------------------------------------------------------
describe("ScoreCell - Soccer in-game", () => {
  it("renders away and home scores for a soccer match", () => {
    const row = makeRow({
      sport: "soccer",
      league: "eng.1",
      state: "in",
      away_score: 1,
      home_score: 0,
    });
    const { container } = render(<ScoreCell row={row} />);
    expect(container.textContent).toContain("1");
    expect(container.textContent).toContain("0");
  });
});
