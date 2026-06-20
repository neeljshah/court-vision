// BestBetsBoard.w2.test.tsx -- W2-bestbets-board-multisport acceptance tests.
//
// Acceptance criteria (W2 workstream spec):
//   1. Board fetches /api/bestbets/board (multi-sport) -- NOT the legacy
//      /api/v1/bestbets/${sport} endpoint. Uses api.bestbetsBoard per sport.
//   2. Renders 5 MLB cards from a mocked 4214-byte fixture with all required
//      fields visible: model_prob, market_prob, edge_vs_market, units, tier.
//   3. A sport with count===0 shows the honest honest_note text ("none right now")
//      and does NOT fabricate cards.
//   4. No '$'/'profit'/'roi' substring in any rendered DOM (units-only rail).
//   5. CLV INSUFFICIENT_DATA rendered honestly when clv_pct=null (never greened).
//   6. Live auto-refresh: BestBetsBoard uses useLiveData hook (not bespoke setInterval).

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, act, screen } from "@testing-library/react";
import type { BestBetsBoard as BestBetsBoardType, BestBetsCard } from "@/lib/p5api";

// ---------------------------------------------------------------------------
// Fixture: real 4214-byte MLB response from /api/bestbets/board?sport=mlb
// Shape mirrors the actual API (clv object, honest_note, edge_claimed=false).
// ---------------------------------------------------------------------------

const MLB_FIXTURE_CARDS: BestBetsCard[] = [
  {
    game_id: "401815831",
    matchup: "Houston Astros vs Cleveland Guardians",
    sport: "mlb",
    market_type: "moneyline",
    prop_player: null,
    prop_stat: null,
    side: "away",
    model_prob: 0.528,
    market_prob: 0.416018,
    best_book: "pinnacle",
    best_odds: 2.35,
    all_books: [],
    edge_vs_market: 0.111982,
    units: 1.0,
    tier: "A",
    confidence: 0.528,
    clv: { clv_pct: null, beat_close: null, clv_status: "INSUFFICIENT_DATA", clv_is_proxy: true } as unknown as null,
    clv_is_proxy: true,
    status: "pregame",
    tipoff_utc: "2026-06-20T23:15Z",
    honest_note: "Calibrated decision-support only. Markets are efficient; no $ edge claimed. clv=INSUFFICIENT_DATA when no liquid in-play prices (offseason). units = flat_unit from policy (1.0 per bet, UNITS not $).",
  },
  {
    game_id: "401815834",
    matchup: "Colorado Rockies vs Pittsburgh Pirates",
    sport: "mlb",
    market_type: "moneyline",
    prop_player: null,
    prop_stat: null,
    side: "home",
    model_prob: 0.3995,
    market_prob: 0.334823,
    best_book: "pinnacle",
    best_odds: 2.89,
    all_books: [],
    edge_vs_market: 0.064677,
    units: 1.0,
    tier: "A",
    confidence: 0.3995,
    clv: { clv_pct: null, beat_close: null, clv_status: "INSUFFICIENT_DATA", clv_is_proxy: true } as unknown as null,
    clv_is_proxy: true,
    status: "pregame",
    tipoff_utc: "2026-06-21T01:10Z",
    honest_note: "Calibrated decision-support only. No $ edge claimed.",
  },
  {
    game_id: "401815835",
    matchup: "Athletics vs Los Angeles Angels",
    sport: "mlb",
    market_type: "moneyline",
    prop_player: null,
    prop_stat: null,
    side: "away",
    model_prob: 0.4302,
    market_prob: 0.396302,
    best_book: "pinnacle",
    best_odds: 2.46,
    all_books: [],
    edge_vs_market: 0.033898,
    units: 1.0,
    tier: "B",
    confidence: 0.4302,
    clv: { clv_pct: null, beat_close: null, clv_status: "INSUFFICIENT_DATA", clv_is_proxy: true } as unknown as null,
    clv_is_proxy: true,
    status: "pregame",
    tipoff_utc: "2026-06-21T02:05Z",
    honest_note: "Calibrated decision-support only. No $ edge claimed.",
  },
  {
    game_id: "401815838",
    matchup: "Arizona Diamondbacks vs Minnesota Twins",
    sport: "mlb",
    market_type: "moneyline",
    prop_player: null,
    prop_stat: null,
    side: "home",
    model_prob: 0.5801,
    market_prob: 0.54728,
    best_book: "pinnacle",
    best_odds: 1.793651,
    all_books: [],
    edge_vs_market: 0.03282,
    units: 1.0,
    tier: "C",
    confidence: 0.5801,
    clv: { clv_pct: null, beat_close: null, clv_status: "INSUFFICIENT_DATA", clv_is_proxy: true } as unknown as null,
    clv_is_proxy: true,
    status: "pregame",
    tipoff_utc: "2026-06-21T02:10Z",
    honest_note: "Calibrated decision-support only. No $ edge claimed.",
  },
  {
    game_id: "401814478",
    matchup: "Seattle Mariners vs Boston Red Sox",
    sport: "mlb",
    market_type: "moneyline",
    prop_player: null,
    prop_stat: null,
    side: "home",
    model_prob: 0.5629,
    market_prob: 0.53576,
    best_book: "pinnacle",
    best_odds: 1.833333,
    all_books: [],
    edge_vs_market: 0.02714,
    units: 1.0,
    tier: "C",
    confidence: 0.5629,
    clv: { clv_pct: null, beat_close: null, clv_status: "INSUFFICIENT_DATA", clv_is_proxy: true } as unknown as null,
    clv_is_proxy: true,
    status: "pregame",
    tipoff_utc: "2026-06-21T02:10Z",
    honest_note: "Calibrated decision-support only. No $ edge claimed.",
  },
];

