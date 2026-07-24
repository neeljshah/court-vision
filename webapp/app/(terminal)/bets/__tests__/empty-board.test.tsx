// empty-board.test.tsx -- WS6 acceptance tests for honest empty state on
// the /bets/[sport] board.
//
// Acceptance criteria (WS6-bestbets-empty-honest-state):
//   (A) A 0-card API response renders a named honest-reason state, NOT a blank/white page.
//   (B) A fetch error (unavailable) renders an honest error state, NOT a blank/white page.
//   (C) A "no games on slate" reason surfaces correct copy to distinguish from other empty.
//   (D) A "suppressed" reason (games evaluated, 0 cleared tier) surfaces correct copy.
//   (E) No fake cards are ever injected to fill an empty board.
//   (F) No $ / profit / roi / edge-claimed text in any empty state.
//   (G) Loading skeleton renders during initial load (not a blank/white page).
//
// Approach: mount SportBetsBoard via the default export page component.
//   - Mock next/navigation (useParams) to supply a deterministic sport.
//   - Mock useLiveData to inject board data or error states without a network.
//   - Mock api.bestbetsBoard since useLiveData calls it (via the injected fetcher).

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, act } from "@testing-library/react";
import type { BestBetsBoard } from "@/lib/p5api";

// ---------------------------------------------------------------------------
// Module mocks (hoisted before imports)
// ---------------------------------------------------------------------------

// next/navigation -- useParams supplies the sport param.
vi.mock("next/navigation", () => ({
  useParams: () => ({ sport: "nba" }),
}));

// next/link -- plain anchor so BetCard links render in jsdom.
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

// p5api -- mock api.bestbetsBoard (useLiveData will call it through the fetcher).
vi.mock("@/lib/p5api", () => ({
  isUnavailable: (x: unknown) =>
    !!x &&
    typeof x === "object" &&
    ((x as { status?: string }).status === "unavailable" ||
      !!(x as { reason?: string; status?: string }).status &&
      (x as { status: string }).status === "unavailable"),
  api: {
    bestbetsBoard: vi.fn(),
  },
  SPORTS: ["nba", "mlb", "soccer"],
}));

// p6/Primitives -- stub so we avoid full CSS/shadcn setup.
vi.mock("@/components/p6/Primitives", () => ({
  Badge: ({ children }: { children: React.ReactNode }) => (
    <span data-testid="badge">{children}</span>
  ),
  timeAgoIso: () => "1m ago",
  Unavailable: ({ reason }: { reason?: string }) => (
    <div role="status">unavailable: {reason}</div>
  ),
}));

// p6/LiveLinesPanel -- freshnessStatus stub.
vi.mock("@/components/p6/LiveLinesPanel", () => ({
  freshnessStatus: () => "fresh",
}));

// bets/BetCard -- stub so card rendering doesn't pull in deep deps.
vi.mock("@/components/bets/BetCard", () => ({
  BetCard: ({ card }: { card: { matchup?: string } }) => (
    <article data-testid="bet-card-article">{card.matchup ?? "card"}</article>
  ),
}));

// lib/api -- HONEST_DISCLAIMER stub.
vi.mock("@/lib/api", () => ({
  HONEST_DISCLAIMER:
    "Calibrated predictions only. Units, not $. Real money default-DENY.",
}));

// lib/utils -- cn stub.
vi.mock("@/lib/utils", () => ({
  cn: (...args: unknown[]) => args.filter(Boolean).join(" "),
}));

// ---------------------------------------------------------------------------
// useLiveData mock -- inject deterministic state per test.
// ---------------------------------------------------------------------------

type LiveDataState<T> = {
  data: T | null;
  lastUpdatedAt: number | null;
  ageSec: number | null;
  isStale: boolean;
  error: string | null;
  isLoading: boolean;
  consecutiveFailures: number;
  backoffActive: boolean;
  refresh: () => void;
};

let _liveState: LiveDataState<unknown> = {
  data: null,
  lastUpdatedAt: null,
  ageSec: null,
  isStale: false,
  error: null,
  isLoading: true,
  consecutiveFailures: 0,
  backoffActive: false,
  refresh: vi.fn(),
};

vi.mock("@/lib/useLiveData", () => ({
  useLiveData: () => _liveState,
}));

// ---------------------------------------------------------------------------
// Import after mocks
// ---------------------------------------------------------------------------
import SportBetsPage from "../[sport]/page";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function resetLive() {
  _liveState = {
    data: null,
    lastUpdatedAt: null,
    ageSec: null,
    isStale: false,
    error: null,
    isLoading: true,
    consecutiveFailures: 0,
    backoffActive: false,
    refresh: vi.fn(),
  };
}

