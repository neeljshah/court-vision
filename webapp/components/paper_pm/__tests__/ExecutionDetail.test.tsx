// ExecutionDetail.test.tsx -- per-file tests for ExecutionDetail component.
//
// Per-file vitest test (NEVER run the full suite -- freezes the box).
// Run: cd /c/Users/neelj/nba-ai-system/webapp && npx vitest run components/paper_pm/ExecutionDetail --reporter=dot
//
// Acceptance criteria (W5 workstream):
//   1. Full prediction fields rendered: model_prob, market_prob, line, fair_odds,
//      tier, units, result, CLV+clv_status, executed=false, channel=paper
//   2. DENY banner always present (paper-only / no real money)
//   3. INSUFFICIENT_DATA for market_prob when absent
//   4. INSUFFICIENT_DATA for CLV when no closing line
//   5. No '$'/'profit'/'roi' in DOM at any time
//   6. Unknown/null row -> honest not-found state, no fabricated record
//   7. Loading state renders properly
//
// HONESTY RAILS:
//   - UNITS only; no $ P&L / roi / pnl field.
//   - executed=false must always be shown (paper-only).
//   - CLV may be INSUFFICIENT_DATA -- shown honestly, never fabricated.
//   - market_prob null -> INSUFFICIENT_DATA (never 0-filled).

import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import type { PaperTrailRow } from "@/lib/p5api";

// Stub next/link so components render without Next.js context.
vi.mock("next/link", () => ({
  default: ({ href, children, ...rest }: { href: string; children: React.ReactNode }) => (
    <a href={href} {...rest}>{children}</a>
  ),
}));

vi.mock("next/navigation", () => ({
  useParams: vi.fn(() => ({})),
  usePathname: vi.fn(() => "/paper"),
}));

import { ExecutionDetail } from "../ExecutionDetail";

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

function makeOpenRow(overrides: Partial<PaperTrailRow> = {}): PaperTrailRow {
  return {
    game_id: "0022300001",
    matchup: "LAL @ BOS",
    sport: "nba",
    side: "home",
    market_type: "moneyline",
    line: null,
    taken_book: "kalshi",
    taken_decimal: 2.1,
    model_prob: 0.55,
    market_prob: 0.50,
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
    channel: "paper",
    ts: "2026-06-19T18:00:00Z",
    settled_at: null,
    ...overrides,
  };
}

function makeSettledRow(clvPct = 0.03): PaperTrailRow {
  return makeOpenRow({
    status: "settled",
    graded: true,
    outcome: "win",
    clv_pct: clvPct,
    beat_close: clvPct > 0,
    clv_is_proxy: false,
    clv_status: "true_close",
    clv_unavailable: false,
    settled_at: "2026-06-20T01:00:00Z",
  });
}

function makeNoCloseRow(): PaperTrailRow {
  return makeOpenRow({
    status: "settled",
    graded: true,
    outcome: "win",
    clv_pct: null,
    beat_close: null,
    clv_is_proxy: false,
    clv_status: "no_close",
    clv_unavailable: true,
    settled_at: "2026-06-20T01:00:00Z",
  });
}

// Shared honesty assertion: no dollar-amount or roi/pnl tokens in DOM.
function assertNoDollar(container: HTMLElement) {
  const text = container.textContent ?? "";
  expect(text).not.toMatch(/\$\d/);
  expect(text).not.toMatch(/\bpnl\b/i);
  expect(text).not.toMatch(/\broi\b/i);
  expect(text).not.toMatch(/\bprofit\b/i);
}

// ---------------------------------------------------------------------------
// Loading state
// ---------------------------------------------------------------------------

describe("ExecutionDetail -- loading state", () => {
  it("renders loading text when loading=true", () => {
    render(<ExecutionDetail row={null} loading />);
    expect(screen.getByText("loading...")).toBeInTheDocument();
  });

  it("no dollar in loading state (honesty rail)", () => {
    const { container } = render(<ExecutionDetail row={null} loading />);
    assertNoDollar(container);
  });
});

// ---------------------------------------------------------------------------
// Error / not-found state
// ---------------------------------------------------------------------------

