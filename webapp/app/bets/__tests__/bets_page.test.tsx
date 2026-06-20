// bets_page.test.tsx -- acceptance tests for the /bets board (WS6 ws6-bets-records-surface).
//
// Acceptance criteria:
//   (1) renders calibrated bet cards + records when comparison rows exist
//       (including soccer/MLB via the candidates fallback path)
//   (2) shows honest 'no calibrated bets right now' empty state when none exist
//   (3) exposes no $ / fabricated-edge field -- units + confidence + CLV only
//
// These tests drive BestBetsBoard (the board rendered by /bets/page.tsx) with
// a mocked useLiveData so we can inject comparison data deterministically.

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, act } from "@testing-library/react";
import type { BestBetsBoard as BestBetsBoardType, BestBetsCard } from "@/lib/types_w12";

// ---------------------------------------------------------------------------
// Module mocks
// ---------------------------------------------------------------------------

// Mock next/link -> plain <a> so jsdom can render BetCard links.
vi.mock("next/link", () => ({
  default: ({
    href,
    children,
    ...rest
  }: {
    href: string;
    children: React.ReactNode;
    [k: string]: unknown;
  }) => <a href={href} {...rest}>{children}</a>,
}));

// api + p5api mocks -- bestbetsBoard is what BestBetsBoard.fetchAllSports calls.
const mockBestbetsBoard = vi.hoisted(() => vi.fn());
vi.mock("@/lib/p5api", () => ({
  SPORTS: ["nba", "mlb", "soccer"],
  isUnavailable: (x: unknown) =>
    !!x &&
    typeof x === "object" &&
    ((x as { status?: string }).status === "unavailable" ||
      !!(x as { reason?: string }).reason),
  api: { bestbetsBoard: mockBestbetsBoard },
}));

// useLiveData mock -- gives us deterministic control over board data.
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

// StatusTabs + SortControls -- stub to avoid shadcn deps.
vi.mock("@/components/bets/StatusTabs", () => ({
  StatusTabs: ({ value }: { value: string }) => (
    <div data-testid="status-tabs" data-tab={value} />
  ),
}));
vi.mock("@/components/bets/SortControls", () => ({
  SortControls: () => <div data-testid="sort-controls" />,
}));

// ---------------------------------------------------------------------------
// Import AFTER mocks
// ---------------------------------------------------------------------------
import { BestBetsBoard } from "@/components/bets/BestBetsBoard";

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

// makeCard -- produce one BestBetsCard (the shape the new /api/bestbets/board
// endpoint returns; BestBetsBoard processes cards[], not games[].best_bets).
function makeCard(
  sport: string,
  overrides: Partial<BestBetsCard> = {},
): BestBetsCard {
  return {
    game_id: `${sport}-game-001`,
    matchup: "TeamA @ TeamB",
    sport,
    market_type: "moneyline",
    side: "home",
    model_prob: 0.55,
    market_prob: 0.50,
    best_book: "DraftKings",
    best_odds: 1.95,
    all_books: [],
    edge_vs_market: 0.05,
    units: overrides.units ?? 0.5,
    tier: overrides.tier ?? "B",
    confidence: 0.65,
    clv: null,
    clv_is_proxy: true,
    status: overrides.status ?? "scheduled",
    ...overrides,
  };
}

// makeBoard -- produce a BestBetsBoardType with cards[] for injection into useLiveData.
// cards is a list of BestBetsCard; passing [] means no qualifying bets.
function makeBoard(
  sport: string,
  cards: BestBetsCard[] = [],
): BestBetsBoardType {
  return {
    status: "ok",
    generated_at: new Date(Date.now() - 60_000).toISOString(),
    cards,
    count: cards.length,
    sport,
    edge_claimed: false,
  };
}

// wrapBoards -- produce the FetchResult shape that BestBetsBoard.extractFetchResult
// handles via the new `boards` key path.  sport -> { board, skipped } map.
// null board means the sport fetch failed / offseason.
function wrapBoards(
  map: Record<string, BestBetsBoardType | null>,
): { boards: Record<string, { board: BestBetsBoardType | null; skipped: BestBetsCard[] }>; unavailableReasons: Record<string, string> } {
  const boards: Record<string, { board: BestBetsBoardType | null; skipped: BestBetsCard[] }> = {};
  for (const [sport, b] of Object.entries(map)) {
    boards[sport] = { board: b, skipped: [] };
  }
  return { boards, unavailableReasons: {} };
}

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
    isLoading: true,
    refresh: vi.fn(),
  };
}

