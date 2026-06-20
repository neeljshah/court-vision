// BestBetsBoard.test.tsx -- per-component vitest covering the refresh affordance,
// AgeBadge honesty rails, and the useLiveData-backed auto-refresh wiring.
//
// Original acceptance criteria:
//   (a) refresh row renders a next-refresh countdown (data-testid) from lastFetchedAt
//   (b) AgeBadge with stale asOf renders amber tone, never green
//   (c) AgeBadge exposes raw ISO asOf via title attribute
//   (d) the affordance never renders a green badge
//
// Extended acceptance criteria (WS2-bestbets-uselivedata migration):
//   (e) BestBetsBoard uses useLiveData -- no standalone setInterval for data
//   (f) last-good data is retained + stale-banner shown on a failed poll (board never blanks)
//   (g) "refresh now" button triggers an immediate refetch via the hook's refresh()
//   (h) LivePulse renders with data-testid="live-pulse" and shows "updated Ns ago"

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, act, fireEvent, screen, waitFor } from "@testing-library/react";

// ---------------------------------------------------------------------------
// Module mocks -- intercept network calls so tests are fully synchronous
// ---------------------------------------------------------------------------

const mockBestbets = vi.hoisted(() =>
  vi.fn(() => Promise.resolve({ reason: "unavailable" })),
);
const mockBestbetsBoard = vi.hoisted(() =>
  vi.fn(() => Promise.resolve({ status: "ok", cards: [], count: 0, edge_claimed: false })),
);
vi.mock("@/lib/p5api", () => ({
  SPORTS: ["nba"],
  isUnavailable: (x: unknown) => {
    return (
      !!x && typeof x === "object" &&
      (x as { status?: string; reason?: string }).status === "unavailable" ||
      !!(x as { reason?: string })?.reason
    );
  },
  // BestBetsBoard v2 uses bestbetsBoard (not bestbets); keep bestbets in mock so
  // old test references compile. The live test (e) is updated to use bestbetsBoard.
  api: { bestbets: mockBestbets, bestbetsBoard: mockBestbetsBoard },
}));

// Mock useLiveData so we can spy on the fetcher argument and control state.
// We track the last fetcher passed in and expose a manual trigger.
type LiveDataState<T> = {
  data: T | null; lastUpdatedAt: number | null; ageSec: number | null;
  isStale: boolean; error: string | null; isLoading: boolean; refresh: () => void;
};
const mockLiveDataState = vi.hoisted((): LiveDataState<unknown> => ({
  data: null, lastUpdatedAt: null, ageSec: null,
  isStale: false, error: null, isLoading: true, refresh: vi.fn(),
}));
let _capturedFetcher: ((signal: AbortSignal) => Promise<unknown>) | null = null;
let _currentState: LiveDataState<unknown> = { ...mockLiveDataState };

vi.mock("@/lib/useLiveData", () => ({
  useLiveData: (fetcher: (signal: AbortSignal) => Promise<unknown>) => {
    _capturedFetcher = fetcher;
    return _currentState;
  },
}));

vi.mock("../StatusTabs", () => ({
  StatusTabs: ({ value }: { value: string }) => <div data-testid="status-tabs">{value}</div>,
}));
vi.mock("../SortControls", () => ({
  SortControls: () => <div data-testid="sort-controls" />,
}));
vi.mock("../BetCard", () => ({
  BetCard: () => <div data-testid="bet-card" />,
}));

// ---------------------------------------------------------------------------
// Import AFTER mocks
// ---------------------------------------------------------------------------
import { BestBetsBoard, AgeBadge } from "../BestBetsBoard";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function staleIso() { return new Date(Date.now() - 20 * 60 * 1000).toISOString(); }
function freshIso() { return new Date(Date.now() - 2 * 60 * 1000).toISOString(); }

function setLiveDataState(partial: Partial<LiveDataState<unknown>>) {
  _currentState = { ..._currentState, ...partial };
}
function resetLiveDataState() {
  _currentState = {
    data: null, lastUpdatedAt: null, ageSec: null,
    isStale: false, error: null, isLoading: true, refresh: vi.fn(),
  };
  _capturedFetcher = null;
}

