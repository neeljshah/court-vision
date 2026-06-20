// PaperTrailSettled.test.tsx -- Acceptance tests for PaperTrailSettled component.
//
// Acceptance criteria (W2 workstream):
//   1. With 54 settled rows mocked, renders a populated settled-records table.
//   2. Win/loss/push tally tiles show correct counts.
//   3. Per-row result label is "win", "loss", or "push" for settled rows.
//   4. CLV/clv_status column shows correct values or "no-close"/"pending".
//   5. PM-empty block only appears in /paper page -- NOT this component.
//   6. No $/dollar/pnl token appears in the rendered DOM (honesty rail).
//   7. No-settled honest-empty state shows correct message.
//   8. Open positions section shows pending bets separately.

import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { PaperTrailSettled, deriveSettledTally } from "../PaperTrailSettled";
import type { PaperTrailRow } from "@/lib/p5api";

// Mock next/link -> plain <a> for jsdom rendering
vi.mock("next/link", () => ({
  default: ({ href, children, ...rest }: { href: string; children: React.ReactNode }) => (
    <a href={href} {...rest}>{children}</a>
  ),
}));

// ---------------------------------------------------------------------------
// Fixtures: 54-row settled book (representative subset)
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
    stake_units: 1.0,
    status: "settled",
    graded: true,
    outcome: "win",
    clv_pct: 0.025,
    beat_close: true,
    clv_is_proxy: false,
    clv_status: "true_close",
    clv_unavailable: false,
    clv_note: null,
    executed: false,
    ts: "2026-06-15T20:00:00Z",
    settled_at: "2026-06-15T23:30:00Z",
    ...overrides,
  };
}

// Build 54 settled rows with mix of win/loss/push
function make54Rows(): PaperTrailRow[] {
  const rows: PaperTrailRow[] = [];
  for (let i = 0; i < 24; i++) {
    rows.push(makeRow({ game_id: `g-win-${i}`, outcome: "win" }));
  }
  for (let i = 0; i < 20; i++) {
    rows.push(makeRow({
      game_id: `g-loss-${i}`,
      outcome: "loss",
      clv_pct: -0.015,
      beat_close: false,
    }));
  }
  for (let i = 0; i < 8; i++) {
    rows.push(makeRow({
      game_id: `g-push-${i}`,
      outcome: "push",
      clv_pct: null,
      clv_unavailable: true,
      clv_status: "no_close",
    }));
  }
  for (let i = 0; i < 2; i++) {
    rows.push(makeRow({
      game_id: `g-open-${i}`,
      status: "open",
      graded: false,
      outcome: null,
      clv_pct: null,
      clv_unavailable: true,
      clv_status: null,
      settled_at: null,
    }));
  }
  return rows;
}

const ROWS_54 = make54Rows();
const SETTLED_54 = ROWS_54.filter((r) => r.graded && r.status !== "open");

// ---------------------------------------------------------------------------
// deriveSettledTally unit tests
// ---------------------------------------------------------------------------

describe("deriveSettledTally", () => {
  it("counts 52 settled rows in the 54-row fixture", () => {
    const t = deriveSettledTally(ROWS_54);
    expect(t.nSettled).toBe(52);
  });

  it("counts 2 open rows", () => {
    const t = deriveSettledTally(ROWS_54);
    expect(t.nOpen).toBe(2);
  });

  it("counts wins correctly (24)", () => {
    const t = deriveSettledTally(ROWS_54);
    expect(t.nWin).toBe(24);
  });

  it("counts losses correctly (20)", () => {
    const t = deriveSettledTally(ROWS_54);
    expect(t.nLoss).toBe(20);
  });

  it("counts pushes correctly (8)", () => {
    const t = deriveSettledTally(ROWS_54);
    expect(t.nPush).toBe(8);
  });

  it("empty row list yields all-zero tally", () => {
    const t = deriveSettledTally([]);
    expect(t.nSettled).toBe(0);
    expect(t.nOpen).toBe(0);
    expect(t.nWin).toBe(0);
    expect(t.nLoss).toBe(0);
    expect(t.nPush).toBe(0);
  });
});

