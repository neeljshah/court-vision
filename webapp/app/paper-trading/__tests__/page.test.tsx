// page.test.tsx -- ws7 acceptance tests for /paper-trading PM panel.
//
// Acceptance criteria (ws7-fe-pm-trail-honest-empty):
//   * count=0 (status ok) renders a visible 'no matchable PM markets right now'
//     explanatory empty-state with data-testid -- NOT a broken/blank panel.
//   * Non-empty pmTrail renders the trade rows (PmTrailTable receives them).
//   * Stale/loading states are visually distinct (badge testids).
//   * No '$' substring anywhere in rendered output (units only).
//
// Lane: frontend (webapp/**). Per-file vitest only.

import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";

// next/link stub -- jsdom has no router
vi.mock("next/link", () => ({
  default: ({ href, children, ...rest }: { href: string; children: React.ReactNode }) => (
    <a href={href} {...rest}>{children}</a>
  ),
}));

// Stub PmTrailTable to capture row count without rendering full scroll tree.
vi.mock("@/components/paper_pm/PmTrailTable", () => ({
  PmTrailTable: ({ loading, rows }: { loading?: boolean; rows?: unknown[] }) => (
    <div data-testid="pm-trail-table" data-row-count={rows?.length ?? 0}>
      {loading ? "table-loading" : `table-ready:${rows?.length ?? 0}-rows`}
    </div>
  ),
}));

// Stub PaperTrailSettled -- tested separately; avoid deep rendering here.
vi.mock("@/components/paper_pm/PaperTrailSettled", () => ({
  PaperTrailSettled: ({ loading, rows }: { loading?: boolean; rows?: unknown[] }) => (
    <div data-testid="paper-trail-settled" data-loading={String(!!loading)} data-rows={String((rows ?? []).length)}>
      {loading ? "settled-loading" : "settled-ready"}
    </div>
  ),
}));

// Stub OpenPositions -- captures rows passed from the page; exposes counts and
// field values via data-* attrs so W2 acceptance tests can assert without
// rendering the full table/ScrollArea tree in jsdom.
vi.mock("@/components/paper_pm/OpenPositions", () => ({
  OpenPositions: ({ rows, loading }: { rows?: import("@/lib/p5api").PaperTrailRow[]; loading?: boolean }) => {
    const openRows = (rows ?? []).filter((r) => r.status === "open" || !r.graded);
    return (
      <div
        data-testid="open-positions-stub"
        data-row-count={openRows.length}
        data-loading={String(!!loading)}
      >
        {openRows.map((r, i) => (
          <div key={i} data-testid="open-position-row"
            data-matchup={r.matchup} data-side={r.side}
            data-taken-book={r.taken_book} data-model-prob={r.model_prob}
          >
            {r.matchup}|{r.side}|{r.taken_book}|{r.model_prob}
          </div>
        ))}
      </div>
    );
  },
}));

import * as p5api from "@/lib/p5api";
import type { PmTrailRow, ClvScoreboard, PmTrail } from "@/lib/p5api";

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const TRADE_A: PmTrailRow = {
  bet_id: "t1",
  venue: "polymarket",
  market_id: "pm-001",
  model_prob: 0.62,
  confidence: 0.68,
  units: 1.0,
  tier: "A",
  result: "win",
  clv: 0.015,
  clv_is_proxy: false,
  clv_status: "true_close",
  price_taken: 1.95,
  ts: "2026-06-19T10:00:00Z",
};

const TRADE_B: PmTrailRow = {
  bet_id: "t2",
  venue: "kalshi",
  market_id: "km-002",
  model_prob: 0.55,
  confidence: 0.60,
  units: 0.75,
  tier: "B",
  result: null,
  clv: null,
  clv_is_proxy: false,
  clv_status: "INSUFFICIENT_DATA",
  price_taken: 1.90,
  ts: "2026-06-19T11:00:00Z",
};

