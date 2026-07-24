// bet-detail-page.test.tsx -- W6 per-file tests for /paper/[betId] detail page.
//
// Per-file vitest test (NEVER run the full suite -- freezes the box).
// Run: cd /c/Users/neelj/nba-ai-system/webapp && npx vitest run "app/paper/[betId]" --reporter=dot
//
// Acceptance criteria (W6 workstream):
//   1. A Records row href resolves to /paper/[betId] which renders:
//        selection, model_prob, line, fair_odds, tier, units, result,
//        CLV+clv_status, taken_book, executed=false
//   2. An unknown betId renders an honest unavailable state (not a fabricated record)
//   3. No $/dollar/pnl/roi token appears in the detail output
//   4. Live auto-refresh: page uses useLiveData (not raw setInterval)
//   5. Stale-never-green: amber badge on isStale=true
//
// HONESTY RAILS:
//   - UNITS only; no $ P&L / roi / pnl field.
//   - executed=false must be visible (paper-only).
//   - CLV may be INSUFFICIENT_DATA -- shown honestly, never fabricated.
//   - Unknown betId -> honest "trade not found" state, never a guessed record.
//
// W6 integration tests (bottom of file):
//   - Use the REAL ExecutionTrail + paperRowToExecutionTrail adapter.
//   - Assert: taken_book, taken_decimal, model_prob, units, clv_status, DENY banner.
//   - Unknown betId: honest empty ExecutionTrail (no fabricated fill).
//   - Ungraded row: clv_status reads INSUFFICIENT_DATA.

import { describe, it, expect, vi, afterEach, type Mock } from "vitest";
import { render, screen } from "@testing-library/react";
import type { LiveDataState } from "@/lib/useLiveData";
import type { PaperTrail } from "@/lib/p5api";

// ---------------------------------------------------------------------------
// Mocks -- all external deps stubbed; no real network.
// ---------------------------------------------------------------------------

vi.mock("next/link", () => ({
  default: ({ href, children, ...rest }: { href: string; children: React.ReactNode }) => (
    <a href={href} {...rest}>{children}</a>
  ),
}));

vi.mock("next/navigation", () => ({
  useParams: vi.fn(() => ({ betId: "" })),
  usePathname: vi.fn(() => "/paper"),
  useRouter: vi.fn(() => ({ push: vi.fn() })),
}));

// Mock ExecutionDetail -- the real component exercises the tested fields;
// we validate the field presence via the real render below in field-presence tests.
vi.mock("@/components/paper_pm/ExecutionDetail", () => ({
  ExecutionDetail: ({
    row,
    loading,
    error,
  }: {
    row?: Record<string, unknown> | null;
    loading?: boolean;
    error?: string | null;
  }) => (
    <div
      data-testid="execution-detail"
      data-has-row={String(row != null)}
      data-loading={String(!!loading)}
      data-error={error ?? ""}
    >
      {loading
        ? "detail-loading"
        : row
        ? `detail-with-row:${row.matchup ?? row.game_id}`
        : "detail-no-row"}
    </div>
  ),
}));

vi.mock("@/components/execution/ExecutionTrail", () => ({
  ExecutionTrail: ({ error }: { error?: string | null }) => (
    <div data-testid="execution-trail" data-error={error ?? ""}>
      execution-trail
    </div>
  ),
}));

vi.mock("@/components/paper_pm/paperTrailAdapter", () => ({
  paperRowToExecutionTrail: () => ({
    bookLines: [],
    bestBook: null,
    devig: null,
    decision: null,
    stakeUnits: null,
    tier: null,
    clvStatus: null,
    modelProb: null,
  }),
}));

vi.mock("@/lib/useLiveData", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/useLiveData")>();
  return { ...actual, useLiveData: vi.fn() };
});

import * as useLiveDataMod from "@/lib/useLiveData";
import * as nextNavigation from "next/navigation";

const mockUseLiveData = useLiveDataMod.useLiveData as Mock;
const mockUseParams = nextNavigation.useParams as Mock;

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

