// _lib.ts -- shared reader for GET /api/bestbets/[sport](/[gameId]).
//
// Reads data/frontend/best_bets.json (written fresh every ~5min by the m10
// daemon) straight off disk and reshapes it into the GameEdge/BestBetsEnvelope
// shape the webapp already renders (same shape the :8099 live
// /api/v1/bestbets/{sport} route served, minus the >45s synchronous compute
// that wedges the event loop -- see docs/research/execution-quality/
// live_coherence_audit_2026-07-15.md). READ-ONLY: never writes data/.
//
// Cached in module scope keyed by the file's mtime -- a cheap fs.stat on every
// request, re-parsed only when the digest actually changes.

import { promises as fs } from "node:fs";
import path from "node:path";

export const BEST_BETS_PATH = path.join(
  process.cwd(),
  process.cwd().endsWith("webapp") ? ".." : ".",
  "data",
  "frontend",
  "best_bets.json",
);

// One flat card as written by the m10 digest (frontend.exec_decision shape).
type Card = {
  game_id: string;
  matchup?: string;
  sport: string;
  market_type: string;
  side: string;
  model_prob: number;
  market_prob: number | null;
  best_book: string;
  best_odds: number;
  line: number | null;
  edge_vs_market: number | null;
  units: number;
  tier: string | null;
  decision: string;
  clv_is_proxy: boolean;
  clv?: { beat_close?: unknown; clv_is_proxy?: boolean; clv_pct?: unknown; clv_status?: string };
  status: string;
  reason?: string;
  honest_note?: string;
  edge_claimed?: boolean;
};

type Digest = { card_count: number; cards: Card[] };

let cache: { mtimeMs: number; digest: Digest } | null = null;

async function readDigest(): Promise<{ digest: Digest; generatedAt: string } | null> {
  let stat;
  try {
    stat = await fs.stat(BEST_BETS_PATH);
  } catch {
    return null;
  }
  if (!cache || cache.mtimeMs !== stat.mtimeMs) {
    try {
      const raw = await fs.readFile(BEST_BETS_PATH, "utf-8");
      cache = { mtimeMs: stat.mtimeMs, digest: JSON.parse(raw) as Digest };
    } catch {
      return null;
    }
  }
  return { digest: cache.digest, generatedAt: stat.mtime.toISOString() };
}

// A card's `units` IS the flat-unit stake (see the digest's own honest_note:
// "units = flat_unit from policy"). The digest carries no separate
// kelly_units/ev/stake_units breakout -- approximate both with the same
// probability-space figure the digest already validated.
// ponytail: approximation ceiling: kelly_units/flat_unit/stake_units/ev all
// collapse to the digest's units/edge_vs_market. Upgrade if the digest ever
// starts writing the full breakout, no need to reverse the live route for it.
function cardToBestBet(c: Card) {
  return {
    market_type: c.market_type,
    side: c.side,
    model_prob: c.model_prob,
    market_prob: c.market_prob ?? 0,
    best_book: c.best_book,
    best_odds: c.best_odds,
    line: c.line ?? null,
    edge: c.edge_vs_market ?? null,
    ev: c.edge_vs_market ?? 0,
    tier: c.tier,
    decision: c.decision,
    stake_units: c.units,
    flat_unit: c.units,
    kelly_units: c.units,
    clv_is_proxy: c.clv_is_proxy,
    reason: c.reason,
  };
}

function matchupParts(matchup?: string): { away?: string; home?: string } {
  if (!matchup) return {};
  const parts = matchup.split(" vs ");
  if (parts.length !== 2) return {};
  return { away: parts[0], home: parts[1] };
}

export type GameEdgeDoc = {
  game_id: string;
  home?: string;
  away?: string;
  status: string;
  candidates: ReturnType<typeof cardToBestBet>[];
  best_bets: ReturnType<typeof cardToBestBet>[];
  clv?: Card["clv"];
  reason?: string;
};

function buildGames(cards: Card[], sport: string): GameEdgeDoc[] {
  const bySport = cards.filter((c) => c.sport === sport);
  const byGame = new Map<string, Card[]>();
  for (const c of bySport) {
    const arr = byGame.get(c.game_id) ?? [];
    arr.push(c);
    byGame.set(c.game_id, arr);
  }
  const games: GameEdgeDoc[] = [];
  for (const [gameId, gcards] of byGame) {
    const { away, home } = matchupParts(gcards[0]?.matchup);
    const candidates = gcards.map(cardToBestBet);
    games.push({
      game_id: gameId,
      home,
      away,
      status: gcards[0]?.status ?? "unknown",
      candidates,
      best_bets: candidates.filter((b) => b.decision === "bet"),
      clv: gcards[0]?.clv,
    });
  }
  return games;
}

export async function getBestBetsForSport(sport: string) {
  const loaded = await readDigest();
  if (!loaded) return null;
  const games = buildGames(loaded.digest.cards, sport);
  return {
    sport,
    generated_at: loaded.generatedAt,
    status: "ok" as const,
    count: games.length,
    n_best_bets: games.reduce((n, g) => n + g.best_bets.length, 0),
    games,
    edge_claimed: false,
    honest_note:
      "Served from the m10 digest file (data/frontend/best_bets.json), not the live compute route.",
  };
}

export async function getBestBetsForGame(sport: string, gameId: string) {
  const env = await getBestBetsForSport(sport);
  if (!env) return null;
  const game = env.games.find((g) => g.game_id === gameId);
  if (!game) return { status: "unavailable" as const, reason: "game not found in digest" };
  return game;
}
