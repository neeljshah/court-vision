// live-results.test.tsx -- W2-live-done-results acceptance tests.
//
// Acceptance criteria:
//   (a) liveSections.buildDoneEntryFromResult produces a non-empty DONE entry
//       from a completed ResultRow (final score shown, model call when available).
//   (b) partitionEntries routes result-derived entries into the DONE bucket.
//   (c) LiveGamesView DONE section is populated from a mocked /api/results
//       payload (completed:true rows) and renders with final scores.
//   (d) LIVE/PREGAME sections still derive from predict/bestbets as before.
//   (e) Honest-empty: offseason empty state only when results+predict+bestbets
//       are all genuinely empty.
//   (f) No '$' rendered anywhere (honesty rail).
//
// Strategy: use the real liveSections functions (pure, no network) for unit
// tests; mock api for the component integration test.

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import {
  buildDoneEntryFromResult,
  partitionEntries,
  type LiveGameEntry,
} from "../liveSections";
import type { ResultRow, PredictRecord } from "@/lib/api";

// ---------------------------------------------------------------------------
// api mock -- getResults and getPredict/bestbets controlled per test.
// ---------------------------------------------------------------------------

const getPredict = vi.fn();
const bestbets = vi.fn();
const getResults = vi.fn();

vi.mock("@/lib/api", async (orig) => {
  const real = (await orig()) as Record<string, unknown>;
  return {
    ...real,
    api: {
      ...((real.api as Record<string, unknown>) ?? {}),
      getPredict: (...a: unknown[]) => getPredict(...a),
      bestbets: (...a: unknown[]) => bestbets(...a),
      getResults: (...a: unknown[]) => getResults(...a),
    },
  };
});

// Import after mocks.
import { LiveGamesView } from "../LiveGamesView";
import type { PredictEnvelope, BestBetsEnvelope, Results } from "@/lib/api";

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

function makeResultRow(over: Partial<ResultRow> = {}): ResultRow {
  return {
    game_id: "result-001",
    home: "Detroit Tigers",
    away: "Chicago White Sox",
    home_score: 4,
    away_score: 1,
    completed: true,
    state: "post",
    status_detail: "Final",
    commence_time: "2026-06-20T17:10Z",
    ...over,
  };
}

function makePredRec(over: Partial<PredictRecord> = {}): PredictRecord {
  return {
    sport: "mlb",
    game_id: "result-001",
    home: "Detroit Tigers",
    away: "Chicago White Sox",
    tipoff: "2026-06-20T17:10Z",
    pregame_probs: { home_ml: 0.55, away_ml: 0.45 },
    markets: [],
    leak_guard: { in_sample: false },
    produced_at: null,
    ...over,
  };
}

function makeResultsEnvelope(rows: ResultRow[], sport = "mlb"): Results {
  return {
    status: "ok",
    sport,
    results: rows,
    count: rows.length,
    honest_note: "Settled game finals for outcome display only.",
    edge_claimed: false,
  };
}

function okPredictEnv(sport = "mlb"): PredictEnvelope {
  return {
    status: "ok",
    sport,
    generated_at: new Date().toISOString(),
    predictions: [],
  };
}

function okBetsEnv(sport = "mlb"): BestBetsEnvelope {
  return {
    sport,
    generated_at: new Date().toISOString(),
    status: "ok",
    count: 0,
    n_best_bets: 0,
    games: [],
  };
}

const unavailable = () => ({ status: "unavailable" as const, reason: "down" });

const assertNoDollar = (el: HTMLElement) =>
  expect(el.textContent ?? "").not.toMatch(/\$\s*\d/);

// ---------------------------------------------------------------------------
// (a) Unit: buildDoneEntryFromResult
// ---------------------------------------------------------------------------

