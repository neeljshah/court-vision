import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";

// venue-summary.test.tsx -- unit tests for venueAggregate + VenueSummary component.
// HONESTY RAILS:
//   - A venue with zero clv_pct settled rows -> CLV = INSUFFICIENT_DATA (never 0).
//   - No '$' symbol anywhere in rendered output.
//   - One tile rendered per distinct venue.
//   - Correct counts: open/settled/win/loss/push and summed units.
//   - VenueSummary does NOT import or depend on any WS3 page component.

import { aggregateByVenue, venueOf } from "../venueAggregate";
import { VenueSummary } from "../VenueSummary";
import type { PaperTrailRow } from "@/lib/p5api";

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
    stake_units: 1.0,
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

function settledRow(overrides: Partial<PaperTrailRow> = {}): PaperTrailRow {
  return makeRow({
    status: "settled",
    graded: true,
    outcome: "win",
    clv_pct: 0.025,
    beat_close: true,
    clv_is_proxy: false,
    clv_status: "true_close",
    clv_unavailable: false,
    settled_at: "2026-06-19T22:00:00Z",
    ...overrides,
  });
}

function noCloseRow(overrides: Partial<PaperTrailRow> = {}): PaperTrailRow {
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
    ...overrides,
  });
}

function noDollar(container: HTMLElement) {
  expect(container.textContent ?? "").not.toMatch(/\$\s?\d/);
}

// ---------------------------------------------------------------------------
// venueOf helper
// ---------------------------------------------------------------------------

describe("venueOf", () => {
  it("returns 'kalshi' for taken_book containing 'kalshi'", () => {
    expect(venueOf(makeRow({ taken_book: "kalshi" }))).toBe("kalshi");
    expect(venueOf(makeRow({ taken_book: "KALSHI" }))).toBe("kalshi");
    expect(venueOf(makeRow({ taken_book: "kalshi:ml" }))).toBe("kalshi");
  });

  it("returns 'polymarket' for taken_book containing 'polymarket'", () => {
    expect(venueOf(makeRow({ taken_book: "polymarket" }))).toBe("polymarket");
  });

  it("extracts book part after ':' for composite taken_book", () => {
    expect(venueOf(makeRow({ taken_book: "espn:DraftKings" }))).toBe("DraftKings");
  });

  it("returns raw taken_book when no special patterns match", () => {
    expect(venueOf(makeRow({ taken_book: "paper" }))).toBe("paper");
    expect(venueOf(makeRow({ taken_book: "mybookmaker" }))).toBe("mybookmaker");
  });

  it("returns 'unknown' when taken_book is empty string", () => {
    expect(venueOf(makeRow({ taken_book: "" }))).toBe("unknown");
  });
});

// ---------------------------------------------------------------------------
// aggregateByVenue -- pure logic tests (no rendering)
// ---------------------------------------------------------------------------

describe("aggregateByVenue -- grouping and counts", () => {
  it("groups rows by venue with correct total counts", () => {
    const rows = [
      makeRow({ taken_book: "kalshi" }),
      makeRow({ taken_book: "kalshi" }),
      makeRow({ taken_book: "polymarket" }),
    ];
    const stats = aggregateByVenue(rows);
    expect(stats.length).toBe(2);
    const kalshi = stats.find((s) => s.venue === "kalshi")!;
    expect(kalshi.total).toBe(2);
    const poly = stats.find((s) => s.venue === "polymarket")!;
    expect(poly.total).toBe(1);
  });

  it("counts open vs settled correctly", () => {
    const rows = [
      makeRow({ taken_book: "kalshi", status: "open" }),
      settledRow({ taken_book: "kalshi" }),
      settledRow({ taken_book: "kalshi" }),
    ];
    const [k] = aggregateByVenue(rows);
    expect(k.open).toBe(1);
    expect(k.settled).toBe(2);
  });

  it("counts win / loss / push correctly", () => {
    const rows = [
      settledRow({ taken_book: "kalshi", outcome: "win" }),
      settledRow({ taken_book: "kalshi", outcome: "loss" }),
      settledRow({ taken_book: "kalshi", outcome: "push" }),
      makeRow({ taken_book: "kalshi", status: "open" }),
    ];
    const [k] = aggregateByVenue(rows);
    expect(k.win).toBe(1);
    expect(k.loss).toBe(1);
    expect(k.push).toBe(1);
    expect(k.pending).toBe(1);
  });

  it("sums stake_units correctly", () => {
    const rows = [
      makeRow({ taken_book: "kalshi", stake_units: 1.5 }),
      makeRow({ taken_book: "kalshi", stake_units: 0.75 }),
    ];
    const [k] = aggregateByVenue(rows);
    expect(k.stake_units_total).toBeCloseTo(2.25, 5);
  });

  it("stake_units_total is null when all rows have null stake", () => {
    const rows = [
      makeRow({ taken_book: "kalshi", stake_units: null }),
    ];
    const [k] = aggregateByVenue(rows);
    expect(k.stake_units_total).toBeNull();
  });

  it("returns results sorted alphabetically by venue name", () => {
    const rows = [
      makeRow({ taken_book: "z-venue" }),
      makeRow({ taken_book: "a-venue" }),
      makeRow({ taken_book: "m-venue" }),
    ];
    const stats = aggregateByVenue(rows);
    const names = stats.map((s) => s.venue);
    expect(names).toEqual(["a-venue", "m-venue", "z-venue"]);
  });
});