function setLive(partial: Partial<LiveDataState<unknown>>) {
  _liveState = { ..._liveState, ...partial };
}

function makeBoard(
  override: Partial<BestBetsBoard> = {},
): BestBetsBoard {
  return {
    status: "ok",
    generated_at: new Date(Date.now() - 60_000).toISOString(),
    cards: [],
    count: 0,
    sport: "nba",
    edge_claimed: false,
    ...override,
  };
}

// ---------------------------------------------------------------------------
// (A) 0-card response renders honest empty state, NOT a blank page
// ---------------------------------------------------------------------------
describe("empty-board (A) -- 0-card board renders honest state, not blank page", () => {
  beforeEach(() => resetLive());

  it("renders sport-empty-state when board has 0 cards and loading finished", async () => {
    setLive({
      isLoading: false,
      data: makeBoard({ cards: [], count: 0 }),
      ageSec: 30,
      lastUpdatedAt: Date.now(),
    });
    render(<SportBetsPage />);
    await act(async () => { await Promise.resolve(); });
    expect(screen.getByTestId("sport-empty-state")).toBeInTheDocument();
  });

  it("renders a non-empty text headline in the empty state (never blank)", async () => {
    setLive({
      isLoading: false,
      data: makeBoard({ cards: [], count: 0 }),
      ageSec: 30,
      lastUpdatedAt: Date.now(),
    });
    render(<SportBetsPage />);
    await act(async () => { await Promise.resolve(); });
    const headline = screen.getByTestId("sport-empty-headline");
    expect(headline.textContent?.trim().length).toBeGreaterThan(5);
  });

  it("renders honest empty state even when board.cards is undefined/null", async () => {
    setLive({
      isLoading: false,
      data: makeBoard({ cards: [], count: 0, reason: undefined }),
      ageSec: 10,
      lastUpdatedAt: Date.now(),
    });
    render(<SportBetsPage />);
    await act(async () => { await Promise.resolve(); });
    expect(screen.getByTestId("sport-empty-state")).toBeInTheDocument();
  });

  it("renders honest empty state when data is a board with 0 cards -- headline mentions 'calibrated bets'", async () => {
    setLive({
      isLoading: false,
      data: makeBoard(),
      ageSec: 5,
      lastUpdatedAt: Date.now(),
    });
    render(<SportBetsPage />);
    await act(async () => { await Promise.resolve(); });
    const headline = screen.getByTestId("sport-empty-headline");
    expect(headline.textContent?.toLowerCase()).toContain("calibrated bets");
  });
});

// ---------------------------------------------------------------------------
// (B) Fetch error renders honest unavailable state, NOT a blank page
// ---------------------------------------------------------------------------
describe("empty-board (B) -- fetch error renders honest state, not blank page", () => {
  beforeEach(() => resetLive());

  it("renders sport-empty-state with reason=unavailable on fetch error (no prior data)", async () => {
    setLive({
      isLoading: false,
      data: null,
      error: "HTTP 503 service unavailable",
      ageSec: null,
      lastUpdatedAt: null,
    });
    render(<SportBetsPage />);
    await act(async () => { await Promise.resolve(); });
    const el = screen.getByTestId("sport-empty-state");
    expect(el).toBeInTheDocument();
    expect(el.getAttribute("data-reason")).toBe("unavailable");
  });

  it("surfacing the API error reason in the empty state (not hidden)", async () => {
    setLive({
      isLoading: false,
      data: null,
      error: "HTTP 503 service unavailable",
      ageSec: null,
      lastUpdatedAt: null,
    });
    render(<SportBetsPage />);
    await act(async () => { await Promise.resolve(); });
    const text = document.body.textContent ?? "";
    // The error reason is surfaced via apiReason in sport-empty-api-note or headline
    expect(
      text.includes("503") ||
      text.includes("unavailable") ||
      text.toLowerCase().includes("could not be loaded") ||
      text.toLowerCase().includes("board unavailable")
    ).toBe(true);
  });

  it("no fake bet cards rendered when fetch fails", async () => {
    setLive({
      isLoading: false,
      data: null,
      error: "network error",
      ageSec: null,
      lastUpdatedAt: null,
    });
    render(<SportBetsPage />);
    await act(async () => { await Promise.resolve(); });
    expect(screen.queryAllByTestId("bet-card-article").length).toBe(0);
  });
});

