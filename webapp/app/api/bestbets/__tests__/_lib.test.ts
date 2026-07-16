// _lib.test.ts -- the digest-file -> GameEdge/BestBetsEnvelope reshape used by
// GET /api/bestbets/[sport](/[gameId]). Mocks node:fs so no real disk I/O.

import { describe, it, expect, vi, beforeEach } from "vitest";

const FIXTURE = {
  card_count: 2,
  cards: [
    {
      game_id: "G1",
      matchup: "Away Team vs Home Team",
      sport: "mlb",
      market_type: "moneyline",
      side: "home",
      model_prob: 0.6,
      market_prob: 0.5,
      best_book: "kalshi",
      best_odds: 2.0,
      line: null,
      edge_vs_market: 0.1,
      units: 1,
      tier: "A",
      decision: "bet",
      clv_is_proxy: true,
      clv: { clv_status: "INSUFFICIENT_DATA" },
      status: "pregame",
    },
    {
      game_id: "G2",
      matchup: "Other vs Team",
      sport: "nba",
      market_type: "moneyline",
      side: "away",
      model_prob: 0.4,
      market_prob: 0.45,
      best_book: "fanduel",
      best_odds: 1.9,
      line: null,
      edge_vs_market: -0.05,
      units: 1,
      tier: null,
      decision: "no_bet",
      clv_is_proxy: false,
      clv: { clv_status: "INSUFFICIENT_DATA" },
      status: "pregame",
    },
  ],
};

vi.mock("node:fs", () => {
  const promises = {
    stat: vi.fn(async () => ({ mtimeMs: 123, mtime: new Date("2026-07-15T00:00:00Z") })),
    readFile: vi.fn(async () => JSON.stringify(FIXTURE)),
  };
  return { promises, default: { promises } };
});

describe("bestbets _lib", () => {
  beforeEach(() => {
    vi.resetModules();
  });

  it("groups cards by sport + game_id and splits home/away from matchup", async () => {
    const { getBestBetsForSport } = await import("../_lib");
    const env = await getBestBetsForSport("mlb");
    expect(env?.status).toBe("ok");
    expect(env?.games).toHaveLength(1);
    const g = env!.games[0];
    expect(g.game_id).toBe("G1");
    expect(g.away).toBe("Away Team");
    expect(g.home).toBe("Home Team");
    expect(g.best_bets).toHaveLength(1); // only decision='bet' candidates
    expect(g.candidates).toHaveLength(1);
    expect(g.best_bets[0].stake_units).toBe(1);
    expect(env?.generated_at).toBe("2026-07-15T00:00:00.000Z");
  });

  it("filters a no_bet-only game out of best_bets but keeps it in candidates", async () => {
    const { getBestBetsForSport } = await import("../_lib");
    const env = await getBestBetsForSport("nba");
    const g = env!.games[0];
    expect(g.best_bets).toHaveLength(0);
    expect(g.candidates).toHaveLength(1);
    expect(g.candidates[0].decision).toBe("no_bet");
  });

  it("bestbetsGame returns unavailable for an unknown game_id", async () => {
    const { getBestBetsForGame } = await import("../_lib");
    const missing = await getBestBetsForGame("mlb", "nope");
    expect(missing?.status).toBe("unavailable");
  });

  it("degrades to null when the digest file is missing", async () => {
    const fs = await import("node:fs");
    (fs.promises.stat as ReturnType<typeof vi.fn>).mockRejectedValueOnce(new Error("ENOENT"));
    const { getBestBetsForSport } = await import("../_lib");
    const env = await getBestBetsForSport("mlb");
    expect(env).toBeNull();
  });
});
