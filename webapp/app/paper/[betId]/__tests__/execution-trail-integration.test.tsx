// execution-trail-integration.test.tsx -- W6 acceptance: real ExecutionTrail render.
//
// Per-file vitest test (NEVER run the full suite -- freezes the box).
// Run: cd /c/Users/neelj/nba-ai-system/webapp && npx vitest run "app/paper/[betId]/__tests__/execution-trail-integration" --reporter=dot
//
// Uses the REAL ExecutionTrail component + paperRowToExecutionTrail adapter
// (no mocks of these modules -- the fixture row drives the adapter and we
// assert on the real rendered DOM).
//
// W6 acceptance criteria covered here:
//   - taken_book visible as book name in the line-shopping table
//   - taken_decimal visible as decimal odds (no $ column)
//   - model_prob visible as a percentage in the decision trail
//   - stake_units visible as a units string (no $ sign)
//   - clv_status reads INSUFFICIENT_DATA for ungraded (clv_unavailable=true) rows
//   - real-money DENY banner always present
//   - unknown betId path: empty bookLines -> honest unavailable (no fabricated fill)
//   - no '$' amount anywhere in rendered output
//
// HONESTY RAILS:
//   - UNITS only. No $ P&L / roi / pnl anywhere.
//   - CLV must be INSUFFICIENT_DATA for ungraded rows -- never fabricated.
//   - Empty/unknown row -> honest 'No book lines available', never a filled quote.
//   - Real-money DENY banner is always rendered.

import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { ExecutionTrail } from "@/components/execution/ExecutionTrail";
import { paperRowToExecutionTrail } from "@/components/paper_pm/paperTrailAdapter";
import type { PaperTrailRow } from "@/lib/types";

// ---------------------------------------------------------------------------
// Fixture row -- mirrors the bet_id in the page tests (sport|game_id|...).
// clv_unavailable=true + clv_status='no_close' -> adapter maps to INSUFFICIENT_DATA.
// ---------------------------------------------------------------------------

const FIXTURE_ROW: PaperTrailRow = {
  game_id: "0022300001",
  matchup: "LAL @ BOS",
  sport: "nba",
  side: "home",
  market_type: "moneyline",
  taken_book: "kalshi",
  taken_decimal: 2.1,
  model_prob: 0.55,
  model_ev: 0.155,
  tier: "A",
  stake_units: 0.25,
  status: "open",
  graded: false,
  outcome: null,
  clv_pct: null,
  beat_close: null,
  clv_is_proxy: false,
  clv_status: "no_close",
  clv_unavailable: true,
  clv_note: null,
  executed: false,
  ts: "2026-06-19T18:00:00Z",
  settled_at: null,
  line: null,
};

// ---------------------------------------------------------------------------
// W6 acceptance: real ExecutionTrail render via paperRowToExecutionTrail
// ---------------------------------------------------------------------------

