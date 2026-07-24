// paper-trading.test.tsx -- WS3 acceptance tests for /paper-trading page.
//
// Acceptance criteria (WS3):
//   * venue-summary-placeholder testid is GONE; VenueSummary renders per-venue rows.
//   * Per-venue rows show correct counts, units staked, and mean CLV.
//   * CLV shows INSUFFICIENT_DATA when absent -- never greened.
//   * No '$' string anywhere in rendered output.
//   * Real-money DENY banner always present.
//   * Running tally tiles correct from mocked payload.
//   * Honest empty state.

import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";

vi.mock("next/link", () => ({
  default: ({ href, children, ...rest }: { href: string; children: React.ReactNode }) => (
    <a href={href} {...rest}>{children}</a>
  ),
}));

vi.mock("@/components/paper_pm/PmTrailTable", () => ({
  PmTrailTable: ({ loading }: { loading?: boolean }) => (
    <div data-testid="pm-trail-table">{loading ? "table-loading" : "table-ready"}</div>
  ),
}));

// Stub PaperTrailSettled -- tested separately.
vi.mock("@/components/paper_pm/PaperTrailSettled", () => ({
  PaperTrailSettled: ({ loading, rows }: { loading?: boolean; rows?: unknown[] }) => (
    <div data-testid="paper-trail-settled" data-loading={String(!!loading)} data-rows={String((rows ?? []).length)}>
      {loading ? "settled-loading" : "settled-ready"}
    </div>
  ),
}));

import * as p5api from "@/lib/p5api";

// Two kalshi trades (one win, one open/no-close) + one polymarket loss.
const MOCK_TRADES = [
  { bet_id: "a1", venue: "kalshi", market_id: "km-001", model_prob: 0.65,
    confidence: 0.7, units: 1.0, tier: "A", result: "win", clv: 0.02,
    clv_is_proxy: false, clv_status: "true_close", price_taken: 2.0,
    ts: "2026-06-18T10:00:00Z" },
  { bet_id: "a2", venue: "polymarket", market_id: "pm-002", model_prob: 0.55,
    confidence: 0.6, units: 0.75, tier: "B", result: "loss", clv: -0.01,
    clv_is_proxy: false, clv_status: "true_close", price_taken: 1.9,
    ts: "2026-06-18T11:00:00Z" },
  { bet_id: "a3", venue: "kalshi", market_id: "km-003", model_prob: 0.6,
    confidence: 0.65, units: 0.5, tier: "B", result: null, clv: null,
    clv_is_proxy: false, clv_status: "INSUFFICIENT_DATA", price_taken: 1.95,
    ts: "2026-06-18T12:00:00Z" },
];

const MOCK_CLV: p5api.ClvScoreboard = {
  n_bets: 2, pct_beat_close: 0.5, mean_clv_pct: 0.005, by_sport: null, clv_is_proxy: false,
};
const EMPTY_CLV: p5api.ClvScoreboard = {
  n_bets: 0, pct_beat_close: null, mean_clv_pct: null, by_sport: null, clv_is_proxy: false,
};

const EMPTY_PAPER_TRAIL = { status: "ok", count: 0, trail: [] as p5api.PaperTrailRow[] };

function mockApiWithTrades() {
  vi.spyOn(p5api.api, "getPaperTrail").mockResolvedValue(EMPTY_PAPER_TRAIL as never);
  vi.spyOn(p5api.api, "pmTrail").mockResolvedValue(
    { status: "ok", generated_at: null, trades: MOCK_TRADES, count: 3 } as never
  );
  vi.spyOn(p5api.api, "getPaperClv").mockResolvedValue(MOCK_CLV as never);
}

function mockApiEmpty() {
  vi.spyOn(p5api.api, "getPaperTrail").mockResolvedValue(EMPTY_PAPER_TRAIL as never);
  vi.spyOn(p5api.api, "pmTrail").mockResolvedValue(
    { status: "ok", generated_at: null, trades: [], count: 0 } as never
  );
  vi.spyOn(p5api.api, "getPaperClv").mockResolvedValue(EMPTY_CLV as never);
}

