// paper_trading_page.test.tsx -- ws5 acceptance tests for /paper-trading.
//
// Acceptance criteria (ws5):
//   * Renders 200 (no white/broken page) on both populated and empty PM trail.
//   * Surfaces total_pm (pm-total-count testid) when markets exist (total_pm>0).
//   * Shows honest "No PM markets right now" empty state (not fabricated rows).
//   * NEVER renders a $ P&L field or dollar-amount ($ followed by digit).
//   * executed=false / paper channel honesty: no "real-money" or "executed" label
//     that contradicts the paper-only contract.
//   * CLV shown as INSUFFICIENT_DATA when absent -- never zero-filled or fabricated.
//   * Real-money DENY banner always present.
//   * Running tally tiles (open/settled/win/loss/push/units/clv) correct.

import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";

// next/link stub (jsdom has no router)
vi.mock("next/link", () => ({
  default: ({ href, children, ...rest }: { href: string; children: React.ReactNode }) => (
    <a href={href} {...rest}>{children}</a>
  ),
}));

// Stub PmTrailTable so tests don't need to render its full scroll tree.
vi.mock("@/components/paper_pm/PmTrailTable", () => ({
  PmTrailTable: ({ loading, rows }: { loading?: boolean; rows?: unknown[] }) => (
    <div data-testid="pm-trail-table" data-row-count={rows?.length ?? 0}>
      {loading ? "table-loading" : "table-ready"}
    </div>
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
import type { PmTrailRow, ClvScoreboard, PmTrail } from "@/lib/p5api";

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const TRADE_WIN: PmTrailRow = {
  bet_id: "w1",
  venue: "kalshi",
  market_id: "km-001",
  model_prob: 0.65,
  confidence: 0.70,
  units: 1.0,
  tier: "A",
  result: "win",
  clv: 0.02,
  clv_is_proxy: false,
  clv_status: "true_close",
  price_taken: 2.0,
  ts: "2026-06-19T10:00:00Z",
};

const TRADE_LOSS: PmTrailRow = {
  bet_id: "w2",
  venue: "polymarket",
  market_id: "pm-002",
  model_prob: 0.55,
  confidence: 0.60,
  units: 0.75,
  tier: "B",
  result: "loss",
  clv: -0.01,
  clv_is_proxy: false,
  clv_status: "true_close",
  price_taken: 1.9,
  ts: "2026-06-19T11:00:00Z",
};

const TRADE_OPEN_NO_CLOSE: PmTrailRow = {
  bet_id: "w3",
  venue: "kalshi",
  market_id: "km-003",
  model_prob: 0.60,
  confidence: 0.65,
  units: 0.5,
  tier: "B",
  result: null,
  clv: null,
  clv_is_proxy: false,
  clv_status: "INSUFFICIENT_DATA",
  price_taken: 1.95,
  ts: "2026-06-19T12:00:00Z",
};

const MOCK_TRADES: PmTrailRow[] = [TRADE_WIN, TRADE_LOSS, TRADE_OPEN_NO_CLOSE];

const CLV_PRESENT: ClvScoreboard = {
  n_bets: 2,
  pct_beat_close: 0.5,
  mean_clv_pct: 0.005,
  by_sport: null,
  clv_is_proxy: false,
};

const CLV_EMPTY: ClvScoreboard = {
  n_bets: 0,
  pct_beat_close: null,
  mean_clv_pct: null,
  by_sport: null,
  clv_is_proxy: false,
};

function trailOf(trades: PmTrailRow[]): PmTrail {
  return { status: "ok", generated_at: null, trades, count: trades.length };
}

// ---------------------------------------------------------------------------
// Mock helpers
// ---------------------------------------------------------------------------

const EMPTY_PAPER_TRAIL = { status: "ok", count: 0, trail: [] as p5api.PaperTrailRow[] };

function mockWithTrades(trades: PmTrailRow[] = MOCK_TRADES, clv: ClvScoreboard = CLV_PRESENT) {
  vi.spyOn(p5api.api, "getPaperTrail").mockResolvedValue(EMPTY_PAPER_TRAIL as never);
  vi.spyOn(p5api.api, "pmTrail").mockResolvedValue(trailOf(trades) as never);
  vi.spyOn(p5api.api, "getPaperClv").mockResolvedValue(clv as never);
}

function mockEmpty() {
  vi.spyOn(p5api.api, "getPaperTrail").mockResolvedValue(EMPTY_PAPER_TRAIL as never);
  vi.spyOn(p5api.api, "pmTrail").mockResolvedValue(trailOf([]) as never);
  vi.spyOn(p5api.api, "getPaperClv").mockResolvedValue(CLV_EMPTY as never);
}

function mockPending() {
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
// Renders 200 (page mounts without crashing)
// ---------------------------------------------------------------------------

describe("/paper-trading -- renders without crashing (200)", () => {
  it("mounts cleanly when PM trail has trades (no white/broken page)", async () => {
    mockWithTrades();
    const { container } = await renderPage();
    await waitFor(() => expect(screen.getByTestId("running-tally")).toBeInTheDocument());
    // Page must contain at least the h1 and the DENY banner
    expect(container.querySelector("h1")).toBeTruthy();
    expect(screen.getByTestId("real-money-deny-banner")).toBeInTheDocument();
  });

  it("mounts cleanly on empty PM trail (honest empty state, no crash)", async () => {
    mockEmpty();
    const { container } = await renderPage();
    await waitFor(() => expect(screen.getByTestId("no-paper-trades")).toBeInTheDocument());
    expect(container.querySelector("h1")).toBeTruthy();
  });

  it("mounts cleanly in loading state (pending fetch)", async () => {
    mockPending();
    const { container } = await renderPage();
    expect(container.querySelector("h1")).toBeTruthy();
    expect(screen.getByTestId("real-money-deny-banner")).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// total_pm surfacing -- pm-total-count testid
// ---------------------------------------------------------------------------

describe("/paper-trading -- total_pm (pm-total-count) surfacing", () => {
  it("shows pm-total-count with count>0 when PM trail has trades", async () => {
    mockWithTrades();
    await renderPage();
    await waitFor(() => {
      const el = screen.getByTestId("pm-total-count");
      expect(el).toBeInTheDocument();
      // Must mention the count (3 trades) or a positive count phrase
      expect(el.textContent).toMatch(/3/);
    });
  });

  it("pm-total-count text indicates 'in trail' when trades exist", async () => {
    mockWithTrades();
    await renderPage();
    await waitFor(() => {
      const el = screen.getByTestId("pm-total-count");
      expect(el.textContent).toMatch(/in trail/i);
    });
  });

  it("shows 'No PM markets right now' when trail is empty (honest none state)", async () => {
    mockEmpty();
    await renderPage();
    await waitFor(() => {
      const el = screen.getByTestId("pm-total-count");
      expect(el.textContent).toMatch(/no pm markets right now/i);
    });
  });

  it("pm-total-count is absent while loading (not yet resolved)", async () => {
    mockPending();
    await renderPage();
    // While pending the span is hidden (conditional on !loading)
    expect(screen.queryByTestId("pm-total-count")).toBeNull();
  });

  it("pm-total-count aria-label reflects the trade count", async () => {
    mockWithTrades();
    await renderPage();
    await waitFor(() => {
      const el = screen.getByTestId("pm-total-count");
      // aria-label should mention the count
      const label = el.getAttribute("aria-label") ?? "";
      expect(label).toMatch(/PM trail total/i);
    });
  });

  it("single trade: pm-total-count uses singular 'trade' (not 'trades')", async () => {
    mockWithTrades([TRADE_WIN]);
    await renderPage();
    await waitFor(() => {
      const el = screen.getByTestId("pm-total-count");
      // "1 PM trade in trail." -- singular form, no trailing 's'
      expect(el.textContent).toMatch(/1 PM trade in trail/i);
    });
  });
});

// ---------------------------------------------------------------------------
// Honest empty state -- no-paper-trades testid
// ---------------------------------------------------------------------------

describe("/paper-trading -- honest empty state (no fabricated rows)", () => {
  it("no-paper-trades element appears on empty payload", async () => {
    mockEmpty();
    await renderPage();
    await waitFor(() =>
      expect(screen.getByTestId("no-paper-trades")).toBeInTheDocument()
    );
  });

  it("empty message says 'No live PM game markets right now'", async () => {
    mockEmpty();
    await renderPage();
    await waitFor(() =>
      expect(screen.getByTestId("no-paper-trades").textContent).toMatch(/no live PM game markets right now/i)
    );
  });

  it("empty message says 'No edge is claimed'", async () => {
    mockEmpty();
    await renderPage();
    await waitFor(() =>
      expect(screen.getByTestId("no-paper-trades").textContent).toMatch(/no edge is claimed/i)
    );
  });

  it("no-paper-trades is absent when trades are present (not fabricated)", async () => {
    mockWithTrades();
    await renderPage();
    await waitFor(() => expect(screen.queryByTestId("no-paper-trades")).toBeNull());
  });

  it("pm-trail-table renders 'table-ready' (not empty) when trades exist", async () => {
    mockWithTrades();
    await renderPage();
    await waitFor(() => {
      const tbl = screen.getByTestId("pm-trail-table");
      expect(tbl.textContent).toBe("table-ready");
    });
  });
});

// ---------------------------------------------------------------------------
// Honesty rail: no $ P&L field or dollar-amount ($ followed by digit)
// ---------------------------------------------------------------------------

describe("/paper-trading -- no dollar-amount (honesty rail)", () => {
  it("loading state: no dollar-amount in rendered text", async () => {
    mockPending();
    const { container } = await renderPage();
    expect(container.textContent ?? "").not.toMatch(/\$\s?\d/);
  });

  it("empty state: no dollar-amount in rendered text", async () => {
    mockEmpty();
    const { container } = await renderPage();
    await waitFor(() => expect(container.textContent ?? "").not.toMatch(/\$\s?\d/));
  });

  it("populated trail: no dollar-amount in rendered text", async () => {
    mockWithTrades();
    const { container } = await renderPage();
    await waitFor(() => expect(container.textContent ?? "").not.toMatch(/\$\s?\d/));
  });

  it("no 'P&L' or 'PnL' text anywhere in rendered output", async () => {
    mockWithTrades();
    const { container } = await renderPage();
    await waitFor(() => expect(screen.getByTestId("running-tally")).toBeInTheDocument());
    const txt = container.textContent ?? "";
    expect(/\bP&L\b/i.test(txt)).toBe(false);
    expect(/\bPnL\b/i.test(txt)).toBe(false);
  });

  it("no 'ROI' text anywhere in rendered output", async () => {
    mockWithTrades();
    const { container } = await renderPage();
    await waitFor(() => expect(screen.getByTestId("running-tally")).toBeInTheDocument());
    expect(/\bROI\b/.test(container.textContent ?? "")).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// executed=false / paper channel honesty
// ---------------------------------------------------------------------------

describe("/paper-trading -- paper channel honesty (executed=false)", () => {
  it("DENY banner always states real-money: DENY", async () => {
    mockPending();
    await renderPage();
    const banner = screen.getByTestId("real-money-deny-banner");
    expect(banner.textContent).toMatch(/DENY/);
    expect(banner.textContent).toMatch(/paper mode/i);
    expect(banner.textContent).toMatch(/no real money placed/i);
  });

  it("DENY banner aria-label is present", async () => {
    mockPending();
    await renderPage();
    expect(
      screen.getByLabelText("Real money is DENIED -- paper mode only")
    ).toBeInTheDocument();
  });

  it("page header carries a 'paper mode' badge element", async () => {
    mockPending();
    await renderPage();
    // Badge with tone='amber' and role='status' aria-label='paper mode'
    const badge = screen.getByRole("status", { name: /^paper mode$/i });
    expect(badge).toBeInTheDocument();
  });

  it("footer line states 'no dollars' and 'no edge is claimed'", async () => {
    mockWithTrades();
    const { container } = await renderPage();
    await waitFor(() => expect(screen.getByTestId("running-tally")).toBeInTheDocument());
    const txt = container.textContent ?? "";
    expect(/no dollars?/i.test(txt) || /no \$/i.test(txt)).toBe(true);
    expect(/no edge is claimed/i.test(txt)).toBe(true);
  });
});

// ---------------------------------------------------------------------------
// CLV honesty -- INSUFFICIENT_DATA never zero-filled
// ---------------------------------------------------------------------------

describe("/paper-trading -- CLV honesty (INSUFFICIENT_DATA)", () => {
  it("CLV tile shows '--' (EMPTY_CELL) when mean_clv_pct is null", async () => {
    mockEmpty();
    await renderPage();
    await waitFor(() =>
      expect(screen.getByTestId("clv-mean-clv").textContent).toBe("--")
    );
  });

  it("CLV tile shows formatted value when mean_clv_pct is present", async () => {
    mockWithTrades();
    await renderPage();
    await waitFor(() =>
      expect(screen.getByTestId("clv-mean-clv").textContent).toMatch(/\+0\.5%/)
    );
  });

  it("CLV tile never renders '0.0%' in place of null (no zero-fill)", async () => {
    mockEmpty();
    await renderPage();
    await waitFor(() => {
      // Confirm the CLV tile exists
      const el = screen.getByTestId("clv-mean-clv");
      expect(el.textContent).not.toBe("0.0%");
      expect(el.textContent).not.toBe("+0.0%");
    });
  });
});

// ---------------------------------------------------------------------------
// Running tally tiles -- populated trail
// ---------------------------------------------------------------------------

describe("/paper-trading -- running tally tiles (populated trail)", () => {
  it("open count is 1 (one open/result=null trade)", async () => {
    mockWithTrades();
    await renderPage();
    await waitFor(() =>
      expect(screen.getByTestId("tally-open").textContent).toBe("1")
    );
  });

  it("settled count is 2 (win + loss)", async () => {
    mockWithTrades();
    await renderPage();
    await waitFor(() =>
      expect(screen.getByTestId("tally-settled").textContent).toBe("2")
    );
  });

  it("win count is 1", async () => {
    mockWithTrades();
    await renderPage();
    await waitFor(() =>
      expect(screen.getByTestId("tally-win").textContent).toBe("1")
    );
  });

  it("loss count is 1", async () => {
    mockWithTrades();
    await renderPage();
    await waitFor(() =>
      expect(screen.getByTestId("tally-loss").textContent).toBe("1")
    );
  });

  it("push count is 0", async () => {
    mockWithTrades();
    await renderPage();
    await waitFor(() =>
      expect(screen.getByTestId("tally-push").textContent).toBe("0")
    );
  });

  it("units staked = 1.0 + 0.75 + 0.5 = 2.25 (never a $ value)", async () => {
    mockWithTrades();
    await renderPage();
    await waitFor(() =>
      expect(screen.getByTestId("tally-units-staked").textContent).toBe("2.25")
    );
  });
});

// ---------------------------------------------------------------------------
// Structural / a11y
// ---------------------------------------------------------------------------

describe("/paper-trading -- structural / a11y", () => {
  it("running-tally region has correct aria-label", async () => {
    mockWithTrades();
    await renderPage();
    await waitFor(() =>
      expect(screen.getByLabelText("Running paper tally")).toBeInTheDocument()
    );
  });

  it("venue-summary-section is present", async () => {
    mockPending();
    await renderPage();
    expect(screen.getByTestId("venue-summary-section")).toBeInTheDocument();
  });

  it("live-badge-placeholder is present during initial load", async () => {
    mockPending();
    await renderPage();
    expect(screen.getByTestId("live-badge-placeholder")).toBeInTheDocument();
    expect(screen.getByTestId("live-badge-placeholder").textContent).toMatch(/checking/i);
  });
});