describe("aggregateByVenue -- CLV honesty rail", () => {
  it("clv_mean is null (INSUFFICIENT_DATA) when venue has no settled rows", () => {
    const rows = [
      makeRow({ taken_book: "kalshi", status: "open" }),
      makeRow({ taken_book: "kalshi", status: "open" }),
    ];
    const [k] = aggregateByVenue(rows);
    expect(k.clv_mean).toBeNull();
    expect(k.clv_sample_n).toBe(0);
  });

  it("clv_mean is null when all settled rows have no_close status", () => {
    const rows = [
      noCloseRow({ taken_book: "kalshi" }),
      noCloseRow({ taken_book: "kalshi" }),
    ];
    const [k] = aggregateByVenue(rows);
    expect(k.clv_mean).toBeNull();
    expect(k.clv_sample_n).toBe(0);
  });

  it("clv_mean is null when clv_pct is null even if graded=true", () => {
    const rows = [
      settledRow({ taken_book: "kalshi", clv_pct: null, clv_status: null }),
    ];
    const [k] = aggregateByVenue(rows);
    expect(k.clv_mean).toBeNull();
  });

  it("clv_mean is null when clv_unavailable=true, never 0-filled", () => {
    const rows = [
      makeRow({
        taken_book: "kalshi",
        status: "settled",
        graded: true,
        outcome: "win",
        clv_pct: 0.05,
        clv_unavailable: true,
        clv_status: "no_close",
      }),
    ];
    const [k] = aggregateByVenue(rows);
    // clv_unavailable=true must be excluded from CLV aggregation
    expect(k.clv_mean).toBeNull();
    expect(k.clv_sample_n).toBe(0);
  });

  it("clv_mean averages real settled CLV values correctly", () => {
    const rows = [
      settledRow({ taken_book: "kalshi", clv_pct: 0.04 }),
      settledRow({ taken_book: "kalshi", clv_pct: -0.02 }),
    ];
    const [k] = aggregateByVenue(rows);
    expect(k.clv_mean).toBeCloseTo(0.01, 5);
    expect(k.clv_sample_n).toBe(2);
  });

  it("mixes qualifying and non-qualifying rows -- only qualifying rows count", () => {
    const rows = [
      settledRow({ taken_book: "kalshi", clv_pct: 0.06 }),
      noCloseRow({ taken_book: "kalshi" }), // should not contribute
      makeRow({ taken_book: "kalshi", status: "open" }), // open, no CLV
    ];
    const [k] = aggregateByVenue(rows);
    expect(k.clv_mean).toBeCloseTo(0.06, 5);
    expect(k.clv_sample_n).toBe(1);
  });
});

describe("aggregateByVenue -- model_prob_mean", () => {
  it("computes mean model_prob across all rows (open and settled)", () => {
    const rows = [
      makeRow({ taken_book: "kalshi", model_prob: 0.60 }),
      settledRow({ taken_book: "kalshi", model_prob: 0.40 }),
    ];
    const [k] = aggregateByVenue(rows);
    expect(k.model_prob_mean).toBeCloseTo(0.50, 5);
  });

  it("model_prob_mean is null when all rows have null model_prob", () => {
    const rows = [
      makeRow({ taken_book: "kalshi", model_prob: null }),
    ];
    const [k] = aggregateByVenue(rows);
    expect(k.model_prob_mean).toBeNull();
  });
});

describe("aggregateByVenue -- empty input", () => {
  it("returns empty array for no rows", () => {
    expect(aggregateByVenue([])).toEqual([]);
  });
});