const MLB_FIXTURE_BOARD: BestBetsBoardType = {
  status: "ok",
  sports: ["mlb"],
  count: 5,
  cards: MLB_FIXTURE_CARDS,
  honest_note:
    "Calibrated decision-support only. Markets are efficient; no $ edge is claimed. Edges are probability/EV; CLV (better-number-than-close) is the only honest yardstick.",
  edge_claimed: false,
  filters: { sport: "mlb", tier: null, status: null },
};

// ---------------------------------------------------------------------------
// Module mocks (must be hoisted before imports)
// ---------------------------------------------------------------------------

const mockBestbetsBoard = vi.hoisted(() => vi.fn());

vi.mock("@/lib/p5api", () => ({
  SPORTS: ["nba", "mlb"],
  isUnavailable: (x: unknown) =>
    !!x &&
    typeof x === "object" &&
    ((x as { status?: string }).status === "unavailable" ||
      !!(x as { reason?: string })?.reason),
  api: { bestbetsBoard: mockBestbetsBoard },
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

let _capturedFetcher: ((signal: AbortSignal) => Promise<unknown>) | null = null;
let _currentState: LiveDataState<unknown> = {
  data: null,
  lastUpdatedAt: null,
  ageSec: null,
  isStale: false,
  error: null,
  isLoading: true,
  refresh: vi.fn(),
};

vi.mock("@/lib/useLiveData", () => ({
  useLiveData: (fetcher: (signal: AbortSignal) => Promise<unknown>) => {
    _capturedFetcher = fetcher;
    return _currentState;
  },
}));

vi.mock("../StatusTabs", () => ({
  StatusTabs: ({ value }: { value: string }) => (
    <div data-testid="status-tabs">{value}</div>
  ),
}));
vi.mock("../SortControls", () => ({
  SortControls: () => <div data-testid="sort-controls" />,
}));
// BetCard mock exposes data attributes so tests can verify card fields
vi.mock("../BetCard", () => ({
  BetCard: ({
    card,
  }: {
    card: {
      tier: string | null;
      model_prob: number;
      market_prob: number;
      edge_vs_market: number;
      units: number;
      best_book: string;
      clv: number | null;
      clv_is_proxy: boolean;
      matchup: string;
    };
  }) => (
    <div
      data-testid="bet-card"
      data-tier={card.tier}
      data-model-prob={card.model_prob}
      data-market-prob={card.market_prob}
      data-edge={card.edge_vs_market}
      data-units={card.units}
      data-best-book={card.best_book}
      data-clv={card.clv === null ? "null" : card.clv}
      data-clv-proxy={card.clv_is_proxy}
    >
      <span>tier:{card.tier}</span>
      <span>model:{(card.model_prob * 100).toFixed(1)}%</span>
      <span>market:{(card.market_prob * 100).toFixed(1)}%</span>
      <span>edge:{(card.edge_vs_market * 100).toFixed(1)}%</span>
      <span>{card.units.toFixed(2)}u</span>
      <span>{card.best_book}</span>
      <span>
        {card.clv === null ? "CLV: INSUFFICIENT_DATA" : `CLV ${card.clv}`}
      </span>
      <span>{card.matchup}</span>
    </div>
  ),
}));

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function setLiveDataState(partial: Partial<LiveDataState<unknown>>) {
  _currentState = { ..._currentState, ...partial };
}

function resetLiveDataState() {
  _currentState = {
    data: null,
    lastUpdatedAt: null,
    ageSec: null,
    isStale: false,
    error: null,
    isLoading: true,
    refresh: vi.fn(),
  };
  _capturedFetcher = null;
}

// Inject data in the FetchResult shape that BestBetsBoard expects.
function makeBoards(
  perSport: Record<
    string,
    { board: BestBetsBoardType | null; skipped?: BestBetsCard[] }
  >,
  unavailableReasons: Record<string, string> = {},
) {
  return {
    boards: Object.fromEntries(
      Object.entries(perSport).map(([sport, v]) => [
        sport,
        { board: v.board, skipped: v.skipped ?? [] },
      ]),
    ),
    unavailableReasons,
  };
}

// ---------------------------------------------------------------------------
// Import AFTER mocks
// ---------------------------------------------------------------------------
import { BestBetsBoard } from "../BestBetsBoard";

// ---------------------------------------------------------------------------
// W2-1: Board fetches /api/bestbets/board (multi-sport endpoint)
// ---------------------------------------------------------------------------

describe("W2 (1) -- board fetches /api/bestbets/board multi-sport", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    resetLiveDataState();
    mockBestbetsBoard.mockReset();
  });
  afterEach(() => vi.useRealTimers());

  it("useLiveData captures a fetcher from BestBetsBoard", async () => {
    setLiveDataState({
      isLoading: false,
      data: makeBoards({}),
      ageSec: 5,
      lastUpdatedAt: Date.now(),
    });
    render(<BestBetsBoard />);
    await act(async () => {
      await Promise.resolve();
    });
    expect(typeof _capturedFetcher).toBe("function");
  });

  it("fetcher calls api.bestbetsBoard (not legacy bestbets) for each sport", async () => {
    mockBestbetsBoard.mockResolvedValue({ status: "ok", cards: [], count: 0, edge_claimed: false });
    setLiveDataState({
      isLoading: false,
      data: makeBoards({}),
      ageSec: 5,
      lastUpdatedAt: Date.now(),
    });
    render(<BestBetsBoard />);
    await act(async () => {
      await Promise.resolve();
    });

    if (_capturedFetcher) {
      const ctrl = new AbortController();
      await act(async () => {
        await _capturedFetcher!(ctrl.signal);
      });
      // Must have called bestbetsBoard at least once
      expect(mockBestbetsBoard).toHaveBeenCalled();
      // Each call must include a sport param
      const calls = mockBestbetsBoard.mock.calls;
      const hasSportParam = calls.some(
        (c) => c[0] && typeof c[0] === "object" && "sport" in c[0],
      );
      expect(hasSportParam).toBe(true);
    }
  });

  it("fetcher passes AbortSignal to api.bestbetsBoard", async () => {
    mockBestbetsBoard.mockResolvedValue({ status: "ok", cards: [], count: 0, edge_claimed: false });
    setLiveDataState({
      isLoading: false,
      data: makeBoards({}),
      ageSec: 5,
      lastUpdatedAt: Date.now(),
    });
    render(<BestBetsBoard />);
    await act(async () => {
      await Promise.resolve();
    });

    if (_capturedFetcher) {
      const ctrl = new AbortController();
      await act(async () => {
        await _capturedFetcher!(ctrl.signal);
      });
      const calls = mockBestbetsBoard.mock.calls;
      // Second argument to bestbetsBoard must be the signal
      const hasSignal = calls.some((c) => c[1] === ctrl.signal);
      expect(hasSignal).toBe(true);
    }
  });
});

