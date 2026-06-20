// executionTrailAdapter.test.ts -- vitest unit tests for linesMatrixToExecutionTrail.
//
// Per-file vitest test (NEVER run the full suite -- freezes the box).
// Run: cd /c/Users/neelj/nba-ai-system/webapp && npx vitest run components/bets_detail/__tests__/executionTrailAdapter.test.ts
//
// Acceptance criteria (WS5-card-detail-exec-trail):
//   1. Returns BookLineRow[] sorted descending by decimal_odds (best = highest odds first).
//   2. bestBook = book with the highest decimal_odds.
//   3. Best-marked entry is the first in the sorted array.
//   4. Threads devig.fair_prob + devig.vig_pct from the best line.
//   5. Threads decision + tier + stakeUnits + modelProb from the primary BestBet.
//   6. clvStatus = INSUFFICIENT_DATA when clv_is_proxy = true; else 'proxy'.
//   7. When matrix is null: bookLines = [], bestBook = null, devig = null.
//   8. When matrix is unavailable sentinel: bookLines = [], bestBook = null.
//   9. When matrix has no markets: bookLines = [], bestBook = null.
//  10. No $ field anywhere in the output shape.

import { describe, it, expect } from "vitest";
import type { LinesMatrix } from "@/lib/p5api_ext";
import type { GameEdge, BestBet } from "@/lib/types";
import {
  linesMatrixToExecutionTrail,
} from "../executionTrailAdapter";

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const NOW = new Date().toISOString();

