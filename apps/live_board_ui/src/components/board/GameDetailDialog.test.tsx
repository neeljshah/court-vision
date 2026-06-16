/**
 * RTL tests for GameDetailDialog.
 *
 * GameDetailDialog is a controlled Radix dialog (open + onOpenChange props).
 * Radix mounts portal content into document.body, so screen queries find it
 * even though the render container is separate. When open=false Radix
 * withholds the portal content from the DOM entirely.
 */
import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import type { BoardRow } from "@/types/board";
import { GameDetailDialog } from "./GameDetailDialog";

// ---------------------------------------------------------------------------
// BoardRow fixture helpers
// ---------------------------------------------------------------------------

/** Minimal valid MLB BoardRow with all required fields. */
function makeMlbRow(overrides: Partial<BoardRow> = {}): BoardRow {
  return {
    sport: "mlb",
    league: "MLB",
    state: "pre",
    start_time: "2026-06-15T19:05:00Z",
    home: "NYY",
    away: "BOS",
    home_score: null,
    away_score: null,
    clock_text: null,
    win_home: 0.58,
    win_away: 0.42,
    draw: null,
    total: 8.5,
    market_odds: null,
    provider: null,
    source: "model",
    market_implied: false,
    note: "Ace on the mound",
    ...overrides,
  };
}

/** Row with source="unavailable" and no odds -- score/clock only. */
function makeUnavailableRow(): BoardRow {
  return makeMlbRow({
    source: "unavailable",
    market_odds: null,
    win_home: null,
    win_away: null,
    total: null,
    note: null,
  });
}

// ---------------------------------------------------------------------------
// Closed state -- dialog content must be absent from the document
// ---------------------------------------------------------------------------

describe("GameDetailDialog - closed state", () => {
  it("does NOT render dialog content when open=false", () => {
    const row = makeMlbRow();
    render(
      <GameDetailDialog open={false} onOpenChange={vi.fn()} row={row} />
    );
    // Radix skips mounting the portal when open=false; the matchup title must
    // be absent.
    expect(screen.queryByText(/BOS @ NYY/i)).toBeNull();
  });

  it("does NOT render dialog content when row=null even if open=true", () => {
    render(
      <GameDetailDialog open={true} onOpenChange={vi.fn()} row={null} />
    );
    // Nothing to show -- the dialog should not be in the document.
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Model MLB row -- open=true assertions
// ---------------------------------------------------------------------------

describe("GameDetailDialog - model MLB row open", () => {
  function renderOpen() {
    const row = makeMlbRow();
    render(
      <GameDetailDialog open={true} onOpenChange={vi.fn()} row={row} />
    );
  }

  it('renders the matchup title "BOS @ NYY"', () => {
    renderOpen();
    // Radix renders the title in both RadixDialog.Title (<h2>) and a sr-only
    // RadixDialog.Description fallback -- use getAllByText to tolerate both.
    expect(screen.getAllByText(/BOS @ NYY/i).length).toBeGreaterThan(0);
  });

  it('shows "58%" for the home win probability (win_home=0.58)', () => {
    renderOpen();
    // pct(0.58) = 58 -> displayed as "58%"
    expect(screen.getByText(/58%/i)).toBeInTheDocument();
  });

  it('shows the total "8.5"', () => {
    renderOpen();
    // fmtTotal(8.5) = "8.5"
    expect(screen.getByText(/8\.5/)).toBeInTheDocument();
  });

  it("shows the full note text", () => {
    renderOpen();
    expect(screen.getByText(/Ace on the mound/i)).toBeInTheDocument();
  });

  it("shows an honest provenance sentence mentioning in our data or in-corpus", () => {
    renderOpen();
    // The provenance copy for source="model" must state the model is
    // calibrated on in-corpus matchups; never claim a $ edge.
    expect(
      screen.getByText(/in our data|in-corpus/i)
    ).toBeInTheDocument();
  });

  it("does NOT contain edge / beat the market / +EV language", () => {
    renderOpen();
    expect(screen.queryByText(/edge|beat the market|\+EV/i)).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// Unavailable row -- provenance must mention score and clock
// ---------------------------------------------------------------------------

describe("GameDetailDialog - unavailable row open", () => {
  function renderUnavailable() {
    const row = makeUnavailableRow();
    render(
      <GameDetailDialog open={true} onOpenChange={vi.fn()} row={row} />
    );
  }

  it("renders the dialog when open=true with an unavailable row", () => {
    renderUnavailable();
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });

  it("provenance text mentions score and clock for unavailable source", () => {
    renderUnavailable();
    expect(screen.getByText(/score and clock/i)).toBeInTheDocument();
  });

  it("does NOT contain edge / beat the market / +EV language", () => {
    renderUnavailable();
    expect(screen.queryByText(/edge|beat the market|\+EV/i)).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// onOpenChange is wired to the Radix Dialog root
// ---------------------------------------------------------------------------

describe("GameDetailDialog - onOpenChange prop", () => {
  it("accepts onOpenChange without throwing", () => {
    const onOpenChange = vi.fn();
    const row = makeMlbRow();
    expect(() =>
      render(
        <GameDetailDialog open={true} onOpenChange={onOpenChange} row={row} />
      )
    ).not.toThrow();
  });
});