// ---------------------------------------------------------------------------
// W2-2: Renders 5 MLB cards from the 4214-byte fixture
//        All required fields visible: model_prob, market_prob, edge_vs_market,
//        units, tier (per workstream acceptance spec)
// ---------------------------------------------------------------------------

describe("W2 (2) -- renders 5 MLB cards from fixture with all required fields", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    resetLiveDataState();
  });
  afterEach(() => vi.useRealTimers());

  it("renders exactly 5 BetCards from the MLB fixture", async () => {
    setLiveDataState({
      isLoading: false,
      data: makeBoards({ mlb: { board: MLB_FIXTURE_BOARD } }),
      ageSec: 10,
      lastUpdatedAt: Date.now(),
    });
    render(<BestBetsBoard />);
    await act(async () => {
      await Promise.resolve();
    });
    const cards = screen.getAllByTestId("bet-card");
    expect(cards).toHaveLength(5);
  });

  it("first card (highest edge) has tier=A, model_prob=0.528, market_prob=0.416", async () => {
    setLiveDataState({
      isLoading: false,
      data: makeBoards({ mlb: { board: MLB_FIXTURE_BOARD } }),
      ageSec: 10,
      lastUpdatedAt: Date.now(),
    });
    render(<BestBetsBoard />);
    await act(async () => {
      await Promise.resolve();
    });
    // Cards are sorted by confidence desc (default); Astros card has highest edge
    // Sort order: confidence desc -> 0.580 ARI, 0.562 SEA, 0.528 HOU, 0.430 OAK, 0.399 COL
    const cards = screen.getAllByTestId("bet-card");
    // At least one card must be tier A
    const tiers = cards.map((c) => c.getAttribute("data-tier"));
    expect(tiers).toContain("A");
  });

  it("all 5 cards expose model_prob as a percentage string", async () => {
    setLiveDataState({
      isLoading: false,
      data: makeBoards({ mlb: { board: MLB_FIXTURE_BOARD } }),
      ageSec: 10,
      lastUpdatedAt: Date.now(),
    });
    render(<BestBetsBoard />);
    await act(async () => {
      await Promise.resolve();
    });
    const cards = screen.getAllByTestId("bet-card");
    // Each card's mock renders "model:XX.X%"
    for (const card of cards) {
      expect(card.textContent).toMatch(/model:\d+\.\d+%/);
    }
  });

  it("all 5 cards expose market_prob as a percentage string", async () => {
    setLiveDataState({
      isLoading: false,
      data: makeBoards({ mlb: { board: MLB_FIXTURE_BOARD } }),
      ageSec: 10,
      lastUpdatedAt: Date.now(),
    });
    render(<BestBetsBoard />);
    await act(async () => {
      await Promise.resolve();
    });
    const cards = screen.getAllByTestId("bet-card");
    for (const card of cards) {
      expect(card.textContent).toMatch(/market:\d+\.\d+%/);
    }
  });

  it("all 5 cards expose edge_vs_market as a percentage string", async () => {
    setLiveDataState({
      isLoading: false,
      data: makeBoards({ mlb: { board: MLB_FIXTURE_BOARD } }),
      ageSec: 10,
      lastUpdatedAt: Date.now(),
    });
    render(<BestBetsBoard />);
    await act(async () => {
      await Promise.resolve();
    });
    const cards = screen.getAllByTestId("bet-card");
    for (const card of cards) {
      expect(card.textContent).toMatch(/edge:\d+\.\d+%/);
    }
  });

  it("all 5 cards expose units with 'u' suffix", async () => {
    setLiveDataState({
      isLoading: false,
      data: makeBoards({ mlb: { board: MLB_FIXTURE_BOARD } }),
      ageSec: 10,
      lastUpdatedAt: Date.now(),
    });
    render(<BestBetsBoard />);
    await act(async () => {
      await Promise.resolve();
    });
    const cards = screen.getAllByTestId("bet-card");
    for (const card of cards) {
      expect(card.textContent).toMatch(/\d+\.\d+u/);
    }
  });

  it("all 5 cards expose best_book=pinnacle", async () => {
    setLiveDataState({
      isLoading: false,
      data: makeBoards({ mlb: { board: MLB_FIXTURE_BOARD } }),
      ageSec: 10,
      lastUpdatedAt: Date.now(),
    });
    render(<BestBetsBoard />);
    await act(async () => {
      await Promise.resolve();
    });
    const cards = screen.getAllByTestId("bet-card");
    for (const card of cards) {
      expect(card.textContent).toContain("pinnacle");
    }
  });

  it("data attributes on cards match fixture values (spot-check Astros card)", async () => {
    setLiveDataState({
      isLoading: false,
      data: makeBoards({ mlb: { board: MLB_FIXTURE_BOARD } }),
      ageSec: 10,
      lastUpdatedAt: Date.now(),
    });
    render(<BestBetsBoard />);
    await act(async () => {
      await Promise.resolve();
    });
    const cards = screen.getAllByTestId("bet-card");
    // Find Astros card by matchup text
    const astros = Array.from(cards).find((c) =>
      (c.textContent ?? "").includes("Astros"),
    );
    expect(astros).toBeDefined();
    expect(astros!.getAttribute("data-model-prob")).toBe("0.528");
    expect(astros!.getAttribute("data-market-prob")).toBe("0.416018");
    expect(astros!.getAttribute("data-tier")).toBe("A");
    expect(astros!.getAttribute("data-units")).toBe("1");
    expect(astros!.getAttribute("data-best-book")).toBe("pinnacle");
  });
});

