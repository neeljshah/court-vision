// paper.page.test.tsx -- Acceptance tests for /paper page AND /paper/[betId] page.
//
// Verifies (WS5 acceptance criteria for /paper):
//   * Page consumes useLiveData (no raw setInterval data poll in the page)
//   * Shows last-updated age (data-testid="paper-last-updated")
//   * Shows stale flag when isStale=true
//   * Retains last-good rows on a failed poll (data survives error state)
//   * No $ P&L field in DOM (honesty rail)
//   * app/paper/error.tsx exists and renders an honest recoverable error
//
// NEW -- WS3 acceptance criteria for /paper/[betId] detail page:
//   * Page renders a LiveBadge / last-updated age element (data-testid="bet-detail-last-updated")
//   * A failed poll keeps the previously-found row visible (last-good, not blank)
//     and surfaces an honest stale/error indicator (never green on stale)
//   * A matching row still resolves and renders via ExecutionDetail
//   * No $ P&L in the detail page DOM (honesty rail)
//
// Legacy CLV strip tests retained (all still pass):
//   * CLV strip has aria-label="CLV summary" region
//   * While loading, tiles show aria-busy neutral skeleton
//   * 'No settled bets yet' on 0 bets (honest empty)
//   * Mean-CLV color honesty
//   * data-testid="paper-unit-convention-note" present

import { describe, it, expect, vi, afterEach, type Mock } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import type { LiveDataState } from "@/lib/useLiveData";
import type { PaperTrail, ClvScoreboard } from "@/lib/p5api";

// Mock next/link -> plain <a> for jsdom rendering
vi.mock("next/link", () => ({
  default: ({ href, children, ...rest }: { href: string; children: React.ReactNode }) => (
    <a href={href} {...rest}>{children}</a>
  ),
}));

// Mock next/navigation (useParams) -- betId overridden per describe block.
vi.mock("next/navigation", () => ({
  useParams: vi.fn(() => ({ betId: "" })),
  usePathname: vi.fn(() => "/paper"),
  useRouter: vi.fn(() => ({ push: vi.fn() })),
}));

// Mock PmTrailTable -- it has deep shadcn/ui deps that don't matter here.
vi.mock("@/components/paper_pm/PmTrailTable", () => ({
  PmTrailTable: ({ loading, rows }: { loading?: boolean; rows?: unknown[] }) => (
    <div data-testid="pm-trail-table" data-loading={String(!!loading)} data-rows={String((rows ?? []).length)}>
      {loading ? "table-loading" : "table-ready"}
    </div>
  ),
}));

// Mock PaperTrailSettled -- the primary settled book component (deep deps).
vi.mock("@/components/paper_pm/PaperTrailSettled", () => ({
  PaperTrailSettled: ({ loading, rows }: { loading?: boolean; rows?: unknown[] }) => (
    <div data-testid="paper-trail-settled" data-loading={String(!!loading)} data-rows={String((rows ?? []).length)}>
      {loading ? "settled-loading" : "settled-ready"}
    </div>
  ),
}));

// Mock ExecutionDetail -- used by the [betId] detail page.
vi.mock("@/components/paper_pm/ExecutionDetail", () => ({
  ExecutionDetail: ({ row, loading, error }: { row?: unknown; loading?: boolean; error?: string | null }) => (
    <div
      data-testid="execution-detail"
      data-has-row={String(row != null)}
      data-loading={String(!!loading)}
      data-error={error ?? ""}
    >
      {loading ? "detail-loading" : row ? "detail-with-row" : "detail-no-row"}
    </div>
  ),
}));

// Mock ExecutionTrail -- used by the [betId] detail page.
vi.mock("@/components/execution/ExecutionTrail", () => ({
  ExecutionTrail: ({ error }: { error?: string | null }) => (
    <div data-testid="execution-trail" data-error={error ?? ""}>
      execution-trail
    </div>
  ),
}));

// Mock paperTrailAdapter -- used by the [betId] detail page.
vi.mock("@/components/paper_pm/paperTrailAdapter", () => ({
  paperRowToExecutionTrail: (row: unknown) => ({
    bookLines: [],
    bestBook: null,
    devig: null,
    decision: null,
    stakeUnits: null,
    tier: null,
    clvStatus: null,
    modelProb: null,
    error: null,
    _row: row,
  }),
}));

// ---------------------------------------------------------------------------
// Mock useLiveData so we control its output without real timers/fetch.
// This lets us verify: (a) the page calls useLiveData (not raw setInterval),
// (b) the page correctly renders each LiveDataState facet.
// ---------------------------------------------------------------------------

vi.mock("@/lib/useLiveData", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/useLiveData")>();
  return {
    ...actual,
    // The page only imports `useLiveData` (not useLiveDataUrl).
    useLiveData: vi.fn(),
  };
});

import * as useLiveDataMod from "@/lib/useLiveData";
import * as nextNavigation from "next/navigation";

// Helper: cast the mock for assertion
const mockUseLiveData = useLiveDataMod.useLiveData as Mock;
const mockUseParams = nextNavigation.useParams as Mock;

// ---------------------------------------------------------------------------
// Test data shapes
// ---------------------------------------------------------------------------

type PageData = { trail: PaperTrail; clv: ClvScoreboard | null };

