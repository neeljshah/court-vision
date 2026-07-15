import { describe, it, expect, vi, afterEach, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";

// Tests for W6 Best Bets board components.
//
// Scope: BetCard, StatusTabs, SortControls, BookShoppingRow, BestBetsBoard.
// BestBetsBoard honesty-critical logic is tested below with a mocked api.
//
// HONESTY RAIL asserted: no $ field in any rendered output; units shown;
// INSUFFICIENT_DATA shown when CLV is null; honest empty state present;
// stale-never-green: stale generated_at must NOT render a green badge;
// non-bet candidates are dropped (decision filter);
// empty/offseason state shown when no bets clear the floor.

// next/link -> plain anchor for jsdom rendering
vi.mock("next/link", () => ({
  default: ({
    href,
    children,
    ...rest
  }: {
    href: string;
    children: React.ReactNode;
    [key: string]: unknown;
  }) => (
    <a href={href} {...rest}>
      {children}
    </a>
  ),
}));

import { BetCard, type BetCardData } from "@/components/bets/BetCard";
import { StatusTabs, type BetStatus } from "@/components/bets/StatusTabs";
import { SortControls, type SortKey } from "@/components/bets/SortControls";
import {
  BookShoppingRow,
  type BookOddsEntry,
} from "@/components/bets/BookShoppingRow";

// ---------------------------------------------------------------------------
// Shared fixtures

function makeBetCard(overrides: Partial<BetCardData> = {}): BetCardData {
  return {
    game_id: "0022401234",
    sport: "nba",
    matchup: "NYK @ SAS",
    market_type: "moneyline",
    side: "home",
    model_prob: 0.54,
    market_prob: 0.48,
    best_book: "kalshi",
    best_odds: 1.85,
    all_books: [
      { book: "kalshi", odds: 1.85, is_best: true },
      { book: "polymarket", odds: 1.82, is_best: false },
    ],
    edge_vs_market: 0.06,
    units: 0.75,
    tier: "A",
    confidence: 0.72,
    clv: null,
    clv_is_proxy: true,
    status: "pregame",
    line: null,
    ...overrides,
  };
}

// ---------------------------------------------------------------------------
// BetCard tests

describe("BetCard", () => {
  it("renders the matchup and market type", () => {
    render(<BetCard card={makeBetCard()} />);
    // Multiple elements may contain matchup text (visible header + sr-only detail link);
    // use getAllByText to avoid the "multiple elements" error.
    expect(screen.getAllByText(/NYK @ SAS/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/moneyline/i).length).toBeGreaterThan(0);
  });

  it("shows tier badge with tier value", () => {
    render(<BetCard card={makeBetCard({ tier: "A" })} />);
    const tierEl = screen.getByText("A");
    expect(tierEl).toBeTruthy();
  });

  it("shows model_prob and market_prob as percentages", () => {
    render(<BetCard card={makeBetCard({ model_prob: 0.54, market_prob: 0.48 })} />);
    expect(screen.getByText("54.0%")).toBeTruthy();
    expect(screen.getByText("48.0%")).toBeTruthy();
  });

  it("divergence label has exactly one plus sign (no double-plus regression)", () => {
    // edge_vs_market=0.06 -> formatDivergence(0.06) -> '+6.0pp' (WS6: calibrated-divergence
    // pp framing, regression-locked by BetCard.test.tsx); must render '+6.0pp' not '++6.0pp'
    render(<BetCard card={makeBetCard({ edge_vs_market: 0.06 })} />);
    expect(screen.getByText("+6.0pp")).toBeTruthy();
    // Absence of double-plus is the regression lock
    expect(screen.queryByText("++6.0pp")).toBeNull();
  });

  it("negative divergence renders without a plus sign", () => {
    // edge_vs_market=-0.04 -> formatDivergence(-0.04) -> '-4.0pp'
    render(<BetCard card={makeBetCard({ edge_vs_market: -0.04 })} />);
    expect(screen.getByText("-4.0pp")).toBeTruthy();
  });

  it("shows units with explicit UNITS label and no dollar sign", () => {
    // WS6: explicit "UNITS" label replaces the old 'u' suffix (regression-locked
    // by BetCard.test.tsx "no 'u' suffix").
    const { container } = render(<BetCard card={makeBetCard({ units: 0.75 })} />);
    const unitsEl = container.querySelector("[data-testid='units-value']");
    // units.toFixed(1): 0.75 -> "0.8"
    expect(unitsEl?.textContent ?? "").toContain("0.8");
    expect((unitsEl?.textContent ?? "").toUpperCase()).toContain("UNITS");
    const txt = container.textContent ?? "";
    // No dollar value ($ followed by digits)
    expect(/\$\s*\d/.test(txt)).toBe(false);
    // No dollar P&L fields
    expect(/\bROI\b/.test(txt)).toBe(false);
    expect(/\bP&L\b|\bPnL\b/i.test(txt)).toBe(false);
  });

  it("shows INSUFFICIENT_DATA when CLV is null", () => {
    render(<BetCard card={makeBetCard({ clv: null, clv_is_proxy: true })} />);
    expect(screen.getByText(/INSUFFICIENT_DATA/i)).toBeTruthy();
  });

  it("shows CLV percentage when CLV is provided", () => {
    render(<BetCard card={makeBetCard({ clv: 0.03, clv_is_proxy: false })} />);
    // Should show CLV +3.0%
    expect(screen.getByText(/CLV \+3\.0%/i)).toBeTruthy();
  });

  it("shows LIVE status dot for live cards", () => {
    render(<BetCard card={makeBetCard({ status: "live" })} />);
    expect(screen.getByText(/LIVE/i)).toBeTruthy();
  });

  it("shows DONE status dot for done cards", () => {
    render(<BetCard card={makeBetCard({ status: "done" })} />);
    expect(screen.getByText(/DONE/i)).toBeTruthy();
  });

  it("links to the correct bets detail route", () => {
    render(<BetCard card={makeBetCard({ sport: "nba", game_id: "0022401234" })} />);
    const link = screen.getByRole("link");
    expect(link.getAttribute("href")).toContain("/bets/nba/0022401234");
  });

  it("shows the best book name", () => {
    render(<BetCard card={makeBetCard({ best_book: "kalshi" })} />);
    // best book shown in the card
    const bookEls = screen.getAllByText(/kalshi/i);
    expect(bookEls.length).toBeGreaterThan(0);
  });

  it("shows units-only badge (no dollar text)", () => {
    // The honesty footnote inside ModelVsMarketBar also matches /units only/i,
    // so assert at least one match rather than a single unique element.
    render(<BetCard card={makeBetCard()} />);
    expect(screen.getAllByText(/units only/i).length).toBeGreaterThan(0);
  });

  // ---------------------------------------------------------------------------
  // Honesty: confidence -> signal proxy (ws1-betcard-confidence-honesty)

  it("labels the derived value as 'signal' not bare 'confidence'", () => {
    const { container } = render(<BetCard card={makeBetCard({ confidence: 0.72 })} />);
    // The accessible element with aria-label must exist and reference 'signal strength proxy'
    const signalEl = container.querySelector("[aria-label*='signal strength proxy']");
    expect(signalEl).not.toBeNull();
    // The footer must NOT use bare 'confidence' as a standalone label for the value --
    // check that the element text starts with 'signal', not 'confidence'.
    const elText = signalEl?.textContent ?? "";
    expect(/signal/i.test(elText)).toBe(true);
  });

  it("accessible title conveys derived-proxy framing (EV magnitude, not fabricated)", () => {
    const { container } = render(<BetCard card={makeBetCard({ confidence: 0.72 })} />);
    const signalEl = container.querySelector("[title*='EV magnitude']");
    expect(signalEl).not.toBeNull();
    const titleAttr = signalEl?.getAttribute("title") ?? "";
    // Title must mention 'proxy' (honest framing)
    expect(/proxy/i.test(titleAttr)).toBe(true);
    // Title must mention 'EV magnitude' (the actual derivation)
    expect(/EV magnitude/i.test(titleAttr)).toBe(true);
    // Title must explicitly disclaim being a real confidence/profit figure
    // ("Not a ..." framing ensures the user is never misled)
    expect(/Not a/i.test(titleAttr)).toBe(true);
  });

  it("aria-label on signal element describes it as a derived proxy, not profit", () => {
    const { container } = render(<BetCard card={makeBetCard({ confidence: 0.72 })} />);
    const el = container.querySelector("[aria-label*='derived from EV magnitude']");
    expect(el).not.toBeNull();
    const aria = el?.getAttribute("aria-label") ?? "";
    expect(/not a profit/i.test(aria)).toBe(true);
  });

  it("signal percentage value matches confidence field (72 -> '72%')", () => {
    render(<BetCard card={makeBetCard({ confidence: 0.72 })} />);
    // The footer should show '72%' adjacent to 'signal'
    expect(screen.getByText("72%")).toBeTruthy();
  });

  it("renders no dollar P&L amount (no $ followed by digits) on the card", () => {
    const { container } = render(<BetCard card={makeBetCard()} />);
    const txt = container.textContent ?? "";
    // The 'units only -- no $' badge itself contains '$' so we check for $ followed
    // by a digit (a P&L amount), not the literal phrase 'no $'.
    expect(/\$\s*\d/.test(txt)).toBe(false);
  });

  it("card still links to /bets/[sport]/[gameId] after honesty update", () => {
    render(
      <BetCard card={makeBetCard({ sport: "nba", game_id: "0022401234" })} />,
    );
    const link = screen.getByRole("link");
    expect(link.getAttribute("href")).toContain("/bets/nba/0022401234");
  });
});

// ---------------------------------------------------------------------------
// StatusTabs tests

describe("StatusTabs", () => {
  it("renders three tabs: Live, Pregame, Done", () => {
    const onChange = vi.fn();
    render(<StatusTabs value="pregame" onChange={onChange} />);
    expect(screen.getByText(/Live/i)).toBeTruthy();
    expect(screen.getByText(/Pregame/i)).toBeTruthy();
    expect(screen.getByText(/Done/i)).toBeTruthy();
  });

  it("marks the active tab as selected", () => {
    render(<StatusTabs value="live" onChange={() => {}} />);
    const liveBtn = screen.getByRole("tab", { name: /Live/i });
    expect(liveBtn.getAttribute("aria-selected")).toBe("true");
  });

  it("fires onChange with the clicked tab key", () => {
    const onChange = vi.fn();
    render(<StatusTabs value="pregame" onChange={onChange} />);
    fireEvent.click(screen.getByRole("tab", { name: /Done/i }));
    expect(onChange).toHaveBeenCalledWith("done");
  });

  it("shows count badge when count > 0", () => {
    render(
      <StatusTabs
        value="pregame"
        onChange={() => {}}
        counts={{ live: 2, pregame: 5, done: 0 }}
      />,
    );
    expect(screen.getByText("2")).toBeTruthy();
    expect(screen.getByText("5")).toBeTruthy();
    // done has count 0, badge should not appear
    const doneTab = screen.getByRole("tab", { name: /Done/i });
    // "0" should not be in doneTab
    expect(doneTab.textContent).not.toContain("0");
  });
});

// ---------------------------------------------------------------------------
// SortControls tests

describe("SortControls", () => {
  it("renders Confidence and Tier sort buttons", () => {
    render(<SortControls value="confidence" onChange={() => {}} />);
    expect(screen.getByText(/Confidence/i)).toBeTruthy();
    expect(screen.getByText(/Tier/i)).toBeTruthy();
  });

  it("marks the active sort as pressed", () => {
    render(<SortControls value="tier" onChange={() => {}} />);
    const tierBtn = screen.getByRole("button", { name: /Tier/i });
    expect(tierBtn.getAttribute("aria-pressed")).toBe("true");
  });

  it("fires onChange with the clicked sort key", () => {
    const onChange = vi.fn();
    render(<SortControls value="confidence" onChange={onChange} />);
    fireEvent.click(screen.getByRole("button", { name: /Tier/i }));
    expect(onChange).toHaveBeenCalledWith("tier");
  });

  it("does not render any edge or profit framing", () => {
    const { container } = render(
      <SortControls value="confidence" onChange={() => {}} />,
    );
    const txt = container.textContent ?? "";
    expect(/edge/i.test(txt)).toBe(false);
    expect(/\bROI\b/.test(txt)).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// BookShoppingRow tests

describe("BookShoppingRow", () => {
  const books: BookOddsEntry[] = [
    { book: "kalshi", odds: 1.85, is_best: true },
    { book: "polymarket", odds: 1.82, is_best: false },
  ];

  it("renders a pill for each book", () => {
    render(<BookShoppingRow books={books} />);
    expect(screen.getByText(/kalshi/i)).toBeTruthy();
    expect(screen.getByText(/polymarket/i)).toBeTruthy();
  });

  it("shows honest UNAVAILABLE when no books", () => {
    render(<BookShoppingRow books={[]} />);
    expect(screen.getByText(/unavailable/i)).toBeTruthy();
  });

  it("converts decimal odds to American format (>2 -> positive)", () => {
    render(<BookShoppingRow books={[{ book: "test", odds: 2.5, is_best: false }]} />);
    // 2.5 decimal -> +150 American
    expect(screen.getByText("+150")).toBeTruthy();
  });

  it("renders no dollar amounts", () => {
    const { container } = render(<BookShoppingRow books={books} />);
    const txt = container.textContent ?? "";
    expect(/\$\s*\d/.test(txt)).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// BestBetsBoard tests -- honesty-critical board logic
//
// BestBetsBoard calls api.bestbetsBoard({sport}, signal) for each sport in
// SPORTS (the W-wave board endpoint -- flat cards[], not the legacy
// games[]/best_bets[] envelope). We mock @/lib/p5api.api.bestbetsBoard to
// return only for "nba" and Unavailable for the rest, keeping assertions clean.

import { BestBetsBoard } from "@/components/bets/BestBetsBoard";
import type { Unavailable, BestBetsBoard as BestBetsBoardType, BestBetsCard } from "@/lib/p5api";

const BOARD_HOUR_MS = 60 * 60_000;

function makeCard(overrides: Partial<BestBetsCard> = {}): BestBetsCard {
  return {
    game_id: "0022401234",
    matchup: "NYK @ SAS",
    sport: "nba",
    market_type: "moneyline",
    side: "home",
    model_prob: 0.55,
    market_prob: 0.50,
    best_book: "kalshi",
    best_odds: 1.90,
    all_books: [],
    edge_vs_market: 0.05,
    units: 0.5,
    tier: "B",
    confidence: 0.6,
    clv: null,
    clv_is_proxy: true,
    status: "pregame",
    ...overrides,
  };
}

function makeBoardEnvelope(
  generated_at: string,
  cards: BestBetsCard[] = [],
): BestBetsBoardType {
  return {
    status: "ok",
    generated_at,
    cards,
    count: cards.length,
    sport: "nba",
    honest_note: "calibration only",
    edge_claimed: false,
  };
}

// Unavailable sentinel that isUnavailable() recognises
const UNAVAILABLE = { status: "unavailable", reason: "offline" } satisfies Unavailable;

describe("BestBetsBoard -- honesty-critical board logic", () => {
  let originalBestbetsBoard: typeof import("@/lib/p5api").api.bestbetsBoard;

  beforeEach(async () => {
    const mod = await import("@/lib/p5api");
    originalBestbetsBoard = mod.api.bestbetsBoard;
  });

  afterEach(async () => {
    const mod = await import("@/lib/p5api");
    mod.api.bestbetsBoard = originalBestbetsBoard;
    vi.restoreAllMocks();
  });

  it("drops settled candidates -- only non-post/final cards render", async () => {
    const recentTs = new Date(Date.now() - 5_000).toISOString();
    const envelope = makeBoardEnvelope(recentTs, [
      makeCard({ market_type: "moneyline_kept", side: "home", status: "pregame" }),
      // status=post -- excluded entirely by fetchAllSports (game already over)
      makeCard({ game_id: "g2", market_type: "total_dropped", side: "over", status: "post" }),
    ]);
    const mod = await import("@/lib/p5api");
    mod.api.bestbetsBoard = vi.fn(async (params?: { sport?: string }) =>
      params?.sport === "nba" ? envelope : UNAVAILABLE,
    );

    render(<BestBetsBoard />);

    await waitFor(() => {
      expect(screen.queryAllByText(/moneyline_kept/i).length).toBeGreaterThan(0);
    });
    // The settled market_type must NOT appear anywhere in the rendered output
    expect(screen.queryAllByText(/total_dropped/i)).toHaveLength(0);
  });

  it("shows aging badge (amber, not green) when generated_at is hours old", async () => {
    const staleTs = new Date(Date.now() - 3 * BOARD_HOUR_MS).toISOString();
    const envelope = makeBoardEnvelope(staleTs, [
      makeCard({ market_type: "moneyline", side: "home" }),
    ]);
    const mod = await import("@/lib/p5api");
    mod.api.bestbetsBoard = vi.fn(async (params?: { sport?: string }) =>
      params?.sport === "nba" ? envelope : UNAVAILABLE,
    );

    render(<BestBetsBoard />);

    // Wait for the AgeBadge to resolve to "aging" (stale-never-green rail)
    await waitFor(() => {
      expect(screen.queryAllByText(/aging/i).length).toBeGreaterThan(0);
    });

    // The aging badge element (or its closest parent with a class) must NOT carry
    // green (tier-a) class -- stale-never-green rail
    const agingEls = screen.queryAllByText(/aging/i);
    for (const el of agingEls) {
      const cls = el.closest("[class]")?.className ?? el.className;
      expect(cls).not.toContain("tier-a");
    }
    // The badge wrapper must carry amber styling
    const agingBadge = agingEls[0].closest(".inline-flex");
    expect(agingBadge?.className ?? "").toContain("amber");
  });

  it("shows honest empty state when all sports return Unavailable", async () => {
    const mod = await import("@/lib/p5api");
    mod.api.bestbetsBoard = vi.fn(async () => UNAVAILABLE);

    const { container } = render(<BestBetsBoard />);

    await waitFor(() => {
      const txt = container.textContent ?? "";
      const hasHonestMsg =
        /No bet decisions cleared the tier floor/i.test(txt) ||
        /predict service may be offline/i.test(txt) ||
        /No data returned/i.test(txt) ||
        /no tradable cards/i.test(txt) ||
        /none right now/i.test(txt);
      expect(hasHonestMsg).toBe(true);
    });
  });

  // -----------------------------------------------------------------------
  // ws2-board-refresh-affordance acceptance tests
  // -----------------------------------------------------------------------

  it("renders a manual refresh control with an accessible label", async () => {
    const recentTs = new Date(Date.now() - 5_000).toISOString();
    const envelope = makeBoardEnvelope(recentTs, [makeCard()]);
    const mod = await import("@/lib/p5api");
    mod.api.bestbetsBoard = vi.fn(async (params?: { sport?: string }) =>
      params?.sport === "nba" ? envelope : UNAVAILABLE,
    );

    render(<BestBetsBoard />);

    // The refresh button must exist with an accessible label
    await waitFor(() => {
      const btn = screen.getByRole("button", { name: /refresh best bets now/i });
      expect(btn).toBeTruthy();
    });
  });

  it("clicking refresh now re-invokes the fetch (load called again)", async () => {
    const recentTs = new Date(Date.now() - 5_000).toISOString();
    const envelope = makeBoardEnvelope(recentTs, [makeCard()]);
    const mod = await import("@/lib/p5api");
    const mockFn = vi.fn(async (params?: { sport?: string }) =>
      params?.sport === "nba" ? envelope : UNAVAILABLE,
    );
    mod.api.bestbetsBoard = mockFn;

    render(<BestBetsBoard />);

    // Wait for initial load to settle and button to be enabled
    await waitFor(() => {
      const btn = screen.getByRole("button", { name: /refresh best bets now/i });
      expect(btn).toBeTruthy();
      expect((btn as HTMLButtonElement).disabled).toBe(false);
    });

    const callsBefore = mockFn.mock.calls.length;

    // Click the manual refresh button
    fireEvent.click(screen.getByRole("button", { name: /refresh best bets now/i }));

    // Fetch must be re-invoked (each sport triggers a call)
    await waitFor(() => {
      expect(mockFn.mock.calls.length).toBeGreaterThan(callsBefore);
    });
  });

  it("auto-refresh affordance label is present in the rendered board", async () => {
    const recentTs = new Date(Date.now() - 5_000).toISOString();
    const envelope = makeBoardEnvelope(recentTs, []);
    const mod = await import("@/lib/p5api");
    mod.api.bestbetsBoard = vi.fn(async (params?: { sport?: string }) =>
      params?.sport === "nba" ? envelope : UNAVAILABLE,
    );

    const { container } = render(<BestBetsBoard />);

    // The "auto-refreshing every" disclosure text must be visible immediately
    // (it is part of the RefreshAffordance, rendered before any async load).
    // Interval copy is now ~30s (real 30-second cadence, not the old wrong "~2m").
    await waitFor(() => {
      const txt = container.textContent ?? "";
      expect(/auto-refreshing every/i.test(txt)).toBe(true);
    });
  });

  it("data age affordance appears after data loads", async () => {
    const recentTs = new Date(Date.now() - 5_000).toISOString();
    const envelope = makeBoardEnvelope(recentTs, []);
    const mod = await import("@/lib/p5api");
    mod.api.bestbetsBoard = vi.fn(async (params?: { sport?: string }) =>
      params?.sport === "nba" ? envelope : UNAVAILABLE,
    );

    const { container } = render(<BestBetsBoard />);

    await waitFor(() => {
      const txt = container.textContent ?? "";
      // Either "data Xs ago" from AgeBadge or "fetched Xs ago" from client timestamp
      const hasAge =
        /data \d+s? ago/i.test(txt) ||
        /fetched \d+s? ago/i.test(txt) ||
        /data age:/i.test(txt);
      expect(hasAge).toBe(true);
    });
  });

  it("stale asOf means badge tone is NOT green (stale-never-green rail)", async () => {
    const staleTs = new Date(Date.now() - 3 * BOARD_HOUR_MS).toISOString();
    const envelope = makeBoardEnvelope(staleTs, []);
    const mod = await import("@/lib/p5api");
    mod.api.bestbetsBoard = vi.fn(async (params?: { sport?: string }) =>
      params?.sport === "nba" ? envelope : UNAVAILABLE,
    );

    render(<BestBetsBoard />);

    // Badge rendered for a stale feed must be amber -- never green
    await waitFor(() => {
      const agingEls = screen.queryAllByText(/aging/i);
      expect(agingEls.length).toBeGreaterThan(0);
    });

    const agingEls = screen.queryAllByText(/aging/i);
    for (const el of agingEls) {
      const cls = el.closest("[class]")?.className ?? el.className;
      // No green (tier-a) class
      expect(cls).not.toContain("tier-a");
    }
  });

  it("Live, Pregame, Done tabs still render after affordance is added", async () => {
    const mod = await import("@/lib/p5api");
    mod.api.bestbetsBoard = vi.fn(async () => UNAVAILABLE);

    render(<BestBetsBoard />);

    expect(screen.getByRole("tab", { name: /Live/i })).toBeTruthy();
    expect(screen.getByRole("tab", { name: /Pregame/i })).toBeTruthy();
    expect(screen.getByRole("tab", { name: /Done/i })).toBeTruthy();
  });

  it("loading skeleton renders before data arrives", async () => {
    // Use a never-resolving promise to hold the loading state
    let resolveLoad!: (v: unknown) => void;
    const mod = await import("@/lib/p5api");
    mod.api.bestbetsBoard = vi.fn(
      () => new Promise((res) => { resolveLoad = res; }),
    ) as typeof mod.api.bestbetsBoard;

    const { container } = render(<BestBetsBoard />);

    // While loading (no data yet), skeleton-shimmer divs must be present
    const skeletons = container.querySelectorAll(".skeleton-shimmer");
    expect(skeletons.length).toBeGreaterThan(0);

    // Also: refresh affordance and auto-refresh label are rendered even during load.
    // Interval copy is now ~30s (real 30-second cadence, not the old wrong "~2m").
    const txt = container.textContent ?? "";
    expect(/auto-refreshing every/i.test(txt)).toBe(true);

    // Clean up the pending promise
    resolveLoad(UNAVAILABLE);
  });
});

// ---------------------------------------------------------------------------
// Sport-filtered board (/bets/[sport]) acceptance tests -- P0 bets-board surface
//
// These tests cover the SportBetsBoard component (from app/bets/[sport]/page.tsx).
// Acceptance criteria:
//   1. Renders ranked cards (tier/confidence/units/CLV) from mock API data
//   2. No $ string in any rendered card output (units only)
//   3. CLV null -> INSUFFICIENT_DATA shown honestly, never greened
//   4. Honest empty state when the board returns 0 cards (flat slate / offseason)
//   5. Cards are sorted: tier order (S->A->B->C) then confidence desc
// ---------------------------------------------------------------------------

// We need to import the SportBetsBoard internals. Since the sport page is a "use
// client" module and exports a default page component, we test it via next/navigation
// mock + direct module import of the component logic. The BetCard is mocked to
// keep these tests focused on the board-level orchestration.

vi.mock("next/navigation", () => ({
  useParams: () => ({ sport: "nba" }),
}));

// Mock api.bestbetsBoard for sport-board tests
const mockBestbetsBoard = vi.hoisted(() => vi.fn());

// We override the existing p5api mock to also expose bestbetsBoard.
// Since the existing mock patches api.bestbetsBoard in afterEach, we use a
// separate describe block with its own mock setup.
// (BestBetsBoardType / BestBetsCard already imported above for the
// BestBetsBoard describe block -- reused here.)

function makeBestBetsCard(overrides: Partial<BestBetsCard> = {}): BestBetsCard {
  return {
    game_id: "0022401234",
    matchup: "NYK @ SAS",
    sport: "nba",
    market_type: "moneyline",
    side: "home",
    model_prob: 0.55,
    market_prob: 0.49,
    best_book: "kalshi",
    best_odds: 1.90,
    all_books: [{ book: "kalshi", odds: 1.90, line: null }],
    edge_vs_market: 0.06,
    units: 0.75,
    tier: "A",
    confidence: 0.70,
    clv: null,
    clv_is_proxy: true,
    status: "pregame",
    ...overrides,
  };
}

function makeBoardResponse(cards: BestBetsCard[]): BestBetsBoardType {
  return {
    status: "ok",
    generated_at: new Date(Date.now() - 5_000).toISOString(),
    cards,
    count: cards.length,
    sport: "nba",
    honest_note: "calibration only",
    edge_claimed: false,
  };
}

// Import the default export (SportBetsPage) after navigation mock is set up.
// We test SportBetsBoard behavior indirectly through the page render.
const SportBetsPage = (await import("@/app/bets/[sport]/page")).default;

describe("Sport bets board (/bets/[sport]) -- P0 acceptance tests", () => {
  let originalBestbetsBoard: typeof import("@/lib/p5api").api.bestbetsBoard;

  beforeEach(async () => {
    const mod = await import("@/lib/p5api");
    originalBestbetsBoard = mod.api.bestbetsBoard;
  });

  afterEach(async () => {
    const mod = await import("@/lib/p5api");
    mod.api.bestbetsBoard = originalBestbetsBoard;
    vi.restoreAllMocks();
  });

  // -----------------------------------------------------------------------
  // 1. Renders ranked cards from mock API (tier/confidence/units/CLV visible)
  // -----------------------------------------------------------------------

  it("renders ranked best-bet cards from mock API (tier + units + divergence shown)", async () => {
    const cards = [
      makeBestBetsCard({ tier: "A", confidence: 0.70, units: 0.75, market_type: "moneyline" }),
      makeBestBetsCard({ game_id: "0022401235", tier: "B", confidence: 0.55, units: 0.50, market_type: "total" }),
    ];
    const mod = await import("@/lib/p5api");
    mod.api.bestbetsBoard = vi.fn(async () => makeBoardResponse(cards));

    const { container } = render(<SportBetsPage />);

    await waitFor(() => {
      const grid = container.querySelector("[data-testid='sport-cards-grid']");
      expect(grid).not.toBeNull();
    });

    // Both tiers must appear in the rendered output
    expect(screen.queryAllByText("A").length).toBeGreaterThan(0);
    expect(screen.queryAllByText("B").length).toBeGreaterThan(0);

    // Units value visible for each card (WS6: explicit "UNITS" label, no 'u' suffix)
    const unitEls = container.querySelectorAll("[data-testid='units-value']");
    expect(unitEls.length).toBeGreaterThan(0);
  });

  // -----------------------------------------------------------------------
  // 2. No $ string in any rendered output (units only rail)
  // -----------------------------------------------------------------------

  it("renders NO dollar-amount string ($\\d) anywhere in the sport board", async () => {
    const cards = [makeBestBetsCard({ units: 1.0 })];
    const mod = await import("@/lib/p5api");
    mod.api.bestbetsBoard = vi.fn(async () => makeBoardResponse(cards));

    const { container } = render(<SportBetsPage />);

    await waitFor(() => {
      // Wait for cards to load
      expect(container.querySelector("[data-testid='sport-cards-grid']")).not.toBeNull();
    });

    const txt = container.textContent ?? "";
    // No dollar followed by digit (monetary P&L claim)
    expect(/\$\s*\d/.test(txt)).toBe(false);
    // No ROI or P&L label
    expect(/\bROI\b/.test(txt)).toBe(false);
    expect(/\bP&L\b|\bPnL\b/i.test(txt)).toBe(false);
  });

  // -----------------------------------------------------------------------
  // 3. CLV null -> INSUFFICIENT_DATA shown honestly, never greened
  // -----------------------------------------------------------------------

  it("shows INSUFFICIENT_DATA when CLV is null (never greened or fabricated)", async () => {
    const cards = [makeBestBetsCard({ clv: null, clv_is_proxy: true })];
    const mod = await import("@/lib/p5api");
    mod.api.bestbetsBoard = vi.fn(async () => makeBoardResponse(cards));

    const { container } = render(<SportBetsPage />);

    await waitFor(() => {
      expect(screen.queryAllByText(/INSUFFICIENT_DATA/i).length).toBeGreaterThan(0);
    });

    // The INSUFFICIENT_DATA element must NOT carry any green class
    const insEl = screen.queryAllByText(/INSUFFICIENT_DATA/i)[0];
    const cls = insEl?.className ?? "";
    expect(cls).not.toMatch(/green|tier-a/);
  });

  // -----------------------------------------------------------------------
  // 4. Honest empty state when board returns 0 cards
  // -----------------------------------------------------------------------

  it("shows honest empty state when board returns 0 cards (flat slate / offseason)", async () => {
    const mod = await import("@/lib/p5api");
    mod.api.bestbetsBoard = vi.fn(async () => makeBoardResponse([]));

    const { container } = render(<SportBetsPage />);

    await waitFor(() => {
      const emptyEl = container.querySelector("[data-testid='sport-empty-state']");
      expect(emptyEl).not.toBeNull();
    });

    const txt = container.textContent ?? "";
    // Honest messaging: no calibrated bets, no fabricated cards
    expect(/No calibrated bets right now/i.test(txt)).toBe(true);
    // No fabricated profit claim in empty state
    expect(/\$\s*\d/.test(txt)).toBe(false);
    // CLV INSUFFICIENT_DATA note shown in empty state
    expect(/INSUFFICIENT_DATA/i.test(txt)).toBe(true);
  });

  // -----------------------------------------------------------------------
  // 5. Cards sorted: tier order (S->A->B->C) then confidence desc
  // -----------------------------------------------------------------------

  it("renders cards sorted by tier then confidence (S before A, higher confidence first within tier)", async () => {
    const cards = [
      // B tier (should render after A)
      makeBestBetsCard({ game_id: "g2", tier: "B", confidence: 0.90, market_type: "spread_B" }),
      // A tier, lower confidence
      makeBestBetsCard({ game_id: "g3", tier: "A", confidence: 0.50, market_type: "total_A_low" }),
      // A tier, higher confidence (should render first among A)
      makeBestBetsCard({ game_id: "g4", tier: "A", confidence: 0.80, market_type: "moneyline_A_high" }),
    ];
    const mod = await import("@/lib/p5api");
    mod.api.bestbetsBoard = vi.fn(async () => makeBoardResponse(cards));

    const { container } = render(<SportBetsPage />);

    await waitFor(() => {
      expect(container.querySelector("[data-testid='sport-cards-grid']")).not.toBeNull();
    });

    const grid = container.querySelector("[data-testid='sport-cards-grid']");
    const listItems = grid?.querySelectorAll("[role='listitem']") ?? [];
    // Should have 3 rendered cards
    expect(listItems.length).toBe(3);
    // First two items are tier A (moneyline_A_high then total_A_low by confidence)
    // Third item is tier B (spread_B)
    // We verify by checking that market_type text ordering matches our sort
    const texts = Array.from(listItems).map((el) => el.textContent ?? "");
    // Both A-tier cards appear before the B-tier card
    const idxAHigh = texts.findIndex((t) => /moneyline_A_high/i.test(t));
    const idxALow = texts.findIndex((t) => /total_A_low/i.test(t));
    const idxB = texts.findIndex((t) => /spread_B/i.test(t));
    expect(idxAHigh).toBeLessThan(idxB);
    expect(idxALow).toBeLessThan(idxB);
    // Higher confidence A card before lower confidence A card
    expect(idxAHigh).toBeLessThan(idxALow);
  });

  // -----------------------------------------------------------------------
  // 6. Honest framing: no edge/profit claim in page headers or banners
  // -----------------------------------------------------------------------

  it("does not claim edge or profit anywhere on the sport page", async () => {
    const mod = await import("@/lib/p5api");
    mod.api.bestbetsBoard = vi.fn(async () => makeBoardResponse([]));

    const { container } = render(<SportBetsPage />);
    await waitFor(() => {
      expect(container.querySelector("[data-testid='sport-empty-state']")).not.toBeNull();
    });

    const txt = container.textContent ?? "";
    // No bare "edge" claim (allow "edge_vs_market" as a label but not "profit edge" or "we have edge")
    expect(/\bwe have edge\b/i.test(txt)).toBe(false);
    expect(/\bROI\b/.test(txt)).toBe(false);
  });
});