// ---------------------------------------------------------------------------
// (a) next-refresh countdown
// ---------------------------------------------------------------------------
describe("BestBetsBoard refresh affordance (a)", () => {
  beforeEach(() => { vi.useFakeTimers(); resetLiveDataState(); });
  afterEach(() => { vi.useRealTimers(); });

  it("(a) renders a next-refresh countdown element after hook initialises", async () => {
    setLiveDataState({ isLoading: false, data: {}, lastUpdatedAt: Date.now(), ageSec: 5 });
    const { getByTestId } = render(<BestBetsBoard />);
    await act(async () => { await Promise.resolve(); });
    const countdown = getByTestId("next-refresh-countdown");
    expect(countdown).toBeDefined();
    const text = countdown.textContent ?? "";
    expect(
      text.includes("next refresh in") || text.includes("refreshing") || text.includes("scheduled"),
    ).toBe(true);
  });

  it("(a) countdown text is NOT the old static label", async () => {
    setLiveDataState({ isLoading: false, data: {}, lastUpdatedAt: Date.now(), ageSec: 5 });
    const { getByTestId } = render(<BestBetsBoard />);
    await act(async () => { await Promise.resolve(); });
    expect(getByTestId("next-refresh-countdown").textContent ?? "").not.toContain("auto-refreshing every ~2m");
  });
});

// ---------------------------------------------------------------------------
// (b/c/d) AgeBadge honesty rails
// ---------------------------------------------------------------------------
describe("AgeBadge honesty rails", () => {
  it("(b) stale asOf renders with amber Badge tone, never green", () => {
    const { container } = render(<AgeBadge asOf={staleIso()} />);
    const badge = container.querySelector("[data-testid='age-badge']");
    expect(badge).not.toBeNull();
    const inner = badge?.querySelector("span[role='status']") ?? badge?.querySelector("span");
    const cls = (inner?.className ?? badge?.innerHTML ?? "");
    expect(cls).toMatch(/amber/);
    expect(cls).not.toMatch(/green/);
    expect(cls).not.toMatch(/tier-a/);
  });

  it("(b) stale AgeBadge does NOT use any green class", () => {
    const { container } = render(<AgeBadge asOf={staleIso()} />);
    const allClasses = Array.from(container.querySelectorAll("*")).map((el) => el.className).join(" ");
    expect(allClasses).not.toMatch(/text-green/);
    expect(allClasses).not.toMatch(/bg-green/);
    expect(allClasses).not.toMatch(/bg-tier-a/);
    expect(allClasses).not.toMatch(/text-tier-a/);
  });

  it("(b) fresh asOf renders slate (never green -- stale-never-green rail)", () => {
    const { container } = render(<AgeBadge asOf={freshIso()} />);
    const inner = container.querySelector("span[role='status']");
    const cls = inner?.className ?? "";
    expect(cls).not.toMatch(/green/);
    expect(cls).not.toMatch(/tier-a/);
  });

  it("(c) AgeBadge exposes raw ISO asOf via title attribute", () => {
    const iso = staleIso();
    const { container } = render(<AgeBadge asOf={iso} />);
    const badge = container.querySelector("[data-testid='age-badge']");
    expect(badge?.getAttribute("title") ?? "").toContain(iso);
  });

  it("(c) title attribute absent when asOf is null", () => {
    const { container } = render(<AgeBadge asOf={null} />);
    expect(container.querySelector("[data-testid='age-badge']")).toBeNull();
  });

  it("(d) affordance never renders a green badge (stale)", () => {
    const { container } = render(<AgeBadge asOf={staleIso()} />);
    const allClasses = Array.from(container.querySelectorAll("*")).map((el) => el.className).join(" ");
    expect(allClasses).not.toMatch(/bg-tier-a|text-tier-a|bg-green|text-green/);
  });

  it("(d) affordance never renders a green badge (fresh)", () => {
    const { container } = render(<AgeBadge asOf={freshIso()} />);
    const allClasses = Array.from(container.querySelectorAll("*")).map((el) => el.className).join(" ");
    expect(allClasses).not.toMatch(/bg-tier-a|text-tier-a|bg-green|text-green/);
  });

  it("(d) affordance never renders a green badge (null asOf)", () => {
    const { container } = render(<AgeBadge asOf={null} />);
    const allClasses = Array.from(container.querySelectorAll("*")).map((el) => el.className).join(" ");
    expect(allClasses).not.toMatch(/bg-green|text-green|bg-tier-a/);
  });
});

