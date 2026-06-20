// RecordsRollup.test.tsx -- W1-records-clv-analytics per-file test.
//
// Acceptance assertions per spec:
//   1. rollup groups real rows by sport with result tallies.
//   2. NO '$' string in rendered output.
//   3. renders empty state when rows=[].
//   4. shows win/loss/pending counts correctly.
//   5. model_prob-vs-market_prob divergence stats correct.

import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { RecordsRollup } from "../RecordsRollup";
import type { PaperPredictionRow } from "@/lib/types";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeRow(overrides: Partial<PaperPredictionRow> = {}): PaperPredictionRow {
  return {
    game_id:     "gid-1",
    matchup:     "NYK vs SAS",
    sport:       "nba",
    market_type: "moneyline",
    side:        "home",
    model_prob:  0.60,
    market_prob: 0.55,
    tier:        null,
    outcome:     null,
    clv_pct:     null,
    ts:          "2026-06-01T12:00:00Z",
    ...overrides,
  };
}

// ---------------------------------------------------------------------------
// 1. Groups rows by sport with result tallies
// ---------------------------------------------------------------------------

describe("RecordsRollup -- groups by sport with result tallies", () => {
  it("renders a sport row for each sport present in the data", () => {
    const rows = [
      makeRow({ sport: "nba", outcome: "win" }),
      makeRow({ sport: "nba", outcome: "loss" }),
      makeRow({ sport: "mlb", outcome: "win" }),
    ];
    render(<RecordsRollup rows={rows} />);
    expect(screen.getByTestId("rollup-sport-nba")).toBeInTheDocument();
    expect(screen.getByTestId("rollup-sport-mlb")).toBeInTheDocument();
  });

  it("does NOT render a sport row for a sport not present", () => {
    const rows = [makeRow({ sport: "nba", outcome: "win" })];
    render(<RecordsRollup rows={rows} />);
    expect(screen.queryByTestId("rollup-sport-mlb")).not.toBeInTheDocument();
  });

  it("counts wins correctly per sport", () => {
    const rows = [
      makeRow({ sport: "nba", outcome: "win" }),
      makeRow({ sport: "nba", outcome: "win" }),
      makeRow({ sport: "nba", outcome: "loss" }),
    ];
    render(<RecordsRollup rows={rows} />);
    // 2 wins for nba
    const sportRow = screen.getByTestId("rollup-sport-nba");
    expect(sportRow.textContent).toContain("2");   // wins
    expect(sportRow.textContent).toContain("1");   // losses
  });

  it("counts pending (outcome=null) rows correctly", () => {
    const rows = [
      makeRow({ sport: "tennis", outcome: null }),
      makeRow({ sport: "tennis", outcome: null }),
      makeRow({ sport: "tennis", outcome: "win" }),
    ];
    render(<RecordsRollup rows={rows} />);
    const sportRow = screen.getByTestId("rollup-sport-tennis");
    // 2 pending -- the word "2" should appear for pending
    expect(sportRow.textContent).toContain("2");
  });

  it("shows sport labels in uppercase", () => {
    render(<RecordsRollup rows={[makeRow({ sport: "nba" })]} />);
    const label = screen.getByTestId("rollup-sport-label-nba");
    expect(label.textContent?.toUpperCase()).toBe("NBA");
  });

  it("sorts sports by count descending (most rows first)", () => {
    const rows = [
      makeRow({ sport: "mlb" }),
      makeRow({ sport: "nba" }),
      makeRow({ sport: "nba" }),
    ];
    render(<RecordsRollup rows={rows} />);
    const rollup = screen.getByTestId("records-rollup");
    // textContent does NOT apply CSS uppercase; the DOM text is lowercase
    const content = rollup.textContent?.toLowerCase() ?? "";
    const nbaPosn = content.indexOf("nba");
    const mlbPosn = content.indexOf("mlb");
    // nba (2 rows) should appear before mlb (1 row)
    expect(nbaPosn).toBeGreaterThanOrEqual(0);
    expect(mlbPosn).toBeGreaterThan(nbaPosn);
  });
});

// ---------------------------------------------------------------------------
// 2. No $ token
// ---------------------------------------------------------------------------