describe("(a) buildDoneEntryFromResult -- unit tests", () => {
  it("returns null for a non-completed row", () => {
    const row = makeResultRow({ completed: false });
    expect(buildDoneEntryFromResult(row, "mlb", null)).toBeNull();
  });

  it("builds a DONE entry with final score for a completed row", () => {
    const row = makeResultRow();
    const entry = buildDoneEntryFromResult(row, "mlb", null);
    expect(entry).not.toBeNull();
    expect(entry!.section).toBe("DONE");
    expect(entry!.game_id).toBe("result-001");
    expect(entry!.home).toBe("Detroit Tigers");
    expect(entry!.away).toBe("Chicago White Sox");
    expect(entry!.finalScore).not.toBeNull();
    expect(entry!.finalScore!.home_score).toBe(4);
    expect(entry!.finalScore!.away_score).toBe(1);
    expect(entry!.finalScore!.label).toBe("Final");
  });

  it("final score is null when scores are missing from the row", () => {
    const row = makeResultRow({ home_score: null, away_score: null });
    const entry = buildDoneEntryFromResult(row, "mlb", null);
    expect(entry).not.toBeNull();
    expect(entry!.section).toBe("DONE");
    expect(entry!.finalScore).toBeNull();
  });

  it("sets modelCall.favoured=home when homeProb > 0.5", () => {
    const pred = makePredRec({ pregame_probs: { home_ml: 0.55 } });
    const entry = buildDoneEntryFromResult(makeResultRow(), "mlb", pred);
    expect(entry!.modelCall).not.toBeNull();
    expect(entry!.modelCall!.favoured).toBe("home");
    expect(entry!.modelCall!.prob).toBeCloseTo(0.55);
  });

  it("sets modelCall.favoured=away when awayProb > homeProb", () => {
    const pred = makePredRec({ pregame_probs: { home_ml: 0.40 } });
    const entry = buildDoneEntryFromResult(makeResultRow(), "mlb", pred);
    expect(entry!.modelCall!.favoured).toBe("away");
    expect(entry!.modelCall!.prob).toBeCloseTo(0.60);
  });

  it("modelCall.correct=true when favoured team won", () => {
    // home_score=4 away_score=1 -> home wins; model favours home (0.55)
    const pred = makePredRec({ pregame_probs: { home_ml: 0.55 } });
    const entry = buildDoneEntryFromResult(makeResultRow(), "mlb", pred);
    expect(entry!.modelCall!.correct).toBe(true);
  });

  it("modelCall.correct=false when favoured team lost", () => {
    // home_score=4 away_score=1 -> home wins; model favours away (0.60)
    const pred = makePredRec({ pregame_probs: { home_ml: 0.40 } });
    const entry = buildDoneEntryFromResult(makeResultRow(), "mlb", pred);
    // home wins (4-1) but model favoured away -> wrong
    expect(entry!.modelCall!.correct).toBe(false);
  });

  it("modelCall is null when no PredictRecord provided", () => {
    const entry = buildDoneEntryFromResult(makeResultRow(), "mlb", null);
    expect(entry!.modelCall).toBeNull();
  });

  it("status_detail fallback 'Final' used when absent", () => {
    const row = makeResultRow({ status_detail: undefined });
    const entry = buildDoneEntryFromResult(row, "mlb", null);
    expect(entry!.finalScore!.label).toBe("Final");
  });
});

// ---------------------------------------------------------------------------
// (b) Unit: partitionEntries routes result-derived entries into DONE bucket
// ---------------------------------------------------------------------------

describe("(b) partitionEntries -- routes result-derived entries into DONE", () => {
  it("places a buildDoneEntryFromResult entry into the done bucket", () => {
    const entry = buildDoneEntryFromResult(makeResultRow(), "mlb", null)!;
    const { live, pregame, done } = partitionEntries([entry]);
    expect(done).toHaveLength(1);
    expect(live).toHaveLength(0);
    expect(pregame).toHaveLength(0);
  });

  it("partitions mixed entries correctly including a result-derived DONE", () => {
    const resultEntry = buildDoneEntryFromResult(makeResultRow(), "mlb", null)!;
    const pregameEntry: LiveGameEntry = {
      game_id: "g-pre",
      sport: "nba",
      home: "SAS",
      away: "NYK",
      tipoff: null,
      homeWinProb: 0.6,
      liveState: null,
      section: "PREGAME",
      finalScore: null,
      modelCall: null,
    };
    const { live, pregame, done } = partitionEntries([resultEntry, pregameEntry]);
    expect(done).toHaveLength(1);
    expect(pregame).toHaveLength(1);
    expect(live).toHaveLength(0);
    expect(done[0].game_id).toBe("result-001");
  });
});

// ---------------------------------------------------------------------------
// (c) Component: DONE section populated from /api/results payload
// ---------------------------------------------------------------------------