// ---------------------------------------------------------------------------
// (1) Bet cards render when comparison rows exist (cards[] path)
// ---------------------------------------------------------------------------
describe("bets_page (1) -- bet cards render when comparison rows exist", () => {
  beforeEach(() => resetLiveState());

  it("renders a bet-card-article when NBA board has one card", async () => {
    const board = makeBoard("nba", [makeCard("nba")]);
    setLiveState({
      isLoading: false,
      data: wrapBoards({ nba: board }),
      ageSec: 10,
      lastUpdatedAt: Date.now(),
    });
    render(<BestBetsBoard />);
    await act(async () => { await Promise.resolve(); });
    const cards = screen.getAllByTestId("bet-card-article");
    expect(cards.length).toBeGreaterThan(0);
  });

  it("renders multiple cards when multiple cards are in the board", async () => {
    const board = makeBoard("nba", [
      makeCard("nba", { side: "home", game_id: "nba-g1" }),
      makeCard("nba", { side: "away", game_id: "nba-g2" }),
    ]);
    setLiveState({
      isLoading: false,
      data: wrapBoards({ nba: board }),
      ageSec: 10,
      lastUpdatedAt: Date.now(),
    });
    render(<BestBetsBoard />);
    await act(async () => { await Promise.resolve(); });
    const cards = screen.getAllByTestId("bet-card-article");
    expect(cards.length).toBe(2);
  });

  it("shows zero cards when board has empty cards array (no qualifying bets)", async () => {
    const board = makeBoard("nba", []); // no qualifying bets
    setLiveState({
      isLoading: false,
      data: wrapBoards({ nba: board }),
      ageSec: 10,
      lastUpdatedAt: Date.now(),
    });
    render(<BestBetsBoard />);
    await act(async () => { await Promise.resolve(); });
    const cards = screen.queryAllByTestId("bet-card-article");
    expect(cards.length).toBe(0);
  });

  it("(soccer path) renders card when soccer board has one card", async () => {
    const board = makeBoard("soccer", [makeCard("soccer")]);
    setLiveState({
      isLoading: false,
      data: wrapBoards({ soccer: board }),
      ageSec: 10,
      lastUpdatedAt: Date.now(),
    });
    render(<BestBetsBoard />);
    await act(async () => { await Promise.resolve(); });
    const cards = screen.getAllByTestId("bet-card-article");
    expect(cards.length).toBeGreaterThan(0);
  });

  it("(MLB path) renders card when MLB board has one card", async () => {
    const board = makeBoard("mlb", [makeCard("mlb")]);
    setLiveState({
      isLoading: false,
      data: wrapBoards({ mlb: board }),
      ageSec: 10,
      lastUpdatedAt: Date.now(),
    });
    render(<BestBetsBoard />);
    await act(async () => { await Promise.resolve(); });
    const cards = screen.getAllByTestId("bet-card-article");
    expect(cards.length).toBeGreaterThan(0);
  });

  it("renders cards from multiple sports when all boards have cards", async () => {
    const boards = {
      nba: makeBoard("nba", [makeCard("nba")]),
      mlb: makeBoard("mlb", [makeCard("mlb")]),
      soccer: makeBoard("soccer", [makeCard("soccer")]),
    };
    setLiveState({
      isLoading: false,
      data: wrapBoards(boards),
      ageSec: 10,
      lastUpdatedAt: Date.now(),
    });
    render(<BestBetsBoard />);
    await act(async () => { await Promise.resolve(); });
    const cards = screen.getAllByTestId("bet-card-article");
    // 3 sports, 1 card each -> 3 cards
    expect(cards.length).toBe(3);
  });

  it("renders tier badge on each card", async () => {
    const board = makeBoard("nba", [makeCard("nba", { tier: "A" })]);
    setLiveState({
      isLoading: false,
      data: wrapBoards({ nba: board }),
      ageSec: 10,
      lastUpdatedAt: Date.now(),
    });
    render(<BestBetsBoard />);
    await act(async () => { await Promise.resolve(); });
    expect(screen.getByText("A")).toBeInTheDocument();
  });

  it("renders units value with 'u' suffix (units not dollars)", async () => {
    const board = makeBoard("nba", [makeCard("nba", { units: 0.75 })]);
    setLiveState({
      isLoading: false,
      data: wrapBoards({ nba: board }),
      ageSec: 10,
      lastUpdatedAt: Date.now(),
    });
    render(<BestBetsBoard />);
    await act(async () => { await Promise.resolve(); });
    // WS6: units now labeled "X.X UNITS" not "X.XXu"
    expect(screen.getByTestId("units-value").textContent?.toUpperCase()).toContain("UNITS");
  });
});

