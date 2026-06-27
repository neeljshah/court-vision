// PlacedBetsForGamePanel + BetsMoneyHeadline -- execution-hand-in-hand tests.
//
// Per-file vitest test (NEVER run the full suite -- freezes the box).
// Run: cd /c/Users/neelj/nba-ai-system/webapp && npx vitest run components/bets_detail/__tests__/placed-bets-for-game.test.tsx
//
// Covers:
//   * PlacedBetsForGamePanel: filters the paper trail to THIS game_id; renders
//     placed bets with units / tier / outcome / CLV; links to /paper/[betId];
//     honest-empty when nothing was staked; INSUFFICIENT_DATA CLV never greened;
//     drops bets for other games; no $ anywhere.
//   * BetsMoneyHeadline: renders net paper P&L (units), bankroll, record, mean
//     CLV honestly (INSUFFICIENT_DATA passthrough); no $ in DOM.

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import type { PaperTrail, PaperTrailRow, PnlSeries, PaperBankroll, ClvScoreboard } from "@/lib/types";

// --- controllable useLiveData mock (round-robin per call) -------------------
interface MockLiveState {
  data: unknown;
  lastUpdatedAt: number | null;
  ageSec: number | null;
  isStale: boolean;
  error: string | null;
  isLoading: boolean;
  refresh: () => void;
}
const _default: MockLiveState = {
  data: null, lastUpdatedAt: null, ageSec: null,
  isStale: false, error: null, isLoading: false, refresh: vi.fn(),
};
let _states: MockLiveState[] = [];
let _idx = 0;
function setStates(states: Partial<MockLiveState>[]) {
  _states = states.map((s) => ({ ..._default, ...s }));
  _idx = 0;
}

vi.mock("@/lib/useLiveData", () => ({
  useLiveData: () => _states[_idx++] ?? { ..._default },
}));

vi.mock("@/lib/p5api", () => ({
  api: {
    getPaperTrail: vi.fn(),
    getPaperPnlSeries: vi.fn(),
    getPaperBankroll: vi.fn(),
    getPaperClv: vi.fn(),
  },
  isUnavailable: (x: unknown) =>
    !!(x && typeof x === "object" && (x as { status?: string }).status === "unavailable"),
}));

import { PlacedBetsForGamePanel } from "../PlacedBetsForGamePanel";
import { BetsMoneyHeadline } from "@/components/bets/BetsMoneyHeadline";

function row(over: Partial<PaperTrailRow>): PaperTrailRow {
  return {
    game_id: "G1", matchup: "AAA @ BBB", sport: "nba", side: "home",
    market_type: "moneyline", line: null, taken_book: "fanduel",
    taken_decimal: 1.91, model_prob: 0.56, model_ev: 0.07, tier: "B",
    stake_units: 1.25, status: "settled", graded: true, outcome: "win",
    clv_pct: 0.012, beat_close: true, clv_is_proxy: false, clv_status: "true_close",
    clv_unavailable: false, clv_note: null, executed: false, ts: "2026-06-20T00:00:00Z",
    settled_at: "2026-06-20T03:00:00Z", ...over,
  };
}

function trail(rows: PaperTrailRow[]): PaperTrail {
  return { status: "ok", count: rows.length, trail: rows };
}

beforeEach(() => {
  _states = [];
  _idx = 0;
});