describe("W6 acceptance -- real ExecutionTrail + paperRowToExecutionTrail", () => {
  it("renders taken_book as the book name in the line-shopping table", () => {
    const props = paperRowToExecutionTrail(FIXTURE_ROW);
    render(<ExecutionTrail {...props} />);
    // taken_book='kalshi' must appear as a cell in the book column
    expect(screen.getByText("kalshi")).toBeTruthy();
  });

  it("renders taken_decimal as decimal odds (no $ column)", () => {
    const props = paperRowToExecutionTrail(FIXTURE_ROW);
    render(<ExecutionTrail {...props} />);
    // taken_decimal=2.1 -> fmt2 -> '2.10'
    expect(screen.getByText("2.10")).toBeTruthy();
  });

  it("renders model_prob as a percentage in the decision trail", () => {
    const props = paperRowToExecutionTrail(FIXTURE_ROW);
    render(<ExecutionTrail {...props} />);
    // model_prob=0.55 -> fmtPct -> '55.0%'
    const probEl = screen.getByTestId("model-prob");
    expect(probEl.textContent).toContain("55.0%");
  });

  it("renders stake_units as a units string (no $ sign)", () => {
    const props = paperRowToExecutionTrail(FIXTURE_ROW);
    render(<ExecutionTrail {...props} />);
    const stake = screen.getByTestId("stake-units");
    // stake_units=0.25 -> fmtUnits -> '0.25u'
    expect(stake.textContent).toContain("0.25u");
    expect(stake.textContent).not.toContain("$");
  });

  it("renders tier badge for tier='A'", () => {
    const props = paperRowToExecutionTrail(FIXTURE_ROW);
    render(<ExecutionTrail {...props} />);
    const tierEl = screen.getByTestId("tier-badge");
    expect(tierEl.textContent).toContain("A");
  });

  it("clv_status reads INSUFFICIENT_DATA for ungraded row (clv_unavailable=true)", () => {
    // FIXTURE_ROW has clv_unavailable=true -> adapter maps clvStatus to INSUFFICIENT_DATA
    const props = paperRowToExecutionTrail(FIXTURE_ROW);
    render(<ExecutionTrail {...props} />);
    const clv = screen.getByTestId("clv-status");
    expect(clv.textContent).toContain("INSUFFICIENT_DATA");
  });

  it("clv_status reads INSUFFICIENT_DATA for no_close status (ungraded / no closing line)", () => {
    const row: PaperTrailRow = { ...FIXTURE_ROW, clv_status: "no_close", clv_unavailable: false };
    const props = paperRowToExecutionTrail(row);
    render(<ExecutionTrail {...props} />);
    const clv = screen.getByTestId("clv-status");
    expect(clv.textContent).toContain("INSUFFICIENT_DATA");
  });

  it("always renders the real-money DENY banner", () => {
    const props = paperRowToExecutionTrail(FIXTURE_ROW);
    render(<ExecutionTrail {...props} />);
    expect(screen.getByTestId("real-money-deny")).toBeTruthy();
    expect(screen.getByText(/REAL-MONEY DENY/i)).toBeTruthy();
  });

  it("DENY banner is also rendered for the empty-bookLines (unknown) path", () => {
    const emptyRow: PaperTrailRow = {
      ...FIXTURE_ROW,
      taken_book: "",
      taken_decimal: null,
      stake_units: null,
    };
    const props = paperRowToExecutionTrail(emptyRow);
    render(<ExecutionTrail {...props} />);
    expect(screen.getByTestId("real-money-deny")).toBeTruthy();
  });

  it("unknown/empty row -> 'No book lines available' (no fabricated fill)", () => {
    // Simulate an unknown betId: no taken_book, no taken_decimal
    const emptyRow: PaperTrailRow = {
      ...FIXTURE_ROW,
      taken_book: "",
      taken_decimal: null,
      stake_units: null,
    };
    const props = paperRowToExecutionTrail(emptyRow);
    render(<ExecutionTrail {...props} />);
    // Honest unavailable state -- never a fabricated book quote
    expect(screen.getByText(/No book lines available/i)).toBeTruthy();
    // No book-lines table when bookLines is empty
    expect(screen.queryByTestId("book-lines-table")).toBeNull();
  });

  it("no dollar-amount string ($<digit>) anywhere in the rendered DOM", () => {
    const props = paperRowToExecutionTrail(FIXTURE_ROW);
    const { container } = render(<ExecutionTrail {...props} />);
    expect(container.textContent ?? "").not.toMatch(/\$\d/);
  });

  it("no dollar-amount in the empty-row / unknown-betId DOM", () => {
    const emptyRow: PaperTrailRow = {
      ...FIXTURE_ROW,
      taken_book: "",
      taken_decimal: null,
      stake_units: null,
    };
    const props = paperRowToExecutionTrail(emptyRow);
    const { container } = render(<ExecutionTrail {...props} />);
    expect(container.textContent ?? "").not.toMatch(/\$\d/);
  });
});