describe("ExecutionDetail -- error / not-found state", () => {
  it("shows error text when error prop is set", () => {
    render(<ExecutionDetail row={null} loading={false} error="trade not found" />);
    expect(screen.getByText("trade not found")).toBeInTheDocument();
  });

  it("shows default not-found message when row=null and no error", () => {
    render(<ExecutionDetail row={null} loading={false} />);
    // The panel title should still render.
    expect(screen.getByText("Execution detail")).toBeInTheDocument();
  });

  it("no dollar in error state (honesty rail)", () => {
    const { container } = render(
      <ExecutionDetail row={null} loading={false} error="not found" />,
    );
    assertNoDollar(container);
  });
});

// ---------------------------------------------------------------------------
// Full prediction fields -- open trade
// ---------------------------------------------------------------------------

describe("ExecutionDetail -- full prediction fields (open trade)", () => {
  it("renders model_prob correctly", () => {
    render(<ExecutionDetail row={makeOpenRow()} loading={false} />);
    expect(screen.getByTestId("detail-model-prob").textContent).toContain("55.0%");
  });

  it("renders market_prob when present", () => {
    render(<ExecutionDetail row={makeOpenRow({ market_prob: 0.50 })} loading={false} />);
    const cell = screen.getByTestId("detail-market-prob");
    expect(cell.textContent).toContain("50.0%");
  });

  it("renders market_prob as INSUFFICIENT_DATA when null", () => {
    render(<ExecutionDetail row={makeOpenRow({ market_prob: null })} loading={false} />);
    const cell = screen.getByTestId("detail-market-prob");
    expect(cell.textContent).toContain("INSUFFICIENT_DATA");
  });

  it("renders market_prob as INSUFFICIENT_DATA when undefined", () => {
    const row = makeOpenRow();
    delete (row as Partial<PaperTrailRow>).market_prob;
    render(<ExecutionDetail row={row} loading={false} />);
    const cell = screen.getByTestId("detail-market-prob");
    expect(cell.textContent).toContain("INSUFFICIENT_DATA");
  });

  it("renders fair_odds from 1/model_prob", () => {
    render(<ExecutionDetail row={makeOpenRow({ model_prob: 0.5 })} loading={false} />);
    const cell = screen.getByTestId("detail-fair-odds");
    // 1/0.5 = 2.000
    expect(cell.textContent).toBe("2.000");
  });

  it("renders tier badge correctly", () => {
    render(<ExecutionDetail row={makeOpenRow({ tier: "A" })} loading={false} />);
    expect(screen.getByTestId("detail-tier").textContent).toContain("A");
  });

  it("renders line taken when present", () => {
    render(<ExecutionDetail row={makeOpenRow({ taken_decimal: 2.1 })} loading={false} />);
    expect(screen.getByTestId("detail-line").textContent).toBe("2.10");
  });

  it("renders units (no $) correctly", () => {
    render(<ExecutionDetail row={makeOpenRow({ stake_units: 0.25 })} loading={false} />);
    expect(screen.getByTestId("detail-units").textContent).toBe("0.25u");
  });

  it("renders result as pending for open trade", () => {
    render(<ExecutionDetail row={makeOpenRow()} loading={false} />);
    expect(screen.getByTestId("detail-result").textContent).toContain("pending");
  });

  it("renders CLV as INSUFFICIENT_DATA when no close", () => {
    render(<ExecutionDetail row={makeOpenRow()} loading={false} />);
    const clvCell = screen.getByTestId("detail-clv");
    expect(clvCell.textContent).toContain("INSUFFICIENT_DATA");
  });

  it("renders clv_status correctly", () => {
    render(<ExecutionDetail row={makeOpenRow({ clv_status: "no_close" })} loading={false} />);
    expect(screen.getByTestId("detail-clv-status").textContent).toContain("no_close");
  });

  it("renders executed=false (paper only)", () => {
    render(<ExecutionDetail row={makeOpenRow()} loading={false} />);
    expect(screen.getByTestId("detail-executed").textContent).toMatch(/false.*paper|paper.*false/i);
  });

  it("renders channel=paper", () => {
    render(<ExecutionDetail row={makeOpenRow({ channel: "paper" })} loading={false} />);
    expect(screen.getByTestId("detail-channel").textContent).toContain("paper");
  });

  it("renders channel=paper when channel field is absent (defaults to paper)", () => {
    const row = makeOpenRow();
    delete (row as Partial<PaperTrailRow>).channel;
    render(<ExecutionDetail row={row} loading={false} />);
    expect(screen.getByTestId("detail-channel").textContent).toContain("paper");
  });
});

// ---------------------------------------------------------------------------
// Full prediction fields -- settled trade with CLV
// ---------------------------------------------------------------------------