// Minimal PaperTrail stubs (cast to satisfy the branded type in tests).
const TRAIL_EMPTY = { status: "ok", count: 0, trail: [] } as PaperTrail;
const TRAIL_WITH_ROWS = {
  status: "ok",
  count: 2,
  // Cast individual row objects -- tests care only about row count, not row shape.
  trail: [{ game_id: "g1" }, { game_id: "g2" }] as PaperTrail["trail"],
} as PaperTrail;

const CLV_ZERO: ClvScoreboard = { n_bets: 0, pct_beat_close: null, mean_clv_pct: null, by_sport: null, clv_is_proxy: false };
const CLV_POS: ClvScoreboard = { n_bets: 12, pct_beat_close: 0.583, mean_clv_pct: 0.023, by_sport: null, clv_is_proxy: false };
const CLV_NEG: ClvScoreboard = { n_bets: 8, pct_beat_close: 0.375, mean_clv_pct: -0.018, by_sport: null, clv_is_proxy: false };

// Canonical LiveDataState factory
function makeState<T>(
  overrides: Partial<LiveDataState<T>> = {},
): LiveDataState<T> {
  return {
    data: null,
    lastUpdatedAt: null,
    ageSec: null,
    isStale: false,
    error: null,
    isLoading: true,
    consecutiveFailures: 0,
    backoffActive: false,
    refresh: vi.fn(),
    ...overrides,
  };
}

afterEach(() => vi.restoreAllMocks());

// Lazy-import the page AFTER mocks are registered.
async function renderPage() {
  const { default: PaperPage } = await import("../page");
  return render(<PaperPage />);
}

// ---------------------------------------------------------------------------
// WS5 -- useLiveData integration (no raw setInterval)
// ---------------------------------------------------------------------------