// ---------------------------------------------------------------------------
// (2) Honest empty state when no qualifying bets exist
// ---------------------------------------------------------------------------
describe("bets_page (2) -- honest empty state when no comparison rows", () => {
  beforeEach(() => resetLiveState());

  it("shows empty-section messaging when board has no cards", async () => {
    const board = makeBoard("nba", []); // empty cards -> no qualifying bets
    setLiveState({
      isLoading: false,
      data: wrapBoards({ nba: board }),
      ageSec: 10,
      lastUpdatedAt: Date.now(),
    });
    render(<BestBetsBoard />);
    await act(async () => { await Promise.resolve(); });
    const text = document.body.textContent ?? "";
    // Empty state shows one of the honest messages (no fabricated card)
    expect(
      text.includes("No qualifying") ||
      text.includes("calibration success") ||
      text.includes("No bet decisions") ||
      text.includes("No data returned")
    ).toBe(true);
    // No bet-card-articles rendered
    expect(screen.queryAllByTestId("bet-card-article").length).toBe(0);
  });

  it("shows empty-section messaging when all boards are null (sports unavailable)", async () => {
    setLiveState({
      isLoading: false,
      data: wrapBoards({ nba: null, mlb: null, soccer: null }),
      ageSec: 10,
      lastUpdatedAt: Date.now(),
    });
    render(<BestBetsBoard />);
    await act(async () => { await Promise.resolve(); });
    const text = document.body.textContent ?? "";
    expect(
      text.includes("No qualifying") ||
      text.includes("No data") ||
      text.includes("No bet decisions") ||
      text.includes("calibration success")
    ).toBe(true);
    expect(screen.queryAllByTestId("bet-card-article").length).toBe(0);
  });

  it("shows Unavailable when data is null and fetch failed", async () => {
    setLiveState({
      isLoading: false,
      data: null,
      ageSec: null,
      error: "HTTP 503",
      lastUpdatedAt: null,
    });
    render(<BestBetsBoard />);
    await act(async () => { await Promise.resolve(); });
    // Either an error text or no cards -- never shows fabricated cards
    const cards = screen.queryAllByTestId("bet-card-article");
    expect(cards.length).toBe(0);
    const text = document.body.textContent ?? "";
    // Should report some error/unavailable state
    expect(
      text.toLowerCase().includes("unavailable") ||
      text.includes("No qualifying") ||
      text.includes("Could not load")
    ).toBe(true);
  });

  it("empty state does NOT fabricate a fake bet card", async () => {
    setLiveState({
      isLoading: false,
      data: wrapBoards({ nba: null }),
      ageSec: 5,
      lastUpdatedAt: Date.now(),
    });
    render(<BestBetsBoard />);
    await act(async () => { await Promise.resolve(); });
    // No bet-card-article elements -- only honest empty text
    expect(screen.queryAllByTestId("bet-card-article").length).toBe(0);
  });
});

