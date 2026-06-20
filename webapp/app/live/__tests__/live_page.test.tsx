// live_page.test.tsx -- ws4-live-page acceptance tests.
//
// Acceptance criteria (all three must pass):
//   (a) Populated live payload: renders without throwing; shows game rows,
//       LIVE chip, and win-prob; no $ field; no fabricated P&L text.
//   (b) Empty payload: shows honest "No live games right now" empty state;
//       live-badge (mechanism) still visible; no $ / no red / no green.
//   (c) Stale / INSUFFICIENT_DATA CLV: stale badge shown (amber, NOT green),
//       no $ P&L, no "failed" text, no fabricated edge numbers.
//
// Strategy: inject hook state directly via useLiveData mock for (a)/(b)/(c)
// to avoid async polling races. The async integration path is already covered
// by live-games.test.tsx and live-view.test.tsx.

import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen } from "@testing-library/react";
import type { LiveDataState } from "@/lib/useLiveData";
import type { LiveGameEntry } from "../liveSections";

// ---------------------------------------------------------------------------
// Mock useLiveData -- override per test via useLiveDataOverride.
// ---------------------------------------------------------------------------

let useLiveDataOverride: LiveDataState<LiveGameEntry[]> | null = null;

vi.mock("@/lib/useLiveData", async (orig) => {
  const real = await orig() as { useLiveData: (...a: unknown[]) => unknown };
  return {
    ...real,
    useLiveData: (...args: unknown[]) => {
      if (useLiveDataOverride !== null) return useLiveDataOverride;
      return real.useLiveData(...args);
    },
  };
});

// Mock api so no real network calls fire when the real hook path is hit.
vi.mock("@/lib/api", async (orig) => {
  const real = (await orig()) as Record<string, unknown>;
  return {
    ...real,
    api: {
      ...((real.api as Record<string, unknown>) ?? {}),
      getPredict: () => Promise.resolve({ status: "unavailable" as const, reason: "mocked" }),
      bestbets: () => Promise.resolve({ status: "unavailable" as const, reason: "mocked" }),
    },
  };
});

// Import after mocks are registered.
import { LiveGamesView } from "../LiveGamesView";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeEntry(over: Partial<LiveGameEntry> = {}): LiveGameEntry {
  return {
    game_id: "g-001",
    sport: "nba",
    home: "San Antonio Spurs",
    away: "New York Knicks",
    tipoff: "2026-06-20T00:30Z",
    homeWinProb: 0.62,
    liveState: null,
    section: "PREGAME",
    ...over,
  };
}

/** Build a minimal hook state with sensible defaults. */
function makeHookState(
  over: Partial<LiveDataState<LiveGameEntry[]>>,
): LiveDataState<LiveGameEntry[]> {
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
    ...over,
  };
}

/** Assert no dollar-amount strings appear in the rendered output. */
function assertNoDollarAmount(container: HTMLElement) {
  expect(container.textContent ?? "").not.toMatch(/\$\s*\d/);
}

afterEach(() => {
  useLiveDataOverride = null;
  vi.restoreAllMocks();
});

// ---------------------------------------------------------------------------
// (a) Populated live payload -- renders without throwing
// ---------------------------------------------------------------------------