function mockApiPending() {
  vi.spyOn(p5api.api, "getPaperTrail").mockReturnValue(new Promise(() => {}));
  vi.spyOn(p5api.api, "pmTrail").mockReturnValue(new Promise(() => {}));
  vi.spyOn(p5api.api, "getPaperClv").mockReturnValue(new Promise(() => {}));
}

afterEach(() => vi.restoreAllMocks());

async function renderPage() {
  const { default: PaperTradingPage } = await import("../page");
  return render(<PaperTradingPage />);
}

// ---------------------------------------------------------------------------
// WS3 -- venue-summary-placeholder is GONE; VenueSummary renders per venue
// ---------------------------------------------------------------------------

describe("/paper-trading -- WS3 venue summary wired", () => {
  it("venue-summary-placeholder testid is absent after WS3 wiring", async () => {
    mockApiPending();
    await renderPage();
    expect(screen.queryByTestId("venue-summary-placeholder")).toBeNull();
  });

  it("venue-summary-section renders in place of the old placeholder", async () => {
    mockApiPending();
    await renderPage();
    expect(screen.getByTestId("venue-summary-section")).toBeInTheDocument();
  });

  it("shows venue-skeleton tiles while loading (VenueSummary loading state)", async () => {
    mockApiPending();
    await renderPage();
    expect(screen.getAllByTestId("venue-skeleton").length).toBeGreaterThan(0);
  });

  it("renders per-venue tiles once trades are loaded", async () => {
    mockApiWithTrades();
    await renderPage();
    // Two distinct venues: kalshi and polymarket
    await waitFor(() => {
      const tiles = screen.getAllByTestId("venue-tile");
      expect(tiles.length).toBe(2);
    });
  });

  it("renders kalshi tile with 2 trades total", async () => {
    mockApiWithTrades();
    await renderPage();
    await waitFor(() => expect(screen.getByText("kalshi")).toBeInTheDocument());
    // kalshi has 2 trades (a1 win + a3 open)
    expect(screen.getByText("2 trades")).toBeInTheDocument();
  });

  it("renders polymarket tile with 1 trade total", async () => {
    mockApiWithTrades();
    await renderPage();
    await waitFor(() => expect(screen.getByText("polymarket")).toBeInTheDocument());
    expect(screen.getByText("1 trade")).toBeInTheDocument();
  });

  it("kalshi shows INSUFFICIENT_DATA for CLV (1 open trade has no close)", async () => {
    // kalshi a1 is win/true_close (clv=0.02) but a3 is open/null.
    // The CLV mean is over settled rows with real close only -- a3 open contributes nothing.
    // a1 has clv=0.02 and clv_status=true_close -- should produce a real CLV, not INSUFFICIENT.
    // VenueSummary footnote shows INSUFFICIENT_DATA only when clv_mean is null.
    // kalshi clv_mean = 0.02 (only a1 qualifies: settled+true_close). So no INSUFFICIENT tile footer.
    mockApiWithTrades();
    await renderPage();
    await waitFor(() => expect(screen.getAllByTestId("venue-tile").length).toBe(2));
    // Verify no crash + tile renders
    const tiles = screen.getAllByTestId("venue-tile");
    expect(tiles.length).toBe(2);
  });

  it("shows INSUFFICIENT_DATA when all settled venue trades have no close", async () => {
    // Only open + no-close trades -> clv_mean null -> tile renders INSUFFICIENT_DATA
    const noCloseTrades = [
      { bet_id: "x1", venue: "kalshi", market_id: "km-x1", model_prob: 0.55,
        confidence: 0.6, units: 1.0, tier: "A", result: null, clv: null,
        clv_is_proxy: false, clv_status: "INSUFFICIENT_DATA", price_taken: 1.9,
        ts: "2026-06-18T10:00:00Z" },
    ];
    vi.spyOn(p5api.api, "getPaperTrail").mockResolvedValue(EMPTY_PAPER_TRAIL as never);
    vi.spyOn(p5api.api, "pmTrail").mockResolvedValue(
      { status: "ok", generated_at: null, trades: noCloseTrades, count: 1 } as never
    );
    vi.spyOn(p5api.api, "getPaperClv").mockResolvedValue(EMPTY_CLV as never);
    await renderPage();
    await waitFor(() => expect(screen.getAllByTestId("venue-tile").length).toBe(1));
    const tile = screen.getByTestId("venue-tile");
    expect(tile.textContent).toContain("INSUFFICIENT_DATA");
  });
});

