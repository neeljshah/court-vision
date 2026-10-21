// ws2-settled-columns.test.tsx -- WS2 column additions to PaperTrailSettled.
//
// Verifies the WS2 requirement: outcome / model_prob / model_ev / taken_book
// columns are present and rendered in the settled records table.
// New columns added in this workstream: model_ev (sign-prefixed %) + taken_book (book name).
//
// Lane: frontend (webapp/components/paper_pm/**). Per-file vitest only.

import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { PaperTrailSettled } from "../PaperTrailSettled";
import type { PaperTrailRow } from "@/lib/p5api";

vi.mock("next/link", () => ({
  default: ({ href, children, ...rest }: { href: string; children: React.ReactNode }) => (
    <a href={href} {...rest}>{children}</a>
  ),
}));

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

function makeSettledRow(overrides: Partial<PaperTrailRow> = {}): PaperTrailRow {
  return {
    game_id: "mlb-g001",
    matchup: "NYY @ LAD",
    sport: "mlb",
    side: "away",
    market_type: null,
    line: null,
    taken_book: "espn:DraftKings",
    taken_decimal: 2.17,
    model_prob: 0.4655,
    model_ev: 0.010135,
    tier: null,
    stake_units: null,
    status: "settled",
    graded: true,
    outcome: "win",
    clv_pct: null,
    beat_close: null,
    clv_is_proxy: false,
    clv_status: "no_close",
    clv_unavailable: true,
    clv_note: "no closing line",
    executed: false,
    ts: "2026-06-17T22:59:11.000Z",
    settled_at: "2026-06-17T23:01:06.000Z",
    ...overrides,
  };
}

// ---------------------------------------------------------------------------
// taken_book column
// ---------------------------------------------------------------------------

describe("PaperTrailSettled -- WS2 taken_book column", () => {
  it("table header contains 'Book' column header", () => {
    render(<PaperTrailSettled rows={[makeSettledRow()]} loading={false} />);
    const table = screen.getByRole("grid", { name: "Settled paper book" });
    expect(table.textContent).toMatch(/Book/i);
  });

  it("taken-book-cell renders the book name from taken_book field", () => {
    const row = makeSettledRow({ taken_book: "espn:DraftKings" });
    render(<PaperTrailSettled rows={[row]} loading={false} />);
    const cells = screen.getAllByTestId("taken-book-cell");
    expect(cells.length).toBeGreaterThan(0);
    expect(cells[0].textContent).toBe("espn:DraftKings");
  });

  it("taken-book-cell renders EMPTY_CELL ('--') when taken_book is empty string", () => {
    const row = makeSettledRow({ taken_book: "" });
    render(<PaperTrailSettled rows={[row]} loading={false} />);
    const cells = screen.getAllByTestId("taken-book-cell");
    expect(cells[0].textContent).toBe("--");
  });

  it("taken-book-cell does NOT render a dollar sign (no $ in book name display)", () => {
    const row = makeSettledRow({ taken_book: "DraftKings" });
    render(<PaperTrailSettled rows={[row]} loading={false} />);
    const cells = screen.getAllByTestId("taken-book-cell");
    expect(cells[0].textContent).not.toMatch(/\$\d/);
  });

  it("multiple rows each show their taken_book value", () => {
    const rows = [
      makeSettledRow({ game_id: "g1", taken_book: "DraftKings", outcome: "win" }),
      makeSettledRow({ game_id: "g2", taken_book: "FanDuel", outcome: "loss" }),
    ];
    render(<PaperTrailSettled rows={rows} loading={false} />);
    const cells = screen.getAllByTestId("taken-book-cell");
    const texts = cells.map((c) => c.textContent);
    expect(texts).toContain("DraftKings");
    expect(texts).toContain("FanDuel");
  });
});

// ---------------------------------------------------------------------------
// model_ev column (WS2: explicit EV column)
// ---------------------------------------------------------------------------

describe("PaperTrailSettled -- no Model EV column; never-published columns dropped", () => {
  it("has no 'Model EV' header or cell even when model_ev is set", () => {
    render(<PaperTrailSettled rows={[makeSettledRow({ model_ev: 0.0101 })]} loading={false} />);
    const table = screen.getByRole("grid", { name: "Settled paper book" });
    expect(table.textContent).not.toMatch(/Model EV/i);
    expect(screen.queryByTestId("model-ev-cell")).toBeNull();
  });

  it("drops Tier, Model P and CLV columns when every row leaves them blank", () => {
    render(<PaperTrailSettled rows={[makeSettledRow({ model_prob: null, tier: null, clv_pct: null })]} loading={false} />);
    const heads = screen.getAllByRole("columnheader").map((th) => th.textContent);
    expect(heads).not.toContain("Tier");
    expect(heads).not.toContain("Model P");
    expect(heads).not.toContain("CLV");
    expect(heads).toContain("CLV status");
  });
});