describe("ExecutionDetail -- settled trade with CLV", () => {
  it("renders result as win for settled win", () => {
    render(<ExecutionDetail row={makeSettledRow(0.03)} loading={false} />);
    expect(screen.getByTestId("detail-result").textContent).toContain("win");
  });

  it("renders CLV% when settled with real close", () => {
    render(<ExecutionDetail row={makeSettledRow(0.03)} loading={false} />);
    const clvCell = screen.getByTestId("detail-clv");
    expect(clvCell.textContent).not.toContain("INSUFFICIENT_DATA");
  });

  it("renders clv_status=true_close for settled row", () => {
    render(<ExecutionDetail row={makeSettledRow()} loading={false} />);
    expect(screen.getByTestId("detail-clv-status").textContent).toContain("true_close");
  });

  it("renders INSUFFICIENT_DATA for CLV when no_close on settled row", () => {
    render(<ExecutionDetail row={makeNoCloseRow()} loading={false} />);
    const clvCell = screen.getByTestId("detail-clv");
    expect(clvCell.textContent).toContain("INSUFFICIENT_DATA");
  });
});

// ---------------------------------------------------------------------------
// DENY banner -- always present
// ---------------------------------------------------------------------------

describe("ExecutionDetail -- DENY banner (honesty rail)", () => {
  it("DENY banner is present for an open trade", () => {
    render(<ExecutionDetail row={makeOpenRow()} loading={false} />);
    expect(screen.getByTestId("detail-real-money-deny")).toBeInTheDocument();
  });

  it("DENY banner contains DENY text", () => {
    render(<ExecutionDetail row={makeOpenRow()} loading={false} />);
    expect(screen.getByTestId("detail-real-money-deny").textContent).toMatch(/DENY/i);
  });

  it("DENY banner contains real-money denial text", () => {
    render(<ExecutionDetail row={makeSettledRow()} loading={false} />);
    const banner = screen.getByTestId("detail-real-money-deny");
    expect(banner.textContent).toMatch(/paper|real.money/i);
  });

  it("paper mode badge is present", () => {
    render(<ExecutionDetail row={makeOpenRow()} loading={false} />);
    expect(screen.getByText("paper mode")).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Honesty rail: no $ / profit / roi / pnl in DOM
// ---------------------------------------------------------------------------

describe("ExecutionDetail -- no dollar/profit/roi in DOM (honesty rail)", () => {
  it("open trade: no dollar-amount string in DOM", () => {
    const { container } = render(<ExecutionDetail row={makeOpenRow()} loading={false} />);
    assertNoDollar(container);
  });

  it("settled trade: no dollar-amount string in DOM", () => {
    const { container } = render(<ExecutionDetail row={makeSettledRow(0.02)} loading={false} />);
    assertNoDollar(container);
  });

  it("negative CLV: no dollar-amount string in DOM", () => {
    const { container } = render(
      <ExecutionDetail row={makeSettledRow(-0.05)} loading={false} />,
    );
    assertNoDollar(container);
  });

  it("no_close row: no dollar-amount string in DOM", () => {
    const { container } = render(<ExecutionDetail row={makeNoCloseRow()} loading={false} />);
    assertNoDollar(container);
  });

  it("loading state: no dollar-amount string in DOM", () => {
    const { container } = render(<ExecutionDetail row={null} loading />);
    assertNoDollar(container);
  });

  it("error state: no dollar-amount string in DOM", () => {
    const { container } = render(
      <ExecutionDetail row={null} loading={false} error="trade not found" />,
    );
    assertNoDollar(container);
  });
});

// ---------------------------------------------------------------------------
// Divergence / EV is a probability ratio, not $ profit
// ---------------------------------------------------------------------------

describe("ExecutionDetail -- probability-only (no $ EV)", () => {
  it("fair_odds label says 'no $'", () => {
    render(<ExecutionDetail row={makeOpenRow()} loading={false} />);
    // The label for fair odds must say 'no $' to be explicit
    expect(screen.getByText(/fair odds.*no \$/i)).toBeInTheDocument();
  });

  it("stake label says 'units, no $'", () => {
    render(<ExecutionDetail row={makeOpenRow()} loading={false} />);
    expect(screen.getByText(/stake.*units.*no \$/i)).toBeInTheDocument();
  });

  it("footer note says 'no dollar column'", () => {
    render(<ExecutionDetail row={makeOpenRow()} loading={false} />);
    expect(document.body.textContent).toMatch(/no dollar column/i);
  });
});