describe("/paper -- useLiveData integration (WS5)", () => {
  it("calls useLiveData (not a raw setInterval) for data polling", async () => {
    // Spy on setInterval to detect any raw polling from the page itself.
    const siSpy = vi.spyOn(globalThis, "setInterval");

    mockUseLiveData.mockReturnValue(makeState({ isLoading: true }));

    await renderPage();

    // useLiveData must have been called by the page.
    expect(mockUseLiveData).toHaveBeenCalled();

    // The page must NOT have set up its own setInterval for data polling
    // (useLiveData encapsulates all interval management internally).
    // Any setInterval calls that remain come from useLiveData internals which
    // we've mocked out -- the page code itself must not call setInterval directly.
    const pageSetIntervalCalls = siSpy.mock.calls;
    // Since useLiveData is fully mocked (returns synchronously), any setInterval
    // calls in this render would be from the page, not from useLiveData. Zero calls
    // confirms the page delegates entirely to the hook.
    expect(pageSetIntervalCalls.length).toBe(0);
  });

  it("renders last-updated age element (data-testid=paper-last-updated)", async () => {
    mockUseLiveData.mockReturnValue(
      makeState<PageData>({
        data: { trail: TRAIL_EMPTY, clv: CLV_ZERO },
        isLoading: false,
        lastUpdatedAt: Date.now(),
        ageSec: 5,
        isStale: false,
      }),
    );
    await renderPage();
    expect(screen.getByTestId("paper-last-updated")).toBeInTheDocument();
  });

  it("last-updated shows 'checking' when lastUpdatedAt is null", async () => {
    mockUseLiveData.mockReturnValue(
      makeState({ isLoading: true, lastUpdatedAt: null, ageSec: null }),
    );
    await renderPage();
    expect(screen.getByTestId("paper-last-updated").textContent).toBe("checking");
  });

  it("last-updated shows 'just now' when ageSec < 5", async () => {
    mockUseLiveData.mockReturnValue(
      makeState<PageData>({
        data: { trail: TRAIL_EMPTY, clv: CLV_ZERO },
        isLoading: false,
        lastUpdatedAt: Date.now(),
        ageSec: 2,
        isStale: false,
      }),
    );
    await renderPage();
    expect(screen.getByTestId("paper-last-updated").textContent).toBe("just now");
  });

  it("shows stale indicator when isStale=true", async () => {
    mockUseLiveData.mockReturnValue(
      makeState<PageData>({
        data: { trail: TRAIL_EMPTY, clv: CLV_ZERO },
        isLoading: false,
        lastUpdatedAt: Date.now() - 120_000,
        ageSec: 120,
        isStale: true,
      }),
    );
    await renderPage();
    const el = screen.getByTestId("paper-last-updated");
    expect(el.textContent).toMatch(/stale/i);
    // Must carry the amber warning class
    expect(el.className).toMatch(/amber/);
  });

  it("retains last-good rows after a failed poll (data survives error)", async () => {
    // Simulate: we had good data (2 rows), then a poll failed.
    // useLiveData contract: data=last-good, error=set, isStale=true.
    mockUseLiveData.mockReturnValue(
      makeState<PageData>({
        data: { trail: TRAIL_WITH_ROWS, clv: CLV_ZERO },
        isLoading: false,
        lastUpdatedAt: Date.now() - 60_000,
        ageSec: 60,
        isStale: true,
        error: "HTTP 503",
      }),
    );
    await renderPage();
    // Settled book component is visible with last-good row count (not blank/error-only)
    const settledBook = screen.getByTestId("paper-trail-settled");
    expect(settledBook.dataset["rows"]).toBe("2");
    // Not in loading state -- we have data
    expect(settledBook.dataset["loading"]).toBe("false");
    // Stale indicator is present
    expect(screen.getByTestId("paper-last-updated").textContent).toMatch(/stale/i);
  });

  it("shows unavailable panel only when data is null AND error is set", async () => {
    // First poll failed -- no prior good data.
    mockUseLiveData.mockReturnValue(
      makeState<PageData>({
        data: null,
        isLoading: false,
        error: "HTTP 502",
      }),
    );
    await renderPage();
    // The Unavailable component renders with aria-label containing "unavailable".
    // Both the PM trail panel and the prediction history panel may show unavailable
    // (each has its own useLiveData call), so we assert at least one is present.
    const unavailableEls = screen.getAllByRole("status", { name: /unavailable/i });
    expect(unavailableEls.length).toBeGreaterThanOrEqual(1);
  });

  it("does NOT show unavailable panel when data exists even if error is set", async () => {
    mockUseLiveData.mockReturnValue(
      makeState<PageData>({
        data: { trail: TRAIL_WITH_ROWS, clv: null },
        isLoading: false,
        isStale: true,
        error: "HTTP 503",
      }),
    );
    await renderPage();
    // Table should still show -- error must not erase last-good data from the UI
    expect(screen.getByTestId("pm-trail-table")).toBeInTheDocument();
    // No "unavailable" role=status panel (the "paper mode" badge is role=status
    // but its label is "paper mode", not "unavailable")
    expect(
      screen.queryByRole("status", { name: /unavailable/i }),
    ).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// WS5 -- error.tsx route error boundary exists and renders honestly
// ---------------------------------------------------------------------------

describe("/paper -- error.tsx route boundary", () => {
  it("error.tsx file exists and exports a default component", async () => {
    const mod = await import("../error");
    expect(typeof mod.default).toBe("function");
  });

  it("error boundary renders data-testid=paper-error-boundary", async () => {
    const { default: PaperError } = await import("../error");
    const resetFn = vi.fn();
    render(<PaperError error={new Error("test error")} reset={resetFn} />);
    expect(screen.getByTestId("paper-error-boundary")).toBeInTheDocument();
  });

  it("error boundary renders a retry button", async () => {
    const { default: PaperError } = await import("../error");
    const resetFn = vi.fn();
    render(<PaperError error={new Error("test error")} reset={resetFn} />);
    expect(screen.getByRole("button", { name: /retry/i })).toBeInTheDocument();
  });

  it("error boundary calls reset() when retry is clicked", async () => {
    const { default: PaperError } = await import("../error");
    const resetFn = vi.fn();
    const { getByRole } = render(
      <PaperError error={new Error("test error")} reset={resetFn} />,
    );
    getByRole("button", { name: /retry/i }).click();
    expect(resetFn).toHaveBeenCalledOnce();
  });

  it("error boundary does not show dollar figures (honesty rail)", async () => {
    const { default: PaperError } = await import("../error");
    const { container } = render(
      <PaperError error={new Error("test error")} reset={() => {}} />,
    );
    expect(container.textContent ?? "").not.toMatch(/\$\d/);
  });

  it("error boundary has role=alert so AT announces the degraded state", async () => {
    const { default: PaperError } = await import("../error");
    render(<PaperError error={new Error("test error")} reset={() => {}} />);
    expect(screen.getByRole("alert")).toBeInTheDocument();
  });

  it("error boundary mentions UNITS (no $ edge claim)", async () => {
    const { default: PaperError } = await import("../error");
    const { container } = render(
      <PaperError error={new Error("test error")} reset={() => {}} />,
    );
    expect(container.textContent).toMatch(/UNITS/);
  });
});

// ---------------------------------------------------------------------------
// Legacy CLV strip: aria-label region
// ---------------------------------------------------------------------------

describe("/paper -- CLV strip aria-label", () => {
  it("CLV summary region has aria-label='CLV summary'", async () => {
    mockUseLiveData.mockReturnValue(makeState({ isLoading: true }));
    await renderPage();
    expect(screen.getByLabelText("CLV summary")).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Legacy CLV strip: loading skeleton state (not red, not failed)
// ---------------------------------------------------------------------------

describe("/paper -- CLV strip loading skeleton", () => {
  it("shows aria-busy skeleton tiles while loading (no data yet)", async () => {
    mockUseLiveData.mockReturnValue(
      makeState({ isLoading: true, data: null }),
    );
    await renderPage();
    const busyElements = screen
      .getAllByRole("generic")
      .filter((el) => el.getAttribute("aria-busy") === "true");
    expect(busyElements.length).toBeGreaterThanOrEqual(3);
  });

  it("no text-red or text-danger class on any CLV element while loading", async () => {
    mockUseLiveData.mockReturnValue(
      makeState({ isLoading: true, data: null }),
    );
    await renderPage();
    const strip = screen.getByLabelText("CLV summary");
    expect(strip.innerHTML).not.toMatch(/text-red/);
    expect(strip.innerHTML).not.toMatch(/text-danger/);
  });

  it("loading tiles carry a label indicating their column name", async () => {
    mockUseLiveData.mockReturnValue(
      makeState({ isLoading: true, data: null }),
    );
    await renderPage();
    expect(screen.getByLabelText("Graded bets loading")).toBeInTheDocument();
    expect(screen.getByLabelText("% beat close loading")).toBeInTheDocument();
    expect(screen.getByLabelText("CLV loading")).toBeInTheDocument();
  });

  it("does NOT render a literal '...' string in the CLV strip while loading", async () => {
    mockUseLiveData.mockReturnValue(
      makeState({ isLoading: true, data: null }),
    );
    await renderPage();
    const strip = screen.getByLabelText("CLV summary");
    expect(strip.textContent).not.toContain("...");
  });
});

// ---------------------------------------------------------------------------
// Legacy: honest empty 'no settled bets yet'
// ---------------------------------------------------------------------------

describe("/paper -- honest empty 'no settled bets yet'", () => {
  it("renders the 'No settled bets yet' message when n_bets is 0", async () => {
    mockUseLiveData.mockReturnValue(
      makeState<PageData>({
        data: { trail: TRAIL_EMPTY, clv: CLV_ZERO },
        isLoading: false,
        lastUpdatedAt: Date.now(),
        ageSec: 1,
      }),
    );
    await renderPage();
    expect(screen.getByTestId("paper-no-settled-bets")).toBeInTheDocument();
  });

  it("'No settled bets yet' message does not carry red or danger styling", async () => {
    mockUseLiveData.mockReturnValue(
      makeState<PageData>({
        data: { trail: TRAIL_EMPTY, clv: CLV_ZERO },
        isLoading: false,
        lastUpdatedAt: Date.now(),
        ageSec: 1,
      }),
    );
    await renderPage();
    const el = screen.getByTestId("paper-no-settled-bets");
    const cls = el.className;
    expect(cls).not.toMatch(/text-red/);
    expect(cls).not.toMatch(/text-danger/);
    expect(cls).not.toMatch(/text-destructive/);
  });

  it("'No settled bets yet' message says 'No edge is claimed'", async () => {
    mockUseLiveData.mockReturnValue(
      makeState<PageData>({
        data: { trail: TRAIL_EMPTY, clv: CLV_ZERO },
        isLoading: false,
        lastUpdatedAt: Date.now(),
        ageSec: 1,
      }),
    );
    await renderPage();
    const el = screen.getByTestId("paper-no-settled-bets");
    expect(el.textContent).toMatch(/no edge is claimed/i);
  });

  it("does NOT show 'No settled bets yet' when n_bets > 0", async () => {
    mockUseLiveData.mockReturnValue(
      makeState<PageData>({
        data: { trail: TRAIL_EMPTY, clv: CLV_POS },
        isLoading: false,
        lastUpdatedAt: Date.now(),
        ageSec: 1,
      }),
    );
    await renderPage();
    expect(screen.queryByTestId("paper-no-settled-bets")).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// Legacy: mean-CLV color honesty
// ---------------------------------------------------------------------------

describe("/paper -- mean-CLV color honesty", () => {
  it("mean-CLV shows neutral slate color (not green/danger) when value is null", async () => {
    mockUseLiveData.mockReturnValue(
      makeState<PageData>({
        data: { trail: TRAIL_EMPTY, clv: CLV_ZERO },
        isLoading: false,
        lastUpdatedAt: Date.now(),
        ageSec: 1,
      }),
    );
    await renderPage();
    const strip = screen.getByLabelText("CLV summary");
    expect(strip.innerHTML).not.toMatch(/text-success/);
    expect(strip.innerHTML).not.toMatch(/text-danger/);
  });

  it("mean-CLV shows text-success class when value is positive", async () => {
    mockUseLiveData.mockReturnValue(
      makeState<PageData>({
        data: { trail: TRAIL_EMPTY, clv: CLV_POS },
        isLoading: false,
        lastUpdatedAt: Date.now(),
        ageSec: 1,
      }),
    );
    await renderPage();
    const strip = screen.getByLabelText("CLV summary");
    expect(strip.innerHTML).toMatch(/text-success/);
  });

  it("mean-CLV shows text-danger class when value is negative", async () => {
    mockUseLiveData.mockReturnValue(
      makeState<PageData>({
        data: { trail: TRAIL_EMPTY, clv: CLV_NEG },
        isLoading: false,
        lastUpdatedAt: Date.now(),
        ageSec: 1,
      }),
    );
    await renderPage();
    const strip = screen.getByLabelText("CLV summary");
    expect(strip.innerHTML).toMatch(/text-danger/);
  });
});

// ---------------------------------------------------------------------------
// Legacy: unit-convention note
// ---------------------------------------------------------------------------

describe("/paper -- unit-convention note", () => {
  it("renders data-testid=paper-unit-convention-note", async () => {
    mockUseLiveData.mockReturnValue(makeState({ isLoading: true }));
    await renderPage();
    expect(screen.getByTestId("paper-unit-convention-note")).toBeInTheDocument();
  });

  it("unit-convention note mentions UNITS", async () => {
    mockUseLiveData.mockReturnValue(makeState({ isLoading: true }));
    await renderPage();
    const note = screen.getByTestId("paper-unit-convention-note");
    expect(note.textContent).toMatch(/UNITS/);
  });

  it("unit-convention note does NOT mention dollars with a figure", async () => {
    mockUseLiveData.mockReturnValue(makeState({ isLoading: true }));
    await renderPage();
    const note = screen.getByTestId("paper-unit-convention-note");
    expect(note.textContent ?? "").not.toMatch(/\$\d/);
  });
});

// ---------------------------------------------------------------------------
// Honesty rail: no '$' followed by a digit anywhere in the page DOM
// ---------------------------------------------------------------------------

describe("/paper -- no dollar figure in DOM (honesty rail)", () => {
  it("loading state: no dollar-amount string in the rendered DOM", async () => {
    mockUseLiveData.mockReturnValue(makeState({ isLoading: true }));
    const { container } = await renderPage();
    expect(container.textContent ?? "").not.toMatch(/\$\d/);
  });

  it("empty settled state: no dollar-amount string in the rendered DOM", async () => {
    mockUseLiveData.mockReturnValue(
      makeState<PageData>({
        data: { trail: TRAIL_EMPTY, clv: CLV_ZERO },
        isLoading: false,
        lastUpdatedAt: Date.now(),
        ageSec: 1,
      }),
    );
    const { container } = await renderPage();
    expect(container.textContent ?? "").not.toMatch(/\$\d/);
  });

  it("positive CLV state: no dollar-amount string in the rendered DOM", async () => {
    mockUseLiveData.mockReturnValue(
      makeState<PageData>({
        data: { trail: TRAIL_EMPTY, clv: CLV_POS },
        isLoading: false,
        lastUpdatedAt: Date.now(),
        ageSec: 1,
      }),
    );
    const { container } = await renderPage();
    expect(container.textContent ?? "").not.toMatch(/\$\d/);
  });
});

// ===========================================================================
// WS3 -- /paper/[betId] detail page acceptance tests
//
// Acceptance criteria:
//   1. Page renders a LiveBadge / last-updated age (data-testid="bet-detail-last-updated")
//   2. A failed poll keeps the previously-found row visible (last-good, not blank)
//      and surfaces an honest stale/error indicator (never green on stale)
//   3. A matching row still resolves and renders via ExecutionDetail
//   4. No $ P&L in the detail page DOM (honesty rail)
// ===========================================================================

// Fixture: a minimal trail row (only fields matchRow / ExecutionDetail touch).
const DETAIL_ROW_NBA = {
  game_id: "0022300001",
  matchup: "LAL @ BOS",
  sport: "nba",
  side: "home",
  market_type: "moneyline",
  taken_book: "kalshi",
  taken_decimal: 2.1,
  model_prob: 0.55,
  model_ev: 0.155,
  tier: "A",
  stake_units: 0.25,
  status: "open",
  graded: false,
  outcome: null,
  clv_pct: null,
  beat_close: null,
  clv_is_proxy: false,
  clv_status: "no_close",
  clv_unavailable: true,
  clv_note: null,
  executed: false,
  ts: "2026-06-19T18:00:00Z",
  settled_at: null,
  line: null,
} as PaperTrail["trail"][number];

// betId that encodes the row above (matches toBetId: sport|game_id|market|side|book).
// encodeURIComponent("nba|0022300001|moneyline|home|kalshi") matches the matchRow prefix.
const DETAIL_BET_ID = encodeURIComponent("nba|0022300001|moneyline|home|kalshi");

const TRAIL_WITH_NBA_ROW: PaperTrail = {
  status: "ok",
  count: 1,
  trail: [DETAIL_ROW_NBA],
};

// Lazy-import the detail page AFTER mocks are registered.
async function renderDetailPage() {
  const { default: BetDetailPage } = await import("../[betId]/page");
  return render(<BetDetailPage />);
}

// ---------------------------------------------------------------------------
// WS3: LiveBadge / last-updated age element present
// ---------------------------------------------------------------------------

describe("/paper/[betId] -- LiveBadge / last-updated age (WS3)", () => {
  it("renders data-testid=bet-detail-last-updated element", async () => {
    mockUseParams.mockReturnValue({ betId: DETAIL_BET_ID });
    mockUseLiveData.mockReturnValue(
      makeState<PaperTrail>({
        data: TRAIL_WITH_NBA_ROW,
        isLoading: false,
        lastUpdatedAt: Date.now(),
        ageSec: 3,
        isStale: false,
      }),
    );
    await renderDetailPage();
    expect(screen.getByTestId("bet-detail-last-updated")).toBeInTheDocument();
  });

  it("shows 'checking' when ageSec is null (no data yet)", async () => {
    mockUseParams.mockReturnValue({ betId: DETAIL_BET_ID });
    mockUseLiveData.mockReturnValue(
      makeState<PaperTrail>({ isLoading: true, ageSec: null, data: null }),
    );
    await renderDetailPage();
    expect(screen.getByTestId("bet-detail-last-updated").textContent).toMatch(/checking/);
  });

  it("shows 'just now' when ageSec < 5 and not stale", async () => {
    mockUseParams.mockReturnValue({ betId: DETAIL_BET_ID });
    mockUseLiveData.mockReturnValue(
      makeState<PaperTrail>({
        data: TRAIL_WITH_NBA_ROW,
        isLoading: false,
        lastUpdatedAt: Date.now(),
        ageSec: 2,
        isStale: false,
      }),
    );
    await renderDetailPage();
    expect(screen.getByTestId("bet-detail-last-updated").textContent).toMatch(/just now/);
  });

  it("shows stale indicator (amber class) when isStale=true", async () => {
    mockUseParams.mockReturnValue({ betId: DETAIL_BET_ID });
    mockUseLiveData.mockReturnValue(
      makeState<PaperTrail>({
        data: TRAIL_WITH_NBA_ROW,
        isLoading: false,
        lastUpdatedAt: Date.now() - 120_000,
        ageSec: 120,
        isStale: true,
      }),
    );
    await renderDetailPage();
    const badge = screen.getByTestId("bet-detail-last-updated");
    expect(badge.textContent).toMatch(/stale/i);
    expect(badge.className).toMatch(/amber/);
  });

  it("badge is NOT green (no green-on-stale) when isStale=true", async () => {
    mockUseParams.mockReturnValue({ betId: DETAIL_BET_ID });
    mockUseLiveData.mockReturnValue(
      makeState<PaperTrail>({
        data: TRAIL_WITH_NBA_ROW,
        isLoading: false,
        ageSec: 120,
        isStale: true,
      }),
    );
    await renderDetailPage();
    const badge = screen.getByTestId("bet-detail-last-updated");
    // Must not have any green class while stale
    expect(badge.className).not.toMatch(/green/);
  });
});

// ---------------------------------------------------------------------------
// WS3: last-good data retained on failed poll
// ---------------------------------------------------------------------------

describe("/paper/[betId] -- last-good retention on failed poll (WS3)", () => {
  it("keeps ExecutionDetail visible with last-good row after a failed poll", async () => {
    mockUseParams.mockReturnValue({ betId: DETAIL_BET_ID });
    // Simulate: had good data, then a poll failed.
    // useLiveData contract: data=last-good, error=set, isStale=true.
    mockUseLiveData.mockReturnValue(
      makeState<PaperTrail>({
        data: TRAIL_WITH_NBA_ROW,
        isLoading: false,
        lastUpdatedAt: Date.now() - 60_000,
        ageSec: 60,
        isStale: true,
        error: "HTTP 503",
      }),
    );
    await renderDetailPage();
    const detail = screen.getByTestId("execution-detail");
    // Row must still be visible (has-row=true), not blank
    expect(detail.dataset["hasRow"]).toBe("true");
    // Not in loading state
    expect(detail.dataset["loading"]).toBe("false");
    // Stale indicator is present
    expect(screen.getByTestId("bet-detail-last-updated").textContent).toMatch(/stale/i);
  });

  it("stale badge has amber class when error set with last-good data", async () => {
    mockUseParams.mockReturnValue({ betId: DETAIL_BET_ID });
    mockUseLiveData.mockReturnValue(
      makeState<PaperTrail>({
        data: TRAIL_WITH_NBA_ROW,
        isLoading: false,
        ageSec: 60,
        isStale: true,
        error: "HTTP 502",
      }),
    );
    await renderDetailPage();
    const badge = screen.getByTestId("bet-detail-last-updated");
    expect(badge.className).toMatch(/amber/);
    // And NOT green
    expect(badge.className).not.toMatch(/green/);
  });

  it("shows unavailable (no row) only when data is null AND error is set", async () => {
    mockUseParams.mockReturnValue({ betId: DETAIL_BET_ID });
    // First poll failed -- no prior good data.
    mockUseLiveData.mockReturnValue(
      makeState<PaperTrail>({
        data: null,
        isLoading: false,
        error: "HTTP 502",
      }),
    );
    await renderDetailPage();
    const detail = screen.getByTestId("execution-detail");
    // ExecutionDetail should receive no row and an error
    expect(detail.dataset["hasRow"]).toBe("false");
    expect(detail.dataset["error"]).not.toBe("");
  });

  it("does NOT show error in ExecutionDetail when data is present even if errored", async () => {
    mockUseParams.mockReturnValue({ betId: DETAIL_BET_ID });
    mockUseLiveData.mockReturnValue(
      makeState<PaperTrail>({
        data: TRAIL_WITH_NBA_ROW,
        isLoading: false,
        isStale: true,
        error: "HTTP 503",
      }),
    );
    await renderDetailPage();
    const detail = screen.getByTestId("execution-detail");
    // Row should still be visible
    expect(detail.dataset["hasRow"]).toBe("true");
    // ExecutionDetail error prop should be null/empty (row is shown, stale badge handles UX)
    expect(detail.dataset["error"]).toBe("");
  });
});

// ---------------------------------------------------------------------------
// WS3: matching row resolves and renders via ExecutionDetail
// ---------------------------------------------------------------------------

describe("/paper/[betId] -- row resolution via ExecutionDetail (WS3)", () => {
  it("resolves the matching row and passes it to ExecutionDetail", async () => {
    mockUseParams.mockReturnValue({ betId: DETAIL_BET_ID });
    mockUseLiveData.mockReturnValue(
      makeState<PaperTrail>({
        data: TRAIL_WITH_NBA_ROW,
        isLoading: false,
        lastUpdatedAt: Date.now(),
        ageSec: 5,
        isStale: false,
      }),
    );
    await renderDetailPage();
    const detail = screen.getByTestId("execution-detail");
    expect(detail.dataset["hasRow"]).toBe("true");
    expect(detail.textContent).toContain("detail-with-row");
  });

  it("renders loading state when isLoading=true and data=null", async () => {
    mockUseParams.mockReturnValue({ betId: DETAIL_BET_ID });
    mockUseLiveData.mockReturnValue(
      makeState<PaperTrail>({ isLoading: true, data: null }),
    );
    await renderDetailPage();
    const detail = screen.getByTestId("execution-detail");
    expect(detail.dataset["loading"]).toBe("true");
  });

  it("shows not-found error when trail has rows but none match the betId", async () => {
    // betId that does NOT match any row in the trail
    const unknownBetId = encodeURIComponent("soccer|unknown-game|moneyline|home|betfair");
    mockUseParams.mockReturnValue({ betId: unknownBetId });
    mockUseLiveData.mockReturnValue(
      makeState<PaperTrail>({
        data: TRAIL_WITH_NBA_ROW,
        isLoading: false,
        lastUpdatedAt: Date.now(),
        ageSec: 5,
        isStale: false,
      }),
    );
    await renderDetailPage();
    const detail = screen.getByTestId("execution-detail");
    expect(detail.dataset["hasRow"]).toBe("false");
    // An error message should be provided indicating not-found
    expect(detail.dataset["error"]).toMatch(/not found/i);
  });

  it("calls useLiveData (not a raw setInterval) for polling", async () => {
    const siSpy = vi.spyOn(globalThis, "setInterval");
    mockUseParams.mockReturnValue({ betId: DETAIL_BET_ID });
    mockUseLiveData.mockReturnValue(
      makeState<PaperTrail>({ isLoading: true }),
    );
    await renderDetailPage();
    // useLiveData must have been called
    expect(mockUseLiveData).toHaveBeenCalled();
    // No raw setInterval in the page code (useLiveData is fully mocked and
    // returns synchronously here, so any calls are from the page itself)
    expect(siSpy.mock.calls.length).toBe(0);
  });
});

// ---------------------------------------------------------------------------
// WS3: honesty rail -- no $ figure in detail page DOM
// ---------------------------------------------------------------------------

describe("/paper/[betId] -- no dollar figure in DOM (honesty rail, WS3)", () => {
  it("loading state: no dollar-amount string in the rendered DOM", async () => {
    mockUseParams.mockReturnValue({ betId: DETAIL_BET_ID });
    mockUseLiveData.mockReturnValue(
      makeState<PaperTrail>({ isLoading: true }),
    );
    const { container } = await renderDetailPage();
    expect(container.textContent ?? "").not.toMatch(/\$\d/);
  });

  it("live state with row: no dollar-amount string in the rendered DOM", async () => {
    mockUseParams.mockReturnValue({ betId: DETAIL_BET_ID });
    mockUseLiveData.mockReturnValue(
      makeState<PaperTrail>({
        data: TRAIL_WITH_NBA_ROW,
        isLoading: false,
        lastUpdatedAt: Date.now(),
        ageSec: 5,
        isStale: false,
      }),
    );
    const { container } = await renderDetailPage();
    expect(container.textContent ?? "").not.toMatch(/\$\d/);
  });

  it("stale/error state: no dollar-amount string in the rendered DOM", async () => {
    mockUseParams.mockReturnValue({ betId: DETAIL_BET_ID });
    mockUseLiveData.mockReturnValue(
      makeState<PaperTrail>({
        data: TRAIL_WITH_NBA_ROW,
        isLoading: false,
        ageSec: 120,
        isStale: true,
        error: "HTTP 503",
      }),
    );
    const { container } = await renderDetailPage();
    expect(container.textContent ?? "").not.toMatch(/\$\d/);
  });
});

// ===========================================================================
// W2 -- /paper page: primary settled book visible (54 rows), PM-only secondary
//
// Acceptance criteria (W2):
//   1. With 54 settled rows, PaperTrailSettled receives the full rows (not hidden).
//   2. PM-empty block only appears when PM rows are filtered to 0 (no kalshi/polymarket).
//   3. PM-empty block is labelled 'no liquid PM markets'.
//   4. No $/dollar/pnl token anywhere.
//   5. Real-money DENY banner always present.
//   6. The settled book panel is distinct from the PM trail panel.
// ===========================================================================

// Build 54 minimal settled rows for acceptance test.
function make54TrailRows(): PaperTrail["trail"] {
  const rows: PaperTrail["trail"] = [];
  for (let i = 0; i < 24; i++) {
    rows.push({
      game_id: `g-w-${i}`, matchup: `TeamA vs TeamB`, sport: "nba",
      side: "home", market_type: "moneyline", line: null,
      taken_book: "draftkings", taken_decimal: 1.95,
      model_prob: 0.55, model_ev: 0.07, tier: "A", stake_units: 1.0,
      status: "settled", graded: true, outcome: "win",
      clv_pct: 0.025, beat_close: true, clv_is_proxy: false,
      clv_status: "true_close", clv_unavailable: false, clv_note: null,
      executed: false, ts: "2026-06-15T20:00:00Z", settled_at: "2026-06-15T23:30:00Z",
    });
  }
  for (let i = 0; i < 20; i++) {
    rows.push({
      game_id: `g-l-${i}`, matchup: "TeamC vs TeamD", sport: "nba",
      side: "away", market_type: "moneyline", line: null,
      taken_book: "fanduel", taken_decimal: 2.05,
      model_prob: 0.48, model_ev: -0.02, tier: "B", stake_units: 0.5,
      status: "settled", graded: true, outcome: "loss",
      clv_pct: -0.015, beat_close: false, clv_is_proxy: false,
      clv_status: "true_close", clv_unavailable: false, clv_note: null,
      executed: false, ts: "2026-06-16T20:00:00Z", settled_at: "2026-06-16T23:30:00Z",
    });
  }
  for (let i = 0; i < 8; i++) {
    rows.push({
      game_id: `g-p-${i}`, matchup: "TeamE vs TeamF", sport: "nba",
      side: "home", market_type: "moneyline", line: null,
      taken_book: "betmgm", taken_decimal: null,
      model_prob: 0.5, model_ev: 0, tier: "C", stake_units: 0.25,
      status: "settled", graded: true, outcome: "push",
      clv_pct: null, beat_close: null, clv_is_proxy: false,
      clv_status: "no_close", clv_unavailable: true, clv_note: null,
      executed: false, ts: "2026-06-17T20:00:00Z", settled_at: "2026-06-17T23:30:00Z",
    });
  }
  for (let i = 0; i < 2; i++) {
    rows.push({
      game_id: `g-o-${i}`, matchup: "TeamG vs TeamH", sport: "nba",
      side: "home", market_type: "moneyline", line: null,
      taken_book: "draftkings", taken_decimal: 1.9,
      model_prob: 0.52, model_ev: null, tier: "B", stake_units: 0.5,
      status: "open", graded: false, outcome: null,
      clv_pct: null, beat_close: null, clv_is_proxy: false,
      clv_status: null, clv_unavailable: true, clv_note: null,
      executed: false, ts: "2026-06-18T20:00:00Z", settled_at: null,
    });
  }
  return rows;
}

const TRAIL_54: PaperTrail = {
  status: "ok",
  count: 54,
  trail: make54TrailRows(),
};
const CLV_54: ClvScoreboard = {
  n_bets: 52, pct_beat_close: 0.615, mean_clv_pct: 0.018,
  by_sport: null, clv_is_proxy: false,
};

describe("/paper -- W2 acceptance: primary settled book with 54 rows", () => {
  it("with 54 settled rows, PaperTrailSettled receives all 54 rows", async () => {
    mockUseLiveData.mockReturnValue(
      makeState<PageData>({
        data: { trail: TRAIL_54, clv: CLV_54 },
        isLoading: false,
        lastUpdatedAt: Date.now(),
        ageSec: 3,
        isStale: false,
      }),
    );
    await renderPage();
    const settledBook = screen.getByTestId("paper-trail-settled");
    expect(settledBook.dataset["rows"]).toBe("54");
    expect(settledBook.dataset["loading"]).toBe("false");
  });

  it("real-money DENY banner is always present", async () => {
    mockUseLiveData.mockReturnValue(
      makeState<PageData>({
        data: { trail: TRAIL_54, clv: CLV_54 },
        isLoading: false,
        lastUpdatedAt: Date.now(),
        ageSec: 3,
      }),
    );
    await renderPage();
    expect(screen.getByTestId("real-money-deny-banner")).toBeInTheDocument();
    expect(screen.getByTestId("real-money-deny-banner").textContent).toMatch(/DENY/);
  });

  it("PM-empty block appears when no kalshi/polymarket rows", async () => {
    // Rows have draftkings/fanduel/betmgm -- no kalshi or polymarket
    mockUseLiveData.mockReturnValue(
      makeState<PageData>({
        data: { trail: TRAIL_54, clv: CLV_54 },
        isLoading: false,
        lastUpdatedAt: Date.now(),
        ageSec: 3,
        isStale: false,
      }),
    );
    await renderPage();
    expect(screen.getByTestId("pm-no-liquid-markets")).toBeInTheDocument();
  });

  it("PM-empty block is labelled 'no liquid PM markets'", async () => {
    mockUseLiveData.mockReturnValue(
      makeState<PageData>({
        data: { trail: TRAIL_54, clv: CLV_54 },
        isLoading: false,
        lastUpdatedAt: Date.now(),
        ageSec: 3,
      }),
    );
    await renderPage();
    const pmEmpty = screen.getByTestId("pm-no-liquid-markets");
    expect(pmEmpty.textContent).toMatch(/no liquid PM markets/i);
  });

  it("PM-empty block is NOT rendered when kalshi rows exist", async () => {
    const trailWithKalshi: PaperTrail = {
      status: "ok",
      count: 1,
      trail: [{
        game_id: "k1", matchup: "A vs B", sport: "nba", side: "home",
        market_type: "moneyline", line: null, taken_book: "kalshi",
        taken_decimal: 2.0, model_prob: 0.55, model_ev: 0.1, tier: "A",
        stake_units: 1.0, status: "settled", graded: true, outcome: "win",
        clv_pct: 0.02, beat_close: true, clv_is_proxy: false,
        clv_status: "true_close", clv_unavailable: false, clv_note: null,
        executed: false, ts: "2026-06-15T20:00:00Z", settled_at: "2026-06-15T23:30:00Z",
      }],
    };
    mockUseLiveData.mockReturnValue(
      makeState<PageData>({
        data: { trail: trailWithKalshi, clv: CLV_POS },
        isLoading: false,
        lastUpdatedAt: Date.now(),
        ageSec: 3,
      }),
    );
    await renderPage();
    // PM-empty block should NOT appear because kalshi row exists
    expect(screen.queryByTestId("pm-no-liquid-markets")).toBeNull();
  });

  it("no $/dollar/pnl token in DOM with 54 rows", async () => {
    mockUseLiveData.mockReturnValue(
      makeState<PageData>({
        data: { trail: TRAIL_54, clv: CLV_54 },
        isLoading: false,
        lastUpdatedAt: Date.now(),
        ageSec: 3,
      }),
    );
    const { container } = await renderPage();
    expect(container.textContent ?? "").not.toMatch(/\$\d/);
    expect((container.textContent ?? "").toLowerCase()).not.toMatch(/p&l|pnl/);
  });

  it("'no settled bets' message is absent when trail has settled rows", async () => {
    mockUseLiveData.mockReturnValue(
      makeState<PageData>({
        data: { trail: TRAIL_54, clv: CLV_54 },
        isLoading: false,
        lastUpdatedAt: Date.now(),
        ageSec: 3,
      }),
    );
    await renderPage();
    expect(screen.queryByTestId("paper-no-settled-bets")).toBeNull();
  });
});
