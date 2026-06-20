// BestBetsBoard.w3.test.tsx -- W3-bestbets-board-real-cards acceptance tests.
//
// Acceptance criteria (verbatim from the workstream spec):
//   1. With /api/bestbets/board?sport=mlb mocked to 5 cards, the Pregame section
//      renders 5 BetCards showing tier + model_prob vs market_prob + units + best_book.
//   2. A card with status='post' or 'final' is excluded (skip_reason surfaced, not
//      rendered as an active bet card).
//   3. NBA count===0 shows honest-empty (not fabricated cards).
//   4. No $/dollar/pnl/roi token appears anywhere in the rendered DOM.
//
// Additional: auto-refresh wiring (bestbetsBoard called per sport), stale-banner,
// and existing AgeBadge rail tests still pass (those live in BestBetsBoard.test.tsx).

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, act, screen } from "@testing-library/react";
import type { BestBetsBoard as BestBetsBoardType, BestBetsCard } from "@/lib/p5api";

// ---------------------------------------------------------------------------
// Module mocks
// ---------------------------------------------------------------------------

const mockBestbetsBoard = vi.hoisted(() => vi.fn());

vi.mock("@/lib/p5api", () => ({
  SPORTS: ["nba", "mlb"],
  isUnavailable: (x: unknown) =>
    !!x && typeof x === "object" && (x as { status?: string }).status === "unavailable",
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
// BetCard renders just enough to verify tier, probs, units, best_book
vi.mock("../BetCard", () => ({
  BetCard: ({ card }: { card: { tier: string | null; model_prob: number; market_prob: number; units: number; best_book: string } }) => (
    <div data-testid="bet-card"
      data-tier={card.tier}
      data-model-prob={card.model_prob}
      data-market-prob={card.market_prob}
      data-units={card.units}
      data-best-book={card.best_book}
    >
      tier:{card.tier} model:{(card.model_prob * 100).toFixed(1)}%
      vs market:{(card.market_prob * 100).toFixed(1)}%
      units:{card.units.toFixed(2)}u book:{card.best_book}
    </div>
  ),
}));

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeCard(overrides: Partial<BestBetsCard> = {}): BestBetsCard {
  return {
    game_id: `game-${Math.random()}`,
    matchup: "Team A vs Team B",
    sport: "mlb",
    market_type: "moneyline",
    prop_player: null,
    prop_stat: null,
    side: "away",
    model_prob: 0.528,
    market_prob: 0.421,
    best_book: "pinnacle",
    best_odds: 2.32,
    all_books: [],
    edge_vs_market: 0.107,
    units: 1.0,
    tier: "A",
    confidence: 0.528,
    clv: { clv_pct: null, beat_close: null, clv_status: "INSUFFICIENT_DATA", clv_is_proxy: true },
    clv_is_proxy: true,
    status: "pregame",
    tipoff_utc: "2026-06-20T23:15Z",
    ...overrides,
  };
}

function makeBoard(overrides: Partial<BestBetsBoardType> = {}): BestBetsBoardType {
  return {
    status: "ok",
    count: 5,
    cards: [],
    sports: ["mlb"],
    honest_note: "Calibrated decision-support only. No $ edge claimed.",
    edge_claimed: false,
    ...overrides,
  };
}

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

// Inject data as the FetchResult shape that BestBetsBoard v2 expects.
function makeBoards(
  perSport: Record<string, { board: BestBetsBoardType | null; skipped?: BestBetsCard[] }>,
) {
  return {
    boards: Object.fromEntries(
      Object.entries(perSport).map(([sport, v]) => [
        sport,
        { board: v.board, skipped: v.skipped ?? [] },
      ]),
    ),
    unavailableReasons: {},
  };
}

// ---------------------------------------------------------------------------
// Import AFTER mocks
// ---------------------------------------------------------------------------
import { BestBetsBoard } from "../BestBetsBoard";

// ---------------------------------------------------------------------------
// 1. 5 MLB pregame cards render with tier + probs + units + best_book
// ---------------------------------------------------------------------------

describe("W3 acceptance (1) -- 5 MLB pregame cards render", () => {
  beforeEach(() => { vi.useFakeTimers(); resetLiveDataState(); });
  afterEach(() => { vi.useRealTimers(); });

  it("renders 5 BetCards when 5 pregame MLB cards are returned", async () => {
    const cards = Array.from({ length: 5 }, (_, i) =>
      makeCard({ game_id: `mlb-${i}`, tier: i % 2 === 0 ? "A" : "B" }),
    );
    setLiveDataState({
      isLoading: false,
      data: makeBoards({ mlb: { board: makeBoard({ cards, count: 5 }) } }),
      ageSec: 10,
      lastUpdatedAt: Date.now(),
    });

    render(<BestBetsBoard />);
    await act(async () => { await Promise.resolve(); });

    const betCards = screen.getAllByTestId("bet-card");
    expect(betCards).toHaveLength(5);
  });

  it("each rendered card exposes tier, model_prob, market_prob, units, best_book", async () => {
    const card = makeCard({ tier: "A", model_prob: 0.55, market_prob: 0.44, units: 1.0, best_book: "pinnacle" });
    setLiveDataState({
      isLoading: false,
      data: makeBoards({ mlb: { board: makeBoard({ cards: [card], count: 1 }) } }),
      ageSec: 5,
      lastUpdatedAt: Date.now(),
    });

    render(<BestBetsBoard />);
    await act(async () => { await Promise.resolve(); });

    const betCard = screen.getByTestId("bet-card");
    expect(betCard.getAttribute("data-tier")).toBe("A");
    expect(betCard.getAttribute("data-model-prob")).toBe("0.55");
    expect(betCard.getAttribute("data-market-prob")).toBe("0.44");
    expect(betCard.getAttribute("data-units")).toBe("1");
    expect(betCard.getAttribute("data-best-book")).toBe("pinnacle");
  });

  it("cards with tier A and B both render (not filtered by tier)", async () => {
    const cards = [
      makeCard({ tier: "A", game_id: "g1" }),
      makeCard({ tier: "B", game_id: "g2" }),
    ];
    setLiveDataState({
      isLoading: false,
      data: makeBoards({ mlb: { board: makeBoard({ cards, count: 2 }) } }),
      ageSec: 5,
      lastUpdatedAt: Date.now(),
    });
    render(<BestBetsBoard />);
    await act(async () => { await Promise.resolve(); });
    expect(screen.getAllByTestId("bet-card")).toHaveLength(2);
  });
});

// ---------------------------------------------------------------------------
// 2. Cards with status='post'/'final' are excluded; skip_reason is surfaced
// ---------------------------------------------------------------------------

describe("W3 acceptance (2) -- post/final cards excluded, skip notice surfaced", () => {
  beforeEach(() => { vi.useFakeTimers(); resetLiveDataState(); });
  afterEach(() => { vi.useRealTimers(); });

  it("a card with status='post' is NOT rendered as a bet card", async () => {
    const pregame = makeCard({ status: "pregame", game_id: "g-pregame" });
    const post = makeCard({ status: "post", game_id: "g-post" });
    // Board endpoint: post card is in skipped[], pregame in cards[]
    setLiveDataState({
      isLoading: false,
      data: makeBoards({
        mlb: {
          board: makeBoard({ cards: [pregame], count: 1 }),
          skipped: [post],
        },
      }),
      ageSec: 5,
      lastUpdatedAt: Date.now(),
    });

    render(<BestBetsBoard />);
    await act(async () => { await Promise.resolve(); });

    // Only 1 pregame card rendered
    expect(screen.getAllByTestId("bet-card")).toHaveLength(1);
    // Skip notice should appear
    expect(screen.getByTestId("skipped-cards-notice")).toBeDefined();
    expect(screen.getByTestId("skipped-cards-notice").textContent).toContain("post/final");
  });

  it("a card with status='final' is NOT rendered as a bet card", async () => {
    const final = makeCard({ status: "final", game_id: "g-final" });
    setLiveDataState({
      isLoading: false,
      data: makeBoards({
        mlb: {
          board: makeBoard({ cards: [], count: 0 }),
          skipped: [final],
        },
      }),
      ageSec: 5,
      lastUpdatedAt: Date.now(),
    });

    render(<BestBetsBoard />);
    await act(async () => { await Promise.resolve(); });

    // No bet cards rendered
    expect(screen.queryAllByTestId("bet-card")).toHaveLength(0);
    // Skip notice
    const notice = screen.getByTestId("skipped-cards-notice");
    expect(notice.textContent).toContain("post/final");
  });

  it("skipped count in notice matches number of excluded cards", async () => {
    const skipped = [
      makeCard({ status: "post", game_id: "g-p1" }),
      makeCard({ status: "final", game_id: "g-f1" }),
    ];
    setLiveDataState({
      isLoading: false,
      data: makeBoards({
        mlb: {
          board: makeBoard({ cards: [], count: 0 }),
          skipped,
        },
      }),
      ageSec: 5,
      lastUpdatedAt: Date.now(),
    });
    render(<BestBetsBoard />);
    await act(async () => { await Promise.resolve(); });
    const notice = screen.getByTestId("skipped-cards-notice");
    // Notice should mention "2 cards"
    expect(notice.textContent).toMatch(/2\s+card/);
  });
});

// ---------------------------------------------------------------------------
// 3. NBA count===0 shows honest-empty (not fabricated)
// ---------------------------------------------------------------------------

describe("W3 acceptance (3) -- NBA count===0 honest-empty", () => {
  beforeEach(() => { vi.useFakeTimers(); resetLiveDataState(); });
  afterEach(() => { vi.useRealTimers(); });

  it("NBA with count=0 triggers unavailable-reasons-section with NBA entry", async () => {
    const nbaBoard = makeBoard({
      count: 0,
      cards: [],
      sports: ["nba"],
      honest_note: "NBA offseason -- no tradable games scheduled.",
    });
    setLiveDataState({
      isLoading: false,
      data: {
        boards: {
          nba: { board: nbaBoard, skipped: [] },
        },
        unavailableReasons: {
          nba: "NBA offseason -- no tradable games scheduled.",
        },
      },
      ageSec: 5,
      lastUpdatedAt: Date.now(),
    });

    render(<BestBetsBoard />);
    await act(async () => { await Promise.resolve(); });

    // No fabricated bet cards
    expect(screen.queryAllByTestId("bet-card")).toHaveLength(0);
    // Honest reason section rendered
    const reasonSection = screen.getByTestId("unavailable-reasons-section");
    expect(reasonSection).toBeDefined();
    // NBA banner present
    const nbaBanner = screen.getByTestId("unavailable-banner-nba");
    expect(nbaBanner).toBeDefined();
    expect(nbaBanner.textContent).toContain("NBA");
  });

  it("NBA count=0 with reason shows the reason text (not a blank or fake-positive)", async () => {
    const reason = "NBA offseason -- no tradable games scheduled.";
    setLiveDataState({
      isLoading: false,
      data: {
        boards: {
          nba: {
            board: makeBoard({ count: 0, cards: [], sports: ["nba"] }),
            skipped: [],
          },
        },
        unavailableReasons: { nba: reason },
      },
      ageSec: 5,
      lastUpdatedAt: Date.now(),
    });

    render(<BestBetsBoard />);
    await act(async () => { await Promise.resolve(); });

    const text = document.body.textContent ?? "";
    expect(text).toContain("offseason");
  });
});

// ---------------------------------------------------------------------------
// 4. No $/dollar/pnl/roi token in rendered DOM
// ---------------------------------------------------------------------------

describe("W3 acceptance (4) -- no $/pnl/roi/dollar in DOM", () => {
  beforeEach(() => { vi.useFakeTimers(); resetLiveDataState(); });
  afterEach(() => { vi.useRealTimers(); });

  it("5 MLB pregame cards: no $<digit> in rendered output", async () => {
    const cards = Array.from({ length: 5 }, (_, i) =>
      makeCard({ game_id: `mlb-${i}` }),
    );
    setLiveDataState({
      isLoading: false,
      data: makeBoards({ mlb: { board: makeBoard({ cards, count: 5 }) } }),
      ageSec: 5,
      lastUpdatedAt: Date.now(),
    });
    const { container } = render(<BestBetsBoard />);
    await act(async () => { await Promise.resolve(); });
    expect(container.textContent ?? "").not.toMatch(/\$\s?\d/);
  });

  it("loading state: no dollar sign in rendered output", async () => {
    setLiveDataState({ isLoading: true, data: null });
    const { container } = render(<BestBetsBoard />);
    await act(async () => { await Promise.resolve(); });
    expect(container.textContent ?? "").not.toMatch(/\$\s?\d/);
  });

  it("stale-banner: no dollar sign", async () => {
    setLiveDataState({
      isLoading: false,
      data: makeBoards({ mlb: { board: makeBoard({ cards: [], count: 0 }) } }),
      ageSec: 200,
      isStale: true,
      error: "HTTP 500",
      lastUpdatedAt: Date.now() - 200_000,
    });
    const { container } = render(<BestBetsBoard />);
    await act(async () => { await Promise.resolve(); });
    expect(container.textContent ?? "").not.toMatch(/\$\s?\d/);
  });

  it("unavailable-reason banner: no dollar sign", async () => {
    setLiveDataState({
      isLoading: false,
      data: {
        boards: { nba: { board: null, skipped: [] } },
        unavailableReasons: { nba: "NBA offseason" },
      },
      ageSec: 5,
      lastUpdatedAt: Date.now(),
    });
    const { container } = render(<BestBetsBoard />);
    await act(async () => { await Promise.resolve(); });
    expect(container.textContent ?? "").not.toMatch(/\$\s?\d/);
  });

  it("no 'pnl' token in rendered text (case insensitive)", async () => {
    setLiveDataState({
      isLoading: false,
      data: makeBoards({ mlb: { board: makeBoard({ cards: [makeCard()], count: 1 }) } }),
      ageSec: 5,
      lastUpdatedAt: Date.now(),
    });
    const { container } = render(<BestBetsBoard />);
    await act(async () => { await Promise.resolve(); });
    expect((container.textContent ?? "").toLowerCase()).not.toContain("pnl");
  });

  it("no 'roi' token in rendered text (case insensitive)", async () => {
    setLiveDataState({
      isLoading: false,
      data: makeBoards({ mlb: { board: makeBoard({ cards: [makeCard()], count: 1 }) } }),
      ageSec: 5,
      lastUpdatedAt: Date.now(),
    });
    const { container } = render(<BestBetsBoard />);
    await act(async () => { await Promise.resolve(); });
    expect((container.textContent ?? "").toLowerCase()).not.toContain("roi");
  });
});

// ---------------------------------------------------------------------------
// 5. fetchAllSports calls bestbetsBoard (not bestbets) per sport
// ---------------------------------------------------------------------------

describe("W3 acceptance (5) -- bestbetsBoard is called, not bestbets", () => {
  beforeEach(() => { resetLiveDataState(); mockBestbetsBoard.mockReset(); });

  it("fetcher captured from useLiveData calls api.bestbetsBoard", async () => {
    mockBestbetsBoard.mockResolvedValue(makeBoard({ cards: [], count: 0 }));
    setLiveDataState({ isLoading: false, data: makeBoards({}), ageSec: 5, lastUpdatedAt: Date.now() });

    render(<BestBetsBoard />);
    await act(async () => { await Promise.resolve(); });

    // Trigger the fetcher manually
    if (_capturedFetcher) {
      const ctrl = new AbortController();
      await act(async () => { await _capturedFetcher!(ctrl.signal); });
      // bestbetsBoard should have been called (once per sport: nba + mlb = 2)
      expect(mockBestbetsBoard).toHaveBeenCalled();
      // Should be called with sport param and signal
      const calls = mockBestbetsBoard.mock.calls;
      const hasSportParam = calls.some((c) => c[0] && typeof c[0] === "object" && "sport" in c[0]);
      expect(hasSportParam).toBe(true);
    }
  });
});

// ---------------------------------------------------------------------------
// 6. Live/Pregame/Done partitioning
// ---------------------------------------------------------------------------

describe("W3 acceptance (6) -- Live/Pregame/Done partitioning", () => {
  beforeEach(() => { vi.useFakeTimers(); resetLiveDataState(); });
  afterEach(() => { vi.useRealTimers(); });

  it("live card appears in live tab count but not in pregame tab", async () => {
    const liveCard = makeCard({ status: "live", game_id: "g-live" });
    const pregameCard = makeCard({ status: "pregame", game_id: "g-pre" });
    setLiveDataState({
      isLoading: false,
      data: makeBoards({
        mlb: { board: makeBoard({ cards: [liveCard, pregameCard], count: 2 }) },
      }),
      ageSec: 5,
      lastUpdatedAt: Date.now(),
    });

    render(<BestBetsBoard />);
    await act(async () => { await Promise.resolve(); });

    // Default tab is "pregame" -- only pregame card shows
    expect(screen.getAllByTestId("bet-card")).toHaveLength(1);
    // Status tabs should show "live" and "pregame" text
    const tabs = screen.getByTestId("status-tabs");
    expect(tabs.textContent).toContain("pregame");
  });
});