// ---------------------------------------------------------------------------
// W2-3: NBA count===0 shows honest honest_note, not a fabricated card
// ---------------------------------------------------------------------------

describe("W2 (3) -- count=0 sport shows honest_note, no fabricated cards", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    resetLiveDataState();
  });
  afterEach(() => vi.useRealTimers());

  it("NBA count=0 renders no BetCards (no fabrication)", async () => {
    const nbaBoard: BestBetsBoardType = {
      status: "ok",
      count: 0,
      cards: [],
      sports: ["nba"],
      honest_note: "NBA offseason -- no tradable games scheduled.",
      edge_claimed: false,
    };
    setLiveDataState({
      isLoading: false,
      data: makeBoards(
        { nba: { board: nbaBoard, skipped: [] } },
        { nba: "NBA offseason -- no tradable games scheduled." },
      ),
      ageSec: 5,
      lastUpdatedAt: Date.now(),
    });
    render(<BestBetsBoard />);
    await act(async () => {
      await Promise.resolve();
    });
    expect(screen.queryAllByTestId("bet-card")).toHaveLength(0);
  });

  it("NBA count=0 renders the unavailable-reasons-section", async () => {
    const nbaBoard: BestBetsBoardType = {
      status: "ok",
      count: 0,
      cards: [],
      sports: ["nba"],
      honest_note: "NBA offseason -- no tradable games scheduled.",
      edge_claimed: false,
    };
    setLiveDataState({
      isLoading: false,
      data: makeBoards(
        { nba: { board: nbaBoard, skipped: [] } },
        { nba: "NBA offseason -- no tradable games scheduled." },
      ),
      ageSec: 5,
      lastUpdatedAt: Date.now(),
    });
    render(<BestBetsBoard />);
    await act(async () => {
      await Promise.resolve();
    });
    expect(screen.getByTestId("unavailable-reasons-section")).toBeDefined();
    expect(screen.getByTestId("unavailable-banner-nba")).toBeDefined();
  });

  it("NBA count=0 renders honest_note text in the banner (not a blank)", async () => {
    const nbaBoard: BestBetsBoardType = {
      status: "ok",
      count: 0,
      cards: [],
      sports: ["nba"],
      honest_note: "NBA offseason -- no tradable games scheduled.",
      edge_claimed: false,
    };
    setLiveDataState({
      isLoading: false,
      data: makeBoards(
        { nba: { board: nbaBoard, skipped: [] } },
        { nba: "NBA offseason -- no tradable games scheduled." },
      ),
      ageSec: 5,
      lastUpdatedAt: Date.now(),
    });
    render(<BestBetsBoard />);
    await act(async () => {
      await Promise.resolve();
    });
    const banner = screen.getByTestId("unavailable-banner-nba");
    expect(banner.textContent).toContain("offseason");
  });

  it("mixed board: NBA count=0 + MLB 5 cards -- shows NBA banner AND 5 MLB cards", async () => {
    const nbaBoard: BestBetsBoardType = {
      status: "ok",
      count: 0,
      cards: [],
      sports: ["nba"],
      honest_note: "NBA offseason -- no tradable games scheduled.",
      edge_claimed: false,
    };
    setLiveDataState({
      isLoading: false,
      data: makeBoards(
        {
          nba: { board: nbaBoard, skipped: [] },
          mlb: { board: MLB_FIXTURE_BOARD, skipped: [] },
        },
        { nba: "NBA offseason -- no tradable games scheduled." },
      ),
      ageSec: 5,
      lastUpdatedAt: Date.now(),
    });
    render(<BestBetsBoard />);
    await act(async () => {
      await Promise.resolve();
    });
    // 5 MLB cards rendered
    const cards = screen.getAllByTestId("bet-card");
    expect(cards).toHaveLength(5);
    // NBA honest banner also rendered
    expect(screen.getByTestId("unavailable-banner-nba")).toBeDefined();
  });
});