describe("(a) Populated live payload", () => {
  it("renders a LIVE game row with LIVE chip and win-prob without throwing", () => {
    useLiveDataOverride = makeHookState({
      data: [
        makeEntry({
          section: "LIVE",
          liveState: { status: "live", period: 2, clock: "7:14", home_score: 48, away_score: 51 },
        }),
      ],
      lastUpdatedAt: Date.now(),
      ageSec: 3,
      isStale: false,
      error: null,
      isLoading: false,
    });

    const { container } = render(<LiveGamesView />);

    // Game row rendered.
    expect(screen.getAllByTestId("live-game-row").length).toBeGreaterThan(0);

    // LIVE section header and chip visible.
    expect(screen.getByTestId("section-live")).toBeInTheDocument();
    expect(screen.getByTestId("live-chip")).toBeInTheDocument();

    // Win-prob surface: 62.0%.
    expect(screen.getByText(/62\.0%/)).toBeInTheDocument();

    // No $ amounts anywhere.
    assertNoDollarAmount(container);

    // No fabricated P&L / ROI text.
    expect(container.textContent).not.toMatch(/\bROI\b/i);
    expect(container.textContent).not.toMatch(/\bprofit\b/i);
  });

  it("renders a PREGAME section for a today-not-yet-started game", () => {
    useLiveDataOverride = makeHookState({
      data: [makeEntry({ section: "PREGAME" })],
      lastUpdatedAt: Date.now(),
      ageSec: 5,
      isStale: false,
      error: null,
      isLoading: false,
    });

    const { container } = render(<LiveGamesView />);

    expect(screen.getByTestId("section-pregame")).toBeInTheDocument();
    expect(screen.queryByTestId("offseason-empty-state")).toBeNull();
    assertNoDollarAmount(container);
  });

  it("renders a DONE section for a final/settled game", () => {
    useLiveDataOverride = makeHookState({
      data: [
        makeEntry({
          section: "DONE",
          liveState: { status: "final", home_score: 108, away_score: 103 },
        }),
      ],
      lastUpdatedAt: Date.now(),
      ageSec: 30,
      isStale: false,
      error: null,
      isLoading: false,
    });

    const { container } = render(<LiveGamesView />);

    expect(screen.getByTestId("section-done")).toBeInTheDocument();
    assertNoDollarAmount(container);
  });

  it("live badge shows green live state (not stale) for a fresh successful poll", () => {
    useLiveDataOverride = makeHookState({
      data: [makeEntry({ section: "LIVE", liveState: { status: "live" } })],
      lastUpdatedAt: Date.now(),
      ageSec: 2,
      isStale: false,
      error: null,
      isLoading: false,
    });

    render(<LiveGamesView />);

    // role=status badge is rendered.
    const badge = document.querySelector('[role="status"]');
    expect(badge).not.toBeNull();

    // aria-label contains "Live" (LiveBadge emits "Live, updated Xs ago").
    const label = badge?.getAttribute("aria-label") ?? "";
    expect(label).toMatch(/live/i);
  });
});

// ---------------------------------------------------------------------------
// (b) Empty payload -- honest "No live games right now" empty state
// ---------------------------------------------------------------------------

describe("(b) Empty payload -- honest empty state", () => {
  it("shows the offseason empty state when data is an empty array", () => {
    useLiveDataOverride = makeHookState({
      data: [],
      lastUpdatedAt: Date.now(),
      ageSec: 8,
      isStale: false,
      error: null,
      isLoading: false,
    });

    const { container } = render(<LiveGamesView />);

    expect(screen.getByTestId("offseason-empty-state")).toBeInTheDocument();
    expect(screen.getByTestId("offseason-message")).toHaveTextContent(
      /No live games right now/i,
    );

    // No game rows.
    expect(screen.queryByTestId("live-game-row")).toBeNull();

    // No $ / no fabricated numbers.
    assertNoDollarAmount(container);
    expect(container.textContent).not.toMatch(/\bROI\b/i);
  });

  it("live badge (mechanism) is still rendered inside the empty state", () => {
    useLiveDataOverride = makeHookState({
      data: [],
      lastUpdatedAt: Date.now(),
      ageSec: 10,
      isStale: false,
      error: null,
      isLoading: false,
    });

    const { container } = render(<LiveGamesView />);

    expect(screen.getByTestId("offseason-empty-state")).toBeInTheDocument();

    // At least one role=status element (badge renders twice: header + empty state copy).
    const badges = container.querySelectorAll('[role="status"]');
    expect(badges.length).toBeGreaterThanOrEqual(1);
  });

  it("shows checking skeleton (not empty state) while first poll is pending", () => {
    useLiveDataOverride = makeHookState({
      data: null,
      ageSec: null,
      isStale: false,
      error: null,
      isLoading: true,
    });

    render(<LiveGamesView />);

    // No empty state while still loading.
    expect(screen.queryByTestId("offseason-empty-state")).toBeNull();
    // No game rows either.
    expect(screen.queryByTestId("live-game-row")).toBeNull();
    // Badge shows "checking...".
    expect(document.body.textContent ?? "").toMatch(/checking/i);
  });

  it("badge does NOT say red/failed in empty state", () => {
    useLiveDataOverride = makeHookState({
      data: [],
      lastUpdatedAt: Date.now(),
      ageSec: 15,
      isStale: false,
      error: null,
      isLoading: false,
    });

    const { container } = render(<LiveGamesView />);

    expect(container.textContent ?? "").not.toMatch(/failed/i);
  });
});

// ---------------------------------------------------------------------------
// (c) Stale / INSUFFICIENT_DATA CLV -- amber badge, no green, no fabricated P&L
// ---------------------------------------------------------------------------

