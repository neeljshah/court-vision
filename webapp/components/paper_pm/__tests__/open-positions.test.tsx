// open-positions.test.tsx -- Acceptance tests for OpenPositions component.
//
// Acceptance criteria (W6 workstream):
//   1. OPEN-positions section renders real open rows (status=open) from a
//      mocked trail with units shown as UNITS (no '$').
//   2. Large stake_units (>1.0) render with a quarter-Kelly units clarifier.
//   3. Settled/graded rows are NOT shown in open positions.
//   4. Honest empty state when no open rows exist.
//   5. No '$' character in rendered DOM.

import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { OpenPositions } from "../OpenPositions";
import type { PaperTrailRow } from "@/lib/p5api";

// Stub ScrollArea to avoid jsdom layout quirks.
vi.mock("@/components/ui/scroll-area", () => ({
  ScrollArea: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="scroll-area">{children}</div>
  ),
}));

vi.mock("@/components/ui/skeleton", () => ({
  Skeleton: ({ className }: { className?: string }) => (
    <div data-testid="skeleton" className={className} />
  ),
}));

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

function makeRow(overrides: Partial<PaperTrailRow> = {}): PaperTrailRow {
  return {
    game_id: "g001",
    matchup: "LAL @ BOS",
    sport: "nba",
    side: "home",
    market_type: "moneyline",
    line: null,
    taken_book: "draftkings",
    taken_decimal: 1.95,
    model_prob: 0.55,
    model_ev: 0.07,
    tier: "A",
    stake_units: 0.75,
    status: "open",
    graded: false,
    outcome: null,
    clv_pct: null,
    beat_close: null,
    clv_is_proxy: false,
    clv_status: null,
    clv_unavailable: true,
    clv_note: null,
    executed: false,
    ts: "2026-06-15T20:00:00Z",
    settled_at: null,
    ...overrides,
  };
}

function makeSettledRow(overrides: Partial<PaperTrailRow> = {}): PaperTrailRow {
  return makeRow({
    status: "settled",
    graded: true,
    outcome: "win",
    clv_pct: 0.025,
    beat_close: true,
    clv_status: "true_close",
    clv_unavailable: false,
    settled_at: "2026-06-15T23:30:00Z",
    ...overrides,
  });
}

// Three open rows + two settled rows.
const MIXED_ROWS: PaperTrailRow[] = [
  makeRow({ game_id: "open-1", matchup: "LAL @ BOS", stake_units: 0.5 }),
  makeRow({ game_id: "open-2", matchup: "GSW @ MIA", stake_units: 0.75, sport: "nba" }),
  makeRow({ game_id: "open-mlb", matchup: "NYY @ LAD", sport: "mlb", stake_units: 0.25 }),
  makeSettledRow({ game_id: "settled-1" }),
  makeSettledRow({ game_id: "settled-2", outcome: "loss", clv_pct: -0.01 }),
];

// One open row with a large (>1.0) stake_units to test quarter-Kelly clarifier.
const LARGE_STAKE_ROW = makeRow({ game_id: "large-1", stake_units: 1.5, matchup: "MIL @ PHI" });
const ROWS_WITH_LARGE_STAKE: PaperTrailRow[] = [
  LARGE_STAKE_ROW,
  makeRow({ game_id: "normal-1", stake_units: 0.5 }),
];

// ---------------------------------------------------------------------------
// Core rendering: open rows from mixed trail
// ---------------------------------------------------------------------------