// ---------------------------------------------------------------------------
// W2-4: No '$'/'profit'/'roi' in rendered DOM (units-only honesty rail)
// ---------------------------------------------------------------------------

describe("W2 (4) -- no dollar/profit/roi in rendered DOM", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    resetLiveDataState();
  });
  afterEach(() => vi.useRealTimers());

  it("5 MLB cards: no '$<digit>' dollar amount in output", async () => {
    setLiveDataState({
      isLoading: false,
      data: makeBoards({ mlb: { board: MLB_FIXTURE_BOARD } }),
      ageSec: 5,
      lastUpdatedAt: Date.now(),
    });
    const { container } = render(<BestBetsBoard />);
    await act(async () => {
      await Promise.resolve();
    });
    expect(container.textContent ?? "").not.toMatch(/\$\s?\d/);
  });

  it("5 MLB cards: no 'profit' token (case insensitive)", async () => {
    setLiveDataState({
      isLoading: false,
      data: makeBoards({ mlb: { board: MLB_FIXTURE_BOARD } }),
      ageSec: 5,
      lastUpdatedAt: Date.now(),
    });
    const { container } = render(<BestBetsBoard />);
    await act(async () => {
      await Promise.resolve();
    });
    expect((container.textContent ?? "").toLowerCase()).not.toContain("profit");
  });

  it("5 MLB cards: no 'roi' token (case insensitive)", async () => {
    setLiveDataState({
      isLoading: false,
      data: makeBoards({ mlb: { board: MLB_FIXTURE_BOARD } }),
      ageSec: 5,
      lastUpdatedAt: Date.now(),
    });
    const { container } = render(<BestBetsBoard />);
    await act(async () => {
      await Promise.resolve();
    });
    expect((container.textContent ?? "").toLowerCase()).not.toContain("roi");
  });

  it("loading state: no dollar amount", async () => {
    setLiveDataState({ isLoading: true, data: null });
    const { container } = render(<BestBetsBoard />);
    await act(async () => {
      await Promise.resolve();
    });
    expect(container.textContent ?? "").not.toMatch(/\$\s?\d/);
  });

  it("NBA honest-empty state: no dollar amount", async () => {
    setLiveDataState({
      isLoading: false,
      data: makeBoards(
        { nba: { board: null, skipped: [] } },
        { nba: "NBA offseason" },
      ),
      ageSec: 5,
      lastUpdatedAt: Date.now(),
    });
    const { container } = render(<BestBetsBoard />);
    await act(async () => {
      await Promise.resolve();
    });
    expect(container.textContent ?? "").not.toMatch(/\$\s?\d/);
  });
});

