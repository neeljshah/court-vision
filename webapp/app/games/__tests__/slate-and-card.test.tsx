// slate-and-card.test.tsx -- RTL render guards for the /games hub: SlateCards
// (per-sport slate that degrades INDEPENDENTLY to honest empty) and GameCard
// (one coherent prediction + key markets + best-bet chip in UNITS or honest
// NO BET). Complements the pure card-utils unit tests by rendering the DOM.
//
// Covered:
//   * a sport with live games renders GameCards; tennis (offseason) renders an
//     honest empty line, NEVER a fabricated slate
//   * an Unavailable predict envelope renders an honest Unavailable, not a slate
//   * GameCard shows the coherent pick (prob), key market rows, and a best-bet
//     chip in UNITS+tier -- or an honest "no bet (below floor)"
//   * COHERENCE: the displayed pick prob == the max pregame_probs value
//   * missing pick prob -> "--"; below-floor edge -> NO BET; NO $ rendered
//
// api is mocked so no network is hit. This lane does NOT edit source/shared
// components; shared-component bugs are REPORTED.

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, within, waitFor } from "@testing-library/react";

import type {
  PredictEnvelope,
  PredictRecord,
  GameEdge,
  BestBetsEnvelope,
} from "@/lib/api";

// --- mock the api layer (both SlateCards@/lib/api and GameCard@/lib/p5api) ---
const getPredict = vi.fn();
const bestbets = vi.fn();

vi.mock("@/lib/api", async (orig) => {
  const real = (await orig()) as Record<string, unknown>;
  return {
    ...real,
    api: { getPredict: (...a: unknown[]) => getPredict(...a), bestbets: (...a: unknown[]) => bestbets(...a) },
  };
});

import { SlateCards } from "../SlateCards";
import { GameCard } from "../GameCard";

// --- fixtures ---------------------------------------------------------------

function predRec(over: Partial<PredictRecord> = {}): PredictRecord {
  return {
    sport: "nba",
    game_id: "0042600401",
    home: "San Antonio Spurs",
    away: "New York Knicks",
    tipoff: "2026-06-19T00:30Z",
    pregame_probs: { home_ml: 0.585, away_ml: 0.415 },
    markets: [
      {
        sport: "nba",
        game_id: "0042600401",
        market_type: "moneyline",
        side: "home",
        line: null,
        odds: 1.71,
        book: "dk",
        devigged_prob: 0.585,
        captured_at: null,
        is_close: false,
        clv_is_proxy: true,
      },
      {
        sport: "nba",
        game_id: "0042600401",
        market_type: "total",
        side: "over",
        line: 221.5,
        odds: 1.9,
        book: "dk",
        devigged_prob: 0.51,
        captured_at: null,
        is_close: false,
        clv_is_proxy: false,
      },
    ],
    leak_guard: { in_sample: false },
    produced_at: null,
    ...over,
  };
}

function okEnv(preds: PredictRecord[]): PredictEnvelope {
  return {
    status: "ok",
    sport: "nba",
    generated_at: "2026-06-19T00:00Z",
    predictions: preds,
  };
}

function bet(over = {}) {
  return {
    market_type: "moneyline",
    side: "home",
    model_prob: 0.585,
    market_prob: 0.55,
    best_book: "dk",
    best_odds: 1.71,
    line: null,
    edge: 0.035,
    ev: 0.03,
    tier: "B",
    decision: "bet",
    stake_units: 1.5,
    flat_unit: 1,
    kelly_units: 0.5,
    clv_is_proxy: true,
    ...over,
  };
}

const pct = (p: number) => `${(p * 100).toFixed(1)}%`;

function assertNoDollar(c: HTMLElement) {
  expect(c.textContent || "").not.toMatch(/\$\s*\d/);
}

// --- GameCard (pure render, no fetch) ---------------------------------------