describe("OpenPositions -- renders open rows from mixed trail", () => {
  it("renders open-positions-panel when open rows exist", () => {
    render(<OpenPositions rows={MIXED_ROWS} loading={false} />);
    expect(screen.getByTestId("open-positions-panel")).toBeInTheDocument();
  });

  it("renders open-positions-table with correct aria-label", () => {
    render(<OpenPositions rows={MIXED_ROWS} loading={false} />);
    expect(screen.getByRole("grid", { name: "Open paper positions" })).toBeInTheDocument();
  });

  it("renders exactly 3 open rows (not the 2 settled rows)", () => {
    render(<OpenPositions rows={MIXED_ROWS} loading={false} />);
    const rows = screen.getAllByTestId("open-position-row");
    expect(rows).toHaveLength(3);
  });

  it("shows matchup text for open rows", () => {
    render(<OpenPositions rows={MIXED_ROWS} loading={false} />);
    expect(screen.getByText("LAL @ BOS")).toBeInTheDocument();
    expect(screen.getByText("GSW @ MIA")).toBeInTheDocument();
    expect(screen.getByText("NYY @ LAD")).toBeInTheDocument();
  });

  it("shows 'pending' status for open rows", () => {
    render(<OpenPositions rows={MIXED_ROWS} loading={false} />);
    const pendingCells = screen.getAllByText("pending");
    expect(pendingCells.length).toBeGreaterThanOrEqual(3);
  });

  it("settled rows are NOT rendered in open positions", () => {
    render(<OpenPositions rows={MIXED_ROWS} loading={false} />);
    // settled-1 and settled-2 should not appear in open positions
    const rows = screen.getAllByTestId("open-position-row");
    expect(rows).toHaveLength(3);
  });
});

// ---------------------------------------------------------------------------
// Units display: UNITS only, no '$'
// ---------------------------------------------------------------------------

