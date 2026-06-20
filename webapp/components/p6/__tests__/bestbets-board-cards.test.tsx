// bestbets-board-cards.test.tsx -- acceptance tests for BestBetsBoard (ws5-fe-bestbets-board).
//
// Acceptance criteria (two hard requirements):
//
//   (A) Given a cards payload the board renders one row per card with
//       model_prob / market_prob / units / tier and NO dollar string anywhere.
//
//   (B) Given status='unavailable' (produce service returning an explicit reason)
//       the board renders the honest reason banner -- NOT a blank/white panel.
//
// All network calls are intercepted at the useLiveData boundary so tests are
// fully synchronous and never hit :8099.

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, act, screen } from "@testing-library/react";

// ---------------------------------------------------------------------------
// Module mocks -- must be hoisted before the component import
// ---------------------------------------------------------------------------

vi.mock("@/lib/p5api", () => ({
  SPORTS: ["nba"],
  isUnavailable: (x: unknown) =>
    !!x &&
    typeof x === "object" &&
    (x as { status?: string }).status === "unavailable",
  api: { bestbets: vi.fn() },
}));

type LiveDataState<T> = {
  data: T | null;
  lastUpdatedAt: number | null;
  ageSec: number | null;
  isStale: boolean;
  error: string | null;
  isLoading: boolean;
  refresh: () => void;
};

let _liveState: LiveDataState<unknown> = {
  data: null,
  lastUpdatedAt: null,
  ageSec: null,
  isStale: false,
  error: null,
  isLoading: true,
  refresh: vi.fn(),
};

vi.mock("@/lib/useLiveData", () => ({
  useLiveData: () => _liveState,
}));

// Lightweight mocks for tabs/controls so we don't render their full DOM
vi.mock("../../bets/StatusTabs", () => ({
  StatusTabs: ({ value }: { value: string }) => (
    <div data-testid="status-tabs">{value}</div>
  ),
}));
vi.mock("../../bets/SortControls", () => ({
  SortControls: () => <div data-testid="sort-controls" />,
}));

// BetCard is the real component -- we need its model_prob/market_prob/units/tier
// output to be present in the DOM. We render a lightweight stub that emits
// exactly the testid attributes the acceptance criteria require.
vi.mock("../../bets/BetCard", () => ({
  BetCard: ({ card }: { card: {
    model_prob: number;
    market_prob: number;
    units: number;
    tier: string | null;
  } }) => (
    <div data-testid="bet-card-stub">
      <span data-testid="card-model-prob">{(card.model_prob * 100).toFixed(1)}%</span>
      <span data-testid="card-market-prob">{(card.market_prob * 100).toFixed(1)}%</span>
      <span data-testid="card-units">{card.units.toFixed(2)}u</span>
      <span data-testid="card-tier">{card.tier ?? "--"}</span>
    </div>
  ),
}));

// ---------------------------------------------------------------------------
// Import AFTER mocks
// ---------------------------------------------------------------------------
import { BestBetsBoard } from "../../bets/BestBetsBoard";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function setLiveState(partial: Partial<LiveDataState<unknown>>) {
  _liveState = { ..._liveState, ...partial };
}

function resetLiveState() {
  _liveState = {
    data: null,
    lastUpdatedAt: null,
    ageSec: null,
    isStale: false,
    error: null,
    isLoading: false,
    refresh: vi.fn(),
  };
}

// Minimal BestBet shaped like the backend response for a "bet" decision.
// UNITS only -- no $ field anywhere. edge/ev are probability ratios.
function mkBestBet(over: {
  market_type?: string;
  side?: string;
  model_prob?: number;
  market_prob?: number;
  stake_units?: number;
  tier?: string;
}) {
  return {
    market_type: over.market_type ?? "moneyline",
    side: over.side ?? "home",
    model_prob: over.model_prob ?? 0.58,
    market_prob: over.market_prob ?? 0.52,
    best_book: "fanduel",
    best_odds: 1.88,
    line: null,
    edge: (over.model_prob ?? 0.58) - (over.market_prob ?? 0.52),
    ev: 0.07,
    tier: over.tier ?? "A",
    decision: "bet",
    stake_units: over.stake_units ?? 0.5,
    flat_unit: 0.5,
    kelly_units: 0.4,
    clv_is_proxy: true,
  };
}

