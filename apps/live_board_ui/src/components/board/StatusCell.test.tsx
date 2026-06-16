/** RTL tests for StatusCell: live clock, final/post, and pre-game scheduled time. */
import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { StatusCell } from "./StatusCell";
import type { BoardRow } from "@/types/board";

// ---------------------------------------------------------------------------
// Helper: builds a minimal BoardRow; override only what each test needs.
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
// state "in" -- live game with clock text
// ---------------------------------------------------------------------------
describe('StatusCell - state "in"', () => {
  it('renders the clock_text "Bot 7" when game is live', () => {
    const row = makeRow({ state: "in", clock_text: "Bot 7" });
    const { container } = render(<StatusCell row={row} />);
    expect(container.textContent).toContain("Bot 7");
  });

  it('is labelled live: aria-label includes /live/i', () => {
    const row = makeRow({ state: "in", clock_text: "Bot 7" });
    render(<StatusCell row={row} />);
    // The top-level span carries aria-label="Live: Bot 7"
    const el = screen.getByLabelText(/live/i);
    expect(el).toBeTruthy();
  });

  it("falls back to live label text when clock_text is null", () => {
    const row = makeRow({ state: "in", clock_text: null });
    render(<StatusCell row={row} />);
    // aria-label should still contain "live" and text should be "Live"
    const el = screen.getByLabelText(/live/i);
    expect(el.textContent).toMatch(/live/i);
  });
});

// ---------------------------------------------------------------------------
// state "post" -- finished game
// ---------------------------------------------------------------------------
describe('StatusCell - state "post"', () => {
  it('renders "Final" when clock_text is null', () => {
    const row = makeRow({ state: "post", clock_text: null });
    render(<StatusCell row={row} />);
    expect(screen.getByText("Final")).toBeTruthy();
  });

  it("renders clock_text when it is present on a finished game", () => {
    const row = makeRow({ state: "post", clock_text: "F/OT" });
    render(<StatusCell row={row} />);
    expect(screen.getByText("F/OT")).toBeTruthy();
  });

  it('does NOT render "Final" when clock_text is explicitly provided', () => {
    const row = makeRow({ state: "post", clock_text: "F/OT" });
    const { container } = render(<StatusCell row={row} />);
    expect(container.textContent).not.toContain("Final");
  });
});

// ---------------------------------------------------------------------------
// state "pre" -- scheduled game, has a start_time
// ---------------------------------------------------------------------------
describe('StatusCell - state "pre"', () => {
  it("renders a non-empty string for a scheduled game with a start_time", () => {
    const row = makeRow({
      state: "pre",
      start_time: "2026-06-15T19:05:00Z",
      clock_text: null,
    });
    const { container } = render(<StatusCell row={row} />);
    // Must produce some visible text -- must not throw and must not be blank.
    const text = (container.textContent ?? "").trim();
    expect(text.length).toBeGreaterThan(0);
  });

  it("renders clock_text directly when it is set, ignoring start_time", () => {
    const row = makeRow({
      state: "pre",
      start_time: "2026-06-15T19:05:00Z",
      clock_text: "7:05 PM",
    });
    render(<StatusCell row={row} />);
    expect(screen.getByText("7:05 PM")).toBeTruthy();
  });

  it('falls back to "Scheduled" when both clock_text and start_time are null', () => {
    const row = makeRow({ state: "pre", start_time: null, clock_text: null });
    render(<StatusCell row={row} />);
    expect(screen.getByText("Scheduled")).toBeTruthy();
  });
});