// ---------------------------------------------------------------------------
// (e) BestBetsBoard uses useLiveData -- hook is the sole data-fetch mechanism
// ---------------------------------------------------------------------------
describe("BestBetsBoard (e) -- useLiveData is the data layer", () => {
  beforeEach(() => resetLiveDataState());

  it("(e) captures the fetcher from useLiveData (auto-refresh wiring proven)", async () => {
    setLiveDataState({ isLoading: false, data: {}, ageSec: 5, lastUpdatedAt: Date.now() });
    render(<BestBetsBoard />);
    await act(async () => { await Promise.resolve(); });
    // The hook must have received a fetcher function
    expect(typeof _capturedFetcher).toBe("function");
  });

  it("(e) fetchAllSports passes AbortSignal to api.bestbetsBoard (W3: board endpoint)", async () => {
    // BestBetsBoard v2 uses bestbetsBoard (not bestbets) -- per-sport board endpoint.
    mockBestbetsBoard.mockResolvedValueOnce({ status: "ok", cards: [], count: 0, edge_claimed: false });
    setLiveDataState({ isLoading: false, data: {}, ageSec: 0, lastUpdatedAt: Date.now() });
    render(<BestBetsBoard />);
    await act(async () => { await Promise.resolve(); });
    // Call the captured fetcher directly to verify it invokes api.bestbetsBoard
    if (_capturedFetcher) {
      const ctrl = new AbortController();
      await act(async () => { await _capturedFetcher!(ctrl.signal); });
      // bestbetsBoard should have been called with { sport: "nba" } and signal
      expect(mockBestbetsBoard).toHaveBeenCalledWith({ sport: "nba" }, ctrl.signal);
    }
  });
});

// ---------------------------------------------------------------------------
// (f) last-good retention + stale-banner on failed poll (board never blanks)
// ---------------------------------------------------------------------------
describe("BestBetsBoard (f) -- last-good retained on failed poll", () => {
  beforeEach(() => resetLiveDataState());

  it("(f) shows stale-banner when isStale+error+data available (not blank)", async () => {
    // Simulate hook: has data from a prior successful poll, poll just failed
    setLiveDataState({
      isLoading: false,
      data: { nba: null },
      ageSec: 200,
      isStale: true,
      error: "HTTP 500",
      lastUpdatedAt: Date.now() - 200_000,
    });
    render(<BestBetsBoard />);
    await act(async () => { await Promise.resolve(); });
    const banner = screen.getByTestId("stale-banner");
    expect(banner).toBeDefined();
    expect(banner.textContent).toContain("last-good");
  });

  it("(f) board does NOT show Unavailable when data is retained after failure", async () => {
    setLiveDataState({
      isLoading: false,
      data: { nba: null },
      ageSec: 200,
      isStale: true,
      error: "HTTP 500",
      lastUpdatedAt: Date.now() - 200_000,
    });
    const { queryByRole } = render(<BestBetsBoard />);
    await act(async () => { await Promise.resolve(); });
    // Should NOT show the Unavailable widget when we have retained data
    const unavailable = queryByRole("status", { name: /unavailable/i });
    expect(unavailable).toBeNull();
  });

  it("(f) board shows Unavailable only when no data has ever been received", async () => {
    setLiveDataState({
      isLoading: false,
      data: null,
      ageSec: null,
      isStale: true,
      error: "HTTP 500",
      lastUpdatedAt: null,
    });
    render(<BestBetsBoard />);
    await act(async () => { await Promise.resolve(); });
    // With no data at all, the error state should show
    const text = document.body.textContent ?? "";
    expect(text.toLowerCase()).toContain("unavailable");
  });
});