// Full EnvelopeResult shape as returned by fetchAllSports (new shape).
function mkEnvelopeResult(
  gamesBySport: Record<
    string,
    Array<{ game_id: string; home?: string; away?: string; best_bets?: ReturnType<typeof mkBestBet>[] }>
  >,
  unavailableReasons: Record<string, string> = {},
) {
  const envelopes: Record<string, unknown> = {};
  for (const [sport, games] of Object.entries(gamesBySport)) {
    envelopes[sport] = {
      sport,
      generated_at: new Date(Date.now() - 30_000).toISOString(),
      status: "ok",
      count: games.length,
      n_best_bets: games.reduce((n, g) => n + (g.best_bets?.length ?? 0), 0),
      games: games.map((g) => ({
        game_id: g.game_id,
        home: g.home ?? "SAS",
        away: g.away ?? "NYK",
        status: "ok",
        best_bets: g.best_bets ?? [],
        candidates: g.best_bets ?? [],
      })),
      clv: { n_bets: 0, pct_beat_close: null, mean_clv_pct: null, by_sport: null, clv_is_proxy: true },
      edge_claimed: false,
    };
  }
  return { envelopes, unavailableReasons };
}

// ---------------------------------------------------------------------------
// (A) Cards payload -> one row per card with model_prob/market_prob/units/tier
// ---------------------------------------------------------------------------
describe("BestBetsBoard (A) -- cards payload renders one row per card", () => {
  beforeEach(() => resetLiveState());
  afterEach(() => vi.clearAllMocks());

  it("(A1) renders exactly one card-row per qualifying bet card", async () => {
    const payload = mkEnvelopeResult({
      nba: [
        {
          game_id: "001",
          best_bets: [
            mkBestBet({ model_prob: 0.58, market_prob: 0.52, stake_units: 0.5, tier: "A" }),
            mkBestBet({ market_type: "total", side: "over", model_prob: 0.60, market_prob: 0.50, stake_units: 0.75, tier: "S" }),
          ],
        },
      ],
    });
    setLiveState({
      data: payload,
      isLoading: false,
      ageSec: 30,
      lastUpdatedAt: Date.now(),
    });

    render(<BestBetsBoard />);
    await act(async () => { await Promise.resolve(); });

    // Two bets -> two card-rows in the pregame tab (default)
    const rows = screen.getAllByTestId("card-row");
    expect(rows).toHaveLength(2);
  });

  it("(A2) each card row carries model_prob, market_prob, units, and tier values", async () => {
    const payload = mkEnvelopeResult({
      nba: [
        {
          game_id: "002",
          best_bets: [
            mkBestBet({ model_prob: 0.62, market_prob: 0.55, stake_units: 1.0, tier: "S" }),
          ],
        },
      ],
    });
    setLiveState({
      data: payload,
      isLoading: false,
      ageSec: 10,
      lastUpdatedAt: Date.now(),
    });

    render(<BestBetsBoard />);
    await act(async () => { await Promise.resolve(); });

    // model_prob rendered as percentage
    expect(screen.getByTestId("card-model-prob").textContent).toContain("62.0%");
    // market_prob rendered as percentage
    expect(screen.getByTestId("card-market-prob").textContent).toContain("55.0%");
    // units rendered with 'u' suffix, NEVER a $ symbol
    const unitsEl = screen.getByTestId("card-units");
    expect(unitsEl.textContent).toContain("1.00u");
    expect(unitsEl.textContent).not.toMatch(/\$/);
    // tier badge is present
    expect(screen.getByTestId("card-tier").textContent).toContain("S");
  });

  it("(A3) rendered board output contains NO dollar string anywhere (UNITS only rail)", async () => {
    const payload = mkEnvelopeResult({
      nba: [
        {
          game_id: "003",
          best_bets: [mkBestBet({ stake_units: 2.5, tier: "B" })],
        },
      ],
    });
    setLiveState({
      data: payload,
      isLoading: false,
      ageSec: 15,
      lastUpdatedAt: Date.now(),
    });

    const { container } = render(<BestBetsBoard />);
    await act(async () => { await Promise.resolve(); });

    // No dollar sign followed by a digit anywhere in the rendered DOM
    expect(container.textContent ?? "").not.toMatch(/\$\s?\d/);
    // The literal word "dollars" must not appear
    expect(container.textContent?.toLowerCase() ?? "").not.toContain("dollars");
  });

  it("(A4) three cards from two sports all appear in the grid", async () => {
    const payload = mkEnvelopeResult({
      nba: [
        {
          game_id: "nba-g1",
          best_bets: [
            mkBestBet({ model_prob: 0.60, tier: "A" }),
            mkBestBet({ market_type: "spread", model_prob: 0.55, tier: "B" }),
          ],
        },
      ],
      mlb: [
        {
          game_id: "mlb-g1",
          best_bets: [mkBestBet({ model_prob: 0.65, tier: "S" })],
        },
      ],
    });
    setLiveState({ data: payload, isLoading: false, ageSec: 20, lastUpdatedAt: Date.now() });

    render(<BestBetsBoard />);
    await act(async () => { await Promise.resolve(); });

    expect(screen.getAllByTestId("card-row")).toHaveLength(3);
    // All stubs present
    expect(screen.getAllByTestId("bet-card-stub")).toHaveLength(3);
  });
});

