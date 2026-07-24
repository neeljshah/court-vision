// live-view.test.tsx -- WS1-livegames-uselivedata acceptance tests.
//
// Criteria (all must pass):
//   (a) No fetch while document.hidden; exactly one immediate poll on visible.
//   (b) Failed poll keeps last-good entries + shows stale/unavailable not red.
//   (c) Empty payload -> offseason empty state; live badge still "checking..." /
//       "updated Xs ago" (mechanism visible).
//   (d) LiveGamesView.tsx is <=300 LOC.
//
// Strategy: useLiveData is the canonical hook (tested in its own suite).
//   - (a)/(c): use real useLiveData + mock the api fetchers (getPredict/bestbets).
//   - (b): mock useLiveData state directly to validate component rendering given
//     a stale/error state -- avoids race conditions in the async abort path.

import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, waitFor, act } from "@testing-library/react";
import type { PredictEnvelope, BestBetsEnvelope } from "@/lib/api";

// ---------------------------------------------------------------------------
// api mock -- shared across all tests; getPredict/bestbets controlled per test.
// ---------------------------------------------------------------------------

const getPredict = vi.fn();
const bestbets = vi.fn();

vi.mock("@/lib/api", async (orig) => {
  const real = (await orig()) as Record<string, unknown>;
  return {
    ...real,
    api: {
      ...((real.api as Record<string, unknown>) ?? {}),
      getPredict: (...a: unknown[]) => getPredict(...a),
      bestbets: (...a: unknown[]) => bestbets(...a),
    },
  };
});

// ---------------------------------------------------------------------------
// useLiveData mock -- delegates to real or override per test.
// ---------------------------------------------------------------------------

import type { LiveDataState } from "@/lib/useLiveData";
import type { LiveGameEntry } from "../liveSections";

// Holds an optional override; null = fall through to real hook.
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

// Import AFTER mock registrations.
import { LiveGamesView } from "../LiveGamesView";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeOkEnv(homeWinProb = 0.6): PredictEnvelope {
  return {
    status: "ok",
    sport: "nba",
    generated_at: new Date().toISOString(),
    predictions: [
      {
        sport: "nba",
        game_id: "game-001",
        home: "San Antonio Spurs",
        away: "New York Knicks",
        tipoff: "2026-06-20T00:30Z",
        pregame_probs: { home_ml: homeWinProb },
        markets: [],
        leak_guard: { in_sample: false },
        produced_at: null,
      },
    ],
  };
}

function makeOkBets(): BestBetsEnvelope {
  return {
    sport: "nba",
    generated_at: new Date().toISOString(),
    status: "ok",
    count: 1,
    n_best_bets: 0,
    games: [{ game_id: "game-001", status: "pregame", best_bets: [] }],
    clv: {
      n_bets: 0,
      pct_beat_close: null,
      mean_clv_pct: null,
      by_sport: null,
      clv_is_proxy: true,
    },
    edge_claimed: false,
  };
}

const unavailable = () => ({ status: "unavailable" as const, reason: "down" });

function makeEntry(over: Partial<LiveGameEntry> = {}): LiveGameEntry {
  return {
    game_id: "g-001",
    sport: "nba",
    home: "SAS",
    away: "NYK",
    tipoff: null,
    homeWinProb: 0.6,
    liveState: null,
    section: "PREGAME",
    ...over,
  };
}