describe("(c) LiveGamesView -- DONE section from /api/results", () => {
  beforeEach(() => {
    getPredict.mockReset();
    bestbets.mockReset();
    getResults.mockReset();
    // Default: all unavailable
    getPredict.mockResolvedValue(unavailable());
    bestbets.mockResolvedValue(unavailable());
    getResults.mockResolvedValue(unavailable());
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders a DONE section with final score when results has completed games", async () => {
    getPredict.mockImplementation((s: string) =>
      s === "mlb" ? Promise.resolve(okPredictEnv("mlb")) : Promise.resolve(unavailable()),
    );
    bestbets.mockImplementation((s: string) =>
      s === "mlb" ? Promise.resolve(okBetsEnv("mlb")) : Promise.resolve(unavailable()),
    );
    getResults.mockImplementation((s: string) =>
      s === "mlb"
        ? Promise.resolve(makeResultsEnvelope([makeResultRow()], "mlb"))
        : Promise.resolve(unavailable()),
    );

    const { container } = render(<LiveGamesView />);

    await waitFor(
      () => expect(screen.getByTestId("section-done")).toBeInTheDocument(),
      { timeout: 5000 },
    );

    // Final score shown in the DONE card.
    const finalScore = screen.getByTestId("final-score");
    expect(finalScore).toBeInTheDocument();
    // Should contain both team abbreviations/names and the scores.
    expect(finalScore.textContent).toMatch(/4/);
    expect(finalScore.textContent).toMatch(/1/);

    // No $ shown anywhere.
    assertNoDollar(container);
  });

  it("renders model call on a DONE card when predict provides a record for the game", async () => {
    const predRec = makePredRec();
    const predEnv: PredictEnvelope = {
      status: "ok",
      sport: "mlb",
      generated_at: new Date().toISOString(),
      predictions: [predRec],
    };

    getPredict.mockImplementation((s: string) =>
      s === "mlb" ? Promise.resolve(predEnv) : Promise.resolve(unavailable()),
    );
    bestbets.mockImplementation((s: string) =>
      s === "mlb" ? Promise.resolve(okBetsEnv("mlb")) : Promise.resolve(unavailable()),
    );
    getResults.mockImplementation((s: string) =>
      s === "mlb"
        ? Promise.resolve(makeResultsEnvelope([makeResultRow()], "mlb"))
        : Promise.resolve(unavailable()),
    );

    const { container } = render(<LiveGamesView />);

    await waitFor(
      () => expect(screen.getByTestId("section-done")).toBeInTheDocument(),
      { timeout: 5000 },
    );

    // Model call rendered (home favoured, model prob shown, correct/wrong).
    const modelCallEl = screen.getByTestId("model-call");
    expect(modelCallEl).toBeInTheDocument();
    expect(modelCallEl.textContent).toMatch(/home/i);
    // No $ in model call.
    assertNoDollar(container);
  });

  it("does not render a DONE card for a non-completed (completed:false) result row", async () => {
    getPredict.mockImplementation((s: string) =>
      s === "mlb" ? Promise.resolve(okPredictEnv("mlb")) : Promise.resolve(unavailable()),
    );
    bestbets.mockImplementation((s: string) =>
      s === "mlb" ? Promise.resolve(okBetsEnv("mlb")) : Promise.resolve(unavailable()),
    );
    getResults.mockImplementation((s: string) =>
      s === "mlb"
        ? Promise.resolve(makeResultsEnvelope([makeResultRow({ completed: false })], "mlb"))
        : Promise.resolve(unavailable()),
    );

    const { container } = render(<LiveGamesView />);

    // Wait for the poll to complete.
    await waitFor(
      () => expect(getResults).toHaveBeenCalled(),
      { timeout: 5000 },
    );

    // After the poll, no DONE section (only completed rows go there).
    // Give it a little time in case results arrive.
    await new Promise((r) => setTimeout(r, 100));
    expect(screen.queryByTestId("section-done")).toBeNull();
    assertNoDollar(container);
  });
});

// ---------------------------------------------------------------------------
// (d) LIVE/PREGAME sections still derive from predict/bestbets
// ---------------------------------------------------------------------------

describe("(d) LIVE/PREGAME sections still derive from predict/bestbets", () => {
  beforeEach(() => {
    getPredict.mockReset();
    bestbets.mockReset();
    getResults.mockReset();
    getResults.mockResolvedValue(unavailable());
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders a PREGAME section from predict when results returns empty", async () => {
    const predEnv: PredictEnvelope = {
      status: "ok",
      sport: "nba",
      generated_at: new Date().toISOString(),
      predictions: [
        {
          sport: "nba",
          game_id: "game-pre-001",
          home: "San Antonio Spurs",
          away: "New York Knicks",
          tipoff: "2026-06-21T00:30Z",
          pregame_probs: { home_ml: 0.60 },
          markets: [],
          leak_guard: { in_sample: false },
          produced_at: null,
        },
      ],
    };

    getPredict.mockImplementation((s: string) =>
      s === "nba" ? Promise.resolve(predEnv) : Promise.resolve(unavailable()),
    );
    bestbets.mockImplementation((s: string) =>
      s === "nba"
        ? Promise.resolve(okBetsEnv("nba"))
        : Promise.resolve(unavailable()),
    );
    getResults.mockResolvedValue(unavailable());

    const { container } = render(<LiveGamesView />);

    await waitFor(
      () => expect(screen.getByTestId("section-pregame")).toBeInTheDocument(),
      { timeout: 5000 },
    );
    assertNoDollar(container);
  });

  it("renders a LIVE section from bestbets live edge regardless of results", async () => {
    const predEnv: PredictEnvelope = {
      status: "ok",
      sport: "nba",
      generated_at: new Date().toISOString(),
      predictions: [
        {
          sport: "nba",
          game_id: "game-live-001",
          home: "San Antonio Spurs",
          away: "New York Knicks",
          tipoff: "2026-06-20T23:30Z",
          pregame_probs: { home_ml: 0.55 },
          markets: [],
          leak_guard: { in_sample: false },
          produced_at: null,
        },
      ],
    };

    getPredict.mockImplementation((s: string) =>
      s === "nba" ? Promise.resolve(predEnv) : Promise.resolve(unavailable()),
    );
    bestbets.mockImplementation((s: string) =>
      s === "nba"
        ? Promise.resolve({
            sport: "nba",
            generated_at: new Date().toISOString(),
            status: "ok",
            count: 1,
            n_best_bets: 0,
            games: [
              {
                game_id: "game-live-001",
                status: "ok",
                live: { status: "live", period: 2, clock: "7:14" },
                best_bets: [],
              },
            ],
          } as BestBetsEnvelope)
        : Promise.resolve(unavailable()),
    );
    getResults.mockResolvedValue(unavailable());

    const { container } = render(<LiveGamesView />);

    await waitFor(
      () => expect(screen.getByTestId("section-live")).toBeInTheDocument(),
      { timeout: 5000 },
    );
    assertNoDollar(container);
  });
});