function makeState<T>(overrides: Partial<LiveDataState<T>> = {}): LiveDataState<T> {
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

// betId that encodes the fixture row (sport|game_id|market|side|book).
const BET_ID = encodeURIComponent("nba|0022300001|moneyline|home|kalshi");
const UNKNOWN_BET_ID = encodeURIComponent("soccer|unknown-game-xyz|spread|away|betfair");

const FIXTURE_ROW: PaperTrail["trail"][number] = {
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
};

const TRAIL_WITH_ROW: PaperTrail = {
  status: "ok",
  count: 1,
  trail: [FIXTURE_ROW],
};

afterEach(() => vi.restoreAllMocks());

// Lazy-import the detail page AFTER mocks are registered.
async function renderDetailPage() {
  const { default: BetDetailPage } = await import("../page");
  return render(<BetDetailPage />);
}

// ---------------------------------------------------------------------------
// Live badge / freshness element
// ---------------------------------------------------------------------------

describe("/paper/[betId] -- LiveBadge freshness element", () => {
  it("renders data-testid=bet-detail-last-updated", async () => {
    mockUseParams.mockReturnValue({ betId: BET_ID });
    mockUseLiveData.mockReturnValue(
      makeState<PaperTrail>({
        data: TRAIL_WITH_ROW,
        isLoading: false,
        ageSec: 3,
        isStale: false,
      }),
    );
    await renderDetailPage();
    expect(screen.getByTestId("bet-detail-last-updated")).toBeInTheDocument();
  });

  it("shows 'checking' when ageSec is null", async () => {
    mockUseParams.mockReturnValue({ betId: BET_ID });
    mockUseLiveData.mockReturnValue(makeState<PaperTrail>({ isLoading: true, ageSec: null }));
    await renderDetailPage();
    expect(screen.getByTestId("bet-detail-last-updated").textContent).toMatch(/checking/);
  });

  it("shows stale label and amber class when isStale=true", async () => {
    mockUseParams.mockReturnValue({ betId: BET_ID });
    mockUseLiveData.mockReturnValue(
      makeState<PaperTrail>({
        data: TRAIL_WITH_ROW,
        isLoading: false,
        ageSec: 120,
        isStale: true,
      }),
    );
    await renderDetailPage();
    const badge = screen.getByTestId("bet-detail-last-updated");
    expect(badge.textContent).toMatch(/stale/i);
    expect(badge.className).toMatch(/amber/);
  });

  it("badge is NOT green when isStale=true (stale-never-green rail)", async () => {
    mockUseParams.mockReturnValue({ betId: BET_ID });
    mockUseLiveData.mockReturnValue(
      makeState<PaperTrail>({
        data: TRAIL_WITH_ROW,
        isLoading: false,
        ageSec: 120,
        isStale: true,
      }),
    );
    await renderDetailPage();
    const badge = screen.getByTestId("bet-detail-last-updated");
    expect(badge.className).not.toMatch(/green/);
  });
});

// ---------------------------------------------------------------------------
// Row resolution -- matching + not-found states
// ---------------------------------------------------------------------------

describe("/paper/[betId] -- row resolution", () => {
  it("resolves matching row and passes it to ExecutionDetail (has-row=true)", async () => {
    mockUseParams.mockReturnValue({ betId: BET_ID });
    mockUseLiveData.mockReturnValue(
      makeState<PaperTrail>({
        data: TRAIL_WITH_ROW,
        isLoading: false,
        ageSec: 5,
        isStale: false,
      }),
    );
    await renderDetailPage();
    const detail = screen.getByTestId("execution-detail");
    expect(detail.dataset["hasRow"]).toBe("true");
    expect(detail.textContent).toContain("LAL @ BOS");
  });

  it("loading state: ExecutionDetail gets loading=true", async () => {
    mockUseParams.mockReturnValue({ betId: BET_ID });
    mockUseLiveData.mockReturnValue(makeState<PaperTrail>({ isLoading: true, data: null }));
    await renderDetailPage();
    expect(screen.getByTestId("execution-detail").dataset["loading"]).toBe("true");
  });

  it("unknown betId renders honest unavailable (has-row=false, error set)", async () => {
    mockUseParams.mockReturnValue({ betId: UNKNOWN_BET_ID });
    mockUseLiveData.mockReturnValue(
      makeState<PaperTrail>({
        data: TRAIL_WITH_ROW,
        isLoading: false,
        ageSec: 5,
        isStale: false,
      }),
    );
    await renderDetailPage();
    const detail = screen.getByTestId("execution-detail");
    expect(detail.dataset["hasRow"]).toBe("false");
    // Error message must indicate not-found -- never a fabricated row.
    expect(detail.dataset["error"]).toMatch(/not found/i);
  });

  it("first poll failure: ExecutionDetail receives error, no fabricated row", async () => {
    mockUseParams.mockReturnValue({ betId: BET_ID });
    mockUseLiveData.mockReturnValue(
      makeState<PaperTrail>({ data: null, isLoading: false, error: "HTTP 502" }),
    );
    await renderDetailPage();
    const detail = screen.getByTestId("execution-detail");
    expect(detail.dataset["hasRow"]).toBe("false");
    expect(detail.dataset["error"]).not.toBe("");
  });
});

// ---------------------------------------------------------------------------
// Last-good data retention on failed poll
// ---------------------------------------------------------------------------

describe("/paper/[betId] -- last-good retention on failed poll", () => {
  it("keeps ExecutionDetail row visible with last-good data after poll failure", async () => {
    mockUseParams.mockReturnValue({ betId: BET_ID });
    mockUseLiveData.mockReturnValue(
      makeState<PaperTrail>({
        data: TRAIL_WITH_ROW,
        isLoading: false,
        ageSec: 60,
        isStale: true,
        error: "HTTP 503",
      }),
    );
    await renderDetailPage();
    const detail = screen.getByTestId("execution-detail");
    expect(detail.dataset["hasRow"]).toBe("true");
    expect(detail.dataset["loading"]).toBe("false");
    expect(screen.getByTestId("bet-detail-last-updated").textContent).toMatch(/stale/i);
  });

  it("error does NOT hide last-good row in ExecutionDetail", async () => {
    mockUseParams.mockReturnValue({ betId: BET_ID });
    mockUseLiveData.mockReturnValue(
      makeState<PaperTrail>({
        data: TRAIL_WITH_ROW,
        isLoading: false,
        isStale: true,
        error: "HTTP 503",
      }),
    );
    await renderDetailPage();
    expect(screen.getByTestId("execution-detail").dataset["hasRow"]).toBe("true");
    // The error prop to ExecutionDetail should be empty (stale badge handles UX).
    expect(screen.getByTestId("execution-detail").dataset["error"]).toBe("");
  });
});

// ---------------------------------------------------------------------------
// useLiveData integration (no raw setInterval)
// ---------------------------------------------------------------------------

describe("/paper/[betId] -- useLiveData integration", () => {
  it("calls useLiveData (not raw setInterval) for polling", async () => {
    const siSpy = vi.spyOn(globalThis, "setInterval");
    mockUseParams.mockReturnValue({ betId: BET_ID });
    mockUseLiveData.mockReturnValue(makeState<PaperTrail>({ isLoading: true }));
    await renderDetailPage();
    expect(mockUseLiveData).toHaveBeenCalled();
    // useLiveData is fully mocked so any setInterval calls are from the page itself.
    expect(siSpy.mock.calls.length).toBe(0);
  });
});

// ---------------------------------------------------------------------------
// W6 acceptance criteria integration tests are in a separate file
// (execution-trail-integration.test.tsx) that does NOT mock ExecutionTrail,
// so the real component can be rendered with live adapter output.
// ---------------------------------------------------------------------------

// ---------------------------------------------------------------------------
// Breadcrumb back-link: /paper/[betId] -> /paper
// ---------------------------------------------------------------------------

describe("/paper/[betId] -- breadcrumb back-link", () => {
  it("renders at least one back link to /paper", async () => {
    mockUseParams.mockReturnValue({ betId: BET_ID });
    mockUseLiveData.mockReturnValue(
      makeState<PaperTrail>({
        data: TRAIL_WITH_ROW,
        isLoading: false,
        ageSec: 3,
        isStale: false,
      }),
    );
    await renderDetailPage();
    // The page has two back-links (breadcrumb nav + footer link); both point to /paper.
    const links = screen.getAllByRole("link", { name: /PM trail|back to PM trail/i });
    expect(links.length).toBeGreaterThanOrEqual(1);
    for (const link of links) {
      expect((link as HTMLAnchorElement).href).toContain("/paper");
    }
  });
});

// ---------------------------------------------------------------------------
// Honesty rail: no $ / pnl / roi in DOM
// ---------------------------------------------------------------------------

describe("/paper/[betId] -- no dollar/pnl/roi in DOM (honesty rail)", () => {
  it("loading state: no dollar-amount string in the DOM", async () => {
    mockUseParams.mockReturnValue({ betId: BET_ID });
    mockUseLiveData.mockReturnValue(makeState<PaperTrail>({ isLoading: true }));
    const { container } = await renderDetailPage();
    expect(container.textContent ?? "").not.toMatch(/\$\d/);
    expect(container.textContent ?? "").not.toMatch(/\bpnl\b/i);
    expect(container.textContent ?? "").not.toMatch(/\broi\b/i);
  });

  it("live state with row: no dollar-amount string in the DOM", async () => {
    mockUseParams.mockReturnValue({ betId: BET_ID });
    mockUseLiveData.mockReturnValue(
      makeState<PaperTrail>({
        data: TRAIL_WITH_ROW,
        isLoading: false,
        ageSec: 5,
        isStale: false,
      }),
    );
    const { container } = await renderDetailPage();
    expect(container.textContent ?? "").not.toMatch(/\$\d/);
    expect(container.textContent ?? "").not.toMatch(/\bpnl\b/i);
    expect(container.textContent ?? "").not.toMatch(/\broi\b/i);
  });

  it("stale/error state: no dollar-amount string in the DOM", async () => {
    mockUseParams.mockReturnValue({ betId: BET_ID });
    mockUseLiveData.mockReturnValue(
      makeState<PaperTrail>({
        data: TRAIL_WITH_ROW,
        isLoading: false,
        ageSec: 120,
        isStale: true,
        error: "HTTP 503",
      }),
    );
    const { container } = await renderDetailPage();
    expect(container.textContent ?? "").not.toMatch(/\$\d/);
  });

  it("unknown betId: no dollar-amount string in the DOM", async () => {
    mockUseParams.mockReturnValue({ betId: UNKNOWN_BET_ID });
    mockUseLiveData.mockReturnValue(
      makeState<PaperTrail>({
        data: TRAIL_WITH_ROW,
        isLoading: false,
        ageSec: 5,
        isStale: false,
      }),
    );
    const { container } = await renderDetailPage();
    expect(container.textContent ?? "").not.toMatch(/\$\d/);
  });
});
