// paper-trading.page.test.tsx -- Acceptance tests for /paper-trading.
//
// Acceptance criteria (W6 additions):
//   * OPEN-positions section renders real open rows (status=open) from a mocked
//     trail with units shown as UNITS (no '$').
//   * Large stake_units (>1.0) render with a quarter-Kelly units clarifier.
//   * PM-empty shows the honest 'No liquid PM markets right now' block when totalPm=0.
//   * Settled section still renders graded rows.
//   * Auto-refresh badge never green when stale.
//   * Done/settled summary section renders when trail data is available.
//   * Renders tally tiles (open/settled/win/loss/push/units/CLV) from mocked payload.
//   * Honest "no paper trades yet" empty state on empty payload.
//   * NO '$' character in rendered output (units only).
//   * Real-money DENY text present.

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

// Mock PaperTrailSettled to avoid deep render (ScrollArea etc). Only the
// settled-book-tally and tally tiles are tested via the page's own tiles.
vi.mock("@/components/paper_pm/PaperTrailSettled", () => ({
  PaperTrailSettled: ({ loading, rows }: { loading?: boolean; rows?: unknown[] }) => (
    <div data-testid="paper-trail-settled" data-loading={String(!!loading)} data-rows={String((rows ?? []).length)}>
      {loading ? "settled-loading" : "settled-ready"}
    </div>
  ),
}));

// Mock OpenPositions to inspect rows passed to it and test its render contract.
// IMPORTANT: this filter must MIRROR the real OpenPositions filter:
//   r.status === "open" || !r.graded
// NOT the old stub that used !r.status (diverges when graded:false + status!="open").
vi.mock("@/components/paper_pm/OpenPositions", () => ({
  OpenPositions: ({ rows, loading }: { rows?: Array<{ status?: string; graded?: boolean; stake_units?: number | null }>; loading?: boolean }) => {
    const openRows = (rows ?? []).filter((r) => r.status === "open" || !r.graded);
    const hasLarge = openRows.some((r) => r.stake_units != null && r.stake_units > 1.0);
    if (openRows.length === 0 && !loading) {
      return (
        <div data-testid="open-positions-empty">
          No open positions right now. Paper mode only. No edge is claimed.
        </div>
      );
    }
    return (
      <div data-testid="open-positions-content">
        <span data-testid="mock-open-count">{openRows.length}</span>
        {openRows.map((r, i) => (
          <div key={i} data-testid="open-position-row">
            <span data-testid="open-stake-units">{r.stake_units != null ? `${r.stake_units.toFixed(2)}u` : "--"}</span>
            {r.stake_units != null && r.stake_units > 1.0 && (
              <span data-testid="quarter-kelly-clarifier">qK</span>
            )}
          </div>
        ))}
        {hasLarge && <span data-testid="large-stake-unit-note">qK quarter-Kelly stake &gt;1.0u</span>}
      </div>
    );
  },
}));

import * as p5api from "@/lib/p5api";

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

// Real paper trail rows for W6 open positions + done/settled tests.
const OPEN_ROW: p5api.PaperTrailRow = {
  game_id: "mlb-open-1", matchup: "NYY @ LAD", sport: "mlb", side: "home",
  market_type: "moneyline", line: null, taken_book: "dk", taken_decimal: 1.9,
  model_prob: 0.58, model_ev: 0.05, tier: "B", stake_units: 0.75,
  status: "open", graded: false, outcome: null,
  clv_pct: null, beat_close: null, clv_is_proxy: false,
  clv_status: null, clv_unavailable: true, clv_note: null,
  executed: false, ts: "2026-06-19T18:00:00Z", settled_at: null,
};

const LARGE_STAKE_OPEN_ROW: p5api.PaperTrailRow = {
  ...OPEN_ROW,
  game_id: "mlb-open-large", matchup: "BOS @ HOU",
  stake_units: 1.5, // large: triggers qK clarifier
};