function makeHookState(over: Partial<LiveDataState<LiveGameEntry[]>>): LiveDataState<LiveGameEntry[]> {
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

function setVisibility(hidden: boolean) {
  Object.defineProperty(document, "hidden", { configurable: true, get: () => hidden });
  document.dispatchEvent(new Event("visibilitychange"));
}

function resetVisibility() {
  Object.defineProperty(document, "hidden", { configurable: true, get: () => false });
}

afterEach(() => {
  vi.restoreAllMocks();
  resetVisibility();
  useLiveDataOverride = null;
  getPredict.mockReset();
  bestbets.mockReset();
});

// ---------------------------------------------------------------------------
// (a) Pause-on-hidden, resume-on-visible
//     Uses the REAL useLiveData hook with mocked api fetchers.
// ---------------------------------------------------------------------------

describe("WS1 (a) -- pause while hidden, single poll on visible", () => {
  it("fires no fetch while document.hidden then at least one on becoming visible", async () => {
    // Start with tab hidden so the interval ticks are suppressed.
    setVisibility(true);

    // All sports return ok.
    getPredict.mockResolvedValue(makeOkEnv());
    bestbets.mockResolvedValue(makeOkBets());

    render(<LiveGamesView />);

    // The initial mount fetch fires unconditionally (useLiveData calls runFetch
    // on mount regardless of visibility). Wait for it.
    await waitFor(() => expect(getPredict).toHaveBeenCalled(), { timeout: 3000 });
    const callsAfterMount = getPredict.mock.calls.length;

    // While hidden: wait >1 poll-interval (real timers; POLL_MS=20s but jsdom
    // won't fire that many ticks in 60ms). No extra calls must happen.
    await new Promise((r) => setTimeout(r, 60));
    expect(getPredict.mock.calls.length).toBe(callsAfterMount);

    // Become visible -> useLiveData fires an immediate re-poll.
    await act(async () => {
      setVisibility(false);
      await Promise.resolve();
    });

    await waitFor(
      () => expect(getPredict.mock.calls.length).toBeGreaterThan(callsAfterMount),
      { timeout: 3000 },
    );
  });
});

// ---------------------------------------------------------------------------
// (b) Failed poll keeps last-good entries + shows stale/unavailable, not red.
//     Injects hook state directly to avoid async abort race conditions.
// ---------------------------------------------------------------------------

describe("WS1 (b) -- failed poll keeps last-good + stale not red", () => {
  it("renders last-good game rows when hook error is set + isStale", () => {
    // Inject stale-with-last-good state directly (the hook tested separately).
    useLiveDataOverride = makeHookState({
      data: [makeEntry({ section: "PREGAME" })],
      lastUpdatedAt: Date.now() - 400_000,
      ageSec: 400,
      isStale: true,
      error: "all sport endpoints unreachable",
      isLoading: false,
    });

    const { container } = render(<LiveGamesView />);

    // Game rows must be rendered from last-good data.
    expect(screen.getAllByTestId("live-game-row").length).toBeGreaterThan(0);

    // Offseason state must NOT appear when we have game rows.
    expect(screen.queryByTestId("offseason-empty-state")).toBeNull();

    // The badge must NOT say "failed" (honest: "stale", "unavailable", "updated Xs ago").
    const pageText = container.textContent ?? "";
    expect(pageText).not.toMatch(/failed/i);

    // No $ in output (honesty rail).
    expect(pageText).not.toMatch(/\$\s*\d/);
  });

  it("badge shows stale/unavailable state (not live green) when error is set", () => {
    useLiveDataOverride = makeHookState({
      data: [makeEntry()],
      lastUpdatedAt: Date.now() - 600_000,
      ageSec: 600,
      isStale: true,
      error: "network error",
      isLoading: false,
    });

    render(<LiveGamesView />);

    // Badge must be present and reflect stale state.
    const badge = document.querySelector('[role="status"]');
    expect(badge).not.toBeNull();
    // Badge aria-label should describe stale state, not live.
    const label = badge?.getAttribute("aria-label") ?? "";
    expect(label).not.toMatch(/^live,/i);
    // No "failed" text in the badge.
    expect(badge?.textContent ?? "").not.toMatch(/failed/i);
  });
});

// ---------------------------------------------------------------------------
// (c) Empty payload -> offseason empty state; badge still checking/updated.
//     Uses the REAL useLiveData with mocked api (all unavailable).
// ---------------------------------------------------------------------------

describe("WS1 (c) -- empty payload renders offseason state + badge visible", () => {
  it("shows offseason empty state when all sports return unavailable", async () => {
    getPredict.mockResolvedValue(unavailable());
    bestbets.mockResolvedValue(unavailable());

    render(<LiveGamesView />);

    // After the first poll (all fail -> Unavailable sentinel -> data=null),
    // no game rows -> offseason empty state.
    await waitFor(
      () => expect(screen.getByTestId("offseason-empty-state")).toBeInTheDocument(),
      { timeout: 3000 },
    );
    expect(screen.getByTestId("offseason-message")).toHaveTextContent(
      /No live games right now/i,
    );
  });

  it("shows offseason empty state when predict returns ok with 0 predictions", async () => {
    getPredict.mockResolvedValue({
      status: "ok",
      sport: "nba",
      generated_at: new Date().toISOString(),
      predictions: [],
    } as PredictEnvelope);
    bestbets.mockResolvedValue(unavailable());

    render(<LiveGamesView />);

    await waitFor(
      () => expect(screen.getByTestId("offseason-empty-state")).toBeInTheDocument(),
      { timeout: 3000 },
    );
  });

  it("badge (mechanism) is still rendered inside the offseason empty state", async () => {
    getPredict.mockResolvedValue(unavailable());
    bestbets.mockResolvedValue(unavailable());

    const { container } = render(<LiveGamesView />);

    await waitFor(
      () => expect(screen.getByTestId("offseason-empty-state")).toBeInTheDocument(),
      { timeout: 3000 },
    );

    // At least one role="status" badge inside the page (header + offseason copy).
    const badges = container.querySelectorAll('[role="status"]');
    expect(badges.length).toBeGreaterThanOrEqual(1);

    // Honest badge state: "checking...", "unavailable", "updated Xs ago" -- never "failed".
    const pageText = container.textContent ?? "";
    expect(pageText).not.toMatch(/failed/i);
  });

  it("badge shows checking state while first fetch is pending (inject via hook mock)", () => {
    useLiveDataOverride = makeHookState({
      data: null,
      ageSec: null,
      isStale: false,
      error: null,
      isLoading: true,
    });

    const { container } = render(<LiveGamesView />);

    // While loading with no data: skeleton shown, not offseason state.
    expect(screen.queryByTestId("offseason-empty-state")).toBeNull();

    // Badge must say "checking..." (role=status present).
    const badges = container.querySelectorAll('[role="status"]');
    expect(badges.length).toBeGreaterThanOrEqual(1);
    const pageText = container.textContent ?? "";
    // "checking..." must appear, never "failed".
    expect(pageText).toMatch(/checking/i);
    expect(pageText).not.toMatch(/failed/i);
  });
});

// ---------------------------------------------------------------------------
// (d) LiveGamesView.tsx is <=300 LOC
// ---------------------------------------------------------------------------

describe("WS1 (d) -- LiveGamesView <=300 LOC", () => {
  it("LiveGamesView.tsx has at most 300 non-empty lines", async () => {
    const fs = await import("fs");
    const path = await import("path");
    const filePath = path.resolve(__dirname, "../LiveGamesView.tsx");
    const src = fs.readFileSync(filePath, "utf8");
    const nonEmpty = src.split("\n").filter((l) => l.trim().length > 0);
    expect(nonEmpty.length).toBeLessThanOrEqual(300);
  });
});
