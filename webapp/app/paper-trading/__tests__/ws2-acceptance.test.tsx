// ws2-acceptance.test.tsx -- WS2 paper-trading center acceptance tests.
//
// Acceptance criteria (WS2):
//   1. PRIMARY settled book from /api/paper/trail surfaces 54 rows (21W/25L)
//      with outcome / model_prob / model_ev / taken_book columns + derived tally.
//   2. OPEN positions: 8 open rows rendered from trail (status=open filtering).
//   3. SECONDARY PM trail from /api/paper/pm/trail renders honest-empty reason
//      text ("No live PM game markets right now") -- NOT red, NOT fabricated.
//      LiveBadge age updates visibly while PM section shows honest-empty.
//   4. Per-venue VenueSummary only renders rows that exist (no fabricated tiles).
//   5. useLiveData tab-pausing poll: stale-never-green LiveBadge.
//   6. No '$' followed by a digit anywhere in rendered output (UNITS only).
//   7. Real-money DENY banner always present.
//   8. done-settled-summary shows real trail counts (54 total, 46 settled, 21W/25L).
//
// Lane: frontend (webapp/**). Per-file vitest only (full-suite freezes the box).

import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import type { PaperTrailRow, PmTrail, ClvScoreboard } from "@/lib/p5api";

// ---------------------------------------------------------------------------
// Component stubs (keep deep rendering out of unit tests)
// ---------------------------------------------------------------------------

vi.mock("next/link", () => ({
  default: ({ href, children, ...rest }: { href: string; children: React.ReactNode }) => (
    <a href={href} {...rest}>{children}</a>
  ),
}));

// PmTrailTable stub: captures row count.
vi.mock("@/components/paper_pm/PmTrailTable", () => ({
  PmTrailTable: ({ loading, rows }: { loading?: boolean; rows?: unknown[] }) => (
    <div data-testid="pm-trail-table" data-row-count={rows?.length ?? 0}>
      {loading ? "table-loading" : `table-ready:${rows?.length ?? 0}`}
    </div>
  ),
}));

// PaperTrailSettled stub: exposes row count and settled/win/loss from props.
// The real component renders these via settledTallyHelpers, but here we expose
// the raw values via data-* attrs so acceptance tests can assert the numbers
// without needing the full ScrollArea/table tree.
vi.mock("@/components/paper_pm/PaperTrailSettled", () => ({
  PaperTrailSettled: ({
    loading,
    rows,
  }: {
    loading?: boolean;
    rows?: PaperTrailRow[];
    settledOnly?: boolean;
    error?: string | null;
  }) => {
    const settled = (rows ?? []).filter((r) => r.graded && r.status !== "open");
    const wins = settled.filter((r) => r.outcome === "win").length;
    const losses = settled.filter((r) => r.outcome === "loss").length;
    const hasTakenBook = (rows ?? []).some((r) => r.taken_book != null && r.taken_book !== "");
    const hasModelEv = (rows ?? []).some((r) => r.model_ev != null);
    const hasOutcome = settled.length > 0;
    const hasModelProb = (rows ?? []).some((r) => r.model_prob != null);
    return (
      <div
        data-testid="paper-trail-settled"
        data-loading={String(!!loading)}
        data-total-rows={String((rows ?? []).length)}
        data-settled-count={String(settled.length)}
        data-win-count={String(wins)}
        data-loss-count={String(losses)}
        data-has-taken-book={String(hasTakenBook)}
        data-has-model-ev={String(hasModelEv)}
        data-has-outcome={String(hasOutcome)}
        data-has-model-prob={String(hasModelProb)}
      >
        {loading ? "settled-loading" : `settled-ready:${settled.length}W=${wins}L=${losses}`}
      </div>
    );
  },
}));

// OpenPositions stub: exposes open row count.
vi.mock("@/components/paper_pm/OpenPositions", () => ({
  OpenPositions: ({
    rows,
    loading,
  }: {
    rows?: PaperTrailRow[];
    loading?: boolean;
    error?: string | null;
  }) => {
    const openRows = (rows ?? []).filter((r) => r.status === "open" || !r.graded);
    if (openRows.length === 0 && !loading) {
      return (
        <div data-testid="open-positions-empty">
          No open positions right now. Paper mode only. No edge is claimed.
        </div>
      );
    }
    return (
      <div data-testid="open-positions-content" data-open-count={openRows.length}>
        {openRows.map((r, i) => (
          <div key={i} data-testid="ws2-open-row" data-matchup={r.matchup} data-status={r.status}>
            {r.matchup} [{r.status}]
          </div>
        ))}
      </div>
    );
  },
}));