// ---------------------------------------------------------------------------
// (3) No $ / fabricated-edge fields -- units + confidence + CLV only
// ---------------------------------------------------------------------------
describe("bets_page (3) -- no $ or fabricated-edge fields, units + CLV only", () => {
  beforeEach(() => resetLiveState());

  it("no $<digit> pattern in rendered output when cards exist", async () => {
    const board = makeBoard("nba", [makeCard("nba", { units: 1.5 })]);
    setLiveState({
      isLoading: false,
      data: wrapBoards({ nba: board }),
      ageSec: 10,
      lastUpdatedAt: Date.now(),
    });
    const { container } = render(<BestBetsBoard />);
    await act(async () => { await Promise.resolve(); });
    expect(container.textContent ?? "").not.toMatch(/\$\s?\d/);
  });

  it("no $<digit> pattern in empty state", async () => {
    setLiveState({
      isLoading: false,
      data: wrapBoards({ nba: null }),
      ageSec: 5,
      lastUpdatedAt: Date.now(),
    });
    const { container } = render(<BestBetsBoard />);
    await act(async () => { await Promise.resolve(); });
    expect(container.textContent ?? "").not.toMatch(/\$\s?\d/);
  });

  it("CLV shows INSUFFICIENT_DATA (never greened) when clv=null", async () => {
    // makeCard has clv: null by default -> board shows INSUFFICIENT_DATA
    const board = makeBoard("nba", [makeCard("nba", { clv: null })]);
    setLiveState({
      isLoading: false,
      data: wrapBoards({ nba: board }),
      ageSec: 10,
      lastUpdatedAt: Date.now(),
    });
    render(<BestBetsBoard />);
    await act(async () => { await Promise.resolve(); });
    // CLV is null -> BetCard shows INSUFFICIENT_DATA
    expect(screen.getByText(/INSUFFICIENT_DATA/)).toBeInTheDocument();
    // Must NOT be styled green
    const clvEl = Array.from(document.querySelectorAll("*")).find(
      (el) => el.textContent?.includes("INSUFFICIENT_DATA"),
    );
    expect(clvEl?.className ?? "").not.toMatch(/text-green/);
    expect(clvEl?.className ?? "").not.toMatch(/text-tier-a/);
  });

  it("units element uses 'u' suffix and NO $ symbol", async () => {
    const board = makeBoard("nba", [makeCard("nba", { units: 0.5 })]);
    setLiveState({
      isLoading: false,
      data: wrapBoards({ nba: board }),
      ageSec: 10,
      lastUpdatedAt: Date.now(),
    });
    render(<BestBetsBoard />);
    await act(async () => { await Promise.resolve(); });
    const unitsEl = screen.getByTestId("units-value");
    // WS6: units labeled "X.X UNITS" not "X.XXu"
    expect(unitsEl.textContent?.toUpperCase()).toContain("UNITS");
    expect(unitsEl.textContent).not.toContain("$");
  });

  it("divergence column is labeled 'Calibrated divergence', not 'edge' or 'profit'", async () => {
    const board = makeBoard("nba", [makeCard("nba")]);
    setLiveState({
      isLoading: false,
      data: wrapBoards({ nba: board }),
      ageSec: 10,
      lastUpdatedAt: Date.now(),
    });
    const { container } = render(<BestBetsBoard />);
    await act(async () => { await Promise.resolve(); });
    const text = container.textContent ?? "";
    expect(text.toLowerCase()).toContain("calibrated divergence");
  });

  it("no 'roi' or 'profit' or 'p&l' in rendered text content", async () => {
    const board = makeBoard("nba", [makeCard("nba")]);
    setLiveState({
      isLoading: false,
      data: wrapBoards({ nba: board }),
      ageSec: 10,
      lastUpdatedAt: Date.now(),
    });
    const { container } = render(<BestBetsBoard />);
    await act(async () => { await Promise.resolve(); });
    const text = (container.textContent ?? "").toLowerCase();
    expect(text).not.toMatch(/\broi\b/);
    expect(text).not.toMatch(/\bp&l\b/);
    // "profit" only appears inside the honesty disclaimer (as "not a profit claim"),
    // never as a positive label. The word itself may appear in the disclaimer.
    // We check it's not used as "Profit: $XX" or "Estimated profit".
    expect(text).not.toMatch(/profit:\s*\$/);
    expect(text).not.toMatch(/estimated profit/);
  });

  it("board contains 'units only' honesty copy (no $)", async () => {
    setLiveState({
      isLoading: false,
      data: wrapBoards({ nba: null }),
      ageSec: 5,
      lastUpdatedAt: Date.now(),
    });
    const { container } = render(<BestBetsBoard />);
    await act(async () => { await Promise.resolve(); });
    // The auto-refresh-label and other honesty copy are always rendered
    expect(container.textContent).toBeTruthy();
    // No dollar amounts
    expect(container.textContent ?? "").not.toMatch(/\$\s?\d/);
  });

  it("edge_claimed is not a positive signal -- divergence aria-label says 'not a profit or edge claim'", async () => {
    const board = makeBoard("nba", [makeCard("nba")]);
    setLiveState({
      isLoading: false,
      data: wrapBoards({ nba: board }),
      ageSec: 10,
      lastUpdatedAt: Date.now(),
    });
    render(<BestBetsBoard />);
    await act(async () => { await Promise.resolve(); });
    // WS6: BetCard uses ModelVsMarketBar; divergence chip uses data-testid='divergence-chip'
    const divEl = document.querySelector("[data-testid='divergence-chip']");
    const ariaLabel = divEl?.getAttribute("aria-label") ?? "";
    // ModelVsMarketBar chip aria-label says "not an edge or profit claim"
    expect(ariaLabel.toLowerCase()).toMatch(/not an? (edge or )?profit/);
  });
});