// ---------------------------------------------------------------------------
// (e) Honest-empty only when results+predict+bestbets all genuinely empty
// ---------------------------------------------------------------------------

describe("(e) Honest empty state -- only when all three sources empty", () => {
  beforeEach(() => {
    getPredict.mockReset();
    bestbets.mockReset();
    getResults.mockReset();
    window.sessionStorage.clear();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("shows offseason empty state when all three sources are genuinely empty", async () => {
    getPredict.mockResolvedValue(unavailable());
    bestbets.mockResolvedValue(unavailable());
    getResults.mockResolvedValue(unavailable());

    // useLiveData's last-known-value cache (cacheKey "live:games") lives in a
    // module-level Map that survives across tests in this file (sessionStorage
    // alone isn't enough -- the Map is checked first). An earlier populated
    // test seeds it, and an Unavailable poll never clears last-good data
    // (stale-never-green by design), so this test needs a fresh module
    // instance to observe a genuinely cold cache.
    vi.resetModules();
    const { LiveGamesView: FreshLiveGamesView } = await import("../LiveGamesView");

    const { container } = render(<FreshLiveGamesView />);

    await waitFor(
      () => expect(screen.getByTestId("offseason-empty-state")).toBeInTheDocument(),
      { timeout: 5000 },
    );
    assertNoDollar(container);
  });

  it("does NOT show offseason state when results has completed games (even if predict empty)", async () => {
    getPredict.mockImplementation((s: string) =>
      s === "mlb" ? Promise.resolve(okPredictEnv("mlb")) : Promise.resolve(unavailable()),
    );
    bestbets.mockImplementation((s: string) =>
      s === "mlb" ? Promise.resolve(okBetsEnv("mlb")) : Promise.resolve(unavailable()),
    );
    getResults.mockImplementation((s: string) =>
      s === "mlb"
        ? Promise.resolve(makeResultsEnvelope([makeResultRow()], "mlb"))
        : Promise.resolve(unavailable()),
    );

    const { container } = render(<LiveGamesView />);

    await waitFor(
      () => expect(screen.queryByTestId("offseason-empty-state")).toBeNull(),
      { timeout: 5000 },
    );
    assertNoDollar(container);
  });
});

// ---------------------------------------------------------------------------
// (f) No '$' in any rendered output -- snapshot across states
// ---------------------------------------------------------------------------

describe("(f) No dollar sign rendered in any state", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("no $ in DONE section with final score and model call", async () => {
    const predEnv: PredictEnvelope = {
      status: "ok",
      sport: "mlb",
      generated_at: new Date().toISOString(),
      predictions: [makePredRec()],
    };

    getPredict.mockImplementation((s: string) =>
      s === "mlb" ? Promise.resolve(predEnv) : Promise.resolve(unavailable()),
    );
    bestbets.mockImplementation((s: string) =>
      s === "mlb" ? Promise.resolve(okBetsEnv("mlb")) : Promise.resolve(unavailable()),
    );
    getResults.mockImplementation((s: string) =>
      s === "mlb"
        ? Promise.resolve(makeResultsEnvelope([makeResultRow()], "mlb"))
        : Promise.resolve(unavailable()),
    );

    const { container } = render(<LiveGamesView />);

    await waitFor(
      () => expect(screen.getByTestId("section-done")).toBeInTheDocument(),
      { timeout: 5000 },
    );

    assertNoDollar(container);
  });
});