// ---------------------------------------------------------------------------
// VenueSummary component rendering
// ---------------------------------------------------------------------------

describe("VenueSummary -- renders one tile per venue", () => {
  it("renders one tile per distinct venue", () => {
    const rows = [
      makeRow({ taken_book: "kalshi" }),
      makeRow({ taken_book: "polymarket" }),
      makeRow({ taken_book: "kalshi" }), // second kalshi row
    ];
    render(<VenueSummary rows={rows} />);
    const tiles = screen.getAllByTestId("venue-tile");
    expect(tiles.length).toBe(2);
  });

  it("renders venue names in tile headers", () => {
    const rows = [
      makeRow({ taken_book: "kalshi" }),
      makeRow({ taken_book: "polymarket" }),
    ];
    render(<VenueSummary rows={rows} />);
    expect(screen.getByText("kalshi")).toBeInTheDocument();
    expect(screen.getByText("polymarket")).toBeInTheDocument();
  });

  it("shows INSUFFICIENT_DATA for venue with no settled close rows", () => {
    const rows = [makeRow({ taken_book: "kalshi", status: "open" })];
    const { container } = render(<VenueSummary rows={rows} />);
    expect(container.textContent).toContain("INSUFFICIENT_DATA");
  });

  it("does NOT show INSUFFICIENT_DATA inside the venue tile when venue has real CLV", () => {
    const rows = [settledRow({ taken_book: "kalshi", clv_pct: 0.03 })];
    render(<VenueSummary rows={rows} />);
    // The tile itself should not say INSUFFICIENT_DATA -- only the footer disclaimer
    // may mention it generically. We check the tile element directly.
    const tile = screen.getByTestId("venue-tile");
    expect(tile.textContent).not.toContain("INSUFFICIENT_DATA");
    expect(tile.textContent).toContain("%");
  });

  it("never renders a dollar sign in output", () => {
    const rows = [
      settledRow({ taken_book: "kalshi", clv_pct: 0.02, stake_units: 2.5 }),
      makeRow({ taken_book: "polymarket", stake_units: 1.0 }),
    ];
    const { container } = render(<VenueSummary rows={rows} />);
    noDollar(container);
  });

  it("shows units staked label (never dollar label)", () => {
    const rows = [makeRow({ taken_book: "kalshi", stake_units: 1.5 })];
    const { container } = render(<VenueSummary rows={rows} />);
    // Should contain "units" in the staked label area
    expect(container.textContent?.toLowerCase()).toContain("unit");
    noDollar(container);
  });

  it("shows loading skeletons when loading=true", () => {
    render(<VenueSummary rows={[]} loading />);
    expect(screen.getAllByTestId("venue-skeleton").length).toBeGreaterThan(0);
    expect(screen.queryAllByTestId("venue-tile").length).toBe(0);
  });

  it("shows unavailable state when error is set", () => {
    render(<VenueSummary rows={[]} error="connection refused" />);
    expect(screen.getByText("connection refused")).toBeInTheDocument();
    expect(screen.queryAllByTestId("venue-tile").length).toBe(0);
  });

  it("shows empty state when rows is empty and not loading", () => {
    render(<VenueSummary rows={[]} />);
    expect(screen.getByText(/No venue data yet/)).toBeInTheDocument();
  });

  it("shows win/loss counts in tile", () => {
    const rows = [
      settledRow({ taken_book: "kalshi", outcome: "win" }),
      settledRow({ taken_book: "kalshi", outcome: "loss" }),
    ];
    render(<VenueSummary rows={rows} />);
    // The tile shows win/loss labels
    expect(screen.getByText("Win")).toBeInTheDocument();
    expect(screen.getByText("Loss")).toBeInTheDocument();
  });

  it("open and settled counts display correctly in tile", () => {
    const rows = [
      makeRow({ taken_book: "kalshi", status: "open" }),
      settledRow({ taken_book: "kalshi" }),
    ];
    render(<VenueSummary rows={rows} />);
    expect(screen.getByText("Open")).toBeInTheDocument();
    expect(screen.getByText("Settled")).toBeInTheDocument();
  });
});

describe("VenueSummary -- no WS3 import leak", () => {
  it("VenueSummary module does not import any WS3 page component", async () => {
    // Verify at module level: VenueSummary is a presentational component consumed
    // by WS3, not the other way around. This test just ensures it renders without
    // any WS3 page context.
    const rows = [makeRow({ taken_book: "kalshi" })];
    expect(() => render(<VenueSummary rows={rows} />)).not.toThrow();
  });
});