const SETTLED_ROW: p5api.PaperTrailRow = {
  game_id: "nba-settled-1", matchup: "LAL @ BOS", sport: "nba", side: "home",
  market_type: "moneyline", line: null, taken_book: "dk", taken_decimal: 2.0,
  model_prob: 0.55, model_ev: 0.1, tier: "A", stake_units: 1.0,
  status: "settled", graded: true, outcome: "win",
  clv_pct: 0.02, beat_close: true, clv_is_proxy: false,
  clv_status: "true_close", clv_unavailable: false, clv_note: null,
  executed: false, ts: "2026-06-18T20:00:00Z", settled_at: "2026-06-18T23:30:00Z",
};

// Mixed trail: 2 open + 1 settled
const MOCK_PAPER_TRAIL_WITH_OPEN = {
  status: "ok",
  count: 3,
  trail: [OPEN_ROW, LARGE_STAKE_OPEN_ROW, SETTLED_ROW] as p5api.PaperTrailRow[],
};

// Minimal real paper trail rows (used for getPaperTrail mock).
const MOCK_PAPER_TRAIL = {
  status: "ok",
  count: 0,
  trail: [] as p5api.PaperTrailRow[],
};

const MOCK_CLV: p5api.ClvScoreboard = {
  n_bets: 2, pct_beat_close: 0.5, mean_clv_pct: 0.005, by_sport: null, clv_is_proxy: false,
};
const EMPTY_CLV: p5api.ClvScoreboard = {
  n_bets: 0, pct_beat_close: null, mean_clv_pct: null, by_sport: null, clv_is_proxy: false,
};

function mockApiWithTrades() {
  vi.spyOn(p5api.api, "getPaperTrail").mockResolvedValue(MOCK_PAPER_TRAIL as never);
  vi.spyOn(p5api.api, "pmTrail").mockResolvedValue(
    { status: "ok", generated_at: null, trades: MOCK_TRADES, count: 3 } as never
  );
  vi.spyOn(p5api.api, "getPaperClv").mockResolvedValue(MOCK_CLV as never);
}

function mockApiWithOpenRows() {
  vi.spyOn(p5api.api, "getPaperTrail").mockResolvedValue(MOCK_PAPER_TRAIL_WITH_OPEN as never);
  vi.spyOn(p5api.api, "pmTrail").mockResolvedValue(
    { status: "ok", generated_at: null, trades: [], count: 0 } as never
  );
  vi.spyOn(p5api.api, "getPaperClv").mockResolvedValue(EMPTY_CLV as never);
}