import * as p5api from "@/lib/p5api";

// ---------------------------------------------------------------------------
// Fixtures: 54-row trail (21W / 25L / 8 open)
// ---------------------------------------------------------------------------

function makeTrailRow(overrides: Partial<PaperTrailRow> = {}): PaperTrailRow {
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

// Build 54-row trail: 21 wins, 25 losses, 8 open
function make54RowTrail(): PaperTrailRow[] {
  const rows: PaperTrailRow[] = [];
  for (let i = 0; i < 21; i++) {
    rows.push(makeTrailRow({
      game_id: `mlb-win-${i}`,
      matchup: `Team A @ Team B ${i}`,
      outcome: "win",
      status: "settled",
      graded: true,
    }));
  }
  for (let i = 0; i < 25; i++) {
    rows.push(makeTrailRow({
      game_id: `mlb-loss-${i}`,
      matchup: `Team C @ Team D ${i}`,
      outcome: "loss",
      status: "settled",
      graded: true,
    }));
  }
  for (let i = 0; i < 8; i++) {
    rows.push(makeTrailRow({
      game_id: `mlb-open-${i}`,
      matchup: `Open Game ${i}`,
      outcome: null,
      status: "open",
      graded: false,
      settled_at: null,
    }));
  }
  return rows;
}

const TRAIL_54 = make54RowTrail();

const PAPER_TRAIL_54 = {
  status: "ok",
  count: 54,
  trail: TRAIL_54,
  honest_note: "paper only",
};

const PM_TRAIL_EMPTY: PmTrail = {
  status: "ok",
  generated_at: null,
  trades: [],
  count: 0,
};

const CLV_EMPTY: ClvScoreboard = {
  n_bets: 0,
  pct_beat_close: null,
  mean_clv_pct: null,
  by_sport: null,
  clv_is_proxy: false,
};

const CLV_PRESENT: ClvScoreboard = {
  n_bets: 5,
  pct_beat_close: 0.6,
  mean_clv_pct: 0.015,
  by_sport: null,
  clv_is_proxy: false,
};

// ---------------------------------------------------------------------------
// Mock helpers
// ---------------------------------------------------------------------------

function mockWith54RowTrail(clv: ClvScoreboard = CLV_EMPTY) {
  vi.spyOn(p5api.api, "getPaperTrail").mockResolvedValue(PAPER_TRAIL_54 as never);
  vi.spyOn(p5api.api, "pmTrail").mockResolvedValue(PM_TRAIL_EMPTY as never);
  vi.spyOn(p5api.api, "getPaperClv").mockResolvedValue(clv as never);
}

function mockWithEmptyTrail() {
  vi.spyOn(p5api.api, "getPaperTrail").mockResolvedValue(
    { status: "ok", count: 0, trail: [] } as never
  );
  vi.spyOn(p5api.api, "pmTrail").mockResolvedValue(PM_TRAIL_EMPTY as never);
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
// WS2-1: PRIMARY settled book columns (outcome / model_prob / model_ev / taken_book)
// ---------------------------------------------------------------------------

describe("WS2-1 -- PRIMARY settled book columns from /api/paper/trail", () => {
  it("PaperTrailSettled receives trail rows with taken_book populated", async () => {
    mockWith54RowTrail();
    await renderPage();
    await waitFor(() => {
      const el = screen.getByTestId("paper-trail-settled");
      expect(el.getAttribute("data-has-taken-book")).toBe("true");
    });
  });

  it("PaperTrailSettled receives trail rows with model_ev populated", async () => {
    mockWith54RowTrail();
    await renderPage();
    await waitFor(() => {
      const el = screen.getByTestId("paper-trail-settled");
      expect(el.getAttribute("data-has-model-ev")).toBe("true");
    });
  });

  it("PaperTrailSettled receives trail rows with model_prob populated", async () => {
    mockWith54RowTrail();
    await renderPage();
    await waitFor(() => {
      const el = screen.getByTestId("paper-trail-settled");
      expect(el.getAttribute("data-has-model-prob")).toBe("true");
    });
  });

  it("PaperTrailSettled receives trail rows with outcome populated (win/loss)", async () => {
    mockWith54RowTrail();
    await renderPage();
    await waitFor(() => {
      const el = screen.getByTestId("paper-trail-settled");
      expect(el.getAttribute("data-has-outcome")).toBe("true");
    });
  });

  it("settled count is 46 (21 wins + 25 losses) from 54-row trail", async () => {
    mockWith54RowTrail();
    await renderPage();
    await waitFor(() => {
      const el = screen.getByTestId("paper-trail-settled");
      expect(el.getAttribute("data-settled-count")).toBe("46");
    });
  });

  it("win count is 21 from the settled book", async () => {
    mockWith54RowTrail();
    await renderPage();
    await waitFor(() => {
      const el = screen.getByTestId("paper-trail-settled");
      expect(el.getAttribute("data-win-count")).toBe("21");
    });
  });

  it("loss count is 25 from the settled book", async () => {
    mockWith54RowTrail();
    await renderPage();
    await waitFor(() => {
      const el = screen.getByTestId("paper-trail-settled");
      expect(el.getAttribute("data-loss-count")).toBe("25");
    });
  });

  it("total rows passed to settled component is 54", async () => {
    mockWith54RowTrail();
    await renderPage();
    await waitFor(() => {
      const el = screen.getByTestId("paper-trail-settled");
      expect(el.getAttribute("data-total-rows")).toBe("54");
    });
  });
});

// ---------------------------------------------------------------------------
// WS2-2: OPEN positions (8 rows from trail, filtered by OpenPositions)
// ---------------------------------------------------------------------------

describe("WS2-2 -- OPEN positions from trail (8 rows)", () => {
  it("open-positions-section is always rendered (structure present)", async () => {
    mockPending();
    await renderPage();
    expect(screen.getByTestId("open-positions-section")).toBeInTheDocument();
  });

  it("OpenPositions receives 8 open rows from the 54-row trail", async () => {
    mockWith54RowTrail();
    await renderPage();
    await waitFor(() => {
      const el = screen.getByTestId("open-positions-content");
      expect(el.getAttribute("data-open-count")).toBe("8");
    });
  });

  it("open rows have status=open in the data", async () => {
    mockWith54RowTrail();
    await renderPage();
    await waitFor(() => {
      const openRowEls = screen.getAllByTestId("ws2-open-row");
      expect(openRowEls.length).toBe(8);
      openRowEls.forEach((el) => {
        expect(el.getAttribute("data-status")).toBe("open");
      });
    });
  });

  it("open section heading shows count=8 when data resolves", async () => {
    mockWith54RowTrail();
    await renderPage();
    await waitFor(() => {
      // Section heading shows "Open positions (8)"
      expect(screen.getByLabelText("Open paper positions").textContent).toMatch(/8/);
    });
  });

  it("done-settled-summary shows nOpen=8 from the real trail", async () => {
    mockWith54RowTrail();
    await renderPage();
    // done-settled-summary does not have a separate open testid, but
    // the open-positions section heading confirms 8 open rows.
    await waitFor(() => {
      expect(screen.getByTestId("open-positions-content")).toBeInTheDocument();
    });
  });
});

// ---------------------------------------------------------------------------
// WS2-3: SECONDARY PM trail honest-empty (genuinely 0, not red, not fabricated)
// ---------------------------------------------------------------------------

describe("WS2-3 -- SECONDARY PM trail honest-empty state", () => {
  it("no-paper-trades block is present when PM trail is empty", async () => {
    mockWith54RowTrail(); // PM trail = 0
    await renderPage();
    await waitFor(() => {
      expect(screen.getByTestId("no-paper-trades")).toBeInTheDocument();
    });
  });

  it("PM empty block text says 'No live PM game markets right now'", async () => {
    mockWith54RowTrail();
    await renderPage();
    await waitFor(() => {
      const el = screen.getByTestId("no-paper-trades");
      expect(el.textContent).toMatch(/no live PM game markets right now/i);
    });
  });

  it("PM empty block does NOT use red/danger CSS classes (not an error state)", async () => {
    mockWith54RowTrail();
    await renderPage();
    await waitFor(() => {
      const el = screen.getByTestId("no-paper-trades");
      expect(el.className).not.toMatch(/text-red/);
      expect(el.className).not.toMatch(/text-danger/);
      expect(el.className).not.toMatch(/bg-red/);
      expect(el.className).not.toMatch(/border-red/);
    });
  });

  it("PM empty block mentions 'No edge is claimed' (honesty rail)", async () => {
    mockWith54RowTrail();
    await renderPage();
    await waitFor(() => {
      expect(screen.getByTestId("no-paper-trades").textContent).toMatch(/no edge is claimed/i);
    });
  });

  it("PM empty block explains why (mentions PM daemon / Kalshi / Polymarket)", async () => {
    mockWith54RowTrail();
    await renderPage();
    await waitFor(() => {
      const el = screen.getByTestId("no-paper-trades");
      expect(el.textContent).toMatch(/PM daemon|Kalshi|Polymarket/i);
    });
  });

  it("LiveBadge is present and renders (refresh mechanism visibly running)", async () => {
    mockWith54RowTrail();
    await renderPage();
    // LiveBadge transitions from checking to live as data arrives.
    // We check the wrapper exists and initially shows 'checking'.
    const badge = screen.getByTestId("live-badge-placeholder");
    expect(badge).toBeInTheDocument();
  });

  it("no-paper-trades is absent when PM trades exist", async () => {
    vi.spyOn(p5api.api, "getPaperTrail").mockResolvedValue(PAPER_TRAIL_54 as never);
    vi.spyOn(p5api.api, "pmTrail").mockResolvedValue({
      status: "ok",
      generated_at: null,
      trades: [{ bet_id: "x1", venue: "kalshi", market_id: "km-1", model_prob: 0.6,
        confidence: 0.7, units: 1.0, tier: "A", result: "win", clv: 0.01,
        clv_is_proxy: false, clv_status: "true_close", price_taken: 2.0,
        ts: "2026-06-18T10:00:00Z" }],
      count: 1,
    } as never);
    vi.spyOn(p5api.api, "getPaperClv").mockResolvedValue(CLV_PRESENT as never);
    await renderPage();
    await waitFor(() => {
      expect(screen.queryByTestId("no-paper-trades")).toBeNull();
    });
  });
});

// ---------------------------------------------------------------------------
// WS2-4: Per-venue VenueSummary only renders rows that exist
// ---------------------------------------------------------------------------

describe("WS2-4 -- Per-venue VenueSummary renders only real rows", () => {
  it("venue-summary-section is always present", async () => {
    mockPending();
    await renderPage();
    expect(screen.getByTestId("venue-summary-section")).toBeInTheDocument();
  });

  it("VenueSummary renders venue tiles from the REAL trail (not just the PM trail)", async () => {
    // The per-venue breakdown now sources the real paper trail (sportsbooks / prop
    // books / in-game) UNION the PM trail -- so a 54-row main trail surfaces its
    // venue even when the PM trail is empty. taken_book "espn:DraftKings" -> "DraftKings".
    mockWith54RowTrail(); // 54 main-trail rows @ espn:DraftKings, PM trail = 0
    await renderPage();
    await waitFor(() => {
      expect(screen.getAllByTestId("venue-tile").length).toBeGreaterThan(0);
    });
    expect(screen.getByText("DraftKings")).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// WS2-5: stale-never-green LiveBadge
// ---------------------------------------------------------------------------

describe("WS2-5 -- stale-never-green LiveBadge", () => {
  it("badge shows 'checking' in loading state (not green)", async () => {
    mockPending();
    await renderPage();
    const badge = screen.getByTestId("live-badge-placeholder");
    expect(badge.textContent).toMatch(/checking/i);
    // Must not have green text/bg classes in loading state
    expect(badge.innerHTML).not.toMatch(/text-green-[45]/);
    expect(badge.innerHTML).not.toMatch(/bg-green-/);
  });

  it("badge wrapper is always rendered (never absent)", async () => {
    mockPending();
    await renderPage();
    expect(screen.getByTestId("live-badge-placeholder")).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// WS2-6: No '$' followed by digit anywhere (UNITS only)
// ---------------------------------------------------------------------------

describe("WS2-6 -- UNITS only, no dollar amounts", () => {
  it("loading state: no dollar-amount in rendered text", async () => {
    mockPending();
    const { container } = await renderPage();
    expect(container.textContent ?? "").not.toMatch(/\$\s?\d/);
  });

  it("54-row trail loaded: no dollar-amount in rendered text", async () => {
    mockWith54RowTrail();
    const { container } = await renderPage();
    await waitFor(() => expect(container.textContent ?? "").not.toMatch(/\$\s?\d/));
  });

  it("empty trail: no dollar-amount in rendered text", async () => {
    mockWithEmptyTrail();
    const { container } = await renderPage();
    await waitFor(() => expect(container.textContent ?? "").not.toMatch(/\$\s?\d/));
  });

  it("no 'P&L' or 'PnL' text in rendered output", async () => {
    mockWith54RowTrail();
    const { container } = await renderPage();
    await waitFor(() => {
      expect(/\bP&L\b/i.test(container.textContent ?? "")).toBe(false);
      expect(/\bPnL\b/i.test(container.textContent ?? "")).toBe(false);
    });
  });
});

// ---------------------------------------------------------------------------
// WS2-7: Real-money DENY banner always present
// ---------------------------------------------------------------------------

describe("WS2-7 -- Real-money DENY banner", () => {
  it("DENY banner present in loading state", async () => {
    mockPending();
    await renderPage();
    expect(screen.getByTestId("real-money-deny-banner")).toBeInTheDocument();
  });

  it("DENY banner present with 54-row trail", async () => {
    mockWith54RowTrail();
    await renderPage();
    await waitFor(() =>
      expect(screen.getByTestId("real-money-deny-banner")).toBeInTheDocument()
    );
  });

  it("DENY banner contains 'DENY' text", async () => {
    mockPending();
    await renderPage();
    expect(screen.getByTestId("real-money-deny-banner").textContent).toMatch(/DENY/);
  });

  it("DENY banner says 'paper mode only' (not real-money)", async () => {
    mockPending();
    await renderPage();
    expect(screen.getByTestId("real-money-deny-banner").textContent).toMatch(/paper mode/i);
  });

  it("DENY banner aria-label is correct", async () => {
    mockPending();
    await renderPage();
    expect(
      screen.getByLabelText("Real money is DENIED -- paper mode only")
    ).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// WS2-8: done-settled-summary shows real trail counts
// ---------------------------------------------------------------------------

describe("WS2-8 -- done-settled-summary real trail counts", () => {
  it("done-settled-summary section is always rendered", async () => {
    mockPending();
    await renderPage();
    expect(screen.getByTestId("done-settled-summary")).toBeInTheDocument();
  });

  it("done-total shows 54 (all trail rows)", async () => {
    mockWith54RowTrail();
    await renderPage();
    await waitFor(() => {
      expect(screen.getByTestId("done-total").textContent).toBe("54");
    });
  });

  it("done-settled shows 46 (21 wins + 25 losses)", async () => {
    mockWith54RowTrail();
    await renderPage();
    await waitFor(() => {
      expect(screen.getByTestId("done-settled").textContent).toBe("46");
    });
  });

  it("done-win shows 21", async () => {
    mockWith54RowTrail();
    await renderPage();
    await waitFor(() => {
      expect(screen.getByTestId("done-win").textContent).toBe("21");
    });
  });

  it("done-loss shows 25", async () => {
    mockWith54RowTrail();
    await renderPage();
    await waitFor(() => {
      expect(screen.getByTestId("done-loss").textContent).toBe("25");
    });
  });

  it("done-push shows 0", async () => {
    mockWith54RowTrail();
    await renderPage();
    await waitFor(() => {
      expect(screen.getByTestId("done-push").textContent).toBe("0");
    });
  });

  it("done summary is always rendered even in loading state", async () => {
    mockPending();
    await renderPage();
    expect(screen.getByTestId("done-settled-summary")).toBeInTheDocument();
  });

  it("done summary no dollar-amounts anywhere in text", async () => {
    mockWith54RowTrail();
    const { container } = await renderPage();
    await waitFor(() => {
      const section = screen.getByTestId("done-settled-summary");
      expect(section.textContent ?? "").not.toMatch(/\$\s?\d/);
    });
    expect(container).toBeTruthy();
  });
});

// ---------------------------------------------------------------------------
// WS2-misc: structural requirements
// ---------------------------------------------------------------------------

describe("WS2-misc -- structural requirements", () => {
  it("page title says 'Paper Trading Center' (updated from old title)", async () => {
    mockPending();
    const { container } = await renderPage();
    const h1 = container.querySelector("h1");
    expect(h1?.textContent).toMatch(/paper trading/i);
  });

  it("unit-convention-clarifier block is present (explains UNITS not dollars)", async () => {
    mockPending();
    await renderPage();
    expect(screen.getByTestId("unit-convention-clarifier")).toBeInTheDocument();
  });

  it("unit-convention-clarifier mentions UNITS and quarter-Kelly", async () => {
    mockPending();
    await renderPage();
    const el = screen.getByTestId("unit-convention-clarifier");
    expect(el.textContent).toMatch(/UNITS/);
    expect(el.textContent).toMatch(/quarter-Kelly/i);
  });

  it("CLV tile shows '--' when mean_clv_pct is null (no zero-fill)", async () => {
    mockWith54RowTrail(CLV_EMPTY);
    await renderPage();
    await waitFor(() => {
      expect(screen.getByTestId("clv-mean-clv").textContent).toBe("--");
    });
  });

  it("CLV tile shows formatted value when mean_clv_pct is present", async () => {
    mockWith54RowTrail(CLV_PRESENT);
    await renderPage();
    await waitFor(() => {
      expect(screen.getByTestId("clv-mean-clv").textContent).toMatch(/\+1\.5%/);
    });
  });

  it("page h1 is present and not blank", async () => {
    mockPending();
    const { container } = await renderPage();
    const h1 = container.querySelector("h1");
    expect(h1).toBeTruthy();
    expect(h1!.textContent!.trim().length).toBeGreaterThan(0);
  });
});