// ---------------------------------------------------------------------------
// Rendering: populated settled table
// ---------------------------------------------------------------------------

describe("PaperTrailSettled -- populated settled table", () => {
  it("renders settled-records-table when settled rows exist", () => {
    render(<PaperTrailSettled rows={ROWS_54} loading={false} />);
    expect(screen.getByTestId("settled-records-table")).toBeInTheDocument();
  });

  it("does NOT render no-settled-records when rows exist", () => {
    render(<PaperTrailSettled rows={ROWS_54} loading={false} />);
    expect(screen.queryByTestId("no-settled-records")).toBeNull();
  });

  it("settled-book-tally region has aria-label='Settled book tally'", () => {
    render(<PaperTrailSettled rows={ROWS_54} loading={false} />);
    expect(screen.getByLabelText("Settled book tally")).toBeInTheDocument();
  });

  it("tally: settled-tally-settled shows 52", () => {
    render(<PaperTrailSettled rows={ROWS_54} loading={false} />);
    expect(screen.getByTestId("settled-tally-settled").textContent).toBe("52");
  });

  it("tally: settled-tally-win shows 24", () => {
    render(<PaperTrailSettled rows={ROWS_54} loading={false} />);
    expect(screen.getByTestId("settled-tally-win").textContent).toBe("24");
  });

  it("tally: settled-tally-loss shows 20", () => {
    render(<PaperTrailSettled rows={ROWS_54} loading={false} />);
    expect(screen.getByTestId("settled-tally-loss").textContent).toBe("20");
  });

  it("tally: settled-tally-push shows 8", () => {
    render(<PaperTrailSettled rows={ROWS_54} loading={false} />);
    expect(screen.getByTestId("settled-tally-push").textContent).toBe("8");
  });

  it("tally: settled-tally-open shows 2", () => {
    render(<PaperTrailSettled rows={ROWS_54} loading={false} />);
    expect(screen.getByTestId("settled-tally-open").textContent).toBe("2");
  });

  it("table has aria-label='Settled paper book'", () => {
    render(<PaperTrailSettled rows={ROWS_54} loading={false} />);
    expect(screen.getByRole("grid", { name: "Settled paper book" })).toBeInTheDocument();
  });

  it("result labels appear in the table (win/loss/push)", () => {
    render(<PaperTrailSettled rows={ROWS_54} loading={false} />);
    // Multiple result-label cells expected for settled rows
    const resultLabels = screen.getAllByTestId("result-label");
    const textContents = resultLabels.map((el) => el.textContent);
    expect(textContents).toContain("win");
    expect(textContents).toContain("loss");
    expect(textContents).toContain("push");
  });

  it("open positions table is rendered when there are open rows", () => {
    render(<PaperTrailSettled rows={ROWS_54} loading={false} />);
    expect(screen.getByRole("grid", { name: "Open paper positions" })).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Rendering: empty state
// ---------------------------------------------------------------------------

describe("PaperTrailSettled -- honest empty state", () => {
  it("renders no-settled-records when rows is empty", () => {
    render(<PaperTrailSettled rows={[]} loading={false} />);
    expect(screen.getByTestId("no-settled-records")).toBeInTheDocument();
  });

  it("honest-empty message says 'No edge is claimed'", () => {
    render(<PaperTrailSettled rows={[]} loading={false} />);
    expect(screen.getByTestId("no-settled-records").textContent).toMatch(/no edge is claimed/i);
  });

  it("honest-empty does NOT carry red/danger styling", () => {
    render(<PaperTrailSettled rows={[]} loading={false} />);
    const el = screen.getByTestId("no-settled-records");
    expect(el.className).not.toMatch(/text-red/);
    expect(el.className).not.toMatch(/text-danger/);
    expect(el.className).not.toMatch(/text-destructive/);
  });

  it("does NOT show settled-records-table when rows is empty", () => {
    render(<PaperTrailSettled rows={[]} loading={false} />);
    expect(screen.queryByTestId("settled-records-table")).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// Loading state
// ---------------------------------------------------------------------------

describe("PaperTrailSettled -- loading state", () => {
  it("shows aria-busy skeleton when loading=true and rows=[]", () => {
    render(<PaperTrailSettled rows={[]} loading={true} />);
    expect(
      screen.getByRole("generic", { name: "Loading settled paper trades" })
    ).toBeInTheDocument();
  });

  it("does NOT show settled-records-table while loading with no rows", () => {
    render(<PaperTrailSettled rows={[]} loading={true} />);
    expect(screen.queryByTestId("settled-records-table")).toBeNull();
  });

  it("shows settled-records-table when loading=true but rows are available (stale data)", () => {
    render(<PaperTrailSettled rows={ROWS_54} loading={true} />);
    expect(screen.getByTestId("settled-records-table")).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// CLV status column
// ---------------------------------------------------------------------------

describe("PaperTrailSettled -- CLV status column", () => {
  it("clv-status-cell shows 'true_close' for a win row", () => {
    const row = makeRow({ outcome: "win", clv_status: "true_close" });
    render(<PaperTrailSettled rows={[row]} loading={false} />);
    const clvCells = screen.getAllByTestId("clv-status-cell");
    expect(clvCells.some((el) => el.textContent === "true_close")).toBe(true);
  });

  it("clv-status-cell shows 'no_close' for a push row with no close", () => {
    const row = makeRow({
      outcome: "push",
      clv_status: "no_close",
      clv_pct: null,
      clv_unavailable: true,
    });
    render(<PaperTrailSettled rows={[row]} loading={false} />);
    const clvCells = screen.getAllByTestId("clv-status-cell");
    expect(clvCells.some((el) => el.textContent === "no_close")).toBe(true);
  });
});

// ---------------------------------------------------------------------------
// Honesty rail: no dollar figure in DOM
// ---------------------------------------------------------------------------

describe("PaperTrailSettled -- no dollar figure in DOM (honesty rail)", () => {
  it("loading state: no dollar-amount string in rendered DOM", () => {
    const { container } = render(<PaperTrailSettled rows={[]} loading={true} />);
    expect(container.textContent ?? "").not.toMatch(/\$\d/);
  });

  it("empty state: no dollar-amount string in rendered DOM", () => {
    const { container } = render(<PaperTrailSettled rows={[]} loading={false} />);
    expect(container.textContent ?? "").not.toMatch(/\$\d/);
  });

  it("populated state: no dollar-amount string in rendered DOM", () => {
    const { container } = render(<PaperTrailSettled rows={ROWS_54} loading={false} />);
    expect(container.textContent ?? "").not.toMatch(/\$\d/);
  });

  it("no 'pnl' or 'p&l' token in rendered DOM", () => {
    const { container } = render(<PaperTrailSettled rows={ROWS_54} loading={false} />);
    expect((container.textContent ?? "").toLowerCase()).not.toMatch(/p&l|pnl/);
  });
});

// ---------------------------------------------------------------------------
// settledOnly prop
// ---------------------------------------------------------------------------

describe("PaperTrailSettled -- settledOnly prop", () => {
  it("when settledOnly=true, open-positions-table is not rendered", () => {
    render(<PaperTrailSettled rows={ROWS_54} loading={false} settledOnly />);
    expect(screen.queryByRole("grid", { name: "Open paper positions" })).toBeNull();
  });

  it("when settledOnly=false (default), open-positions-table renders for open rows", () => {
    render(<PaperTrailSettled rows={ROWS_54} loading={false} settledOnly={false} />);
    expect(screen.getByRole("grid", { name: "Open paper positions" })).toBeInTheDocument();
  });
});