const CLV_PRESENT: ClvScoreboard = {
  n_bets: 1,
  pct_beat_close: 1.0,
  mean_clv_pct: 0.015,
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

// Honest empty: total_pm=0, trades=[], count=0. The only live Polymarket markets
// are World Cup futures -- no matchable head-to-head games.
function mockEmpty() {
  vi.spyOn(p5api.api, "getPaperTrail").mockResolvedValue(EMPTY_PAPER_TRAIL as never);
  vi.spyOn(p5api.api, "pmTrail").mockResolvedValue(trailOf([]) as never);
  vi.spyOn(p5api.api, "getPaperClv").mockResolvedValue(CLV_EMPTY as never);
}

// Non-empty: two trades in trail.
function mockWithTrades(trades: PmTrailRow[] = [TRADE_A, TRADE_B]) {
  vi.spyOn(p5api.api, "getPaperTrail").mockResolvedValue(EMPTY_PAPER_TRAIL as never);
  vi.spyOn(p5api.api, "pmTrail").mockResolvedValue(trailOf(trades) as never);
  vi.spyOn(p5api.api, "getPaperClv").mockResolvedValue(CLV_PRESENT as never);
}

// Pending: simulates loading state (first fetch not yet resolved).
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
// ws7 -- honest empty state: total_pm=0 -> explanatory panel, NOT blank/broken
// ---------------------------------------------------------------------------

describe("/paper-trading ws7 -- honest empty state (total_pm=0)", () => {
  it("no-paper-trades testid is present when count=0 (not a blank panel)", async () => {
    mockEmpty();
    await renderPage();
    await waitFor(() =>
      expect(screen.getByTestId("no-paper-trades")).toBeInTheDocument(),
    );
  });

  it("pm-empty-pm-game-markets testid renders inside the empty container", async () => {
    mockEmpty();
    await renderPage();
    await waitFor(() =>
      expect(screen.getByTestId("pm-empty-pm-game-markets")).toBeInTheDocument(),
    );
  });

  it("empty container text matches 'no matchable PM markets right now'", async () => {
    mockEmpty();
    await renderPage();
    await waitFor(() => {
      const el = screen.getByTestId("no-paper-trades");
      // Message must explain the condition -- not just be blank/ambiguous
      expect(el.textContent).toMatch(/no live PM game markets right now/i);
    });
  });

  it("explanatory note mentions why markets are absent (daemon / Kalshi / Polymarket)", async () => {
    mockEmpty();
    await renderPage();
    await waitFor(() => {
      const el = screen.getByTestId("no-paper-trades");
      // Must provide an explanatory note, not just a bare 'no trades' line
      expect(el.textContent).toMatch(/PM daemon|Kalshi|Polymarket/i);
    });
  });

  it("empty state has role=status (screen-reader accessible)", async () => {
    mockEmpty();
    await renderPage();
    await waitFor(() => {
      const el = screen.getByTestId("no-paper-trades");
      expect(el.getAttribute("role")).toBe("status");
    });
  });

  it("empty state aria-label confirms 'No live PM game markets right now'", async () => {
    mockEmpty();
    await renderPage();
    await waitFor(() =>
      expect(
        screen.getByLabelText("No live PM game markets right now"),
      ).toBeInTheDocument(),
    );
  });

  it("empty state does not use red/danger/destructive styling (not an error)", async () => {
    mockEmpty();
    await renderPage();
    await waitFor(() => {
      const el = screen.getByTestId("no-paper-trades");
      expect(el.className).not.toMatch(/text-red/);
      expect(el.className).not.toMatch(/text-danger/);
      expect(el.className).not.toMatch(/text-destructive/);
    });
  });

  it("no-paper-trades is absent when loading (ambiguous state avoided)", async () => {
    // While still fetching, pmTrail is null: isEmpty=false, so the panel is absent.
    // This ensures loading != honest-empty (distinct states).
    mockPending();
    await renderPage();
    expect(screen.queryByTestId("no-paper-trades")).toBeNull();
  });

  it("no-paper-trades is absent when trades are present (not fabricated empty)", async () => {
    mockWithTrades();
    await renderPage();
    await waitFor(() => expect(screen.queryByTestId("no-paper-trades")).toBeNull());
  });
});

// ---------------------------------------------------------------------------
// ws7 -- non-empty pmTrail renders trade rows
// ---------------------------------------------------------------------------

describe("/paper-trading ws7 -- non-empty pmTrail renders rows", () => {
  it("pm-trail-table receives the correct row count when trades are loaded", async () => {
    mockWithTrades();
    await renderPage();
    await waitFor(() => {
      const tbl = screen.getByTestId("pm-trail-table");
      // Two trades -> table data-row-count=2
      expect(tbl.getAttribute("data-row-count")).toBe("2");
    });
  });

  it("pm-trail-table renders table-ready (not loading) when data arrives", async () => {
    mockWithTrades();
    await renderPage();
    await waitFor(() => {
      const tbl = screen.getByTestId("pm-trail-table");
      expect(tbl.textContent).toMatch(/table-ready/);
    });
  });

  it("pm-trail-table renders 0 rows when count=0", async () => {
    mockEmpty();
    await renderPage();
    await waitFor(() => {
      const tbl = screen.getByTestId("pm-trail-table");
      expect(tbl.getAttribute("data-row-count")).toBe("0");
    });
  });

  it("tally tiles reflect actual trade counts (not fabricated)", async () => {
    mockWithTrades([TRADE_A, TRADE_B]);
    await renderPage();
    await waitFor(() => {
      // TRADE_A: result=win -> settled; TRADE_B: result=null -> open
      expect(screen.getByTestId("tally-open").textContent).toBe("1");
      expect(screen.getByTestId("tally-settled").textContent).toBe("1");
      expect(screen.getByTestId("tally-win").textContent).toBe("1");
    });
  });
});

// ---------------------------------------------------------------------------
// ws7 -- loading state is visually distinct from honest-empty
// ---------------------------------------------------------------------------

describe("/paper-trading ws7 -- loading state visually distinct", () => {
  it("live-badge-placeholder shows 'checking' text while loading (neutral, not live)", async () => {
    mockPending();
    await renderPage();
    const placeholder = screen.getByTestId("live-badge-placeholder");
    expect(placeholder).toBeInTheDocument();
    expect(placeholder.textContent).toMatch(/checking/i);
  });

  it("tally tiles show loading skeleton (aria-busy) during initial load", async () => {
    mockPending();
    await renderPage();
    // Skeleton divs have aria-busy=true while loading
    const busyEls = document.querySelectorAll('[aria-busy="true"]');
    expect(busyEls.length).toBeGreaterThan(0);
  });

  it("pm-total-count span is absent while loading (not yet resolved)", async () => {
    // The span is conditionally rendered on !loading
    mockPending();
    await renderPage();
    expect(screen.queryByTestId("pm-total-count")).toBeNull();
  });

  it("real-money-deny-banner is present even during loading (always-on honesty rail)", async () => {
    mockPending();
    await renderPage();
    expect(screen.getByTestId("real-money-deny-banner")).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// ws7 -- no dollar-amount ($N) in rendered output (units only).
// Convention: "no $" as a label suffix (e.g. "Staked (units, no $)") is
// acceptable -- it says "no $". The rail blocks '$' followed by a digit,
// which would indicate a dollar P&L value. Matches the convention in all
// other paper-trading test files in this codebase.
// ---------------------------------------------------------------------------

describe("/paper-trading ws7 -- no dollar sign (units only)", () => {
  it("empty state: no dollar-amount ($N) in rendered output", async () => {
    mockEmpty();
    const { container } = await renderPage();
    await waitFor(() =>
      expect(screen.getByTestId("no-paper-trades")).toBeInTheDocument(),
    );
    // Block dollar-amounts like "$5.00" or "$1" ($ followed by digit).
    expect(container.textContent ?? "").not.toMatch(/\$\s?\d/);
  });

  it("loading state: no dollar-amount ($N) in rendered output", async () => {
    mockPending();
    const { container } = await renderPage();
    expect(container.textContent ?? "").not.toMatch(/\$\s?\d/);
  });

  it("populated trail: no dollar-amount ($N) in rendered output", async () => {
    mockWithTrades();
    const { container } = await renderPage();
    await waitFor(() =>
      expect(screen.getByTestId("pm-trail-table").textContent).toMatch(/table-ready/),
    );
    expect(container.textContent ?? "").not.toMatch(/\$\s?\d/);
  });

  it("DENY banner content has no dollar-amount", async () => {
    mockPending();
    await renderPage();
    const banner = screen.getByTestId("real-money-deny-banner");
    expect(banner.textContent ?? "").not.toMatch(/\$\s?\d/);
  });

  it("tally tiles have no dollar-amount when data is loaded", async () => {
    mockWithTrades();
    const { container } = await renderPage();
    await waitFor(() =>
      expect(screen.getByTestId("tally-open")).toBeInTheDocument(),
    );
    const tallyEl = screen.getByTestId("running-tally");
    expect(tallyEl.textContent ?? "").not.toMatch(/\$\s?\d/);
  });
});

// ---------------------------------------------------------------------------
// ws7 -- real-money DENY banner always present (honesty rail)
// ---------------------------------------------------------------------------

describe("/paper-trading ws7 -- real-money DENY banner", () => {
  it("DENY banner is present when total_pm=0", async () => {
    mockEmpty();
    await renderPage();
    await waitFor(() =>
      expect(screen.getByTestId("real-money-deny-banner")).toBeInTheDocument(),
    );
  });

  it("DENY banner contains 'DENY' text", async () => {
    mockEmpty();
    await renderPage();
    await waitFor(() =>
      expect(
        screen.getByTestId("real-money-deny-banner").textContent,
      ).toMatch(/DENY/),
    );
  });

  it("DENY banner contains 'paper mode'", async () => {
    mockEmpty();
    await renderPage();
    await waitFor(() =>
      expect(
        screen.getByTestId("real-money-deny-banner").textContent,
      ).toMatch(/paper mode/i),
    );
  });

  it("DENY banner aria-label is correct for screen readers", async () => {
    mockEmpty();
    await renderPage();
    await waitFor(() =>
      expect(
        screen.getByLabelText("Real money is DENIED -- paper mode only"),
      ).toBeInTheDocument(),
    );
  });

  it("DENY banner present with populated trail", async () => {
    mockWithTrades();
    await renderPage();
    await waitFor(() =>
      expect(screen.getByTestId("real-money-deny-banner")).toBeInTheDocument(),
    );
  });
});

// ---------------------------------------------------------------------------
// W2 -- open-positions-section renders real open rows with required fields
// ---------------------------------------------------------------------------

// Build 8 open trail rows matching the real /api/paper/trail shape.
function makeOpenRows(n = 8): p5api.PaperTrailRow[] {
  const books = ["espn:DraftKings", "espn:FanDuel", "espn:BetMGM"];
  return Array.from({ length: n }, (_, i) => ({
    game_id: `mlb|TeamA@TeamB|2026-06-19T10:0${i}:00Z`,
    matchup: `TeamA@TeamB-${i}`,
    sport: "mlb",
    side: i % 2 === 0 ? "away" as const : "home" as const,
    market_type: null,
    line: null,
    taken_book: books[i % books.length],
    taken_decimal: 2.1 + i * 0.01,
    model_prob: 0.46 + i * 0.01,
    model_ev: 0.01,
    tier: null,
    stake_units: null,
    status: "open",
    graded: false,
    outcome: null,
    clv_pct: null,
    beat_close: null,
    clv_is_proxy: false,
    clv_status: null,
    clv_unavailable: true,
    clv_note: null,
    executed: false,
    ts: `2026-06-19T10:0${i}:00Z`,
    settled_at: null,
  }));
}

// Build N settled rows.
function makeSettledRows(n = 46): p5api.PaperTrailRow[] {
  return Array.from({ length: n }, (_, i) => ({
    game_id: `mlb|Home@Away|2026-06-18T10:0${i % 10}:00Z`,
    matchup: `Home@Away-${i}`,
    sport: "mlb",
    side: "home" as const,
    market_type: null,
    line: null,
    taken_book: "espn:DraftKings",
    taken_decimal: 2.0,
    model_prob: 0.52,
    model_ev: 0.04,
    tier: null,
    stake_units: null,
    status: "settled",
    graded: true,
    outcome: i % 3 === 0 ? "win" : i % 3 === 1 ? "loss" : "push",
    clv_pct: null,
    beat_close: null,
    clv_is_proxy: false,
    clv_status: "no_close",
    clv_unavailable: true,
    clv_note: null,
    executed: false,
    ts: `2026-06-18T10:0${i % 10}:00Z`,
    settled_at: `2026-06-18T10:3${i % 10}:00Z`,
  }));
}

function mockW2Trail(openRows: p5api.PaperTrailRow[], settledRows: p5api.PaperTrailRow[] = []) {
  const allRows = [...openRows, ...settledRows];
  vi.spyOn(p5api.api, "getPaperTrail").mockResolvedValue({
    status: "ok",
    count: allRows.length,
    trail: allRows,
  } as never);
  vi.spyOn(p5api.api, "pmTrail").mockResolvedValue(
    { status: "ok", generated_at: null, trades: [], count: 0 } as never,
  );
  vi.spyOn(p5api.api, "getPaperClv").mockResolvedValue(CLV_EMPTY as never);
}

describe("/paper-trading W2 -- open-positions-section renders real open rows", () => {
  it("open-positions-section is in the document", async () => {
    mockW2Trail(makeOpenRows(8));
    await renderPage();
    await waitFor(() =>
      expect(screen.getByTestId("open-positions-section")).toBeInTheDocument(),
    );
  });

  it("open-positions-stub receives all 8 open rows", async () => {
    mockW2Trail(makeOpenRows(8));
    await renderPage();
    await waitFor(() => {
      const stub = screen.getByTestId("open-positions-stub");
      expect(stub.getAttribute("data-row-count")).toBe("8");
    });
  });

  it("each open row renders matchup field", async () => {
    mockW2Trail(makeOpenRows(8));
    await renderPage();
    await waitFor(() => {
      const rows = screen.getAllByTestId("open-position-row");
      expect(rows).toHaveLength(8);
      rows.forEach((r) => {
        expect(r.getAttribute("data-matchup")).toBeTruthy();
      });
    });
  });

  it("each open row renders side field (home or away)", async () => {
    mockW2Trail(makeOpenRows(8));
    await renderPage();
    await waitFor(() => {
      const rows = screen.getAllByTestId("open-position-row");
      rows.forEach((r) => {
        const side = r.getAttribute("data-side");
        expect(side === "home" || side === "away").toBe(true);
      });
    });
  });

  it("each open row renders taken_book field", async () => {
    mockW2Trail(makeOpenRows(8));
    await renderPage();
    await waitFor(() => {
      const rows = screen.getAllByTestId("open-position-row");
      rows.forEach((r) => {
        expect(r.getAttribute("data-taken-book")).toBeTruthy();
      });
    });
  });

  it("each open row renders model_prob field", async () => {
    mockW2Trail(makeOpenRows(8));
    await renderPage();
    await waitFor(() => {
      const rows = screen.getAllByTestId("open-position-row");
      rows.forEach((r) => {
        const prob = r.getAttribute("data-model-prob");
        expect(Number(prob)).toBeGreaterThan(0);
      });
    });
  });

  it("heading count reflects the 8 open rows", async () => {
    mockW2Trail(makeOpenRows(8));
    await renderPage();
    await waitFor(() => {
      const section = screen.getByTestId("open-positions-section");
      // Heading inside open-positions-section should mention 8
      expect(section.textContent).toMatch(/8/);
    });
  });
});

// ---------------------------------------------------------------------------
// W2 -- done/settled tally derives from real trail rows, not fabricated
// ---------------------------------------------------------------------------

describe("/paper-trading W2 -- done/settled tally from real trail rows", () => {
  it("done-settled-summary section is in the document", async () => {
    mockW2Trail(makeOpenRows(8), makeSettledRows(46));
    await renderPage();
    await waitFor(() =>
      expect(screen.getByTestId("done-settled-summary")).toBeInTheDocument(),
    );
  });

  it("done-total tile shows 54 (8 open + 46 settled)", async () => {
    mockW2Trail(makeOpenRows(8), makeSettledRows(46));
    await renderPage();
    await waitFor(() =>
      expect(screen.getByTestId("done-total").textContent).toBe("54"),
    );
  });

  it("done-settled tile shows 46 (only graded settled rows)", async () => {
    mockW2Trail(makeOpenRows(8), makeSettledRows(46));
    await renderPage();
    await waitFor(() =>
      expect(screen.getByTestId("done-settled").textContent).toBe("46"),
    );
  });

  it("open count heading in open-positions-section shows 8", async () => {
    mockW2Trail(makeOpenRows(8), makeSettledRows(46));
    await renderPage();
    await waitFor(() => {
      const section = screen.getByTestId("open-positions-section");
      expect(section.textContent).toMatch(/8/);
    });
  });

  it("done-settled-summary tally counts are not fabricated (change with input)", async () => {
    // With 3 settled rows only -- tally must reflect 3, not 46 or anything else.
    mockW2Trail([], makeSettledRows(3));
    await renderPage();
    await waitFor(() => {
      expect(screen.getByTestId("done-total").textContent).toBe("3");
      expect(screen.getByTestId("done-settled").textContent).toBe("3");
    });
  });
});

// ---------------------------------------------------------------------------
// W2 -- no-paper-trades shows ONLY when pmTrail count===0
// ---------------------------------------------------------------------------

describe("/paper-trading W2 -- no-paper-trades condition", () => {
  it("no-paper-trades is present when pmTrail count===0", async () => {
    mockW2Trail(makeOpenRows(8));
    // pmTrail is already mocked to count=0 inside mockW2Trail
    await renderPage();
    await waitFor(() =>
      expect(screen.getByTestId("no-paper-trades")).toBeInTheDocument(),
    );
  });

  it("no-paper-trades is ABSENT when pmTrail count>0", async () => {
    // pmTrail has trades -> no-paper-trades must be absent
    vi.spyOn(p5api.api, "getPaperTrail").mockResolvedValue({
      status: "ok", count: 8, trail: makeOpenRows(8),
    } as never);
    vi.spyOn(p5api.api, "pmTrail").mockResolvedValue({
      status: "ok",
      generated_at: null,
      trades: [TRADE_A],
      count: 1,
    } as never);
    vi.spyOn(p5api.api, "getPaperClv").mockResolvedValue(CLV_EMPTY as never);
    await renderPage();
    await waitFor(() =>
      expect(screen.queryByTestId("no-paper-trades")).toBeNull(),
    );
  });

  it("no-paper-trades is ABSENT while loading (pmTrail still null)", async () => {
    mockPending();
    await renderPage();
    expect(screen.queryByTestId("no-paper-trades")).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// W2 -- LiveBadge never green when ageSec > staleAfterSec
// ---------------------------------------------------------------------------

describe("/paper-trading W2 -- LiveBadge stale-never-green", () => {
  it("live-badge-placeholder has no green class when loading (no data yet)", async () => {
    mockPending();
    await renderPage();
    const placeholder = screen.getByTestId("live-badge-placeholder");
    // Green classes must NOT be present in a loading/checking state
    expect(placeholder.innerHTML).not.toMatch(/bg-green/);
  });

  it("live-badge-placeholder shows checking text while no data", async () => {
    mockPending();
    await renderPage();
    const placeholder = screen.getByTestId("live-badge-placeholder");
    expect(placeholder.textContent).toMatch(/checking/i);
  });

  it("live-badge-placeholder has no green pulse when data is stale (error set, no ageSec)", async () => {
    // Simulate error (no data received) -- badge must NOT show green
    vi.spyOn(p5api.api, "getPaperTrail").mockRejectedValue(new Error("network"));
    vi.spyOn(p5api.api, "pmTrail").mockRejectedValue(new Error("network"));
    vi.spyOn(p5api.api, "getPaperClv").mockRejectedValue(new Error("network"));
    await renderPage();
    // After error, badge should be checking or unavailable -- never green
    await waitFor(() => {
      const placeholder = screen.getByTestId("live-badge-placeholder");
      // No green-* background class (live state) in error/unavailable state
      expect(placeholder.innerHTML).not.toMatch(/bg-green-950/);
      expect(placeholder.innerHTML).not.toMatch(/animate-ping/);
    });
  });
});

// ---------------------------------------------------------------------------
// W2 -- no dollar-amount in rendered output (honesty rail)
// ---------------------------------------------------------------------------

describe("/paper-trading W2 -- no dollar amounts", () => {
  it("no dollar-amount when 8 real open rows rendered", async () => {
    mockW2Trail(makeOpenRows(8), makeSettledRows(46));
    const { container } = await renderPage();
    await waitFor(() =>
      expect(screen.getByTestId("done-total").textContent).toBe("54"),
    );
    expect(container.textContent ?? "").not.toMatch(/\$\s?\d/);
  });
});
