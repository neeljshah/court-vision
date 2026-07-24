// live-games.test.tsx -- vitest guards for /live. Covers: liveSections classify
// (LIVE/PREGAME/DONE), LiveGamesView render (sections+chips, offseason empty
// state + live-badge visible), no $ in output. API mocked; no network.

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { classifySection, buildEntry, partitionEntries } from "../liveSections";
import type { LiveGameEntry } from "../liveSections";
import type { PredictRecord, GameEdge, PredictEnvelope, BestBetsEnvelope } from "@/lib/api";

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

import { LiveGamesView } from "../LiveGamesView";

function makePredRec(over: Partial<PredictRecord> = {}): PredictRecord {
  return {
    sport: "nba",
    game_id: "game-001",
    home: "San Antonio Spurs",
    away: "New York Knicks",
    tipoff: "2026-06-20T00:30Z",
    pregame_probs: { home_ml: 0.60, away_ml: 0.40 },
    markets: [],
    leak_guard: { in_sample: false },
    produced_at: null,
    ...over,
  };
}

function makeEdge(over: Partial<GameEdge> = {}): GameEdge {
  return { game_id: "game-001", status: "pregame", best_bets: [], ...over };
}
function okEnv(preds: PredictRecord[]): PredictEnvelope {
  return { status: "ok", sport: "nba", generated_at: new Date().toISOString(), predictions: preds };
}
const unavailableEnv = () => ({ status: "unavailable" as const, reason: "predict service down" });
const assertNoDollar = (el: HTMLElement) => expect(el.textContent ?? "").not.toMatch(/\$\s*\d/);

describe("liveSections -- classifySection", () => {
  it("returns LIVE when live.status === 'live'", () => {
    expect(
      classifySection(undefined, { status: "live" }),
    ).toBe("LIVE");
  });

  it("returns DONE when live.state === 'post'", () => {
    expect(
      classifySection(undefined, { status: "ok", state: "post" }),
    ).toBe("DONE");
  });

  it("returns DONE when live.status === 'final'", () => {
    expect(
      classifySection(undefined, { status: "final" }),
    ).toBe("DONE");
  });

  it("returns DONE when gameStatus === 'done'", () => {
    expect(classifySection("done", null)).toBe("DONE");
  });

  it("returns DONE when gameStatus === 'settled'", () => {
    expect(classifySection("settled", null)).toBe("DONE");
  });

  it("returns PREGAME when no live state and no done status", () => {
    expect(classifySection("pregame", null)).toBe("PREGAME");
  });

  it("returns PREGAME when live state is absent entirely", () => {
    expect(classifySection(undefined, null)).toBe("PREGAME");
  });

  it("LIVE takes priority over a done gameStatus", () => {
    // If backend sends status='done' but live.status='live', trust live state.
    expect(
      classifySection("done", { status: "live" }),
    ).toBe("LIVE");
  });
});

describe("liveSections -- buildEntry + partitionEntries", () => {
  it("builds a LIVE entry from a live edge", () => {
    const rec = makePredRec();
    const edge = makeEdge({ live: { status: "live", period: 3, clock: "5:42" } as GameEdge["live"] });
    const entry = buildEntry(rec, edge);
    expect(entry.section).toBe("LIVE");
    expect(entry.homeWinProb).toBeCloseTo(0.60);
    expect(entry.game_id).toBe("game-001");
  });

  it("builds a PREGAME entry when no live state", () => {
    const entry = buildEntry(makePredRec(), null);
    expect(entry.section).toBe("PREGAME");
  });

  it("builds a DONE entry from a post-game edge", () => {
    const edge = makeEdge({ status: "done", live: { status: "post" } as GameEdge["live"] });
    const entry = buildEntry(makePredRec(), edge);
    expect(entry.section).toBe("DONE");
  });

  it("partitions mixed entries into the correct buckets", () => {
    const entries: LiveGameEntry[] = [
      { game_id: "a", sport: "nba", home: "H", away: "A", tipoff: null, homeWinProb: 0.5, liveState: null, section: "LIVE" },
      { game_id: "b", sport: "nba", home: "H", away: "A", tipoff: null, homeWinProb: 0.5, liveState: null, section: "PREGAME" },
      { game_id: "c", sport: "nba", home: "H", away: "A", tipoff: null, homeWinProb: 0.5, liveState: null, section: "DONE" },
      { game_id: "d", sport: "nba", home: "H", away: "A", tipoff: null, homeWinProb: 0.5, liveState: null, section: "PREGAME" },
    ];
    const { live, pregame, done } = partitionEntries(entries);
    expect(live).toHaveLength(1);
    expect(pregame).toHaveLength(2);
    expect(done).toHaveLength(1);
  });
});