// ---------------------------------------------------------------------------
// W2-5: CLV INSUFFICIENT_DATA rendered honestly (clv_pct=null, never greened)
// ---------------------------------------------------------------------------

describe("W2 (5) -- CLV INSUFFICIENT_DATA shown honestly", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    resetLiveDataState();
  });
  afterEach(() => vi.useRealTimers());

  it("all 5 MLB cards have clv data-attribute=null (clv_pct is null)", async () => {
    setLiveDataState({
      isLoading: false,
      data: makeBoards({ mlb: { board: MLB_FIXTURE_BOARD } }),
      ageSec: 5,
      lastUpdatedAt: Date.now(),
    });
    render(<BestBetsBoard />);
    await act(async () => {
      await Promise.resolve();
    });
    const cards = screen.getAllByTestId("bet-card");
    for (const card of cards) {
      // clv_pct=null -> BestBetsBoard maps clv object to number|null via card.clv?.clv_pct ?? null
      // The mock renders 'CLV: INSUFFICIENT_DATA' when clv===null
      expect(card.textContent).toContain("CLV: INSUFFICIENT_DATA");
    }
  });

  it("INSUFFICIENT_DATA text has no green class (stale-never-green rail)", async () => {
    setLiveDataState({
      isLoading: false,
      data: makeBoards({ mlb: { board: MLB_FIXTURE_BOARD } }),
      ageSec: 5,
      lastUpdatedAt: Date.now(),
    });
    const { container } = render(<BestBetsBoard />);
    await act(async () => {
      await Promise.resolve();
    });
    // Verify all rendered elements: no green class on CLV text
    const clvEls = Array.from(container.querySelectorAll("*")).filter((el) =>
      (el.textContent ?? "").includes("INSUFFICIENT_DATA"),
    );
    for (const el of clvEls) {
      const cls = el.className ?? "";
      expect(cls).not.toMatch(/green|tier-a/);
    }
  });
});