describe("OpenPositions -- units shown as UNITS (no '$')", () => {
  it("renders stake_units as '0.50u' format, not a dollar amount", () => {
    render(<OpenPositions rows={[makeRow({ stake_units: 0.5 })]} loading={false} />);
    const unitCells = screen.getAllByTestId("open-stake-units");
    expect(unitCells[0].textContent).toBe("0.50u");
  });

  it("renders stake_units 0.75 as '0.75u'", () => {
    render(<OpenPositions rows={[makeRow({ stake_units: 0.75 })]} loading={false} />);
    const unitCells = screen.getAllByTestId("open-stake-units");
    expect(unitCells[0].textContent).toBe("0.75u");
  });

  it("no dollar-amount string ($N) in rendered DOM", () => {
    const { container } = render(<OpenPositions rows={MIXED_ROWS} loading={false} />);
    expect(container.textContent ?? "").not.toMatch(/\$\d/);
  });

  it("no 'pnl' or 'p&l' token in rendered DOM", () => {
    const { container } = render(<OpenPositions rows={MIXED_ROWS} loading={false} />);
    expect((container.textContent ?? "").toLowerCase()).not.toMatch(/p&l|pnl/);
  });

  it("shows 'UNITS' clarifier text in the panel", () => {
    render(<OpenPositions rows={MIXED_ROWS} loading={false} />);
    expect(screen.getByText("UNITS")).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Large stake_units (>1.0): quarter-Kelly clarifier
// ---------------------------------------------------------------------------

describe("OpenPositions -- large stake_units quarter-Kelly clarifier", () => {
  it("renders 'qK' clarifier for a row with stake_units > 1.0", () => {
    render(<OpenPositions rows={ROWS_WITH_LARGE_STAKE} loading={false} />);
    const clarifiers = screen.getAllByTestId("quarter-kelly-clarifier");
    expect(clarifiers.length).toBeGreaterThanOrEqual(1);
  });

  it("does NOT render 'qK' clarifier for rows with stake_units <= 1.0", () => {
    render(<OpenPositions rows={[makeRow({ stake_units: 0.5 })]} loading={false} />);
    expect(screen.queryByTestId("quarter-kelly-clarifier")).toBeNull();
  });

  it("large stake note text explains quarter-Kelly", () => {
    render(<OpenPositions rows={ROWS_WITH_LARGE_STAKE} loading={false} />);
    expect(screen.getByTestId("large-stake-unit-note").textContent).toMatch(/qK/);
    expect(screen.getByTestId("large-stake-unit-note").textContent).toMatch(/1\.0u/);
  });

  it("renders 1.50u correctly for stake_units=1.5", () => {
    render(<OpenPositions rows={[LARGE_STAKE_ROW]} loading={false} />);
    const unitCells = screen.getAllByTestId("open-stake-units");
    expect(unitCells[0].textContent).toBe("1.50u");
  });

  it("qK clarifier is NOT shown when stake_units is exactly 1.0", () => {
    render(<OpenPositions rows={[makeRow({ stake_units: 1.0 })]} loading={false} />);
    expect(screen.queryByTestId("quarter-kelly-clarifier")).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// Honest empty state: no open rows
// ---------------------------------------------------------------------------

describe("OpenPositions -- honest empty state", () => {
  it("shows open-positions-empty when rows is empty", () => {
    render(<OpenPositions rows={[]} loading={false} />);
    expect(screen.getByTestId("open-positions-empty")).toBeInTheDocument();
  });

  it("empty state says 'No open positions right now'", () => {
    render(<OpenPositions rows={[]} loading={false} />);
    expect(screen.getByTestId("open-positions-empty").textContent).toMatch(
      /no open positions right now/i,
    );
  });

  it("empty state includes 'No edge is claimed'", () => {
    render(<OpenPositions rows={[]} loading={false} />);
    expect(screen.getByTestId("open-positions-empty").textContent).toMatch(/no edge is claimed/i);
  });

  it("empty state does NOT carry red/danger styling", () => {
    render(<OpenPositions rows={[]} loading={false} />);
    const el = screen.getByTestId("open-positions-empty");
    expect(el.className).not.toMatch(/text-red/);
    expect(el.className).not.toMatch(/text-danger/);
    expect(el.className).not.toMatch(/text-destructive/);
  });

  it("shows empty state when all rows are settled", () => {
    const allSettled = [makeSettledRow({ game_id: "s1" }), makeSettledRow({ game_id: "s2" })];
    render(<OpenPositions rows={allSettled} loading={false} />);
    expect(screen.getByTestId("open-positions-empty")).toBeInTheDocument();
  });

  it("does NOT show table when empty state is active", () => {
    render(<OpenPositions rows={[]} loading={false} />);
    expect(screen.queryByTestId("open-positions-table")).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// Loading state
// ---------------------------------------------------------------------------

describe("OpenPositions -- loading state", () => {
  it("shows loading skeleton when loading=true and rows=[]", () => {
    render(<OpenPositions rows={[]} loading={true} />);
    expect(screen.getByTestId("open-positions-loading")).toBeInTheDocument();
    expect(screen.getByRole("generic", { name: "Loading open positions" })).toBeInTheDocument();
  });

  it("does NOT show empty state while loading with no rows", () => {
    render(<OpenPositions rows={[]} loading={true} />);
    expect(screen.queryByTestId("open-positions-empty")).toBeNull();
  });

  it("renders table when loading=true but stale rows are available", () => {
    render(<OpenPositions rows={MIXED_ROWS} loading={true} />);
    expect(screen.getByTestId("open-positions-table")).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Honesty: no dollar sign across all states
// ---------------------------------------------------------------------------

describe("OpenPositions -- honesty rail across all states", () => {
  it("loading state: no dollar-amount in rendered text", () => {
    const { container } = render(<OpenPositions rows={[]} loading={true} />);
    expect(container.textContent ?? "").not.toMatch(/\$\d/);
  });

  it("empty state: no dollar-amount in rendered text", () => {
    const { container } = render(<OpenPositions rows={[]} loading={false} />);
    expect(container.textContent ?? "").not.toMatch(/\$\d/);
  });

  it("populated state: no dollar-amount in rendered text", () => {
    const { container } = render(<OpenPositions rows={MIXED_ROWS} loading={false} />);
    expect(container.textContent ?? "").not.toMatch(/\$\d/);
  });

  it("large stake state: no dollar-amount in rendered text", () => {
    const { container } = render(<OpenPositions rows={ROWS_WITH_LARGE_STAKE} loading={false} />);
    expect(container.textContent ?? "").not.toMatch(/\$\d/);
  });
});