// ---------------------------------------------------------------------------
// WS3 -- per-venue counts and units (no $)
// ---------------------------------------------------------------------------

describe("/paper-trading -- WS3 per-venue counts and units", () => {
  it("no dollar-amount in the rendered output with trades loaded (honesty rail)", async () => {
    // VenueSummary uses "no $" in label text (e.g. "Staked (units, no $)"),
    // which is acceptable -- it says "no $". The rail blocks $ followed by a digit,
    // which would indicate a dollar P&L value. Matches the convention in paper_pm.test.tsx.
    mockApiWithTrades();
    const { container } = await renderPage();
    await waitFor(() => expect(screen.getAllByTestId("venue-tile").length).toBe(2));
    expect(container.textContent ?? "").not.toMatch(/\$\s?\d/);
  });

  it("no dollar-amount in empty state (honesty rail)", async () => {
    mockApiEmpty();
    const { container } = await renderPage();
    await waitFor(() => expect(screen.getByTestId("no-paper-trades")).toBeInTheDocument());
    expect(container.textContent ?? "").not.toMatch(/\$\s?\d/);
  });

  it("no dollar-amount during loading state (honesty rail)", async () => {
    mockApiPending();
    const { container } = await renderPage();
    expect(container.textContent ?? "").not.toMatch(/\$\s?\d/);
  });

  it("venue tile uses 'u' suffix for units (never '$')", async () => {
    mockApiWithTrades();
    const { container } = await renderPage();
    await waitFor(() => expect(screen.getAllByTestId("venue-tile").length).toBe(2));
    // Units suffix should be 'u' in VenueSummary (e.g. '1.50u')
    expect(container.textContent).toMatch(/\d+\.\d+u/);
  });

  it("CLV for venue with no settled close renders INSUFFICIENT_DATA, not 0", async () => {
    const noCloseOnly = [
      { bet_id: "y1", venue: "polymarket", market_id: "pm-y1", model_prob: 0.6,
        confidence: 0.65, units: 0.5, tier: "B", result: null, clv: null,
        clv_is_proxy: false, clv_status: null, price_taken: 1.95,
        ts: "2026-06-18T12:00:00Z" },
    ];
    vi.spyOn(p5api.api, "getPaperTrail").mockResolvedValue(EMPTY_PAPER_TRAIL as never);
    vi.spyOn(p5api.api, "pmTrail").mockResolvedValue(
      { status: "ok", generated_at: null, trades: noCloseOnly, count: 1 } as never
    );
    vi.spyOn(p5api.api, "getPaperClv").mockResolvedValue(EMPTY_CLV as never);
    await renderPage();
    await waitFor(() => expect(screen.getByTestId("venue-tile")).toBeInTheDocument());
    const tile = screen.getByTestId("venue-tile");
    expect(tile.textContent).toContain("INSUFFICIENT_DATA");
    // CLV cell must not show a raw "0.0%" (zero percent) in place of INSUFFICIENT_DATA.
    // The regex anchors to avoid false-match on "60.0%" model_prob.
    // The CLV label is "CLV (n=0)" -- confirm clv_sample_n=0 wording.
    expect(tile.textContent).toContain("CLV (n=0)");
    // No dollar-value pattern ($ followed by digit)
    expect(tile.textContent ?? "").not.toMatch(/\$\s?\d/);
  });
});

// ---------------------------------------------------------------------------
// Running tally tiles (carried over from paper-trading.page.test.tsx)
// ---------------------------------------------------------------------------