describe("RecordsRollup -- no $ token", () => {
  it("renders no $ token with real rows", () => {
    const rows = [
      makeRow({ sport: "nba", outcome: "win" }),
      makeRow({ sport: "mlb", outcome: "loss" }),
    ];
    const { container } = render(<RecordsRollup rows={rows} />);
    expect(/\$\s*\d/.test(container.textContent ?? "")).toBe(false);
  });

  it("renders no $ token when rows=[]", () => {
    const { container } = render(<RecordsRollup rows={[]} />);
    expect(/\$\s*\d/.test(container.textContent ?? "")).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// 3. Empty state
// ---------------------------------------------------------------------------

describe("RecordsRollup -- empty state", () => {
  it("renders an empty state when rows=[]", () => {
    render(<RecordsRollup rows={[]} />);
    expect(screen.getByTestId("records-rollup-empty")).toBeInTheDocument();
  });

  it("renders no sport rows when rows=[]", () => {
    render(<RecordsRollup rows={[]} />);
    expect(screen.queryByTestId(/rollup-sport-\w+/)).not.toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// 4. Multi-sport rollup correctness
// ---------------------------------------------------------------------------

describe("RecordsRollup -- multi-sport counts", () => {
  it("tallies 3 sports independently", () => {
    const rows = [
      makeRow({ sport: "nba",    outcome: "win" }),
      makeRow({ sport: "nba",    outcome: "loss" }),
      makeRow({ sport: "mlb",    outcome: "win" }),
      makeRow({ sport: "soccer", outcome: null }),
      makeRow({ sport: "soccer", outcome: null }),
      makeRow({ sport: "soccer", outcome: "win" }),
    ];
    render(<RecordsRollup rows={rows} />);
    expect(screen.getByTestId("rollup-sport-nba")).toBeInTheDocument();
    expect(screen.getByTestId("rollup-sport-mlb")).toBeInTheDocument();
    expect(screen.getByTestId("rollup-sport-soccer")).toBeInTheDocument();
  });

  it("shows win rate for a sport with settled bets", () => {
    const rows = [
      makeRow({ sport: "nba", outcome: "win"  }),
      makeRow({ sport: "nba", outcome: "win"  }),
      makeRow({ sport: "nba", outcome: "loss" }),
    ];
    render(<RecordsRollup rows={rows} />);
    const sportRow = screen.getByTestId("rollup-sport-nba");
    // 2 wins / 3 settled = 66.7%
    expect(sportRow.textContent).toContain("66.7%");
  });
});

// ---------------------------------------------------------------------------
// 5. Model-vs-market divergence stats
// ---------------------------------------------------------------------------

describe("RecordsRollup -- divergence stats", () => {
  it("shows positive avg divergence when model_prob > market_prob", () => {
    const rows = [
      makeRow({ sport: "nba", model_prob: 0.65, market_prob: 0.55 }),
      makeRow({ sport: "nba", model_prob: 0.60, market_prob: 0.50 }),
    ];
    render(<RecordsRollup rows={rows} />);
    const divCell = screen.getByTestId("rollup-div-nba");
    // mean divergence = (0.10 + 0.10) / 2 = 0.10 = 10.0pp
    expect(divCell.textContent).toContain("+10.0pp");
  });

  it("shows negative avg divergence when model_prob < market_prob", () => {
    const rows = [
      makeRow({ sport: "mlb", model_prob: 0.45, market_prob: 0.55 }),
    ];
    render(<RecordsRollup rows={rows} />);
    const divCell = screen.getByTestId("rollup-div-mlb");
    expect(divCell.textContent).toContain("-10.0pp");
  });

  it("shows -- divergence when both probs are absent", () => {
    const rows = [
      makeRow({ sport: "tennis", model_prob: null, market_prob: null }),
    ];
    render(<RecordsRollup rows={rows} />);
    const divCell = screen.getByTestId("rollup-div-tennis");
    expect(divCell.textContent).toContain("--");
  });
});

// ---------------------------------------------------------------------------
// 6. Loading skeleton
// ---------------------------------------------------------------------------

describe("RecordsRollup -- loading skeleton", () => {
  it("renders records-rollup testid in loading state", () => {
    render(<RecordsRollup rows={[]} loading />);
    expect(screen.getByTestId("records-rollup")).toBeInTheDocument();
  });

  it("renders presentation skeletons when loading", () => {
    render(<RecordsRollup rows={[]} loading />);
    const skeletons = screen.getAllByRole("presentation");
    expect(skeletons.length).toBeGreaterThan(0);
  });
});