const LINES_MATRIX: LinesMatrix = {
  status: "ok",
  sport: "nba",
  game_id: "0022300001",
  generated_at: NOW,
  markets: {
    moneyline: {
      market_type: "moneyline",
      sides: {
        home: [
          { book: "DraftKings", odds: 1.91, line: null, captured_at: null, is_pm: false },
          { book: "Kalshi", odds: 1.95, line: null, captured_at: null, is_pm: true },
          { book: "FanDuel", odds: 1.88, line: null, captured_at: null, is_pm: false },
        ],
        away: [
          { book: "DraftKings", odds: 2.05, line: null, captured_at: null, is_pm: false },
          { book: "Kalshi", odds: 2.00, line: null, captured_at: null, is_pm: true },
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
  clv_is_proxy: false,
  reason: "AST edge above threshold.",
};

const NO_BET_BET: BestBet = {
  ...BEST_BET,
  decision: "no_bet",
  stake_units: 0,
  flat_unit: 0,
  kelly_units: 0,
  tier: null,
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
// 1. Sort order: descending by decimal_odds
// ---------------------------------------------------------------------------

describe("linesMatrixToExecutionTrail -- sort order", () => {
  it("bookLines are sorted descending by decimal_odds (best = highest odds first)", () => {
    const result = linesMatrixToExecutionTrail(LINES_MATRIX, GAME_EDGE);
    const odds = result.bookLines
      .map((r) => r.decimal_odds ?? -Infinity);
    for (let i = 0; i < odds.length - 1; i++) {
      expect(
        odds[i],
        `index ${i} odds (${odds[i]}) should be >= index ${i + 1} odds (${odds[i + 1]})`,
      ).toBeGreaterThanOrEqual(odds[i + 1]);
    }
  });

  it("first entry is the best (highest decimal_odds) book", () => {
    const result = linesMatrixToExecutionTrail(LINES_MATRIX, GAME_EDGE);
    expect(result.bookLines.length).toBeGreaterThan(0);
    const first = result.bookLines[0];
    // DraftKings has 2.05 away (highest across all books/sides after dedup)
    expect(first.decimal_odds).toBeGreaterThanOrEqual(
      result.bookLines[result.bookLines.length - 1].decimal_odds ?? 0,
    );
  });
});

// ---------------------------------------------------------------------------
// 2. bestBook
// ---------------------------------------------------------------------------

describe("linesMatrixToExecutionTrail -- bestBook", () => {
  it("bestBook matches the book with the highest decimal_odds", () => {
    const result = linesMatrixToExecutionTrail(LINES_MATRIX, GAME_EDGE);
    expect(result.bestBook).not.toBeNull();
    // DraftKings has 2.05 on the away side -- highest single-side odds.
    expect(result.bestBook).toBe("DraftKings");
  });

  it("bestBook is the first bookLines entry's book name", () => {
    const result = linesMatrixToExecutionTrail(LINES_MATRIX, GAME_EDGE);
    if (result.bookLines.length > 0) {
      expect(result.bestBook).toBe(result.bookLines[0].book);
    }
  });
});

// ---------------------------------------------------------------------------
// 3. devig
// ---------------------------------------------------------------------------

describe("linesMatrixToExecutionTrail -- devig", () => {
  it("devig is not null when book lines exist", () => {
    const result = linesMatrixToExecutionTrail(LINES_MATRIX, GAME_EDGE);
    expect(result.devig).not.toBeNull();
  });

  it("devig.fair_prob is in (0,1) for a valid decimal odds quote", () => {
    const result = linesMatrixToExecutionTrail(LINES_MATRIX, GAME_EDGE);
    expect(result.devig!.fair_prob).toBeGreaterThan(0);
    expect(result.devig!.fair_prob).toBeLessThan(1);
  });

  it("devig.vig_pct is in [0,1)", () => {
    const result = linesMatrixToExecutionTrail(LINES_MATRIX, GAME_EDGE);
    expect(result.devig!.vig_pct).toBeGreaterThanOrEqual(0);
    expect(result.devig!.vig_pct).toBeLessThan(1);
  });

  it("devig.fair_prob = 1 / bestOdds (Shin inverse for single-leg)", () => {
    const result = linesMatrixToExecutionTrail(LINES_MATRIX, GAME_EDGE);
    // best odds = 2.05 (DraftKings away), fair_prob = 1/2.05 ~ 0.4878
    const expected = 1 / 2.05;
    expect(result.devig!.fair_prob).toBeCloseTo(expected, 4);
  });
});

// ---------------------------------------------------------------------------
// 4. Decision / tier / units threading
// ---------------------------------------------------------------------------

describe("linesMatrixToExecutionTrail -- decision + tier + units", () => {
  it("decision is 'bet' when BestBet.decision = bet", () => {
    const result = linesMatrixToExecutionTrail(LINES_MATRIX, GAME_EDGE);
    expect(result.decision).toBe("bet");
  });

  it("tier is threaded from the BestBet", () => {
    const result = linesMatrixToExecutionTrail(LINES_MATRIX, GAME_EDGE);
    expect(result.tier).toBe("A");
  });

  it("stakeUnits is threaded when decision = bet", () => {
    const result = linesMatrixToExecutionTrail(LINES_MATRIX, GAME_EDGE);
    expect(result.stakeUnits).toBe(0.5);
  });

  it("stakeUnits is null when decision = no_bet", () => {
    const edge: GameEdge = { ...GAME_EDGE, best_bets: [NO_BET_BET], candidates: [NO_BET_BET] };
    const result = linesMatrixToExecutionTrail(LINES_MATRIX, edge);
    expect(result.stakeUnits).toBeNull();
  });

  it("modelProb is threaded from the BestBet", () => {
    const result = linesMatrixToExecutionTrail(LINES_MATRIX, GAME_EDGE);
    expect(result.modelProb).toBeCloseTo(0.58, 4);
  });

  it("decisionNote is threaded from BestBet.reason", () => {
    const result = linesMatrixToExecutionTrail(LINES_MATRIX, GAME_EDGE);
    expect(result.decisionNote).toBe("AST edge above threshold.");
  });

  it("decision/tier/modelProb are null when edge is null", () => {
    const result = linesMatrixToExecutionTrail(LINES_MATRIX, null);
    expect(result.decision).toBeNull();
    expect(result.tier).toBeNull();
    expect(result.modelProb).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// 5. CLV status honesty
// ---------------------------------------------------------------------------

describe("linesMatrixToExecutionTrail -- clvStatus", () => {
  it("clvStatus = INSUFFICIENT_DATA when clv_is_proxy = true", () => {
    const proxyBet: BestBet = { ...BEST_BET, clv_is_proxy: true };
    const edge: GameEdge = { ...GAME_EDGE, best_bets: [proxyBet] };
    const result = linesMatrixToExecutionTrail(LINES_MATRIX, edge);
    expect(result.clvStatus).toBe("INSUFFICIENT_DATA");
  });

  it("clvStatus != INSUFFICIENT_DATA when clv_is_proxy = false", () => {
    const result = linesMatrixToExecutionTrail(LINES_MATRIX, GAME_EDGE);
    expect(result.clvStatus).not.toBe("INSUFFICIENT_DATA");
  });

  it("clvStatus is null when edge is null", () => {
    const result = linesMatrixToExecutionTrail(LINES_MATRIX, null);
    expect(result.clvStatus).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// 6. Null / unavailable / empty matrix -> honest empty bookLines
// ---------------------------------------------------------------------------

describe("linesMatrixToExecutionTrail -- honest empty states", () => {
  it("null matrix -> bookLines = [], bestBook = null, devig = null", () => {
    const result = linesMatrixToExecutionTrail(null, GAME_EDGE);
    expect(result.bookLines).toEqual([]);
    expect(result.bestBook).toBeNull();
    expect(result.devig).toBeNull();
  });

  it("unavailable sentinel matrix -> bookLines = [], bestBook = null", () => {
    const unavail = { status: "unavailable" as const, reason: "feed down" } as unknown as LinesMatrix;
    const result = linesMatrixToExecutionTrail(unavail, GAME_EDGE);
    expect(result.bookLines).toEqual([]);
    expect(result.bestBook).toBeNull();
  });

  it("empty markets matrix -> bookLines = [], bestBook = null, devig = null", () => {
    const empty: LinesMatrix = { ...LINES_MATRIX, markets: {} };
    const result = linesMatrixToExecutionTrail(empty, GAME_EDGE);
    expect(result.bookLines).toEqual([]);
    expect(result.bestBook).toBeNull();
    expect(result.devig).toBeNull();
  });

  it("null matrix still threads edge decision (not null)", () => {
    const result = linesMatrixToExecutionTrail(null, GAME_EDGE);
    // Even with no book lines, decision/tier/units from edge are still threaded.
    expect(result.decision).toBe("bet");
    expect(result.tier).toBe("A");
    expect(result.modelProb).toBeCloseTo(0.58, 4);
  });
});

// ---------------------------------------------------------------------------
// 7. No $ field in the output
// ---------------------------------------------------------------------------

describe("linesMatrixToExecutionTrail -- honesty rail: no $ field", () => {
  it("output shape has no dollar-sign field names or values", () => {
    const result = linesMatrixToExecutionTrail(LINES_MATRIX, GAME_EDGE);
    const json = JSON.stringify(result);
    // A real $ amount ($ next to a digit) or a named dollar field is banned.
    expect(/\$\s*\d|\d\s*\$|\bpnl\b|\broi\b|\bpayout\b/i.test(json)).toBe(false);
  });

  it("bookLines rows have no $ field (units/probability only)", () => {
    const result = linesMatrixToExecutionTrail(LINES_MATRIX, GAME_EDGE);
    for (const row of result.bookLines) {
      const keys = Object.keys(row);
      for (const k of keys) {
        expect(/\$|pnl|roi|payout/i.test(k)).toBe(false);
      }
    }
  });
});

// ---------------------------------------------------------------------------
// 8. Multi-market: bookLines de-dup keeps highest odds per book
// ---------------------------------------------------------------------------

describe("linesMatrixToExecutionTrail -- multi-market de-dup", () => {
  it("de-duplication keeps highest decimal_odds per book across markets", () => {
    const multiMarket: LinesMatrix = {
      ...LINES_MATRIX,
      markets: {
        moneyline: {
          market_type: "moneyline",
          sides: {
            home: [
              { book: "DraftKings", odds: 1.91, line: null, captured_at: null, is_pm: false },
            ],
          },
          best: { home: { book: "DraftKings", odds: 1.91 } },
        },
        spread: {
          market_type: "spread",
          sides: {
            home: [
              // Same book, higher odds -- should win de-dup.
              { book: "DraftKings", odds: 1.98, line: -5.5, captured_at: null, is_pm: false },
            ],
          },
          best: { home: { book: "DraftKings", odds: 1.98 } },
        },
      },
    };
    const result = linesMatrixToExecutionTrail(multiMarket, GAME_EDGE);
    // Should have exactly one entry for DraftKings.
    const dk = result.bookLines.filter((r) => r.book === "DraftKings");
    expect(dk.length).toBe(1);
    // The kept entry must be the higher odds (1.98).
    expect(dk[0].decimal_odds).toBeCloseTo(1.98, 4);
  });
});
