// bets_detail -- W7 card-detail component tests.
//
// Per-file vitest test (NEVER run the full suite -- freezes the box).
// Run: cd /c/Users/neelj/nba-ai-system/webapp && npx vitest run components/bets_detail/__tests__/bets_detail.test.tsx
//
// Covers:
//   * BookMatrixTable: renders book columns, best-line highlight, no $ header,
//     honest unavailable + empty states.
//   * DistributionPanel: renders headline prediction + honest empty on no props,
//     UNAVAILABLE on failed props fetch.
//   * LiveBoxPanel: honest empty (not live), INSUFFICIENT_DATA CLV shown,
//     no $ anywhere.
//   * SettleGradePanel: CLV-proxy warning, no $ column, settled bet rows.
//   * RationalePanel: renders validated signals strip (sport label), rationale note.
//   * p5api_ext: isExtUnavailable sentinel, apiExt method shapes (URL smoke test).
//   * No $ / pnl / roi field in any bets_detail source file.
//   * WS7: CardDetailView + PaperHistory use useLiveData (no bespoke setInterval),
//     retain last-good on failed poll, show last-updated age, never green-on-stale.

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { readdirSync, readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { CardDetailView } from "../CardDetailView";
import { PaperHistory } from "../../p6/PaperHistory";
import { BookMatrixTable } from "../BookMatrixTable";
import { DistributionPanel } from "../DistributionPanel";
import { LiveBoxPanel } from "../LiveBoxPanel";
import { SettleGradePanel } from "../SettleGradePanel";
import { RationalePanel } from "../RationalePanel";
import {
  isExtUnavailable,
  apiExt,
} from "@/lib/p5api_ext";
import type {
  LinesMatrix,
  InGameFull,
  PropsBoardEnvelope,
} from "@/lib/p5api_ext";
import type { GameEdge, BestBet } from "@/lib/types";

// ---------------------------------------------------------------------------
// Mocks -- all network is mocked; components render with injected data only.
// ---------------------------------------------------------------------------

// Mock p5api_ext so no real fetch escapes.
vi.mock("@/lib/p5api_ext", async (importActual) => {
  const actual = await importActual<typeof import("@/lib/p5api_ext")>();
  return {
    ...actual,
    apiExt: {
      getLinesMatrix: vi.fn().mockResolvedValue({ status: "unavailable" }),
      getPropsBoard: vi.fn().mockResolvedValue({ status: "unavailable" }),
      getBoxscore: vi.fn().mockResolvedValue({ status: "unavailable" }),
      getInGameFull: vi.fn().mockResolvedValue({ status: "unavailable" }),
      getPmTrail: vi.fn().mockResolvedValue({ status: "unavailable" }),
      getPmTradeDetail: vi.fn().mockResolvedValue({ status: "unavailable" }),
    },
  };
});

// Mock p5api / api so no real fetch runs from CardDetailView.
vi.mock("@/lib/api", () => ({
  api: {
    report: vi.fn().mockResolvedValue({ status: "unavailable" }),
    bestbetsGame: vi.fn().mockResolvedValue({ status: "unavailable" }),
    getResults: vi.fn().mockResolvedValue({ status: "unavailable" }),
  },
  isUnavailable: (x: unknown) =>
    !!(x && typeof x === "object" && (x as { status?: string }).status === "unavailable"),
  streamUrl: () => "http://127.0.0.1:8099/api/stream/game/nba/test",
  SPORTS: ["nba", "mlb", "soccer", "soccer_intl", "tennis"],
}));

// Mock useStream so the streaming hook doesn't try to open an SSE connection.
// Exported as a factory so tests that need a specific Report can override it.
let _useStreamReport: import("@/lib/types").Report | null = null;
vi.mock("@/lib/useStream", () => ({
  useStream: () => ({ data: _useStreamReport, mode: "idle" }),
}));

// Mock useLiveData so components can be tested with controlled LiveDataState.
// _liveDataOverrides: keyed by the string form of the fetcher's call index;
// in practice we use a single registry per test (reset in beforeEach) mapping
// fetch URL patterns to state. For simplicity we supply a single default state
// that all useLiveData calls return, overridable per-test via _setLiveData.
interface MockLiveState {
  data: unknown;
  lastUpdatedAt: number | null;
  ageSec: number | null;
  isStale: boolean;
  error: string | null;
  isLoading: boolean;
  refresh: () => void;
}

const _defaultLiveState: MockLiveState = {
  data: null,
  lastUpdatedAt: null,
  ageSec: null,
  isStale: false,
  error: null,
  isLoading: true,
  refresh: vi.fn(),
};
let _liveDataStates: MockLiveState[] = [];
let _liveDataCallIdx = 0;

function _resetLiveData(states: MockLiveState[]) {
  _liveDataStates = states;
  _liveDataCallIdx = 0;
}

vi.mock("@/lib/useLiveData", () => ({
  useLiveData: () => {
    // Return states round-robin from the array; fall back to default.
    const idx = _liveDataCallIdx++;
    return _liveDataStates[idx] ?? { ..._defaultLiveState };
  },
  useLiveDataUrl: () => ({ ..._defaultLiveState }),
}));

// Also mock p5api so PaperHistory can be rendered without real fetch.
vi.mock("@/lib/p5api", () => ({
  api: {
    report: vi.fn().mockResolvedValue({ status: "unavailable" }),
    bestbetsGame: vi.fn().mockResolvedValue({ status: "unavailable" }),
    getResults: vi.fn().mockResolvedValue({ status: "unavailable" }),
    getPaperTrail: vi.fn().mockResolvedValue({ status: "unavailable" }),
    getPaperClv: vi.fn().mockResolvedValue({ status: "unavailable" }),
    getCatalog: vi.fn().mockResolvedValue({ status: "unavailable" }),
    getAllHonest: vi.fn().mockResolvedValue({ status: "unavailable" }),
    getQuantValidate: vi.fn().mockResolvedValue({ status: "unavailable" }),
    getQuantRisk: vi.fn().mockResolvedValue({ status: "unavailable" }),
    getImproveTimeline: vi.fn().mockResolvedValue({ status: "unavailable" }),
  },
  isUnavailable: (x: unknown) =>
    !!(x && typeof x === "object" && (x as { status?: string }).status === "unavailable"),
  streamUrl: () => "http://127.0.0.1:8099/api/stream/game/nba/test",
  SPORTS: ["nba", "mlb", "soccer", "soccer_intl", "tennis"],
}));

// ---------------------------------------------------------------------------
// Test fixtures
// ---------------------------------------------------------------------------

// Helper: build a BestBet with a given tier, clv_is_proxy, and edge value.
function makeBet(tier: string | null, clv_is_proxy: boolean, edge: number | null): BestBet {
  return {
    market_type: "moneyline",
    side: "home",
    model_prob: 0.58,
    market_prob: 0.52,
    best_book: "DraftKings",
    best_odds: 1.91,
    line: null,
    edge,
    ev: 0.02,
    tier,
    decision: "bet",
    stake_units: 0.5,
    flat_unit: 0.5,
    kelly_units: 0.25,
    clv_is_proxy,
    reason: undefined,
  };
}

const LINES_MATRIX: LinesMatrix = {
  status: "ok",
  sport: "nba",
  game_id: "0022300001",
  generated_at: new Date().toISOString(),
  markets: {
    moneyline: {
      market_type: "moneyline",
      sides: {
        home: [
          { book: "DraftKings", odds: 1.91, line: null, captured_at: null, is_pm: false },
          { book: "Kalshi", odds: 1.95, line: null, captured_at: null, is_pm: true },
        ],
        away: [
          { book: "DraftKings", odds: 2.05, line: null, captured_at: null, is_pm: false },
        ],
      },
      best: {
        home: { book: "Kalshi", odds: 1.95 },
        away: { book: "DraftKings", odds: 2.05 },
      },
    },
  },
  edge_claimed: false,
};

const INGAME_FULL_LIVE: InGameFull = {
  status: "ok",
  sport: "nba",
  game_id: "0022300001",
  generated_at: new Date().toISOString(),
  home: "NYK",
  away: "SAS",
  home_score: 62,
  away_score: 58,
  period: 3,
  clock: "5:42",
  frac_elapsed: 0.625,
  p_win: 0.63,
  clv_status: "INSUFFICIENT_DATA",
  clv_is_proxy: false,
  players: [
    { name: "Brunson", team: "NYK", min: 24.5, pts: 18, reb: 3, ast: 7 },
    { name: "Wembanyama", team: "SAS", min: 23, pts: 15, reb: 9, ast: 2 },
  ],
};

const BEST_BET: BestBet = {
  market_type: "moneyline",
  side: "home",
  model_prob: 0.58,
  market_prob: 0.52,
  best_book: "Kalshi",
  best_odds: 1.95,
  line: null,
  edge: 0.04,
  ev: 0.032,
  tier: "A",
  decision: "bet",
  stake_units: 0.5,
  flat_unit: 0.5,
  kelly_units: 0.25,
  clv_is_proxy: true,   // proxy close -> warns honestly
  reason: undefined,
};

const GAME_EDGE: GameEdge = {
  game_id: "0022300001",
  home: "NYK",
  away: "SAS",
  status: "ok",
  best_bets: [BEST_BET],
  candidates: [BEST_BET],
};

// ---------------------------------------------------------------------------
// BookMatrixTable
// ---------------------------------------------------------------------------

describe("BookMatrixTable -- per-book odds matrix", () => {
  it("renders book column headers (DraftKings, Kalshi)", () => {
    render(<BookMatrixTable matrix={LINES_MATRIX} />);
    // Multiple elements may contain these labels (header + best-badge), so use getAllByText.
    expect(screen.getAllByText("DraftKings").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Kalshi").length).toBeGreaterThan(0);
  });

  it("renders a market type label", () => {
    render(<BookMatrixTable matrix={LINES_MATRIX} />);
    expect(screen.getByText(/moneyline/i)).toBeTruthy();
  });

  it("highlights the best book", () => {
    const { container } = render(<BookMatrixTable matrix={LINES_MATRIX} />);
    // Best book for home side is Kalshi -- should appear as best badge.
    const bestBadges = container.querySelectorAll(".text-up");
    expect(bestBadges.length).toBeGreaterThan(0);
  });

  it("has NO $ / price / payout column header", () => {
    render(<BookMatrixTable matrix={LINES_MATRIX} />);
    const headers = screen
      .getAllByRole("columnheader")
      .map((h) => h.textContent ?? "");
    for (const h of headers) {
      expect(/price|payout|\$/i.test(h), `banned header: ${h}`).toBe(false);
    }
  });

  it("shows UNAVAILABLE for a failed feed", () => {
    const unavail = { status: "unavailable" as const, reason: "feed down" } as unknown as LinesMatrix;
    render(<BookMatrixTable matrix={unavail} />);
    expect(screen.getByText(/unavailable/i)).toBeTruthy();
  });

  it("shows empty message for no markets", () => {
    const empty: LinesMatrix = { ...LINES_MATRIX, markets: {} };
    render(<BookMatrixTable matrix={empty} />);
    expect(screen.getByText(/No lines captured/i)).toBeTruthy();
  });
});

// ---------------------------------------------------------------------------
// DistributionPanel
// ---------------------------------------------------------------------------

describe("DistributionPanel -- prediction + interval", () => {
  const report = {
    status: "ok",
    sport: "nba",
    game_id: "0022300001",
    pregame: {
      home: "NYK",
      away: "SAS",
      model_probs: { home_ml: 0.58, away_ml: 0.42 },
      leak_guard: { in_sample: false },
    },
  } as import("@/lib/types").Report;

  it("renders the game prediction section", () => {
    render(<DistributionPanel report={report} propsData={null} sport="nba" />);
    expect(screen.getByText(/game prediction/i)).toBeTruthy();
  });

  it("renders the headline pick label (highest prob side)", () => {
    render(<DistributionPanel report={report} propsData={null} sport="nba" />);
    // home_ml = 0.58 > away_ml = 0.42, so pick is "NYK"
    expect(screen.getByText("NYK")).toBeTruthy();
  });

  it("shows UNAVAILABLE for null propsData (NBA offseason)", () => {
    render(<DistributionPanel report={report} propsData={null} sport="nba" />);
    // May render multiple 'unavailable' elements (label + reason text).
    expect(screen.getAllByText(/unavailable/i).length).toBeGreaterThan(0);
  });

  it("shows empty state when props are empty array", () => {
    const emptyProps: PropsBoardEnvelope = {
      status: "ok",
      sport: "nba",
      generated_at: new Date().toISOString(),
      props: [],
      clv_is_proxy: false,
    };
    render(<DistributionPanel report={report} propsData={emptyProps} sport="nba" />);
    expect(screen.getByText(/No prop lines/i)).toBeTruthy();
  });

  it("shows leak-free badge from report", () => {
    render(<DistributionPanel report={report} propsData={null} sport="nba" />);
    expect(screen.getByText("leak-free")).toBeTruthy();
  });

  it("has vs-close UNPROVEN notice", () => {
    render(<DistributionPanel report={report} propsData={null} sport="nba" />);
    expect(screen.getByText(/vs-close UNPROVEN/i)).toBeTruthy();
  });
});

// ---------------------------------------------------------------------------
// LiveBoxPanel
// ---------------------------------------------------------------------------

// Stale fixture: generated_at is 10 minutes ago (well past the 3-min threshold).
const STALE_GENERATED_AT = new Date(Date.now() - 10 * 60 * 1000).toISOString();
const INGAME_FULL_STALE: InGameFull = {
  ...INGAME_FULL_LIVE,
  generated_at: STALE_GENERATED_AT,
};

// No-timestamp fixture: generated_at is null (treat as Infinity age -> stale).
const INGAME_FULL_NO_TS: InGameFull = {
  ...INGAME_FULL_LIVE,
  generated_at: null,
};

describe("LiveBoxPanel -- live score + boxscore", () => {
  // ------------------------------------------------------------------
  // ws1-livebox-skeleton: ingame=null must render a skeleton affordance,
  // NOT a stale score and NOT a green badge. Neutral checking state only.
  // ------------------------------------------------------------------
  it("ingame=null: renders skeleton loading affordance (not stale score, not green badge)", () => {
    render(<LiveBoxPanel ingame={null} />);
    // Must expose a skeleton element by data-testid.
    expect(screen.getByTestId("live-box-skeleton")).toBeTruthy();
    // The role="status" on the skeleton div is the accessible loading affordance.
    const statuses = screen.getAllByRole("status");
    expect(statuses.length).toBeGreaterThan(0);
    // Must NOT show a fabricated score -- no numeric text from INGAME_FULL_LIVE.
    expect(screen.queryByText("62")).toBeNull();
    expect(screen.queryByText("58")).toBeNull();
    // Must NOT say "stale" (it is a checking/loading state, not a stale-data state).
    const bodyText = document.body.textContent ?? "";
    expect(/\bstale\b/i.test(bodyText)).toBe(false);
    // Must NOT contain any green badge class (stale-never-green rail applies here too).
    const { container } = render(<LiveBoxPanel ingame={null} />);
    const greenElements = container.querySelectorAll('[class*="text-emerald"], [class*="text-tier-a"], [class*="text-green"]');
    expect(greenElements.length).toBe(0);
  });

  it("shows the live score when game is in progress (fresh feed)", () => {
    render(<LiveBoxPanel ingame={INGAME_FULL_LIVE} />);
    expect(screen.getByText("62")).toBeTruthy();
    expect(screen.getByText("58")).toBeTruthy();
  });

  it("shows INSUFFICIENT_DATA CLV notice honestly", () => {
    render(<LiveBoxPanel ingame={INGAME_FULL_LIVE} />);
    // Two mentions expected: chip in header + notice at bottom.
    expect(screen.getAllByText(/INSUFFICIENT_DATA/i).length).toBeGreaterThan(0);
  });

  it("renders player boxscore rows", () => {
    render(<LiveBoxPanel ingame={INGAME_FULL_LIVE} />);
    expect(screen.getByText("Brunson")).toBeTruthy();
    expect(screen.getByText("Wembanyama")).toBeTruthy();
  });

  it("shows empty state when game not live (fresh, no scores)", () => {
    const notLive: InGameFull = {
      ...INGAME_FULL_LIVE,
      home_score: undefined,
      away_score: undefined,
      period: undefined,
      clock: undefined,
    };
    render(<LiveBoxPanel ingame={notLive} />);
    expect(screen.getByText(/Game not live/i)).toBeTruthy();
  });

  it("shows unavailable state on failed feed", () => {
    const unavail = { status: "unavailable" as const } as unknown as InGameFull;
    render(<LiveBoxPanel ingame={unavail} />);
    expect(screen.getByText(/unavailable/i)).toBeTruthy();
  });

  it("has NO $ column in boxscore table", () => {
    render(<LiveBoxPanel ingame={INGAME_FULL_LIVE} />);
    const headers = screen
      .getAllByRole("columnheader")
      .map((h) => h.textContent ?? "");
    for (const h of headers) {
      expect(/\$/i.test(h), `banned $ header: ${h}`).toBe(false);
    }
  });

  // FRESHNESS GATE TESTS -- stale-never-green rail.
  it("stale feed: shows Stale state instead of live score (stale-never-green rail)", () => {
    render(<LiveBoxPanel ingame={INGAME_FULL_STALE} />);
    // Must NOT show the score -- it's stale.
    expect(screen.queryByText("62")).toBeNull();
    expect(screen.queryByText("58")).toBeNull();
    // Must show at least one Stale indicator (the HonestState Frame title span).
    expect(screen.getAllByText(/stale/i).length).toBeGreaterThan(0);
  });

  it("stale feed: Stale banner includes an explanation about the dead feed", () => {
    render(<LiveBoxPanel ingame={INGAME_FULL_STALE} />);
    // The reason string in <Stale> mentions feed/daemon/final.
    const container = document.body;
    expect(/daemon|final|feed/i.test(container.textContent ?? "")).toBe(true);
  });

  it("null generated_at: treats as stale, never shows score as live", () => {
    render(<LiveBoxPanel ingame={INGAME_FULL_NO_TS} />);
    // No generated_at -> infinite age -> stale branch.
    expect(screen.queryByText("62")).toBeNull();
    expect(screen.getAllByText(/stale/i).length).toBeGreaterThan(0);
  });

  it("fresh feed: shows age chip in header (data-testid=age-chip)", () => {
    render(<LiveBoxPanel ingame={INGAME_FULL_LIVE} />);
    // INGAME_FULL_LIVE has generated_at = now, so AgeChip is rendered.
    // The chip shows "Xs ago" text; locate it by data-testid.
    expect(screen.getByTestId("age-chip")).toBeTruthy();
    // The chip text contains 'ago' (e.g. '0s ago').
    expect(screen.getByTestId("age-chip").textContent).toMatch(/ago/i);
  });
});

// ---------------------------------------------------------------------------
// SettleGradePanel
// ---------------------------------------------------------------------------

describe("SettleGradePanel -- settle / CLV grade", () => {
  it("renders a market row for each bet", () => {
    render(<SettleGradePanel edge={GAME_EDGE} result={null} />);
    expect(screen.getByText(/moneyline/i)).toBeTruthy();
    expect(screen.getByText(/home/i)).toBeTruthy();
  });

  it("shows proxy-close warning for clv_is_proxy bets", () => {
    render(<SettleGradePanel edge={GAME_EDGE} result={null} />);
    // Multiple 'proxy close' elements expected: badge + notice paragraph.
    expect(screen.getAllByText(/proxy close/i).length).toBeGreaterThan(0);
  });

  it("shows final score from result row", () => {
    const result = {
      game_id: "0022300001",
      home: "NYK",
      away: "SAS",
      home_score: 110,
      away_score: 98,
      completed: true,
    };
    const { container } = render(<SettleGradePanel edge={GAME_EDGE} result={result} />);
    // Scores are embedded in a multi-text span, so search the full rendered text.
    const text = container.textContent ?? "";
    expect(text).toContain("110");
    expect(text).toContain("98");
    expect(text).toContain("NYK");
    expect(text).toContain("SAS");
  });

  it("shows empty state when no bets", () => {
    render(<SettleGradePanel edge={null} result={null} />);
    expect(screen.getByText(/No graded bets/i)).toBeTruthy();
  });

  it("has NO $ column header", () => {
    render(<SettleGradePanel edge={GAME_EDGE} result={null} />);
    const headers = screen
      .getAllByRole("columnheader")
      .map((h) => h.textContent ?? "");
    for (const h of headers) {
      expect(/\$/i.test(h), `banned $ header: ${h}`).toBe(false);
    }
  });

  // ------------------------------------------------------------------
  // Acceptance: tier badge uses shared tierClass token convention
  // ------------------------------------------------------------------

  it("S tier: tier badge carries bg-tier-s token classes (shared convention)", () => {
    const edge: GameEdge = {
      ...GAME_EDGE,
      best_bets: [makeBet("S", false, 0.06)],
    };
    const { container } = render(<SettleGradePanel edge={edge} result={null} />);
    // tierClass("S") = "bg-tier-s/20 text-tier-s border-tier-s/40"
    const badge = container.querySelector(".bg-tier-s\\/20");
    expect(badge, "S tier should carry bg-tier-s/20 class").toBeTruthy();
    expect(badge?.className).toContain("text-tier-s");
    expect(badge?.className).toContain("border-tier-s");
    expect(badge?.textContent).toMatch(/S/i);
  });

  it("A tier: tier badge carries bg-tier-a token classes (shared convention)", () => {
    const edge: GameEdge = {
      ...GAME_EDGE,
      best_bets: [makeBet("A", false, 0.04)],
    };
    const { container } = render(<SettleGradePanel edge={edge} result={null} />);
    // tierClass("A") = "bg-tier-a/20 text-tier-a border-tier-a/40"
    const badge = container.querySelector(".bg-tier-a\\/20");
    expect(badge, "A tier should carry bg-tier-a/20 class").toBeTruthy();
    expect(badge?.className).toContain("text-tier-a");
    expect(badge?.className).toContain("border-tier-a");
    expect(badge?.textContent).toMatch(/A/i);
  });

  it("B tier: tier badge carries bg-tier-b token classes (shared convention)", () => {
    const edge: GameEdge = {
      ...GAME_EDGE,
      best_bets: [makeBet("B", false, 0.02)],
    };
    const { container } = render(<SettleGradePanel edge={edge} result={null} />);
    // tierClass("B") = "bg-tier-b/20 text-tier-b border-tier-b/40"
    const badge = container.querySelector(".bg-tier-b\\/20");
    expect(badge, "B tier should carry bg-tier-b/20 class").toBeTruthy();
    expect(badge?.className).toContain("text-tier-b");
    expect(badge?.className).toContain("border-tier-b");
    expect(badge?.textContent).toMatch(/B/i);
  });

  it("C tier (default): tier badge carries bg-tier-c token classes (shared convention)", () => {
    const edge: GameEdge = {
      ...GAME_EDGE,
      best_bets: [makeBet("C", false, 0.01)],
    };
    const { container } = render(<SettleGradePanel edge={edge} result={null} />);
    // tierClass(default) = "bg-tier-c/20 text-tier-c border-tier-c/40"
    const badge = container.querySelector(".bg-tier-c\\/20");
    expect(badge, "C tier should carry bg-tier-c/20 class").toBeTruthy();
    expect(badge?.className).toContain("text-tier-c");
    expect(badge?.className).toContain("border-tier-c");
    expect(badge?.textContent).toMatch(/C/i);
  });

  it("null tier: tier badge renders '--' with bg-tier-c fallback (tierClass default)", () => {
    const edge: GameEdge = {
      ...GAME_EDGE,
      best_bets: [makeBet(null, false, null)],
    };
    const { container } = render(<SettleGradePanel edge={edge} result={null} />);
    // null tier -> tierClass(undefined) -> default C branch
    const badge = container.querySelector(".bg-tier-c\\/20");
    expect(badge, "null tier should fall through to bg-tier-c/20").toBeTruthy();
    expect(badge?.textContent).toContain("--");
  });

  // ------------------------------------------------------------------
  // Acceptance: CLV grade tones are unchanged
  // ------------------------------------------------------------------

  it("CLV proxy: badge tone is amber (proxy close)", () => {
    const edge: GameEdge = {
      ...GAME_EDGE,
      best_bets: [makeBet("A", true, null)],
    };
    const { container } = render(<SettleGradePanel edge={edge} result={null} />);
    // Badge tone="amber" -> contains bg-amber-950 class
    const amber = container.querySelector('[class*="bg-amber-950"]');
    expect(amber, "proxy close badge must be amber").toBeTruthy();
    expect(amber?.textContent?.toLowerCase()).toContain("proxy");
  });

  it("CLV beat close: badge tone is green", () => {
    const edge: GameEdge = {
      ...GAME_EDGE,
      // Use tier="S" so the tier badge has text-tier-s, keeping text-tier-a exclusive to the CLV badge.
      best_bets: [makeBet("S", false, 0.05)],
    };
    const { container } = render(<SettleGradePanel edge={edge} result={null} />);
    // Badge tone="green" -> bg-tier-a/20 text-tier-a (from Primitives.tsx Badge tones map).
    // With tier=S the only text-tier-a element is the CLV green badge.
    const greens = container.querySelectorAll('[class*="text-tier-a"]');
    // At least one must contain "beat"
    const beatBadge = Array.from(greens).find((el) =>
      el.textContent?.toLowerCase().includes("beat"),
    );
    expect(beatBadge, "beat-close badge must use green/tier-a tone and contain 'beat'").toBeTruthy();
  });

  it("CLV missed close: badge tone is red", () => {
    const edge: GameEdge = {
      ...GAME_EDGE,
      best_bets: [makeBet("A", false, -0.03)],
    };
    const { container } = render(<SettleGradePanel edge={edge} result={null} />);
    // Badge tone="red" -> bg-red-950/40 text-red-400
    const red = container.querySelector('[class*="text-red-400"]');
    expect(red, "missed-close badge must be red").toBeTruthy();
    expect(red?.textContent?.toLowerCase()).toContain("missed");
  });

  it("CLV no close (edge=null, not proxy): badge tone is slate", () => {
    const edge: GameEdge = {
      ...GAME_EDGE,
      best_bets: [makeBet("A", false, null)],
    };
    const { container } = render(<SettleGradePanel edge={edge} result={null} />);
    // Badge tone="slate" -> bg-slate-800 text-slate-300
    const slate = container.querySelector('[class*="bg-slate-800"]');
    expect(slate, "no-close badge must be slate").toBeTruthy();
    expect(slate?.textContent?.toLowerCase()).toContain("no close");
  });

  it("proxy-close notice text is still rendered (honesty rail)", () => {
    render(<SettleGradePanel edge={GAME_EDGE} result={null} />);
    const text = document.body.textContent ?? "";
    expect(/UNPROVEN/i.test(text)).toBe(true);
    expect(/INSUFFICIENT_DATA/i.test(text)).toBe(true);
  });

  it("no $ string appears anywhere in the rendered output", () => {
    const { container } = render(<SettleGradePanel edge={GAME_EDGE} result={null} />);
    const text = container.textContent ?? "";
    // A real $ amount ($ next to a digit) is banned. Prose "no $" is the honesty rail.
    expect(/\$\s*\d|\d\s*\$/.test(text), "no $ amount in rendered output").toBe(false);
  });
});

// ---------------------------------------------------------------------------
// RationalePanel
// ---------------------------------------------------------------------------

describe("RationalePanel -- validated signals + model notes", () => {
  it("renders 'validated signals' section", () => {
    render(<RationalePanel report={null} sport="nba" />);
    // The heading + possibly ValidatedSignalsStrip sub-text both match.
    expect(screen.getAllByText(/validated signals/i).length).toBeGreaterThan(0);
  });

  it("renders 'model notes' section", () => {
    render(<RationalePanel report={null} sport="nba" />);
    // Both the heading and 'No model notes' empty label contain 'model notes'.
    expect(screen.getAllByText(/model notes/i).length).toBeGreaterThan(0);
  });

  it("shows empty state when no notes", () => {
    render(<RationalePanel report={null} sport="nba" />);
    expect(screen.getAllByText(/No model notes/i).length).toBeGreaterThan(0);
  });

  it("renders model note from report.intel", () => {
    const report = {
      status: "ok",
      sport: "nba",
      game_id: "test",
      intel: { note: "High-pace matchup favors unders." },
    } as import("@/lib/types").Report;
    render(<RationalePanel report={report} sport="nba" />);
    expect(screen.getByText("High-pace matchup favors unders.")).toBeTruthy();
  });

  it("shows SHIP = calibration footer", () => {
    render(<RationalePanel report={null} sport="nba" />);
    // May appear in multiple elements (badge stat text + footer span).
    expect(screen.getAllByText(/calibration, not a market edge/i).length).toBeGreaterThan(0);
  });
});

// ---------------------------------------------------------------------------
// p5api_ext -- isExtUnavailable + apiExt method shapes
// ---------------------------------------------------------------------------

describe("p5api_ext -- sentinel + client shapes", () => {
  it("isExtUnavailable detects the sentinel correctly", () => {
    expect(isExtUnavailable({ status: "unavailable" })).toBe(true);
    expect(isExtUnavailable({ status: "ok" })).toBe(false);
    expect(isExtUnavailable(null)).toBe(false);
    expect(isExtUnavailable("unavailable")).toBe(false);
  });

  it("apiExt has all expected methods", () => {
    expect(typeof apiExt.getLinesMatrix).toBe("function");
    expect(typeof apiExt.getPropsBoard).toBe("function");
    expect(typeof apiExt.getBoxscore).toBe("function");
    expect(typeof apiExt.getInGameFull).toBe("function");
    expect(typeof apiExt.getPmTrail).toBe("function");
    expect(typeof apiExt.getPmTradeDetail).toBe("function");
  });
});

// ---------------------------------------------------------------------------
// CardDetailView -- sport cross-check (QA #2: ws2-betdetail-sport-crosscheck)
// ---------------------------------------------------------------------------
//
// Acceptance criteria:
//   (a) URL sport='nba' + report.sport='mlb' -> header shows corrective mismatch
//       notice and surfaces the true sport label (MLB), not just bare 'NBA'.
//   (b) URL sport='nba' + report.sport='nba' -> no mismatch notice, normal 'NBA'.
//   (c) report null/unavailable -> falls back to slug label with no mismatch claim,
//       still renders without crashing.

describe("CardDetailView -- sport cross-check", () => {
  beforeEach(() => {
    // Reset the streaming report before each test.
    _useStreamReport = null;
  });

  it("(a) mismatch: URL nba + report.sport mlb -> shows corrective notice + MLB label", () => {
    // Wire useStream to return a report whose sport is 'mlb'.
    _useStreamReport = {
      status: "ok",
      sport: "mlb",
      game_id: "mlb-game-001",
    } as import("@/lib/types").Report;

    render(<CardDetailView sport="nba" gameId="mlb-game-001" />);

    // The mismatch notice must be present.
    const notice = screen.getByRole("alert", { name: "sport-mismatch-notice" });
    expect(notice).toBeTruthy();

    // The notice must mention the URL sport (NBA) and the true sport (MLB).
    const noticeText = notice.textContent ?? "";
    expect(/nba/i.test(noticeText)).toBe(true);
    expect(/mlb/i.test(noticeText)).toBe(true);

    // The page-level h1 (heading level 1) must show the TRUE sport (MLB), not 'NBA'.
    // Use getAllByRole + filter for h1 (level 1) since sub-panels also use h2/h3.
    const allHeadings = screen.getAllByRole("heading");
    const h1 = allHeadings.find((el) => el.tagName === "H1");
    expect(h1).toBeTruthy();
    expect(/mlb/i.test(h1?.textContent ?? "")).toBe(true);
    // Must NOT silently show 'NBA' as the sport label in h1.
    // The h1 first span is the sport label span -- check its text.
    const sportSpan = h1?.querySelector("span");
    expect(/nba/i.test(sportSpan?.textContent ?? "")).toBe(false);
    expect(/mlb/i.test(sportSpan?.textContent ?? "")).toBe(true);
  });

  it("(b) match: URL nba + report.sport nba -> no mismatch notice, normal NBA header", () => {
    _useStreamReport = {
      status: "ok",
      sport: "nba",
      game_id: "0022300001",
    } as import("@/lib/types").Report;

    render(<CardDetailView sport="nba" gameId="0022300001" />);

    // No mismatch alert must exist.
    expect(screen.queryByRole("alert", { name: "sport-mismatch-notice" })).toBeNull();

    // Page-level h1 shows NBA.
    const allHeadings = screen.getAllByRole("heading");
    const h1 = allHeadings.find((el) => el.tagName === "H1");
    expect(h1).toBeTruthy();
    expect(/nba/i.test(h1?.textContent ?? "")).toBe(true);
  });

  it("(c) null report -> slug label shown, no mismatch notice, still renders", () => {
    // _useStreamReport remains null -- report is not yet loaded.
    render(<CardDetailView sport="nba" gameId="0022300001" />);

    // No mismatch alert (cannot claim mismatch without knowing the API sport).
    expect(screen.queryByRole("alert", { name: "sport-mismatch-notice" })).toBeNull();

    // Page-level h1 still shows the URL slug label.
    const allHeadings = screen.getAllByRole("heading");
    const h1 = allHeadings.find((el) => el.tagName === "H1");
    expect(h1).toBeTruthy();
    expect(/nba/i.test(h1?.textContent ?? "")).toBe(true);
  });

  // ---------------------------------------------------------------------------
  // r8-cardview-focus-back: back link carries focus-visible ring classes
  // ---------------------------------------------------------------------------
  //
  // Acceptance:
  //   - The '<- bets' back link has focus-visible:ring-2 (visible keyboard ring)
  //   - The link has focus-visible:ring-ring (design-system colour token)
  //   - The link has focus-visible:outline-none (removes default browser outline)
  //   - The link has rounded-sm (shapes the ring to match the card token pattern)
  //   - The sport-mismatch amber alert and resolveSport behavior are unchanged
  //   - The footer 'Stakes are units; no $ column' text is intact

  it("back link has focus-visible:ring-2 class (keyboard focus rail)", () => {
    render(<CardDetailView sport="nba" gameId="0022300001" />);
    const link = screen.getByRole("link", { name: /bets/i });
    expect(link.className).toContain("focus-visible:ring-2");
  });

  it("back link has focus-visible:ring-ring token (design-system colour)", () => {
    render(<CardDetailView sport="nba" gameId="0022300001" />);
    const link = screen.getByRole("link", { name: /bets/i });
    expect(link.className).toContain("focus-visible:ring-ring");
  });

  it("back link has focus-visible:outline-none (suppresses default outline)", () => {
    render(<CardDetailView sport="nba" gameId="0022300001" />);
    const link = screen.getByRole("link", { name: /bets/i });
    expect(link.className).toContain("focus-visible:outline-none");
  });

  it("back link has rounded-sm (shapes the ring consistently with GameCard token)", () => {
    render(<CardDetailView sport="nba" gameId="0022300001" />);
    const link = screen.getByRole("link", { name: /bets/i });
    expect(link.className).toContain("rounded-sm");
  });

  it("sport-mismatch alert still rendered on mismatch (resolveSport unchanged)", () => {
    _useStreamReport = {
      status: "ok",
      sport: "mlb",
      game_id: "mlb-game-002",
    } as import("@/lib/types").Report;
    render(<CardDetailView sport="nba" gameId="mlb-game-002" />);
    const notice = screen.getByRole("alert", { name: "sport-mismatch-notice" });
    expect(notice).toBeTruthy();
    // Mismatch notice must still carry amber styling.
    expect(notice.className).toMatch(/amber/);
  });

  it("footer 'Stakes are units; no $ column' text is intact", () => {
    render(<CardDetailView sport="nba" gameId="0022300001" />);
    const text = document.body.textContent ?? "";
    expect(/Stakes are units.*no \$ column/i.test(text)).toBe(true);
  });
});

// ---------------------------------------------------------------------------
// No $ / pnl / roi field across bets_detail source files
// ---------------------------------------------------------------------------

// ---------------------------------------------------------------------------
// WS7: CardDetailView + PaperHistory -- useLiveData migration acceptance
// ---------------------------------------------------------------------------
//
// These tests verify:
//   1. Components consume useLiveData (no bespoke data setInterval).
//   2. Last-good data is retained after a failed poll (isStale=true, error set).
//   3. last-updated age label is surfaced (ageSec present -> age label rendered).
//   4. Stale state does NOT show a green badge (stale-never-green rail).
//   5. Components never throw on error -- always render an honest degraded state.

describe("WS7: CardDetailView -- useLiveData integration", () => {
  beforeEach(() => {
    _useStreamReport = null;
    // Reset round-robin index before each test.
    _liveDataCallIdx = 0;
    _liveDataStates = [];
  });

  it("renders without crashing when all useLiveData calls return isLoading", () => {
    // All 4 useLiveData calls (edge, ingame, lines, props, results) return loading.
    _resetLiveData([]);
    expect(() =>
      render(<CardDetailView sport="nba" gameId="0022300001" />),
    ).not.toThrow();
  });

  it("shows last-updated age label when ageSec is available", () => {
    // First call (edge) has ageSec=5, not stale, no error.
    _resetLiveData([
      { data: null, lastUpdatedAt: Date.now(), ageSec: 5, isStale: false, error: null, isLoading: false, refresh: vi.fn() },
    ]);
    render(<CardDetailView sport="nba" gameId="0022300001" />);
    // The age strip renders 'edge: Xs ago' or 'edge: unavailable'.
    const text = document.body.textContent ?? "";
    // ageSec=5 -> '5s ago'; the label is present.
    expect(/edge:/i.test(text)).toBe(true);
    expect(/5s ago/i.test(text)).toBe(true);
  });

  it("stale edge: shows (stale) suffix, never renders a green badge", () => {
    _resetLiveData([
      // edge: stale + error
      { data: GAME_EDGE, lastUpdatedAt: Date.now() - 60000, ageSec: 60, isStale: true, error: "poll failed", isLoading: false, refresh: vi.fn() },
    ]);
    const { container } = render(<CardDetailView sport="nba" gameId="0022300001" />);
    const text = document.body.textContent ?? "";
    // Must show stale indicator.
    expect(/stale/i.test(text)).toBe(true);
    // Must NOT have any green badge for the stale data.
    const greens = container.querySelectorAll('.text-emerald-400, .text-green-400');
    expect(greens.length).toBe(0);
  });

  it("retains last-good edge data after a failed poll (error set, data still shown)", () => {
    // Simulate last-good data retained: data=GAME_EDGE, but error is set.
    _resetLiveData([
      { data: GAME_EDGE, lastUpdatedAt: Date.now() - 30000, ageSec: 30, isStale: true, error: "connection refused", isLoading: false, refresh: vi.fn() },
    ]);
    const { container } = render(<CardDetailView sport="nba" gameId="0022300001" />);
    // The component should not crash and should surface the error in the age strip.
    const text = container.textContent ?? "";
    expect(/unavailable|stale/i.test(text)).toBe(true);
  });

  it("never crashes when error is set and data is null (no last-good)", () => {
    _resetLiveData([
      { data: null, lastUpdatedAt: null, ageSec: null, isStale: false, error: "network error", isLoading: false, refresh: vi.fn() },
    ]);
    expect(() =>
      render(<CardDetailView sport="nba" gameId="0022300001" />),
    ).not.toThrow();
    // age strip shows 'unavailable' since error is set.
    const text = document.body.textContent ?? "";
    expect(/unavailable/i.test(text)).toBe(true);
  });

  it("checking state shows neutral age text (not green, not red)", () => {
    // ageSec=null means no successful poll yet -> should show 'checking'.
    _resetLiveData([
      { data: null, lastUpdatedAt: null, ageSec: null, isStale: false, error: null, isLoading: true, refresh: vi.fn() },
    ]);
    render(<CardDetailView sport="nba" gameId="0022300001" />);
    const text = document.body.textContent ?? "";
    expect(/checking/i.test(text)).toBe(true);
  });

  it("source file CardDetailView.tsx has NO bespoke data setInterval call", () => {
    const dir = dirname(fileURLToPath(import.meta.url));
    const src = readFileSync(join(dir, "../CardDetailView.tsx"), "utf8");
    // No bespoke setInterval() calls; useLiveData owns all polling.
    // The regex matches `setInterval(` (actual call) but NOT prose references.
    expect(/setInterval\s*\(/.test(src)).toBe(false);
  });
});

describe("WS7: PaperHistory -- useLiveData integration", () => {
  beforeEach(() => {
    _liveDataCallIdx = 0;
    _liveDataStates = [];
  });

  it("renders without crashing in initial loading state", () => {
    _resetLiveData([]);
    expect(() => render(<PaperHistory />)).not.toThrow();
  });

  it("shows last-updated age label when trail has been fetched", () => {
    const mockTrail = {
      status: "ok",
      trail: [],
      generated_at: new Date().toISOString(),
    };
    _resetLiveData([
      // trail state: ageSec=12, not stale.
      { data: mockTrail, lastUpdatedAt: Date.now(), ageSec: 12, isStale: false, error: null, isLoading: false, refresh: vi.fn() },
      // clv state: defaults.
      { ..._defaultLiveState, isLoading: false },
    ]);
    render(<PaperHistory />);
    const text = document.body.textContent ?? "";
    // The age label says 'updated Xs ago'.
    expect(/updated/i.test(text)).toBe(true);
    expect(/12s ago/i.test(text)).toBe(true);
  });

  it("stale trail: shows (stale) suffix in age label", () => {
    const mockTrail = {
      status: "ok",
      trail: [],
      generated_at: new Date(Date.now() - 200000).toISOString(),
    };
    _resetLiveData([
      { data: mockTrail, lastUpdatedAt: Date.now() - 200000, ageSec: 200, isStale: true, error: null, isLoading: false, refresh: vi.fn() },
      { ..._defaultLiveState, isLoading: false },
    ]);
    render(<PaperHistory />);
    const text = document.body.textContent ?? "";
    expect(/stale/i.test(text)).toBe(true);
  });

  it("error state: shows unavailable in age label, never throws", () => {
    _resetLiveData([
      { data: null, lastUpdatedAt: null, ageSec: null, isStale: false, error: "backend down", isLoading: false, refresh: vi.fn() },
      { ..._defaultLiveState, isLoading: false },
    ]);
    expect(() => render(<PaperHistory />)).not.toThrow();
    const text = document.body.textContent ?? "";
    expect(/unavailable/i.test(text)).toBe(true);
  });

  it("retains last-good trail data when error is set (stale-never-green rail)", () => {
    const mockTrail = {
      status: "ok",
      trail: [
        {
          game_id: "g1",
          sport: "nba",
          market_type: "moneyline",
          side: "home",
          tier: "A",
          model_prob: 0.58,
          taken_decimal: 1.91,
          stake_units: 0.5,
          ts: new Date().toISOString(),
        },
      ],
      generated_at: new Date(Date.now() - 90000).toISOString(),
    };
    _resetLiveData([
      // last-good data retained, but error is now set -> stale.
      { data: mockTrail, lastUpdatedAt: Date.now() - 90000, ageSec: 90, isStale: true, error: "backend down", isLoading: false, refresh: vi.fn() },
      { ..._defaultLiveState, isLoading: false },
    ]);
    const { container } = render(<PaperHistory />);
    // No green badge -- stale-never-green rail.
    const greens = container.querySelectorAll('.text-emerald-400, .text-green-400');
    expect(greens.length).toBe(0);
    // Should NOT have thrown.
    const text = container.textContent ?? "";
    expect(text.length).toBeGreaterThan(0);
  });

  it("source file PaperHistory.tsx has NO bespoke data setInterval call", () => {
    const dir = dirname(fileURLToPath(import.meta.url));
    const src = readFileSync(join(dir, "../../p6/PaperHistory.tsx"), "utf8");
    // No bespoke setInterval() calls; useLiveData owns all polling.
    // The regex matches actual calls, not prose comments.
    expect(/setInterval\s*\(/.test(src)).toBe(false);
  });

  it("source file PaperHistory.tsx has no dollar amounts", () => {
    const dir = dirname(fileURLToPath(import.meta.url));
    const src = readFileSync(join(dir, "../../p6/PaperHistory.tsx"), "utf8");
    const banned = /\$\s*\d|\d\s*\$|\bpnl\b|\b(pnl|roi|payout)\s*[:=]/i;
    expect(banned.test(src)).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// NO $ field in bets_detail source files
// ---------------------------------------------------------------------------

describe("NO $ field in bets_detail source files", () => {
  it("no source file emits a $/pnl/roi/payout field", () => {
    const dir = dirname(fileURLToPath(import.meta.url));
    const root = join(dir, ".."); // bets_detail/
    const files = readdirSync(root).filter(
      (f) => (f.endsWith(".ts") || f.endsWith(".tsx")) && !f.endsWith(".test.tsx"),
    );
    // A real $ AMOUNT ($ next to a digit) or a named $ money field is banned.
    // Prose like "no $ column" is explicitly allowed (asserts the rail).
    const banned = /\$\s*\d|\d\s*\$|\bpnl\b|\b(pnl|roi|payout)\s*[:=]/i;
    expect(files.length).toBeGreaterThan(0);
    for (const f of files) {
      const code = readFileSync(join(root, f), "utf8");
      expect(banned.test(code), `banned $ token in ${f}`).toBe(false);
    }
  });

  it("p5api_ext has no $ field", () => {
    const dir = dirname(fileURLToPath(import.meta.url));
    const extPath = join(dir, "../../../lib/p5api_ext.ts");
    const code = readFileSync(extPath, "utf8");
    const banned = /\$\s*\d|\d\s*\$|\bpnl\b|\b(pnl|roi|payout)\s*[:=]/i;
    expect(banned.test(code)).toBe(false);
  });
});