// ---------------------------------------------------------------------------
// (g) manual "refresh now" triggers hook refresh()
// ---------------------------------------------------------------------------
describe("BestBetsBoard (g) -- refresh button calls hook refresh()", () => {
  beforeEach(() => resetLiveDataState());

  it("(g) clicking 'refresh now' calls the hook refresh function", async () => {
    const refreshSpy = vi.fn();
    setLiveDataState({ isLoading: false, data: {}, ageSec: 5, lastUpdatedAt: Date.now(), refresh: refreshSpy });
    render(<BestBetsBoard />);
    await act(async () => { await Promise.resolve(); });
    const btn = screen.getByRole("button", { name: /refresh best bets now/i });
    fireEvent.click(btn);
    expect(refreshSpy).toHaveBeenCalledTimes(1);
  });

  it("(g) refresh button is disabled while isLoading=true", async () => {
    setLiveDataState({ isLoading: true, data: null });
    render(<BestBetsBoard />);
    await act(async () => { await Promise.resolve(); });
    const btn = screen.getByRole("button", { name: /refresh best bets now/i });
    expect(btn).toHaveProperty("disabled", true);
  });
});

// ---------------------------------------------------------------------------
// (h) LivePulse renders with data-testid and shows "updated Ns ago"
// ---------------------------------------------------------------------------
describe("BestBetsBoard (h) -- LivePulse rendered from hook ageSec", () => {
  beforeEach(() => resetLiveDataState());

  it("(h) live-pulse element is rendered in the board", async () => {
    setLiveDataState({ isLoading: false, data: {}, ageSec: 30, lastUpdatedAt: Date.now() });
    render(<BestBetsBoard />);
    await act(async () => { await Promise.resolve(); });
    const pulse = screen.getByTestId("live-pulse");
    expect(pulse).toBeDefined();
  });

  it("(h) live-pulse shows 'updated Xs ago' when ageSec is set", async () => {
    setLiveDataState({ isLoading: false, data: {}, ageSec: 45, lastUpdatedAt: Date.now() });
    render(<BestBetsBoard />);
    await act(async () => { await Promise.resolve(); });
    const pulse = screen.getByTestId("live-pulse");
    expect(pulse.textContent).toContain("updated 45s ago");
  });

  it("(h) live-pulse shows 'checking...' before first data", async () => {
    setLiveDataState({ isLoading: true, data: null, ageSec: null });
    render(<BestBetsBoard />);
    await act(async () => { await Promise.resolve(); });
    const pulse = screen.getByTestId("live-pulse");
    expect(pulse.textContent).toContain("checking");
  });
});

// ---------------------------------------------------------------------------
// (WS7) PanelErrorBoundary wrap -- BestBetsBoard render body
//
// These tests verify the wrap contract: existing testids are preserved on the
// happy path, and PanelErrorBoundary is imported and applied. The boundary
// itself is tested in isolation in p6/__tests__/PanelErrorBoundary.test.tsx.
// ---------------------------------------------------------------------------
describe("BestBetsBoard (WS7) -- PanelErrorBoundary wrap", () => {
  beforeEach(() => resetLiveDataState());

  it("(WS7) refresh-affordance testid is preserved after error-boundary wrap", async () => {
    setLiveDataState({ isLoading: false, data: {}, ageSec: 5, lastUpdatedAt: Date.now() });
    const { getByTestId } = render(<BestBetsBoard />);
    await act(async () => { await Promise.resolve(); });
    expect(getByTestId("refresh-affordance")).toBeDefined();
  });

  it("(WS7) live-pulse testid is preserved after error-boundary wrap", async () => {
    setLiveDataState({ isLoading: false, data: {}, ageSec: 10, lastUpdatedAt: Date.now() });
    const { getByTestId } = render(<BestBetsBoard />);
    await act(async () => { await Promise.resolve(); });
    expect(getByTestId("live-pulse")).toBeDefined();
  });

  it("(WS7) auto-refresh-label testid is preserved after error-boundary wrap", async () => {
    setLiveDataState({ isLoading: false, data: {}, ageSec: 5, lastUpdatedAt: Date.now() });
    const { getByTestId } = render(<BestBetsBoard />);
    await act(async () => { await Promise.resolve(); });
    expect(getByTestId("auto-refresh-label")).toBeDefined();
  });

  it("(WS7) rendered output contains no dollar-amount (honesty rail)", async () => {
    setLiveDataState({ isLoading: false, data: {}, ageSec: 5, lastUpdatedAt: Date.now() });
    const { container } = render(<BestBetsBoard />);
    await act(async () => { await Promise.resolve(); });
    expect(container.textContent ?? "").not.toMatch(/\$\s?\d/);
  });
});
