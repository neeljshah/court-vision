import { describe, it, expect } from "vitest";
import { readdirSync, readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import {
  coherentPick,
  keyMarkets,
  bestBetChip,
  sportLabel,
} from "../card-utils";
import type { PredictRecord, GameEdge, BestBet } from "@/lib/p5api";

// ---------------------------------------------------------------------------
// Honesty-rail tests for the /games hub card helpers. These gate:
//   * the coherent pick is a probability-only headline (never a $ figure)
//   * a missing probability degrades to null, never a fabricated number
//   * the best-bet chip is a real 'bet' (units) or an honest no_bet -- never a
//     fabricated tier from an unavailable / below-floor edge
//   * no /games source file emits a $/pnl/roi/bankroll field (units only)
// ---------------------------------------------------------------------------

function rec(over: Partial<PredictRecord> = {}): PredictRecord {
  return {
    sport: "nba",
    game_id: "g1",
    home: "San Antonio Spurs",
    away: "New York Knicks",
    tipoff: "2026-06-14T00:30Z",
    pregame_probs: { home_ml: 0.5855, away_ml: 0.4145 },
    markets: [],
    leak_guard: { in_sample: false },
    produced_at: null,
    ...over,
  };
}

describe("coherentPick -- probability-only headline", () => {
  it("picks the highest-probability side and maps it to a team name", () => {
    const p = coherentPick(rec());
    expect(p.side).toBe("home");
    expect(p.teamLabel).toBe("San Antonio Spurs");
    expect(p.prob).toBeCloseTo(0.5855, 4);
  });

  it("supports a draw side (soccer tri-outcome)", () => {
    const p = coherentPick(
      rec({ pregame_probs: { home_ml: 0.3, away_ml: 0.3, draw: 0.4 } }),
    );
    expect(p.side).toBe("draw");
    expect(p.prob).toBeCloseTo(0.4, 4);
  });

  it("degrades to null prob (never a fabricated number) when none present", () => {
    const p = coherentPick(rec({ pregame_probs: {} }));
    expect(p.prob).toBeNull();
  });
});

describe("keyMarkets -- de-dupes and caps", () => {
  it("returns at most the limit and drops duplicate market+side+line", () => {
    const m = (mt: string, side: string, line: number | null) => ({
      sport: "nba",
      game_id: "g1",
      market_type: mt,
      side,
      line,
      odds: 1.9,
      book: "x",
      devigged_prob: 0.5,
      captured_at: null,
      is_close: false,
      clv_is_proxy: true,
    });
    const r = rec({
      markets: [
        m("moneyline", "home", null),
        m("moneyline", "home", null), // dup
        m("total", "over", 220),
        m("total", "under", 220),
      ],
    });
    expect(keyMarkets(r, 3)).toHaveLength(3);
  });
});

describe("bestBetChip -- units or honest no_bet, never a fabricated tier", () => {
  const bet = (over: Partial<BestBet> = {}): BestBet => ({
    market_type: "moneyline",
    side: "home",
    model_prob: 0.6,
    market_prob: 0.55,
    best_book: "dk",
    best_odds: 1.9,
    line: null,
    edge: 0.05,
    ev: 0.04,
    tier: "B",
    decision: "bet",
    stake_units: 1.25,
    flat_unit: 1,
    kelly_units: 0.25,
    clv_is_proxy: true,
    ...over,
  });

  it("returns the highest-units 'bet' decision with units (no $)", () => {
    const edge: GameEdge = {
      game_id: "g1",
      status: "ok",
      best_bets: [bet({ stake_units: 0.5 }), bet({ tier: "A", stake_units: 2 })],
    };
    const chip = bestBetChip(edge);
    expect(chip.decision).toBe("bet");
    expect(chip.tier).toBe("A");
    expect(chip.stakeUnits).toBe(2);
  });

  it("returns honest no_bet for an unavailable edge", () => {
    const chip = bestBetChip({
      game_id: "g1",
      status: "unavailable",
      reason: "x",
    });
    expect(chip.decision).toBe("no_bet");
    expect(chip.tier).toBeNull();
    expect(chip.stakeUnits).toBeNull();
  });

  it("returns honest no_bet when no candidate clears the floor", () => {
    const edge: GameEdge = { game_id: "g1", status: "ok", best_bets: [] };
    expect(bestBetChip(edge).decision).toBe("no_bet");
    expect(bestBetChip(null).decision).toBe("no_bet");
  });
});

describe("sportLabel", () => {
  it("renders soccer_intl distinctly and upper-cases the rest", () => {
    expect(sportLabel("soccer_intl")).toBe("SOCCER (INTL)");
    expect(sportLabel("nba")).toBe("NBA");
  });
});

describe("no /games source file emits a $/pnl/roi/bankroll field", () => {
  it("source scan of app/games is clean of dollar/pnl/roi/bankroll output", () => {
    const testDir = dirname(fileURLToPath(import.meta.url));
    const root = join(testDir, "..");
    const banned = /\bpnl\b|\bbankroll\b|\$\{?[a-zA-Z_]*?(pnl|roi|profit|dollars?)\b/i;
    const offenders: string[] = [];
    const walk = (dir: string) => {
      for (const e of readdirSync(dir, { withFileTypes: true })) {
        if (e.name === "__tests__") continue;
        const full = join(dir, e.name);
        if (e.isDirectory()) walk(full);
        else if (/\.(tsx?|ts)$/.test(e.name)) {
          if (banned.test(readFileSync(full, "utf8"))) offenders.push(e.name);
        }
      }
    };
    walk(root);
    expect(offenders).toEqual([]);
  });
});