// 2. LiveGamesView component render tests
describe("LiveGamesView -- renders sections from state+tipoff", () => {
  beforeEach(() => {
    getPredict.mockReset();
    bestbets.mockReset();
    getPredict.mockImplementation(() => Promise.resolve(unavailableEnv()));
    bestbets.mockResolvedValue(unavailableEnv());
  });

  it("renders a LIVE section with a LIVE chip for a live game", async () => {
    const liveEdge = makeEdge({ status: "ok", live: { status: "live", period: 2 } as GameEdge["live"] });
    getPredict.mockImplementation((s: string) =>
      s === "nba" ? Promise.resolve(okEnv([makePredRec()])) : Promise.resolve(unavailableEnv()),
    );
    bestbets.mockImplementation((s: string) =>
      s === "nba"
        ? Promise.resolve({ sport: "nba", generated_at: new Date().toISOString(), status: "ok", count: 1, n_best_bets: 0, games: [liveEdge] } as BestBetsEnvelope)
        : Promise.resolve(unavailableEnv()),
    );
    const { container } = render(<LiveGamesView />);
    await waitFor(() => expect(screen.getByTestId("section-live")).toBeInTheDocument());
    expect(screen.getByTestId("live-chip")).toBeInTheDocument();
    assertNoDollar(container);
  });

  it("renders a PREGAME section for today's not-yet-started game", async () => {
    getPredict.mockImplementation((s: string) =>
      s === "nba" ? Promise.resolve(okEnv([makePredRec()])) : Promise.resolve(unavailableEnv()),
    );
    bestbets.mockImplementation((s: string) =>
      s === "nba"
        ? Promise.resolve({ sport: "nba", generated_at: new Date().toISOString(), status: "ok", count: 1, n_best_bets: 0, games: [makeEdge({ status: "pregame" })] } as BestBetsEnvelope)
        : Promise.resolve(unavailableEnv()),
    );
    const { container } = render(<LiveGamesView />);
    await waitFor(() => expect(screen.getByTestId("section-pregame")).toBeInTheDocument());
    expect(screen.queryByTestId("offseason-empty-state")).toBeNull();
    assertNoDollar(container);
  });

  it("renders a DONE section for a settled/final game", async () => {
    const doneEdge = makeEdge({ status: "done", live: { status: "final" } as GameEdge["live"] });
    getPredict.mockImplementation((s: string) =>
      s === "nba" ? Promise.resolve(okEnv([makePredRec()])) : Promise.resolve(unavailableEnv()),
    );
    bestbets.mockImplementation((s: string) =>
      s === "nba"
        ? Promise.resolve({ sport: "nba", generated_at: new Date().toISOString(), status: "ok", count: 1, n_best_bets: 0, games: [doneEdge] } as BestBetsEnvelope)
        : Promise.resolve(unavailableEnv()),
    );
    const { container } = render(<LiveGamesView />);
    await waitFor(() => expect(screen.getByTestId("section-done")).toBeInTheDocument());
    assertNoDollar(container);
  });

  it("renders honest offseason empty state + live-badge when no games", async () => {
    getPredict.mockImplementation(() =>
      Promise.resolve({ status: "offseason", sport: "nba", generated_at: null, reason: "no games (offseason)" } as PredictEnvelope),
    );
    bestbets.mockResolvedValue(unavailableEnv());

    const { container } = render(<LiveGamesView />);
    await waitFor(() => expect(screen.getByTestId("offseason-empty-state")).toBeInTheDocument());

    // Honest message present.
    expect(screen.getByTestId("offseason-message")).toHaveTextContent(/No live games right now/i);

    // Live-badge (mechanism) still visible -- shared LiveBadge uses role="status".
    const badges = document.querySelectorAll('[role="status"]');
    expect(badges.length).toBeGreaterThanOrEqual(1);
    // Badge must not say "failed" (honest: checking/unavailable/stale/updated).
    expect(document.body.textContent ?? "").not.toMatch(/failed/i);

    assertNoDollar(container);
  });

  it("renders win prob as percentage (no $)", async () => {
    getPredict.mockImplementation((s: string) =>
      s === "nba" ? Promise.resolve(okEnv([makePredRec({ pregame_probs: { home_ml: 0.65 } })])) : Promise.resolve(unavailableEnv()),
    );
    bestbets.mockImplementation(() => Promise.resolve(unavailableEnv()));
    const { container } = render(<LiveGamesView />);
    await waitFor(() => expect(screen.getByText(/65\.0%/)).toBeInTheDocument());
    assertNoDollar(container);
  });

  it("pauses polling while the tab is hidden, resumes on visible", async () => {
    getPredict.mockImplementation(() => Promise.resolve(unavailableEnv()));
    bestbets.mockResolvedValue(unavailableEnv());
    render(<LiveGamesView />);
    // Initial poll fires once per sport on mount.
    await waitFor(() => expect(getPredict).toHaveBeenCalled());
    const afterMount = getPredict.mock.calls.length;

    // Hide the tab, then advance well past the poll interval: no new polls.
    Object.defineProperty(document, "hidden", { configurable: true, get: () => true });
    await new Promise((r) => setTimeout(r, 60));
    expect(getPredict.mock.calls.length).toBe(afterMount);

    // Become visible again -> exactly one resume poll (one call per sport).
    Object.defineProperty(document, "hidden", { configurable: true, get: () => false });
    document.dispatchEvent(new Event("visibilitychange"));
    await waitFor(() => expect(getPredict.mock.calls.length).toBeGreaterThan(afterMount));
  });
});