describe("GameCard -- one coherent prediction + units chip", () => {
  it("renders the coherent pick (highest-prob side + name + prob)", () => {
    const { container } = render(
      <GameCard sport="nba" rec={predRec()} edge={null} />,
    );
    // Home team appears both in the "away @ home" matchup line and the pick.
    expect(screen.getAllByText(/San Antonio Spurs/).length).toBeGreaterThan(0);
    // COHERENCE: displayed pick prob equals fmtPct of the max pregame_prob.
    expect(screen.getByText(pct(0.585))).toBeInTheDocument();
    assertNoDollar(container);
  });

  it("renders key market rows (devigged probability, no $)", () => {
    render(<GameCard sport="nba" rec={predRec()} edge={null} />);
    const list = screen.getByLabelText(/key markets/i);
    expect(within(list).getByText(/moneyline home/i)).toBeInTheDocument();
    expect(within(list).getByText(/total over 221\.5/i)).toBeInTheDocument();
  });

  it("renders a UNITS + tier best-bet chip from a real bet edge", () => {
    const edge: GameEdge = {
      game_id: "0042600401",
      status: "ok",
      best_bets: [bet({ tier: "A", stake_units: 2.25 })],
    };
    const { container } = render(
      <GameCard sport="nba" rec={predRec()} edge={edge} />,
    );
    expect(screen.getByText(/tier A/i)).toBeInTheDocument();
    expect(screen.getByText(/2\.25u/)).toBeInTheDocument();
    assertNoDollar(container);
  });

  it("renders an honest NO BET chip when no edge clears the floor", () => {
    const edge: GameEdge = {
      game_id: "0042600401",
      status: "ok",
      best_bets: [],
    };
    render(<GameCard sport="nba" rec={predRec()} edge={edge} />);
    expect(screen.getByText(/no bet \(below floor\)/i)).toBeInTheDocument();
  });

  it("renders NO BET for an unavailable edge (no fabricated tier)", () => {
    render(
      <GameCard
        sport="nba"
        rec={predRec()}
        edge={{ game_id: "0042600401", status: "unavailable", reason: "x" }}
      />,
    );
    expect(screen.getByText(/no bet \(below floor\)/i)).toBeInTheDocument();
    expect(screen.queryByText(/tier [A-D]/i)).toBeNull();
  });

  it("renders '--' for a pick when no pregame prob is present", () => {
    render(
      <GameCard
        sport="nba"
        rec={predRec({ pregame_probs: {} })}
        edge={null}
      />,
    );
    expect(screen.getByText("--")).toBeInTheDocument();
  });

  it("flags an in-sample (leak) record honestly", () => {
    render(
      <GameCard
        sport="nba"
        rec={predRec({ leak_guard: { in_sample: true } })}
        edge={null}
      />,
    );
    expect(screen.getByText(/in-sample/i)).toBeInTheDocument();
  });

  it("links to the per-game detail route", () => {
    render(<GameCard sport="nba" rec={predRec()} edge={null} />);
    const link = screen.getByRole("link");
    expect(link).toHaveAttribute("href", "/games/nba/0042600401");
  });
});

// --- SlateCards (mocked fetch) ----------------------------------------------

describe("SlateCards -- per-sport honest degradation", () => {
  beforeEach(() => {
    getPredict.mockReset();
    bestbets.mockReset();
  });

  it("renders live nba games and an honest offseason line for tennis", async () => {
    getPredict.mockImplementation((sport: string) => {
      if (sport === "nba") return Promise.resolve(okEnv([predRec()]));
      if (sport === "tennis")
        return Promise.resolve({
          status: "offseason",
          sport: "tennis",
          generated_at: null,
          reason: "no live tennis slate (offseason)",
        } as PredictEnvelope);
      // other sports: empty ok env
      return Promise.resolve(okEnv([]));
    });
    bestbets.mockResolvedValue({
      status: "unavailable",
      reason: "no bestbets",
    });

    const { container } = render(<SlateCards />);

    await waitFor(() =>
      expect(screen.getAllByText(/San Antonio Spurs/).length).toBeGreaterThan(0),
    );
    // tennis shows an honest empty line, not a fabricated slate.
    expect(
      screen.getByText(/no live tennis slate \(offseason\)/i),
    ).toBeInTheDocument();
    assertNoDollar(container);
  });

  it("renders an honest Unavailable when a predict envelope is unavailable", async () => {
    getPredict.mockImplementation((sport: string) =>
      sport === "nba"
        ? Promise.resolve({ status: "unavailable", reason: "predict api down" })
        : Promise.resolve(okEnv([])),
    );
    bestbets.mockResolvedValue({ status: "unavailable", reason: "x" });

    render(<SlateCards />);
    await waitFor(() =>
      expect(screen.getByText(/predict api down/i)).toBeInTheDocument(),
    );
  });

  it("attaches the best-bet chip from the bestbets envelope to the card", async () => {
    getPredict.mockImplementation((sport: string) =>
      sport === "nba"
        ? Promise.resolve(okEnv([predRec()]))
        : Promise.resolve(okEnv([])),
    );
    bestbets.mockImplementation((sport: string) => {
      if (sport === "nba") {
        const env: BestBetsEnvelope = {
          sport: "nba",
          generated_at: "x",
          status: "ok",
          count: 1,
          n_best_bets: 1,
          games: [
            {
              game_id: "0042600401",
              status: "ok",
              best_bets: [bet({ tier: "A", stake_units: 3 })],
            },
          ],
        } as unknown as BestBetsEnvelope;
        return Promise.resolve(env);
      }
      return Promise.resolve({ status: "unavailable", reason: "x" });
    });

    render(<SlateCards />);
    await waitFor(() => expect(screen.getByText(/tier A/i)).toBeInTheDocument());
    expect(screen.getByText(/3\.00u/)).toBeInTheDocument();
  });
});