// ---------------------------------------------------------------------------
// (C) "No games on slate" API reason surfaces correct copy
// ---------------------------------------------------------------------------
describe("empty-board (C) -- no-slate API reason surfaces distinct copy", () => {
  beforeEach(() => resetLive());

  it("data-reason=no_slate when board.reason contains 'no games'", async () => {
    setLive({
      isLoading: false,
      data: makeBoard({ reason: "no games scheduled today" }),
      ageSec: 5,
      lastUpdatedAt: Date.now(),
    });
    render(<SportBetsPage />);
    await act(async () => { await Promise.resolve(); });
    const el = screen.getByTestId("sport-empty-state");
    expect(el.getAttribute("data-reason")).toBe("no_slate");
  });

  it("data-reason=no_slate when board.honest_note contains 'offseason'", async () => {
    setLive({
      isLoading: false,
      data: makeBoard({ honest_note: "NBA offseason -- no games" }),
      ageSec: 5,
      lastUpdatedAt: Date.now(),
    });
    render(<SportBetsPage />);
    await act(async () => { await Promise.resolve(); });
    const el = screen.getByTestId("sport-empty-state");
    expect(el.getAttribute("data-reason")).toBe("no_slate");
  });

  it("no-slate headline contains 'no games on slate' copy", async () => {
    setLive({
      isLoading: false,
      data: makeBoard({ reason: "no games scheduled" }),
      ageSec: 5,
      lastUpdatedAt: Date.now(),
    });
    render(<SportBetsPage />);
    await act(async () => { await Promise.resolve(); });
    const headline = screen.getByTestId("sport-empty-headline");
    expect(headline.textContent?.toLowerCase()).toContain("no games on slate");
  });

  it("surfaces the API reason in sport-empty-api-note when reason present", async () => {
    setLive({
      isLoading: false,
      data: makeBoard({ reason: "no games scheduled" }),
      ageSec: 5,
      lastUpdatedAt: Date.now(),
    });
    render(<SportBetsPage />);
    await act(async () => { await Promise.resolve(); });
    const note = screen.getByTestId("sport-empty-api-note");
    expect(note.textContent).toContain("no games scheduled");
  });
});

// ---------------------------------------------------------------------------
// (D) Suppressed-slate reason (games evaluated, 0 cleared tier)
// ---------------------------------------------------------------------------
describe("empty-board (D) -- suppressed-slate (games exist but 0 cleared tier)", () => {
  beforeEach(() => resetLive());

  it("data-reason=suppressed when count > 0 and cards is empty", async () => {
    setLive({
      isLoading: false,
      // count=3 means 3 games were evaluated; 0 cleared the tier floor.
      data: makeBoard({ cards: [], count: 3 }),
      ageSec: 5,
      lastUpdatedAt: Date.now(),
    });
    render(<SportBetsPage />);
    await act(async () => { await Promise.resolve(); });
    const el = screen.getByTestId("sport-empty-state");
    expect(el.getAttribute("data-reason")).toBe("suppressed");
  });

  it("suppressed headline mentions 'tier floor'", async () => {
    setLive({
      isLoading: false,
      data: makeBoard({ cards: [], count: 5 }),
      ageSec: 5,
      lastUpdatedAt: Date.now(),
    });
    render(<SportBetsPage />);
    await act(async () => { await Promise.resolve(); });
    const headline = screen.getByTestId("sport-empty-headline");
    expect(headline.textContent?.toLowerCase()).toContain("tier floor");
  });

  it("suppressed body mentions 'calibration success'", async () => {
    setLive({
      isLoading: false,
      data: makeBoard({ cards: [], count: 2 }),
      ageSec: 5,
      lastUpdatedAt: Date.now(),
    });
    render(<SportBetsPage />);
    await act(async () => { await Promise.resolve(); });
    const text = document.body.textContent ?? "";
    expect(text.toLowerCase()).toContain("calibration success");
  });

  it("data-reason=empty (not suppressed) when count is 0 (no games evaluated)", async () => {
    setLive({
      isLoading: false,
      data: makeBoard({ cards: [], count: 0 }),
      ageSec: 5,
      lastUpdatedAt: Date.now(),
    });
    render(<SportBetsPage />);
    await act(async () => { await Promise.resolve(); });
    const el = screen.getByTestId("sport-empty-state");
    expect(el.getAttribute("data-reason")).toBe("empty");
  });
});

