/**
 * BoardTable RTL tests.
 *
 * Strategy: jsdom assigns 0 height to everything, so @tanstack/react-virtual
 * renders 0 virtual items (nothing in the DOM) by default. We patch
 * getBoundingClientRect / offsetHeight / clientHeight so the virtualizer
 * believes the scroll container is 1200px tall, giving it enough room to
 * render our small fixture list.
 *
 * We mock BoardRowItem to a thin div -- it relies on sub-components that
 * import "cva" via an alias not wired in the Vite test config. The mock lets
 * us assert on headers and the finished toggle without needing the full render
 * tree.
 *
 * Robustness: all header / toggle assertions use *ByRole / *ByText so they
 * stay valid even if jsdom keeps some items outside the virtual viewport.
 */

import React from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, beforeAll } from "vitest";
import type { BoardRow, Sport } from "@/types/board";

// ---------------------------------------------------------------------------
// Mock BoardRowItem so we do not pull in the cva / Radix / Tooltip sub-tree.
// The mock renders a minimal accessible row element with the home team name so
// tests can optionally verify row content without fighting the dep chain.
// ---------------------------------------------------------------------------
vi.mock("@/components/board/BoardRowItem", () => ({
  BoardRowItem: ({ row }: { row: BoardRow; generatedAt: string | null; style?: React.CSSProperties }) => (
    <div role="row" data-testid={`row-${row.home}`}>
      {row.home} vs {row.away}
    </div>
  ),
}));

// Import BoardTable AFTER the mock is established.
import { BoardTable } from "@/components/board/BoardTable";

// ---------------------------------------------------------------------------
// jsdom virtualizer shim
// react-virtual reads scroll container dimensions to decide how many items to
// render. In jsdom everything is 0px, so we patch the relevant APIs globally.
// ---------------------------------------------------------------------------
beforeAll(() => {
  const origGetBCR = Element.prototype.getBoundingClientRect;
  Element.prototype.getBoundingClientRect = function () {
    const real = origGetBCR.call(this);
    return {
      ...real,
      height: real.height || 1200,
      width: real.width || 800,
      top: real.top,
      left: real.left,
      right: real.right || 800,
      bottom: real.bottom || 1200,
      x: real.x,
      y: real.y,
      toJSON: real.toJSON ?? (() => ({})),
    };
  };

  Object.defineProperty(HTMLElement.prototype, "offsetHeight", {
    configurable: true,
    get() { return 1200; },
  });
  Object.defineProperty(HTMLElement.prototype, "clientHeight", {
    configurable: true,
    get() { return 1200; },
  });
  Object.defineProperty(HTMLElement.prototype, "offsetWidth", {
    configurable: true,
    get() { return 800; },
  });
  Object.defineProperty(HTMLElement.prototype, "clientWidth", {
    configurable: true,
    get() { return 800; },
  });
});

// ---------------------------------------------------------------------------
// Fixture helpers
// ---------------------------------------------------------------------------

function makeRow(
  state: BoardRow["state"],
  index: number,
  sport: Sport = "mlb"
): BoardRow {
  return {
    sport,
    league: "mlb",
    state,
    start_time: new Date(Date.now() + index * 60_000).toISOString(),
    home: `HomeTeam${index}`,
    away: `AwayTeam${index}`,
    home_score: state === "post" ? 4 : null,
    away_score: state === "post" ? 2 : null,
    clock_text: state === "in" ? "T7" : null,
    win_home: 0.6,
    win_away: 0.4,
    draw: null,
    total: 8.5,
    market_odds: null,
    provider: null,
    source: "market",
    market_implied: true,
    note: null,
  };
}