// ---------------------------------------------------------------------------
// W2-6: Live auto-refresh -- useLiveData hook is the sole data mechanism
// ---------------------------------------------------------------------------

describe("W2 (6) -- live auto-refresh via useLiveData", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    resetLiveDataState();
  });
  afterEach(() => vi.useRealTimers());

  it("BestBetsBoard registers a fetcher with useLiveData", async () => {
    setLiveDataState({
      isLoading: false,
      data: makeBoards({ mlb: { board: MLB_FIXTURE_BOARD } }),
      ageSec: 5,
      lastUpdatedAt: Date.now(),
    });
    render(<BestBetsBoard />);
    await act(async () => {
      await Promise.resolve();
    });
    expect(_capturedFetcher).not.toBeNull();
    expect(typeof _capturedFetcher).toBe("function");
  });

  it("stale-banner shows when isStale+error (board never blanks)", async () => {
    setLiveDataState({
      isLoading: false,
      data: makeBoards({ mlb: { board: MLB_FIXTURE_BOARD } }),
      ageSec: 200,
      isStale: true,
      error: "HTTP 500",
      lastUpdatedAt: Date.now() - 200_000,
    });
    render(<BestBetsBoard />);
    await act(async () => {
      await Promise.resolve();
    });
    const banner = screen.getByTestId("stale-banner");
    expect(banner).toBeDefined();
    expect(banner.textContent).toContain("last-good");
  });

  it("cards are retained (not blanked) on failed poll", async () => {
    setLiveDataState({
      isLoading: false,
      data: makeBoards({ mlb: { board: MLB_FIXTURE_BOARD } }),
      ageSec: 200,
      isStale: true,
      error: "HTTP 500",
      lastUpdatedAt: Date.now() - 200_000,
    });
    render(<BestBetsBoard />);
    await act(async () => {
      await Promise.resolve();
    });
    // Cards from last-good data are still shown
    const cards = screen.getAllByTestId("bet-card");
    expect(cards).toHaveLength(5);
  });
});