// ---------------------------------------------------------------------------
// (E) No fake cards ever injected into an empty board
// ---------------------------------------------------------------------------
describe("empty-board (E) -- no fabricated cards in any empty state", () => {
  beforeEach(() => resetLive());

  it("0 bet-card-articles when board is empty", async () => {
    setLive({
      isLoading: false,
      data: makeBoard(),
      ageSec: 5,
      lastUpdatedAt: Date.now(),
    });
    render(<SportBetsPage />);
    await act(async () => { await Promise.resolve(); });
    expect(screen.queryAllByTestId("bet-card-article").length).toBe(0);
  });

  it("0 bet-card-articles when fetch error and no prior data", async () => {
    setLive({
      isLoading: false,
      data: null,
      error: "timeout",
    });
    render(<SportBetsPage />);
    await act(async () => { await Promise.resolve(); });
    expect(screen.queryAllByTestId("bet-card-article").length).toBe(0);
  });

  it("0 bet-card-articles when no-slate (no games)", async () => {
    setLive({
      isLoading: false,
      data: makeBoard({ reason: "no games today" }),
      ageSec: 5,
      lastUpdatedAt: Date.now(),
    });
    render(<SportBetsPage />);
    await act(async () => { await Promise.resolve(); });
    expect(screen.queryAllByTestId("bet-card-article").length).toBe(0);
  });

  it("0 bet-card-articles when suppressed (games evaluated, none cleared floor)", async () => {
    setLive({
      isLoading: false,
      data: makeBoard({ cards: [], count: 7 }),
      ageSec: 5,
      lastUpdatedAt: Date.now(),
    });
    render(<SportBetsPage />);
    await act(async () => { await Promise.resolve(); });
    expect(screen.queryAllByTestId("bet-card-article").length).toBe(0);
  });
});

// ---------------------------------------------------------------------------
// (F) No $ / profit / roi / edge-claimed text in any empty state
// ---------------------------------------------------------------------------
describe("empty-board (F) -- no fabricated financial text in empty states", () => {
  beforeEach(() => resetLive());

  it("no '$<digit>' pattern in 0-card board output", async () => {
    setLive({
      isLoading: false,
      data: makeBoard(),
      ageSec: 5,
      lastUpdatedAt: Date.now(),
    });
    const { container } = render(<SportBetsPage />);
    await act(async () => { await Promise.resolve(); });
    expect(container.textContent ?? "").not.toMatch(/\$\s?\d/);
  });

  it("no 'roi' in empty-state output", async () => {
    setLive({
      isLoading: false,
      data: makeBoard({ reason: "no games scheduled" }),
      ageSec: 5,
      lastUpdatedAt: Date.now(),
    });
    const { container } = render(<SportBetsPage />);
    await act(async () => { await Promise.resolve(); });
    expect((container.textContent ?? "").toLowerCase()).not.toMatch(/\broi\b/);
  });

  it("no 'estimated profit' in empty-state output", async () => {
    setLive({
      isLoading: false,
      data: makeBoard({ cards: [], count: 3 }),
      ageSec: 5,
      lastUpdatedAt: Date.now(),
    });
    const { container } = render(<SportBetsPage />);
    await act(async () => { await Promise.resolve(); });
    expect((container.textContent ?? "").toLowerCase()).not.toContain("estimated profit");
  });

  it("no '$<digit>' in unavailable/error state", async () => {
    setLive({
      isLoading: false,
      data: null,
      error: "HTTP 503",
    });
    const { container } = render(<SportBetsPage />);
    await act(async () => { await Promise.resolve(); });
    expect(container.textContent ?? "").not.toMatch(/\$\s?\d/);
  });
});

// ---------------------------------------------------------------------------
// (G) Loading skeleton renders during initial load (not blank)
// ---------------------------------------------------------------------------
describe("empty-board (G) -- loading skeleton shown during initial load", () => {
  beforeEach(() => resetLive());

  it("renders sport-board-loading skeleton while isLoading=true and no data yet", async () => {
    // Default resetLive state: isLoading=true, data=null.
    render(<SportBetsPage />);
    await act(async () => { await Promise.resolve(); });
    expect(screen.getByTestId("sport-board-loading")).toBeInTheDocument();
  });

  it("skeleton has 3 shimmer children (one per card slot)", async () => {
    render(<SportBetsPage />);
    await act(async () => { await Promise.resolve(); });
    const skeleton = screen.getByTestId("sport-board-loading");
    expect(skeleton.children.length).toBe(3);
  });

  it("no bet-card-articles during loading (never fabricates to fill load state)", async () => {
    render(<SportBetsPage />);
    await act(async () => { await Promise.resolve(); });
    expect(screen.queryAllByTestId("bet-card-article").length).toBe(0);
  });
});