/** 1 live + 2 upcoming + 15 finished -- the canonical test fixture. */
function buildMixedRows(): BoardRow[] {
  const rows: BoardRow[] = [];
  rows.push(makeRow("in", 0));
  rows.push(makeRow("pre", 1));
  rows.push(makeRow("pre", 2));
  for (let i = 0; i < 15; i++) {
    rows.push(makeRow("post", 10 + i));
  }
  return rows;
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("BoardTable", () => {
  const mixedRows = buildMixedRows();

  // -- Section headers -------------------------------------------------------

  it("renders the 'Live' section header", () => {
    render(<BoardTable rows={mixedRows} sport="mlb" generatedAt={null} />);
    expect(screen.getByText(/^live$/i)).toBeInTheDocument();
  });

  it("renders the 'Upcoming' section header", () => {
    render(<BoardTable rows={mixedRows} sport="mlb" generatedAt={null} />);
    expect(screen.getByText(/^upcoming$/i)).toBeInTheDocument();
  });

  // -- Finished toggle (15 > threshold 12) -----------------------------------

  it("renders the finished-toggle as a button with the count in the label", () => {
    render(<BoardTable rows={mixedRows} sport="mlb" generatedAt={null} />);
    // "Show 15 Finished" -- case-insensitive match
    const btn = screen.getByRole("button", { name: /15 finished/i });
    expect(btn).toBeInTheDocument();
  });

  it("finished-toggle button is initially collapsed (aria-expanded=false)", () => {
    render(<BoardTable rows={mixedRows} sport="mlb" generatedAt={null} />);
    const btn = screen.getByRole("button", { name: /15 finished/i });
    expect(btn).toHaveAttribute("aria-expanded", "false");
  });

  it("finished-toggle has type=button for keyboard operability", () => {
    render(<BoardTable rows={mixedRows} sport="mlb" generatedAt={null} />);
    const btn = screen.getByRole("button", { name: /15 finished/i });
    expect(btn).toHaveAttribute("type", "button");
  });

  // -- Clicking the toggle ---------------------------------------------------

  it("clicking the toggle expands to aria-expanded=true and shows 'Hide Finished'", async () => {
    const user = userEvent.setup();
    render(<BoardTable rows={mixedRows} sport="mlb" generatedAt={null} />);

    const btn = screen.getByRole("button", { name: /15 finished/i });
    await user.click(btn);

    expect(btn).toHaveAttribute("aria-expanded", "true");
    // Label updates to "Hide Finished"
    expect(
      screen.getByRole("button", { name: /hide finished/i })
    ).toBeInTheDocument();
  });

  it("clicking the toggle twice collapses back to 'Show N Finished'", async () => {
    const user = userEvent.setup();
    render(<BoardTable rows={mixedRows} sport="mlb" generatedAt={null} />);

    const showBtn = screen.getByRole("button", { name: /15 finished/i });
    await user.click(showBtn); // expand

    const hideBtn = screen.getByRole("button", { name: /hide finished/i });
    await user.click(hideBtn); // collapse

    expect(
      screen.getByRole("button", { name: /15 finished/i })
    ).toHaveAttribute("aria-expanded", "false");
  });

  // -- ARIA / accessibility --------------------------------------------------

  it("renders the scroll container as an accessible list region", () => {
    render(<BoardTable rows={mixedRows} sport="mlb" generatedAt={null} />);
    const list = screen.getByRole("list", { name: /mlb games/i });
    expect(list).toBeInTheDocument();
  });

  // -- Empty state -----------------------------------------------------------

  it("shows an empty message when the rows array is empty", () => {
    render(<BoardTable rows={[]} sport="mlb" generatedAt={null} />);
    expect(screen.getByText(/no games to display/i)).toBeInTheDocument();
  });

  it("does NOT show the empty message when rows exist", () => {
    render(<BoardTable rows={mixedRows} sport="mlb" generatedAt={null} />);
    expect(screen.queryByText(/no games to display/i)).not.toBeInTheDocument();
  });

  // -- No toggle when post count is at or below the threshold ---------------

  it("shows a plain 'Finished' header (not a toggle) when <= 12 post rows", () => {
    const smallRows: BoardRow[] = [
      makeRow("in", 0),
      makeRow("pre", 1),
      ...Array.from({ length: 3 }, (_, i) => makeRow("post", 10 + i)),
    ];
    render(<BoardTable rows={smallRows} sport="mlb" generatedAt={null} />);
    // No collapsible button rendered
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
    // Plain header is present
    expect(screen.getByText(/^finished$/i)).toBeInTheDocument();
  });
});