describe("PlacedBetsForGamePanel", () => {
  it("renders placed bets for this game with units/tier/outcome/CLV", () => {
    setStates([{ data: trail([row({})]), ageSec: 5 }]);
    render(<PlacedBetsForGamePanel sport="nba" gameId="G1" />);
    expect(screen.getByTestId("placed-bet-row")).toBeInTheDocument();
    expect(screen.getByTestId("placed-units")).toHaveTextContent("1.25u");
    expect(screen.getByTestId("placed-tier")).toHaveTextContent("B");
    expect(screen.getByText("win")).toBeInTheDocument();
    expect(screen.getByTestId("placed-clv")).toHaveTextContent("+1.2%");
    expect(screen.getByTestId("placed-total-units")).toHaveTextContent("1.25u");
  });

  it("links each row to its /paper/[betId] execution detail", () => {
    setStates([{ data: trail([row({})]), ageSec: 5 }]);
    render(<PlacedBetsForGamePanel sport="nba" gameId="G1" />);
    const link = screen.getByRole("link", { name: /Execution detail/i });
    expect(link.getAttribute("href")).toMatch(/^\/paper\//);
  });

  it("excludes bets that belong to other games", () => {
    setStates([{ data: trail([row({ game_id: "OTHER", stake_units: 9 })]), ageSec: 5 }]);
    render(<PlacedBetsForGamePanel sport="nba" gameId="G1" />);
    expect(screen.queryByTestId("placed-bet-row")).not.toBeInTheDocument();
    expect(screen.getByText(/Nothing staked for this game/i)).toBeInTheDocument();
  });

  it("shows INSUFFICIENT_DATA CLV honestly (never greened)", () => {
    setStates([{
      data: trail([row({ clv_pct: null, clv_unavailable: true, clv_status: "no_close", outcome: null, status: "open", graded: false })]),
      ageSec: 5,
    }]);
    render(<PlacedBetsForGamePanel sport="nba" gameId="G1" />);
    expect(screen.getByTestId("placed-clv")).toHaveTextContent("INSUFFICIENT_DATA");
    expect(screen.getByText("pending")).toBeInTheDocument();
  });

  it("honest-empty when the trail has no staked bets for the game", () => {
    setStates([{ data: trail([row({ stake_units: 0 })]), ageSec: 5 }]);
    render(<PlacedBetsForGamePanel sport="nba" gameId="G1" />);
    expect(screen.getByText(/Nothing staked for this game/i)).toBeInTheDocument();
  });

  it("renders no dollar-amount string ($N) in the DOM", () => {
    setStates([{ data: trail([row({})]), ageSec: 5 }]);
    const { container } = render(<PlacedBetsForGamePanel sport="nba" gameId="G1" />);
    expect(container.textContent ?? "").not.toMatch(/\$\s?\d/);
  });
});

describe("BetsMoneyHeadline", () => {
  const pnl: PnlSeries = {
    start_units: 100,
    points: [
      { ts: null, day: null, balance_units: 100, daily_units: 0, cumulative_units: 0, n_bets: 0, n_win: 0, n_loss: 0 },
      { ts: null, day: null, balance_units: 104.5, daily_units: 4.5, cumulative_units: 4.5, n_bets: 12, n_win: 7, n_loss: 5 },
    ],
    daily: [],
    summary: {
      total_units: 4.5, n_bets: 12, n_win: 7, n_loss: 5, n_push: 0,
      win_rate: 0.583, mean_clv_pct_or_INSUFFICIENT: 0.008, current_units: 104.5,
    },
    edge_claimed: false, executed: false, status: "ok",
  };
  const bank: PaperBankroll = { start_units: 100, current_units: 104.5, updated_at: null };
  const clv: ClvScoreboard = { n_bets: 12, pct_beat_close: 0.6, mean_clv_pct: 0.008, by_sport: {}, clv_is_proxy: false } as ClvScoreboard;

  it("renders net paper P&L, bankroll, record from the series", () => {
    setStates([{ data: pnl }, { data: bank }, { data: clv }]);
    render(<BetsMoneyHeadline />);
    expect(screen.getByTestId("money-net-units")).toHaveTextContent("+4.50u");
    expect(screen.getByTestId("money-bankroll")).toHaveTextContent("104.50u");
    expect(screen.getByTestId("money-record")).toHaveTextContent("7-5");
    expect(screen.getByTestId("money-clv")).toHaveTextContent("+0.8%");
  });

  it("shows mean CLV INSUFFICIENT_DATA honestly", () => {
    const pnl2: PnlSeries = {
      ...pnl,
      summary: { ...pnl.summary, mean_clv_pct_or_INSUFFICIENT: "INSUFFICIENT_DATA" },
    };
    setStates([{ data: pnl2 }, { data: bank }, { data: { n_bets: 0 } as ClvScoreboard }]);
    render(<BetsMoneyHeadline />);
    expect(screen.getByTestId("money-clv")).toHaveTextContent("INSUFFICIENT_DATA");
  });

  it("renders no dollar-amount string ($N) in the DOM", () => {
    setStates([{ data: pnl }, { data: bank }, { data: clv }]);
    const { container } = render(<BetsMoneyHeadline />);
    expect(container.textContent ?? "").not.toMatch(/\$\s?\d/);
  });
});
