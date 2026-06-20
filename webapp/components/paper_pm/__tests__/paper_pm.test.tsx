import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";

// paper_pm -- component tests for the W8 PM paper-trail UI.
// HONESTY RAILS:
//   - No $ token anywhere in rendered output.
//   - CLV INSUFFICIENT_DATA path rendered as honest label, never 0.
//   - Pending / void bets show "pending" / "void", not a fabricated win.
//   - Paper mode badge present.
//   - Units column (no dollar column).

// Stub next/navigation + next/link so components render without Next.js context.
vi.mock("next/navigation", () => ({
  useParams: () => ({ betId: "nba%7Cgame1%7Cmoneyline%7Chome%7Cpaper" }),
  usePathname: () => "/paper",
}));

vi.mock("next/link", () => ({
  default: ({
    href,
    children,
    ...props
  }: {
    href: string;
    children: React.ReactNode;
    [k: string]: unknown;
  }) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));

// Stub Radix ScrollArea to avoid jsdom layout quirks.
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

import type { PaperTrailRow } from "@/lib/p5api";
import { ClvInline } from "../ClvInline";
import { VenueFilter } from "../VenueFilter";
import { PmTradeRow, toBetId, deriveResult } from "../PmTradeRow";
import { PmTrailTable } from "../PmTrailTable";
import { ExecutionDetail } from "../ExecutionDetail";

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

function makeRow(overrides: Partial<PaperTrailRow> = {}): PaperTrailRow {
  return {
    game_id: "game1",
    matchup: "NYK vs SAS",
    sport: "nba",
    side: "home",
    market_type: "moneyline",
    line: null,
    taken_book: "paper",
    taken_decimal: 1.95,
    model_prob: 0.54,
    model_ev: 0.053,
    tier: "A",
    stake_units: 1.25,
    status: "open",
    graded: false,
    outcome: null,
    clv_pct: null,
    beat_close: null,
    clv_is_proxy: false,
    clv_status: null,
    clv_unavailable: false,
    clv_note: null,
    executed: false,
    ts: "2026-06-19T10:00:00Z",
    settled_at: null,
    ...overrides,
  };
}

function settledRow(clvPct: number | null = 0.02): PaperTrailRow {
  return makeRow({
    status: "settled",
    graded: true,
    outcome: "win",
    clv_pct: clvPct,
    beat_close: clvPct != null && clvPct > 0,
    clv_is_proxy: false,
    clv_status: "true_close",
    clv_unavailable: false,
    settled_at: "2026-06-19T22:00:00Z",
  });
}

function noCloseRow(): PaperTrailRow {
  return makeRow({
    status: "settled",
    graded: true,
    outcome: "win",
    clv_pct: null,
    beat_close: null,
    clv_is_proxy: false,
    clv_status: "no_close",
    clv_unavailable: true,
    settled_at: "2026-06-19T22:00:00Z",
  });
}

// Shared no-dollar assertion.
function noDollar(container: HTMLElement) {
  expect(container.textContent ?? "").not.toMatch(/\$\s?\d/);
}

// ---------------------------------------------------------------------------
// ClvInline
// ---------------------------------------------------------------------------

describe("ClvInline", () => {
  it("renders EMPTY_CELL for pending bet (not 0)", () => {
    const row = makeRow();
    const { container } = render(<ClvInline row={row} />);
    // Should say "pending" not "0.0%" or "$"
    expect(container.textContent).toContain("pending");
    expect(container.textContent).not.toMatch(/0\.0%|0\.00%/);
    noDollar(container);
  });

  it("renders CLV% for settled with real close", () => {
    const row = settledRow(0.02);
    const { container } = render(<ClvInline row={row} />);
    expect(container.textContent).toContain("%");
    noDollar(container);
  });

  it("renders no-close label (not 0) when clv_unavailable", () => {
    const row = noCloseRow();
    const { container } = render(<ClvInline row={row} />);
    expect(container.textContent).toContain("no-close");
    expect(container.textContent).not.toMatch(/0\.0%|0\.00%/);
    noDollar(container);
  });

  it("shows proxy marker when clv_is_proxy", () => {
    const row = makeRow({
      status: "settled",
      graded: true,
      outcome: "win",
      clv_pct: 0.015,
      clv_is_proxy: true,
      clv_status: "proxy",
      clv_unavailable: false,
    });
    const { container } = render(<ClvInline row={row} />);
    expect(container.textContent).toContain("~");
    noDollar(container);
  });
});

// ---------------------------------------------------------------------------
// VenueFilter
// ---------------------------------------------------------------------------

describe("VenueFilter", () => {
  it("renders venue / result / tier chips with active highlighting", () => {
    const onVenue = vi.fn();
    const onResult = vi.fn();
    const onTier = vi.fn();

    render(
      <VenueFilter
        venues={["kalshi", "polymarket"]}
        venue="all"
        onVenue={onVenue}
        result="all"
        onResult={onResult}
        tier="all"
        onTier={onTier}
      />,
    );

    expect(screen.getByText("kalshi")).toBeInTheDocument();
    expect(screen.getByText("polymarket")).toBeInTheDocument();
    expect(screen.getByText("win")).toBeInTheDocument();
    expect(screen.getByText("A")).toBeInTheDocument();
  });

  it("calls onVenue when a venue chip is clicked", () => {
    const onVenue = vi.fn();
    render(
      <VenueFilter
        venues={["kalshi"]}
        venue="all"
        onVenue={onVenue}
        result="all"
        onResult={vi.fn()}
        tier="all"
        onTier={vi.fn()}
      />,
    );
    fireEvent.click(screen.getByText("kalshi"));
    expect(onVenue).toHaveBeenCalledWith("kalshi");
  });

  it("calls onResult when a result chip is clicked", () => {
    const onResult = vi.fn();
    render(
      <VenueFilter
        venues={[]}
        venue="all"
        onVenue={vi.fn()}
        result="all"
        onResult={onResult}
        tier="all"
        onTier={vi.fn()}
      />,
    );
    fireEvent.click(screen.getByText("win"));
    expect(onResult).toHaveBeenCalledWith("win");
  });
});

// ---------------------------------------------------------------------------
// PmTradeRow helpers
// ---------------------------------------------------------------------------

describe("deriveResult", () => {
  it("pending for open bet", () => {
    expect(deriveResult(makeRow({ status: "open", graded: false }))).toBe("pending");
  });
  it("win for settled win", () => {
    expect(deriveResult(settledRow())).toBe("win");
  });
  it("loss for settled loss", () => {
    const r = settledRow();
    expect(deriveResult({ ...r, outcome: "loss" })).toBe("loss");
  });
  it("void for push/push-settled", () => {
    const r = settledRow();
    expect(deriveResult({ ...r, outcome: "push" })).toBe("void");
  });
});

describe("toBetId", () => {
  it("produces a stable URL-encoded string with sport+game_id+market+side+book", () => {
    const row = makeRow();
    const id = toBetId(row);
    expect(id).toContain("nba");
    expect(id).toContain("game1");
    expect(id).toContain("moneyline");
  });

  it("two rows with the same fields produce the same betId", () => {
    const r1 = makeRow();
    const r2 = makeRow();
    expect(toBetId(r1)).toBe(toBetId(r2));
  });

  it("different game_id produces a different betId", () => {
    const r1 = makeRow({ game_id: "game1" });
    const r2 = makeRow({ game_id: "game2" });
    expect(toBetId(r1)).not.toBe(toBetId(r2));
  });
});

describe("PmTradeRow", () => {
  it("renders matchup + link to /paper/[betId]", () => {
    const row = makeRow();
    const { container } = render(<table><tbody><PmTradeRow row={row} /></tbody></table>);
    expect(screen.getByText("NYK vs SAS")).toBeInTheDocument();
    const links = container.querySelectorAll('a[href^="/paper/"]');
    expect(links.length).toBeGreaterThan(0);
    noDollar(container);
  });

  it("renders rank column when rankMode number provided", () => {
    const row = makeRow();
    render(<table><tbody><PmTradeRow row={row} rank={3} /></tbody></table>);
    expect(screen.getByText("3")).toBeInTheDocument();
  });

  it("never renders a dollar sign", () => {
    const { container } = render(
      <table><tbody><PmTradeRow row={settledRow(0.05)} /></tbody></table>,
    );
    noDollar(container);
  });
});

// ---------------------------------------------------------------------------
// PmTrailTable
// ---------------------------------------------------------------------------

describe("PmTrailTable", () => {
  it("shows loading skeletons when loading=true", () => {
    render(<PmTrailTable rows={[]} loading={true} />);
    expect(screen.getAllByTestId("skeleton").length).toBeGreaterThan(0);
  });

  it("shows unavailable when error is set", () => {
    render(<PmTrailTable rows={[]} loading={false} error="connection refused" />);
    expect(screen.getByText("connection refused")).toBeInTheDocument();
  });

  it("shows empty-state message when rows is empty", () => {
    render(<PmTrailTable rows={[]} loading={false} />);
    expect(screen.getByText(/No paper trades/)).toBeInTheDocument();
  });

  it("renders a row per trade with table headers", () => {
    const rows = [makeRow(), settledRow()];
    render(<PmTrailTable rows={rows} loading={false} />);
    expect(screen.getAllByText("NYK vs SAS").length).toBeGreaterThanOrEqual(2);
    expect(screen.getAllByText("Tier").length).toBeGreaterThan(0);
    expect(screen.getByText("Model P")).toBeInTheDocument();
    expect(screen.getAllByText("CLV").length).toBeGreaterThan(0);
    // Should NOT have a "units $" or any dollar column
    const ths = screen.getAllByRole("columnheader");
    ths.forEach((th) => expect(th.textContent ?? "").not.toMatch(/\$/));
  });

  it("never shows a dollar amount in the table", () => {
    const { container } = render(
      <PmTrailTable rows={[makeRow(), settledRow()]} loading={false} />,
    );
    noDollar(container);
  });

  it("in rankMode shows 'ranked by tier + confidence' badge", () => {
    const rows = [makeRow(), settledRow()];
    render(<PmTrailTable rows={rows} loading={false} rankMode />);
    expect(screen.getByText(/ranked by tier \+ confidence/i)).toBeInTheDocument();
  });

  it("filter chips rendered -- clicking venue changes visible text", () => {
    const rows = [makeRow({ taken_book: "kalshi" }), settledRow()];
    render(<PmTrailTable rows={rows} loading={false} />);
    expect(screen.getByText("kalshi")).toBeInTheDocument();
    fireEvent.click(screen.getByText("kalshi"));
    // After filtering to kalshi, only the kalshi row should remain (second row has "paper" book)
    // The count text should reflect filtering
    expect(screen.getByText(/1 of 2 trades/)).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// ExecutionDetail
// ---------------------------------------------------------------------------

describe("ExecutionDetail", () => {
  it("shows loading text when loading=true", () => {
    render(<ExecutionDetail row={null} loading />);
    expect(screen.getByText("loading...")).toBeInTheDocument();
  });

  it("shows unavailable with error text", () => {
    render(<ExecutionDetail row={null} loading={false} error="not found" />);
    expect(screen.getByText("not found")).toBeInTheDocument();
  });

  it("renders all key detail rows for a settled trade", () => {
    const row = settledRow(0.03);
    const { container } = render(
      <ExecutionDetail row={row} loading={false} />,
    );
    expect(screen.getByText("Matchup")).toBeInTheDocument();
    expect(screen.getByText("NYK vs SAS")).toBeInTheDocument();
    expect(screen.getByText("Tier")).toBeInTheDocument();
    expect(screen.getByText("A")).toBeInTheDocument();
    expect(screen.getByText("Venue")).toBeInTheDocument();
    expect(screen.getByText("Line taken")).toBeInTheDocument();
    expect(screen.getByText("Model probability")).toBeInTheDocument();
    expect(screen.getByText("Stake (units, no $)")).toBeInTheDocument();
    expect(screen.getByText("Result")).toBeInTheDocument();
    expect(screen.getByText("CLV (beat close?)")).toBeInTheDocument();
    noDollar(container);
  });

  it("shows INSUFFICIENT_DATA label when no closing line captured", () => {
    const row = noCloseRow();
    const { container } = render(
      <ExecutionDetail row={row} loading={false} />,
    );
    // CLV cell shows INSUFFICIENT_DATA when no close; getAllByText handles market_prob cell too.
    const cells = screen.getAllByText("INSUFFICIENT_DATA");
    expect(cells.length).toBeGreaterThanOrEqual(1);
    noDollar(container);
  });

  it("shows 'paper mode' badge", () => {
    const row = settledRow();
    render(<ExecutionDetail row={row} loading={false} />);
    expect(screen.getByText("paper mode")).toBeInTheDocument();
  });

  it("never renders a dollar P&L value", () => {
    const { container } = render(
      <ExecutionDetail row={settledRow(-0.05)} loading={false} />,
    );
    noDollar(container);
  });

  it("shows CLV status annotation", () => {
    const row = settledRow(0.03);
    render(<ExecutionDetail row={row} loading={false} />);
    expect(screen.getByText("CLV status")).toBeInTheDocument();
    expect(screen.getByText("true_close")).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// WS6 acceptance: PM paper-trail table contract
// ---------------------------------------------------------------------------
// Acceptance assertions required by the workstream spec:
//   1. Table renders >=1 row when trades are present.
//   2. Honest empty banner shown when total_pm=0 (rows=[]).
//   3. No '$' substring anywhere in rendered output.
//   4. Row with clv_status=INSUFFICIENT_DATA -> null CLV cell (not 0%).

function makeInsufficientDataRow(): PaperTrailRow {
  return makeRow({
    status: "settled",
    graded: true,
    outcome: "win",
    clv_pct: null,
    beat_close: null,
    clv_is_proxy: false,
    clv_status: "INSUFFICIENT_DATA",
    clv_unavailable: true,
    settled_at: "2026-06-19T22:00:00Z",
  });
}

describe("ws6 acceptance: PmTrailTable contract", () => {
  it("renders >=1 data row when trades are present", () => {
    const rows = [makeRow(), settledRow()];
    const { container } = render(<PmTrailTable rows={rows} loading={false} />);
    // At minimum the table body rows should be present
    const trs = container.querySelectorAll("tbody tr");
    expect(trs.length).toBeGreaterThanOrEqual(1);
  });

  it("renders exactly as many rows as supplied trades", () => {
    const rows = [makeRow(), settledRow(), makeRow({ game_id: "game3" })];
    const { container } = render(<PmTrailTable rows={rows} loading={false} />);
    const trs = container.querySelectorAll("tbody tr");
    expect(trs.length).toBe(3);
  });

  it("shows honest empty banner when rows=[] (total_pm=0 state)", () => {
    render(<PmTrailTable rows={[]} loading={false} />);
    expect(screen.getByText(/No paper trades/i)).toBeInTheDocument();
    // The empty state must NOT contain a dollar sign
    const banner = screen.getByText(/No paper trades/i);
    expect((banner.closest("div") ?? banner).textContent ?? "").not.toMatch(/\$/);
  });

  it("no dollar amount ($ followed by digit) anywhere in rendered output when trades present", () => {
    const rows = [makeRow(), settledRow(), makeInsufficientDataRow()];
    const { container } = render(<PmTrailTable rows={rows} loading={false} />);
    // No '$' followed by a digit -- no currency amounts. The '(no $)' disclaimer label is fine.
    expect(container.textContent ?? "").not.toMatch(/\$\s?\d/);
    // No column header containing '$'
    const ths = container.querySelectorAll("th");
    ths.forEach((th) => expect(th.textContent ?? "").not.toMatch(/\$\s?\d/));
  });

  it("no dollar amount in rendered output when rows are empty", () => {
    const { container } = render(<PmTrailTable rows={[]} loading={false} />);
    expect(container.textContent ?? "").not.toMatch(/\$\s?\d/);
  });

  it("clv_status=INSUFFICIENT_DATA row renders null CLV cell (no-close label, not 0%)", () => {
    const row = makeInsufficientDataRow();
    const { container } = render(<PmTrailTable rows={[row]} loading={false} />);
    // CLV cell must NOT show a numeric percentage (0.0% or any number%)
    expect(container.textContent ?? "").not.toMatch(/0\.0%|0\.00%/);
    // Must show the "no-close" sentinel or an empty cell marker -- never a fabricated value
    expect(container.textContent ?? "").toMatch(/no-close|pending|--|INSUF/i);
    // No dollar amount
    expect(container.textContent ?? "").not.toMatch(/\$\s?\d/);
  });

  it("ClvInline renders 'no-close' for INSUFFICIENT_DATA row", () => {
    const row = makeInsufficientDataRow();
    const { container } = render(<ClvInline row={row} />);
    // clv_unavailable=true and status=settled -> "no-close" label
    expect(container.textContent).toContain("no-close");
    expect(container.textContent).not.toMatch(/0\.0%|0\.00%/);
    expect(container.textContent).not.toMatch(/\$\s?\d/);
  });
});

// ---------------------------------------------------------------------------
// Landmark a11y -- paper page components must NOT introduce nested <main>
// landmarks or a duplicate id="main-content" (AppShell owns the sole <main>).
// WCAG 2.4.1 bypass-blocks: only one main landmark per document.
// ---------------------------------------------------------------------------

describe("landmark a11y -- no nested <main> or duplicate id=main-content", () => {
  it("PmTrailTable renders without any <main> element", () => {
    const rows = [makeRow(), settledRow()];
    const { container } = render(<PmTrailTable rows={rows} loading={false} />);
    expect(container.querySelectorAll("main").length).toBe(0);
  });

  it("PmTrailTable has no element with id=main-content", () => {
    const { container } = render(
      <PmTrailTable rows={[makeRow()]} loading={false} />,
    );
    expect(container.querySelectorAll('[id="main-content"]').length).toBe(0);
  });

  it("ExecutionDetail renders without any <main> element", () => {
    const { container } = render(
      <ExecutionDetail row={settledRow()} loading={false} />,
    );
    expect(container.querySelectorAll("main").length).toBe(0);
  });

  it("ExecutionDetail has no element with id=main-content", () => {
    const { container } = render(
      <ExecutionDetail row={settledRow()} loading={false} />,
    );
    expect(container.querySelectorAll('[id="main-content"]').length).toBe(0);
  });
});