// ---------------------------------------------------------------------------
// outcome column (result badge -- already existed, verify still present)
// ---------------------------------------------------------------------------

describe("PaperTrailSettled -- WS2 outcome / result column", () => {
  it("result-label shows 'win' for a win row", () => {
    render(<PaperTrailSettled rows={[makeSettledRow({ outcome: "win" })]} loading={false} />);
    const labels = screen.getAllByTestId("result-label");
    expect(labels.some((el) => el.textContent === "win")).toBe(true);
  });

  it("result-label shows 'loss' for a loss row", () => {
    render(<PaperTrailSettled rows={[makeSettledRow({ outcome: "loss" })]} loading={false} />);
    const labels = screen.getAllByTestId("result-label");
    expect(labels.some((el) => el.textContent === "loss")).toBe(true);
  });

  it("result-label shows 'pending' in mixed rows (open + settled together)", () => {
    // A mix: one settled win + one open. settledRows = [win]. Table renders.
    const settled = makeSettledRow({ game_id: "g-settled", outcome: "win", status: "settled", graded: true });
    const open = makeSettledRow({ game_id: "g-open", status: "open", graded: false, outcome: null, settled_at: null });
    render(<PaperTrailSettled rows={[settled, open]} loading={false} settledOnly={false} />);
    // settled-records-table appears because settledRows.length > 0
    expect(screen.getByTestId("settled-records-table")).toBeInTheDocument();
    // win shows in settled table
    const labels = screen.getAllByTestId("result-label");
    expect(labels.some((el) => el.textContent === "win")).toBe(true);
  });
});

// ---------------------------------------------------------------------------
// model_prob column (already existed, verify data flows through)
// ---------------------------------------------------------------------------

describe("PaperTrailSettled -- WS2 model_prob column", () => {
  it("model_prob renders as percentage in a settled row", () => {
    const row = makeSettledRow({ model_prob: 0.4655 });
    render(<PaperTrailSettled rows={[row]} loading={false} />);
    const table = screen.getByRole("grid", { name: "Settled paper book" });
    // 0.4655 should appear as "46.6%"
    expect(table.textContent).toMatch(/46\.6%/);
  });

  it("Model P header is present in the table", () => {
    render(<PaperTrailSettled rows={[makeSettledRow()]} loading={false} />);
    const table = screen.getByRole("grid", { name: "Settled paper book" });
    expect(table.textContent).toMatch(/Model P/i);
  });
});

// ---------------------------------------------------------------------------
// Full column set: all 4 WS2 columns present simultaneously
// ---------------------------------------------------------------------------

describe("PaperTrailSettled -- WS2 all required columns together", () => {
  it("table has all required WS2 column headers: Book, Model P, Result", () => {
    render(<PaperTrailSettled rows={[makeSettledRow()]} loading={false} />);
    const table = screen.getByRole("grid", { name: "Settled paper book" });
    const text = table.textContent ?? "";
    expect(text).toMatch(/Book/);
    expect(text).not.toMatch(/Model EV/);
    expect(text).toMatch(/Model P/);
    expect(text).toMatch(/Result/);
  });

  it("all 3 required column data cells have content for a real-data row", () => {
    const row = makeSettledRow({
      taken_book: "espn:DraftKings",
      model_ev: 0.010135,
      model_prob: 0.4655,
      outcome: "win",
    });
    render(<PaperTrailSettled rows={[row]} loading={false} />);

    // taken_book cell
    const bookCells = screen.getAllByTestId("taken-book-cell");
    expect(bookCells[0].textContent).toBe("espn:DraftKings");

    // outcome / result label
    const resultLabels = screen.getAllByTestId("result-label");
    expect(resultLabels.some((el) => el.textContent === "win")).toBe(true);

    // model_prob (shown as text in table)
    const table = screen.getByRole("grid", { name: "Settled paper book" });
    expect(table.textContent).toMatch(/46\.6%/);
  });

  it("no dollar amount in any of the 3 required column cells", () => {
    const row = makeSettledRow({
      taken_book: "DraftKings",
      model_ev: 0.07,
      model_prob: 0.55,
      outcome: "win",
    });
    const { container } = render(<PaperTrailSettled rows={[row]} loading={false} />);
    expect(container.textContent ?? "").not.toMatch(/\$\d/);
  });
});