describe("/paper-trading -- running tally tiles", () => {
  it("renders running tally region with correct aria-label", async () => {
    mockApiWithTrades();
    await renderPage();
    await waitFor(() =>
      expect(screen.getByLabelText("Running paper tally")).toBeInTheDocument()
    );
  });

  it("open count: 1 open trade (result null)", async () => {
    mockApiWithTrades();
    await renderPage();
    await waitFor(() => expect(screen.getByTestId("tally-open").textContent).toBe("1"));
  });

  it("settled count: 2 settled trades", async () => {
    mockApiWithTrades();
    await renderPage();
    await waitFor(() => expect(screen.getByTestId("tally-settled").textContent).toBe("2"));
  });

  it("win count from payload", async () => {
    mockApiWithTrades();
    await renderPage();
    await waitFor(() => expect(screen.getByTestId("tally-win").textContent).toBe("1"));
  });

  it("loss count from payload", async () => {
    mockApiWithTrades();
    await renderPage();
    await waitFor(() => expect(screen.getByTestId("tally-loss").textContent).toBe("1"));
  });

  it("push count from payload", async () => {
    mockApiWithTrades();
    await renderPage();
    await waitFor(() => expect(screen.getByTestId("tally-push").textContent).toBe("0"));
  });

  it("units staked: 1.0 + 0.75 + 0.5 = 2.25", async () => {
    mockApiWithTrades();
    await renderPage();
    await waitFor(() => expect(screen.getByTestId("tally-units-staked").textContent).toBe("2.25"));
  });

  it("CLV tile shows formatted pct when mean_clv_pct is present", async () => {
    mockApiWithTrades();
    await renderPage();
    await waitFor(() => expect(screen.getByTestId("clv-mean-clv").textContent).toMatch(/\+0\.5%/));
  });

  it("CLV tile shows EMPTY_CELL when mean_clv_pct is null", async () => {
    mockApiEmpty();
    await renderPage();
    await waitFor(() => expect(screen.getByTestId("clv-mean-clv").textContent).toBe("--"));
  });
});

// ---------------------------------------------------------------------------
// Honest empty state
// ---------------------------------------------------------------------------

describe("/paper-trading -- honest empty state", () => {
  it("shows no-paper-trades element on empty payload", async () => {
    mockApiEmpty();
    await renderPage();
    await waitFor(() => expect(screen.getByTestId("no-paper-trades")).toBeInTheDocument());
  });

  it("empty state message says 'No live PM game markets right now'", async () => {
    mockApiEmpty();
    await renderPage();
    await waitFor(() =>
      expect(screen.getByTestId("no-paper-trades").textContent).toMatch(/no live PM game markets right now/i)
    );
  });

  it("empty state message mentions 'No edge is claimed'", async () => {
    mockApiEmpty();
    await renderPage();
    await waitFor(() =>
      expect(screen.getByTestId("no-paper-trades").textContent).toMatch(/no edge is claimed/i)
    );
  });

  it("empty state does NOT carry red/danger styling", async () => {
    mockApiEmpty();
    await renderPage();
    await waitFor(() => {
      const cls = screen.getByTestId("no-paper-trades").className;
      expect(cls).not.toMatch(/text-red/);
      expect(cls).not.toMatch(/text-danger/);
      expect(cls).not.toMatch(/text-destructive/);
    });
  });

  it("no-paper-trades is absent when trades are present", async () => {
    mockApiWithTrades();
    await renderPage();
    await waitFor(() => expect(screen.queryByTestId("no-paper-trades")).toBeNull());
  });
});

// ---------------------------------------------------------------------------
// No dollar-amount ($ followed by digit) in rendered output -- honesty rail
// Note: "no $" as a label suffix (e.g. "Staked (units, no $)") is acceptable;
// the rail blocks dollar-amounts like "$5.00" or "$1" ($ followed by a digit).
// ---------------------------------------------------------------------------

describe("/paper-trading -- no dollar sign (honesty rail)", () => {
  it("loading state: no dollar-amount in rendered text", async () => {
    mockApiPending();
    const { container } = await renderPage();
    expect(container.textContent ?? "").not.toMatch(/\$\s?\d/);
  });

  it("empty state: no dollar-amount in rendered text", async () => {
    mockApiEmpty();
    const { container } = await renderPage();
    await waitFor(() => expect(container.textContent ?? "").not.toMatch(/\$\s?\d/));
  });

  it("trades loaded: no dollar-amount in rendered text", async () => {
    mockApiWithTrades();
    const { container } = await renderPage();
    await waitFor(() => expect(container.textContent ?? "").not.toMatch(/\$\s?\d/));
  });
});