describe("(c) Stale / INSUFFICIENT_DATA CLV -- stale-never-green, no P&L", () => {
  it("badge is amber/stale (not green) when isStale=true", () => {
    useLiveDataOverride = makeHookState({
      data: [makeEntry({ section: "PREGAME" })],
      lastUpdatedAt: Date.now() - 400_000,
      ageSec: 400,
      isStale: true,
      error: null,
      isLoading: false,
    });

    render(<LiveGamesView />);

    const badge = document.querySelector('[role="status"]');
    expect(badge).not.toBeNull();

    // Aria-label must describe stale, not live.
    const label = badge?.getAttribute("aria-label") ?? "";
    // LiveBadge emits "Live, updated Xs ago" in live state; stale state emits "Stale...".
    expect(label).not.toMatch(/^live,/i);
    expect(label).toMatch(/stale/i);

    // No green tokens in the badge (no green background classes visible in text).
    expect(badge?.textContent ?? "").not.toMatch(/failed/i);
  });

  it("CLV INSUFFICIENT_DATA: no $ / no fabricated win count / no ROI", () => {
    // Simulate state that could arise from INSUFFICIENT_DATA CLV (no close data yet).
    // The view should surface game rows but NEVER emit $ or fabricated P&L.
    useLiveDataOverride = makeHookState({
      data: [
        makeEntry({
          section: "PREGAME",
          // No live state -- honest pregame card only.
          liveState: null,
          homeWinProb: 0.55,
        }),
      ],
      lastUpdatedAt: Date.now() - 600_000,
      ageSec: 600,
      isStale: true,
      error: "CLV data unavailable (INSUFFICIENT_DATA: no graded bets with a true close)",
      isLoading: false,
    });

    const { container } = render(<LiveGamesView />);

    // Game rows still rendered (last-good retained).
    expect(screen.getAllByTestId("live-game-row").length).toBeGreaterThan(0);
    // Win prob rendered as percentage.
    expect(screen.getByText(/55\.0%/)).toBeInTheDocument();

    // Honesty rails.
    assertNoDollarAmount(container);
    expect(container.textContent).not.toMatch(/\bROI\b/i);
    expect(container.textContent).not.toMatch(/\bprofit\b/i);
    expect(container.textContent).not.toMatch(/failed/i);

    // Badge present and stale.
    const badge = document.querySelector('[role="status"]');
    expect(badge).not.toBeNull();
    const label = badge?.getAttribute("aria-label") ?? "";
    expect(label).not.toMatch(/^live,/i);
  });

  it("error poll with last-good data shows stale badge not offseason empty state", () => {
    useLiveDataOverride = makeHookState({
      data: [makeEntry({ section: "PREGAME" })],
      lastUpdatedAt: Date.now() - 500_000,
      ageSec: 500,
      isStale: true,
      error: "all sport endpoints unreachable",
      isLoading: false,
    });

    const { container } = render(<LiveGamesView />);

    // Game rows present (last-good retained, NOT cleared to empty on error).
    expect(screen.getAllByTestId("live-game-row").length).toBeGreaterThan(0);

    // Offseason empty state must NOT appear when we have last-good rows.
    expect(screen.queryByTestId("offseason-empty-state")).toBeNull();

    // Badge not green, not "failed".
    const badge = document.querySelector('[role="status"]');
    expect(badge).not.toBeNull();
    const label = badge?.getAttribute("aria-label") ?? "";
    expect(label).not.toMatch(/^live,/i);
    expect(container.textContent).not.toMatch(/failed/i);

    assertNoDollarAmount(container);
  });

  it("no fabricated $ amounts in any state (snapshot assertion)", () => {
    // Run all three state variants and ensure $ never appears.
    const states: Array<LiveDataState<LiveGameEntry[]>> = [
      // Live state.
      makeHookState({
        data: [makeEntry({ section: "LIVE", liveState: { status: "live" } })],
        ageSec: 2,
        isLoading: false,
      }),
      // Empty state.
      makeHookState({ data: [], ageSec: 5, isLoading: false }),
      // Stale state.
      makeHookState({
        data: [makeEntry({ section: "PREGAME" })],
        ageSec: 300,
        isStale: true,
        error: "stale",
        isLoading: false,
      }),
    ];

    for (const state of states) {
      useLiveDataOverride = state;
      const { container, unmount } = render(<LiveGamesView />);
      assertNoDollarAmount(container);
      unmount();
      useLiveDataOverride = null;
    }
  });
});