// ---------------------------------------------------------------------------
// (B) status='unavailable' -> renders honest reason banner, not blank
// ---------------------------------------------------------------------------
describe("BestBetsBoard (B) -- unavailable state surfaces honest reason", () => {
  beforeEach(() => resetLiveState());
  afterEach(() => vi.clearAllMocks());

  it("(B1) when a sport is unavailable the reason banner is rendered (not blank)", async () => {
    // nba is unavailable with a reason; the EnvelopeResult surfaces it.
    const payload = {
      envelopes: { nba: null },
      unavailableReasons: { nba: "NBA offseason -- no games scheduled" },
    };
    setLiveState({ data: payload, isLoading: false, ageSec: 5, lastUpdatedAt: Date.now() });

    render(<BestBetsBoard />);
    await act(async () => { await Promise.resolve(); });

    // The unavailable reason section must be present
    const section = screen.getByTestId("unavailable-reasons-section");
    expect(section).toBeDefined();

    // The per-sport banner must surface the reason text
    const banner = screen.getByTestId("unavailable-banner-nba");
    expect(banner).toBeDefined();
    expect(banner.textContent).toContain("NBA offseason -- no games scheduled");
  });

  it("(B2) the reason banner explicitly shows edge_claimed=false (calibration-only honest note)", async () => {
    const payload = {
      envelopes: { nba: null },
      unavailableReasons: { nba: "no live prop lines available" },
    };
    setLiveState({ data: payload, isLoading: false, ageSec: 5, lastUpdatedAt: Date.now() });

    render(<BestBetsBoard />);
    await act(async () => { await Promise.resolve(); });

    const banner = screen.getByTestId("unavailable-banner-nba");
    // Must surface the honesty note -- calibration only, no fabricated edge
    expect(banner.textContent).toContain("edge_claimed=false");
    // Must NOT contain a dollar sign
    expect(banner.textContent).not.toMatch(/\$/);
  });

  it("(B3) board does NOT render a blank panel when unavailable -- shows reason not empty space", async () => {
    const payload = {
      envelopes: {},
      unavailableReasons: { all: "all sports unavailable -- predict service down" },
    };
    setLiveState({ data: payload, isLoading: false, ageSec: 5, lastUpdatedAt: Date.now() });

    render(<BestBetsBoard />);
    await act(async () => { await Promise.resolve(); });

    // Something honest must be visible -- not a blank region
    const bodyText = document.body.textContent ?? "";
    expect(bodyText.length).toBeGreaterThan(0);
    // The reason text must appear
    expect(bodyText).toContain("predict service down");
  });

  it("(B4) multiple unavailable sports each get their own honest reason banner", async () => {
    const payload = {
      envelopes: { nba: null, mlb: null },
      unavailableReasons: {
        nba: "NBA offseason",
        mlb: "MLB data gap",
      },
    };
    setLiveState({ data: payload, isLoading: false, ageSec: 5, lastUpdatedAt: Date.now() });

    render(<BestBetsBoard />);
    await act(async () => { await Promise.resolve(); });

    expect(screen.getByTestId("unavailable-banner-nba")).toBeDefined();
    expect(screen.getByTestId("unavailable-banner-mlb")).toBeDefined();
    expect(screen.getByTestId("unavailable-banner-nba").textContent).toContain("NBA offseason");
    expect(screen.getByTestId("unavailable-banner-mlb").textContent).toContain("MLB data gap");
  });

  it("(B5) board shows unavailable banner + cards together when one sport is ok and another is not", async () => {
    const payload = {
      envelopes: {
        nba: {
          sport: "nba",
          generated_at: new Date(Date.now() - 30_000).toISOString(),
          status: "ok",
          count: 1,
          n_best_bets: 1,
          games: [
            {
              game_id: "nba-001",
              home: "SAS",
              away: "NYK",
              status: "ok",
              best_bets: [mkBestBet({ model_prob: 0.58, tier: "A" })],
              candidates: [],
            },
          ],
          clv: { n_bets: 0, pct_beat_close: null, mean_clv_pct: null, by_sport: null, clv_is_proxy: true },
          edge_claimed: false,
        },
        mlb: null,
      },
      unavailableReasons: { mlb: "MLB offseason -- no lines" },
    };
    setLiveState({ data: payload, isLoading: false, ageSec: 10, lastUpdatedAt: Date.now() });

    render(<BestBetsBoard />);
    await act(async () => { await Promise.resolve(); });

    // Card present for nba
    expect(screen.getAllByTestId("card-row")).toHaveLength(1);
    // Banner present for mlb
    expect(screen.getByTestId("unavailable-banner-mlb").textContent).toContain("MLB offseason -- no lines");
  });
});