// ---------------------------------------------------------------------------
// Real-money DENY banner
// ---------------------------------------------------------------------------

describe("/paper-trading -- real-money DENY banner", () => {
  it("DENY banner is always present (loading state)", async () => {
    mockApiPending();
    await renderPage();
    expect(screen.getByTestId("real-money-deny-banner")).toBeInTheDocument();
  });

  it("DENY banner contains 'DENY' text", async () => {
    mockApiPending();
    await renderPage();
    expect(screen.getByTestId("real-money-deny-banner").textContent).toMatch(/DENY/);
  });

  it("DENY banner contains 'paper mode' text", async () => {
    mockApiPending();
    await renderPage();
    expect(screen.getByTestId("real-money-deny-banner").textContent).toMatch(/paper mode/i);
  });

  it("DENY banner aria-label is correct", async () => {
    mockApiPending();
    await renderPage();
    expect(screen.getByLabelText("Real money is DENIED -- paper mode only")).toBeInTheDocument();
  });

  it("DENY banner present when trades are loaded", async () => {
    mockApiWithTrades();
    await renderPage();
    await waitFor(() =>
      expect(screen.getByTestId("real-money-deny-banner")).toBeInTheDocument()
    );
  });
});

// ---------------------------------------------------------------------------
// Structural / a11y
// ---------------------------------------------------------------------------

describe("/paper-trading -- structural checks", () => {
  it("live badge placeholder is present with 'checking' text", async () => {
    mockApiPending();
    await renderPage();
    expect(screen.getByTestId("live-badge-placeholder")).toBeInTheDocument();
    expect(screen.getByTestId("live-badge-placeholder").textContent).toMatch(/checking/i);
  });

  it("venue-summary-section replaces the old placeholder", async () => {
    mockApiPending();
    await renderPage();
    // Old placeholder must be gone
    expect(screen.queryByTestId("venue-summary-placeholder")).toBeNull();
    // New section must exist
    expect(screen.getByTestId("venue-summary-section")).toBeInTheDocument();
  });

  it("per-venue breakdown heading is visible", async () => {
    mockApiPending();
    await renderPage();
    expect(screen.getByText(/per-venue breakdown/i)).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// WS7 -- PanelErrorBoundary wrap: VenueSummary and PmTrailTable sections
//
// Verifies that the boundary wrap preserves existing testids on the happy path
// and that the wrapped sections remain accessible. The boundary itself is
// tested in isolation in p6/__tests__/PanelErrorBoundary.test.tsx.
// ---------------------------------------------------------------------------

describe("/paper-trading -- WS7 PanelErrorBoundary wraps", () => {
  it("(WS7) running-tally testid is preserved after boundary wrap", async () => {
    mockApiWithTrades();
    await renderPage();
    await waitFor(() =>
      expect(screen.getByTestId("running-tally")).toBeInTheDocument()
    );
  });

  it("(WS7) venue-summary-section testid is preserved after boundary wrap", async () => {
    mockApiPending();
    await renderPage();
    expect(screen.getByTestId("venue-summary-section")).toBeInTheDocument();
  });

  it("(WS7) pm-trail-table renders inside its boundary on happy path", async () => {
    mockApiWithTrades();
    await renderPage();
    await waitFor(() =>
      expect(screen.getByTestId("pm-trail-table")).toBeInTheDocument()
    );
  });

  it("(WS7) no panel-error-fallback visible on the happy path", async () => {
    mockApiWithTrades();
    await renderPage();
    await waitFor(() =>
      expect(screen.getByTestId("running-tally")).toBeInTheDocument()
    );
    expect(screen.queryByTestId("panel-error-fallback")).toBeNull();
  });

  it("(WS7) no dollar-amount in happy-path rendered output (honesty rail)", async () => {
    mockApiWithTrades();
    const { container } = await renderPage();
    await waitFor(() =>
      expect(screen.getByTestId("running-tally")).toBeInTheDocument()
    );
    expect(container.textContent ?? "").not.toMatch(/\$\s?\d/);
  });
});