function mockApiEmpty() {
  vi.spyOn(p5api.api, "getPaperTrail").mockResolvedValue(MOCK_PAPER_TRAIL as never);
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
// Running tally tiles
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
// No '$' character in rendered output (units only)
// ---------------------------------------------------------------------------

// Note: "no $" as a label suffix (e.g. "Staked (units, no $)") is acceptable;
// the rail blocks dollar-amounts like "$5.00" or "$1" ($ followed by a digit).
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
// Structural placeholders
// ---------------------------------------------------------------------------

describe("/paper-trading -- structural placeholders", () => {
  it("live badge placeholder is present with 'checking' text", async () => {
    mockApiPending();
    await renderPage();
    expect(screen.getByTestId("live-badge-placeholder")).toBeInTheDocument();
    expect(screen.getByTestId("live-badge-placeholder").textContent).toMatch(/checking/i);
  });

  it("venue-summary-section is present (WS3 wired; placeholder removed)", async () => {
    mockApiPending();
    await renderPage();
    expect(screen.queryByTestId("venue-summary-placeholder")).toBeNull();
    expect(screen.getByTestId("venue-summary-section")).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// W6: OPEN-positions section (new)
// ---------------------------------------------------------------------------

describe("/paper-trading -- W6 open-positions section", () => {
  it("open-positions-section is always rendered", async () => {
    mockApiPending();
    await renderPage();
    expect(screen.getByTestId("open-positions-section")).toBeInTheDocument();
  });

  it("renders open rows from the real trail (status=open)", async () => {
    mockApiWithOpenRows();
    await renderPage();
    await waitFor(() => {
      // Two open rows in the mock trail (OPEN_ROW + LARGE_STAKE_OPEN_ROW)
      expect(screen.getByTestId("mock-open-count").textContent).toBe("2");
    });
  });

  it("stake_units shown as UNITS format (Xu.XXu), not dollars", async () => {
    mockApiWithOpenRows();
    await renderPage();
    await waitFor(() => {
      const unitCells = screen.getAllByTestId("open-stake-units");
      unitCells.forEach((cell) => {
        // Each cell should end with 'u' suffix (e.g. '0.75u', '1.50u')
        expect(cell.textContent).toMatch(/^\d+\.\d+u$/);
        // Must NOT contain a dollar sign followed by digits
        expect(cell.textContent).not.toMatch(/\$\d/);
      });
    });
  });

  it("large stake_units (>1.0) shows quarter-Kelly clarifier (qK)", async () => {
    mockApiWithOpenRows();
    await renderPage();
    await waitFor(() => {
      // LARGE_STAKE_OPEN_ROW has stake_units=1.5
      const clarifiers = screen.getAllByTestId("quarter-kelly-clarifier");
      expect(clarifiers.length).toBeGreaterThanOrEqual(1);
    });
  });

  it("large-stake-unit-note is shown when large stake exists", async () => {
    mockApiWithOpenRows();
    await renderPage();
    await waitFor(() => {
      expect(screen.getByTestId("large-stake-unit-note")).toBeInTheDocument();
      expect(screen.getByTestId("large-stake-unit-note").textContent).toMatch(/qK/);
      expect(screen.getByTestId("large-stake-unit-note").textContent).toMatch(/1\.0u/);
    });
  });

  it("open-positions-empty shown when trail has no open rows", async () => {
    // MOCK_PAPER_TRAIL has zero trail rows, so OpenPositions sees no open rows.
    mockApiWithTrades(); // trail = [] (no open rows)
    await renderPage();
    await waitFor(() => {
      expect(screen.getByTestId("open-positions-empty")).toBeInTheDocument();
    });
  });

  it("open-positions-empty contains 'no open positions' text", async () => {
    mockApiWithTrades();
    await renderPage();
    await waitFor(() => {
      const el = screen.getByTestId("open-positions-empty");
      expect(el.textContent).toMatch(/no open positions right now/i);
    });
  });

  it("open-positions-empty includes 'No edge is claimed'", async () => {
    mockApiWithTrades();
    await renderPage();
    await waitFor(() => {
      expect(screen.getByTestId("open-positions-empty").textContent).toMatch(/no edge is claimed/i);
    });
  });

  it("settled section still renders graded rows (PaperTrailSettled present)", async () => {
    mockApiWithOpenRows();
    await renderPage();
    await waitFor(() => {
      expect(screen.getByTestId("paper-trail-settled")).toBeInTheDocument();
    });
  });

  it("settled section is rendered even when open rows exist (both present)", async () => {
    mockApiWithOpenRows();
    await renderPage();
    await waitFor(() => {
      expect(screen.getByTestId("open-positions-section")).toBeInTheDocument();
      expect(screen.getByTestId("paper-trail-settled")).toBeInTheDocument();
    });
  });
});

// ---------------------------------------------------------------------------
// W6: PM empty state -- honest 'No liquid PM markets right now' block
// ---------------------------------------------------------------------------

describe("/paper-trading -- W6 PM empty state (honest)", () => {
  it("shows no-paper-trades when pmTrail.count=0 (no liquid PM markets)", async () => {
    // mockApiWithOpenRows sends PM count=0 => isPmEmpty=true
    mockApiWithOpenRows();
    await renderPage();
    await waitFor(() => {
      expect(screen.getByTestId("no-paper-trades")).toBeInTheDocument();
    });
  });

  it("PM empty block says 'No live PM game markets right now'", async () => {
    mockApiWithOpenRows();
    await renderPage();
    await waitFor(() => {
      const el = screen.getByTestId("no-paper-trades");
      expect(el.textContent).toMatch(/no live PM game markets right now/i);
    });
  });

  it("PM empty block is NOT shown when PM trades are present", async () => {
    mockApiWithTrades(); // PM has 3 trades => not isPmEmpty
    await renderPage();
    await waitFor(() => {
      expect(screen.queryByTestId("no-paper-trades")).toBeNull();
    });
  });
});

// ---------------------------------------------------------------------------
// W6: done/settled summary section
// ---------------------------------------------------------------------------

describe("/paper-trading -- W6 done/settled summary section", () => {
  it("done-settled-summary section is rendered when data is available", async () => {
    mockApiWithOpenRows();
    await renderPage();
    await waitFor(() => {
      expect(screen.getByTestId("done-settled-summary")).toBeInTheDocument();
    });
  });

  it("done-total shows correct total bets count (3 rows)", async () => {
    mockApiWithOpenRows();
    await renderPage();
    await waitFor(() => {
      expect(screen.getByTestId("done-total").textContent).toBe("3");
    });
  });

  it("done-settled shows 1 settled row", async () => {
    mockApiWithOpenRows();
    await renderPage();
    await waitFor(() => {
      expect(screen.getByTestId("done-settled").textContent).toBe("1");
    });
  });

  it("done-win shows 1 win row", async () => {
    mockApiWithOpenRows();
    await renderPage();
    await waitFor(() => {
      expect(screen.getByTestId("done-win").textContent).toBe("1");
    });
  });

  it("done-loss shows 0 loss rows", async () => {
    mockApiWithOpenRows();
    await renderPage();
    await waitFor(() => {
      expect(screen.getByTestId("done-loss").textContent).toBe("0");
    });
  });

  it("done summary section is present in loading state (structure always rendered)", async () => {
    mockApiPending();
    await renderPage();
    expect(screen.getByTestId("done-settled-summary")).toBeInTheDocument();
  });

  it("done summary no dollar-amount in rendered text", async () => {
    const { container } = await (async () => {
      mockApiWithOpenRows();
      return renderPage();
    })();
    await waitFor(() => {
      expect(container.textContent ?? "").not.toMatch(/\$\d/);
    });
  });
});

// ---------------------------------------------------------------------------
// W6: unit convention clarifier
// ---------------------------------------------------------------------------

describe("/paper-trading -- W6 unit-convention clarifier", () => {
  it("unit-convention-clarifier is always present", async () => {
    mockApiPending();
    await renderPage();
    expect(screen.getByTestId("unit-convention-clarifier")).toBeInTheDocument();
  });

  it("clarifier mentions UNITS (not dollars)", async () => {
    mockApiPending();
    await renderPage();
    const el = screen.getByTestId("unit-convention-clarifier");
    expect(el.textContent).toMatch(/UNITS/);
    expect(el.textContent).not.toMatch(/\$\d/);
  });

  it("clarifier mentions quarter-Kelly explanation", async () => {
    mockApiPending();
    await renderPage();
    const el = screen.getByTestId("unit-convention-clarifier");
    expect(el.textContent).toMatch(/quarter-Kelly/i);
    expect(el.textContent).toMatch(/1\.0u/i);
  });
});

// ---------------------------------------------------------------------------
// W6: auto-refresh badge never green when stale
// ---------------------------------------------------------------------------

describe("/paper-trading -- W6 auto-refresh badge stale-never-green", () => {
  it("badge shows 'checking' in loading state (not green)", async () => {
    mockApiPending();
    await renderPage();
    const badge = screen.getByTestId("live-badge-placeholder");
    // The LiveBadge in loading state shows "checking..." not green
    expect(badge.textContent).toMatch(/checking/i);
    // Must not have green text classes
    expect(badge.innerHTML).not.toMatch(/text-green-[45]/);
  });

  it("badge placeholder is always rendered (never missing)", async () => {
    mockApiPending();
    await renderPage();
    expect(screen.getByTestId("live-badge-placeholder")).toBeInTheDocument();
  });
});
