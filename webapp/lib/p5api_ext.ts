// p5api_ext.ts -- ADDITIVE typed clients for W1/W2/W4/W5 endpoints.
//
// W7 owns this file. p5api.ts is untouched (owned by W12). This module adds
// clients ONLY for the four new API groups: lines matrix (W1), player props
// (W2), ingame full + boxscore (W4), PM paper trail detail (W5).
//
// HONESTY RAILS: UNITS / probability only -- NO dollar/roi field. Any failed
// or non-2xx fetch degrades to an explicit { status:"unavailable" } sentinel,
// NEVER a fabricated body, NEVER green-on-missing. in-game CLV may be
// INSUFFICIENT_DATA -- always shown honestly. Real-money stays default-DENY.
//
// All functions accept an optional AbortSignal for cleanup. fetchHonest
// handles timeout + capped-backoff retries; no manual retry here.

import { fetchHonest } from "./fetchHonest";

export const P5_EXT_BASE =
  process.env.NEXT_PUBLIC_P5_BASE || "/p5";

// ---------------------------------------------------------------------------
// Shared fetch helpers (private to this module)
// ---------------------------------------------------------------------------

async function getExt<T>(
  path: string,
  signal?: AbortSignal,
): Promise<T | ExtUnavailable> {
  return fetchHonest<T>(`${P5_EXT_BASE}${path}`, { signal });
}

// ---------------------------------------------------------------------------
// Shared honest sentinel
// ---------------------------------------------------------------------------

export type ExtUnavailable = { status: "unavailable"; reason?: string };

export function isExtUnavailable(x: unknown): x is ExtUnavailable {
  return (
    !!x &&
    typeof x === "object" &&
    (x as { status?: string }).status === "unavailable"
  );
}

// ---------------------------------------------------------------------------
// W1 -- Lines matrix: per-market, per-book odds matrix + best-line
// ---------------------------------------------------------------------------

// One book's quote for a side of a market.
export type BookQuote = {
  book: string;
  odds: number | null;   // decimal odds as quoted (never $)
  line: number | null;   // handicap line where applicable
  captured_at: string | null;
  is_pm: boolean;        // true = Kalshi/Polymarket venue
};

// Best available price for one side (across all books).
export type BestLineSide = {
  book: string;
  odds: number | null;
};

// One market's book matrix + best-line for both sides.
export type MarketMatrix = {
  market_type: string;
  sides: Record<string, BookQuote[]>;     // side -> quotes per book
  best: Record<string, BestLineSide>;     // side -> best quote
};

// Full per-game lines matrix from GET /api/lines/{sport}/{game_id} (W1 endpoint).
export type LinesMatrix = {
  status: string;
  sport: string;
  game_id: string;
  generated_at: string | null;
  markets: Record<string, MarketMatrix>; // market_type -> matrix
  honest_note?: string;
  edge_claimed?: boolean;   // ALWAYS false
  reason?: string;
};

// ---------------------------------------------------------------------------
// W2 -- Player-prop predictions: P(over/under) per player + book + line
// ---------------------------------------------------------------------------

export type PlayerPropRow = {
  player: string;
  stat: string;
  line: number | null;
  book: string;
  p_over: number | null;    // calibrated P(over) in [0,1] -- never a $ edge
  p_under: number | null;
  proj_mean: number | null;
  proj_sigma: number | null;
  edge_vs_market: number | null;  // probability divergence, NOT a $ edge
  tier: string | null;
  confidence: number | null;
  clv_is_proxy: boolean;
};

export type PropsBoardEnvelope = {
  status: string;
  sport: string;
  game_id?: string | null;
  generated_at: string | null;
  props: PlayerPropRow[];
  honest_note?: string;
  edge_claimed?: boolean;  // ALWAYS false
  clv_is_proxy: boolean;
  reason?: string;
};

// ---------------------------------------------------------------------------
// W4 -- In-game full: score + win-prob + player boxscore + CLV state
// ---------------------------------------------------------------------------

export type BoxscorePlayer = {
  player_id?: number | null;
  name: string;
  team?: string | null;
  min: number | null;     // minutes played (may be fractional)
  pts: number | null;
  reb: number | null;
  ast: number | null;
};

export type BoxscoreEnvelope = {
  status: string;
  sport: string;
  game_id: string;
  generated_at: string | null;
  home?: string | null;
  away?: string | null;
  home_score?: number | null;
  away_score?: number | null;
  period?: number | null;
  clock?: string | null;
  players: BoxscorePlayer[];
  source?: string | null;
  honest_note?: string;
  reason?: string;
};

// Combined in-game full response (score + win-prob + box + prop projections).
// clv_status may be INSUFFICIENT_DATA -- always shown honestly, never fabricated.
export type InGameFull = {
  status: string;
  sport: string;
  game_id: string;
  generated_at: string | null;
  // Score / game state
  home?: string | null;
  away?: string | null;
  home_score?: number | null;
  away_score?: number | null;
  period?: number | null;
  clock?: string | null;
  frac_elapsed?: number | null;
  // Calibrated win-prob from the in-game engine
  p_win?: number | null;        // P(home win); null when game not live
  win_prob_model?: string | null;
  // Per-player live projections (may be empty when not live)
  prop_projections?: Array<{
    player: string;
    stat: string;
    proj_mean: number | null;
    pace_fraction?: number | null;
  }>;
  // CLV status: INSUFFICIENT_DATA is an honest sentinel -- never fabricate
  clv_status: "true_close" | "proxy" | "INSUFFICIENT_DATA" | null;
  clv_is_proxy: boolean;
  // Live player boxscore (may be empty)
  players?: BoxscorePlayer[];
  honest_note?: string;
  reason?: string;
};

// ---------------------------------------------------------------------------
// W5 -- PM paper trail detail: per-trade execution detail
// ---------------------------------------------------------------------------

export type PmTradeDetail = {
  bet_id: string;
  sport: string;
  game_id?: string | null;
  matchup?: string | null;
  side: string;
  market_type?: string | null;
  // Execution context
  venue: string;         // "kalshi" | "polymarket" | "pm"
  taken_book: string;
  taken_decimal: number | null;   // decimal odds -- NOT a $ figure
  // Model inputs at decision time
  model_prob: number | null;      // calibrated probability, never a $ edge
  confidence: number | null;
  units: number | null;           // stake in UNITS (never $)
  tier: string | null;
  // Outcome + CLV grading
  status: string;        // "open" | "settled"
  result: string | null; // "win" | "loss" | "push" | "void" | null
  clv_pct: number | null;         // CLV as a probability ratio, not $ ROI
  beat_close: boolean | null;
  clv_is_proxy: boolean;
  // Honesty: if no true close exists, clv_status = null/INSUFFICIENT_DATA
  clv_status: string | null;
  clv_note: string | null;
  // The paper channel is always executed=false -- never real money
  executed: boolean;    // ALWAYS false
  ts?: string | null;
  settled_at?: string | null;
  honest_note?: string;
};

export type PmTrailEnvelope = {
  status: string;
  count: number;
  trail: PmTradeDetail[];
  honest_note?: string;
  reason?: string;
};

// ---------------------------------------------------------------------------
// Typed client methods for W1/W2/W4/W5
// ---------------------------------------------------------------------------

export const apiExt = {
  // W1 -- Lines matrix: per-book odds matrix for a game.
  // Degrades to UNAVAILABLE when the game has no captured lines.
  getLinesMatrix: (sport: string, gameId: string, s?: AbortSignal) =>
    getExt<LinesMatrix>(`/api/lines/${sport}?game_id=${encodeURIComponent(gameId)}`, s),

  // W2 -- Props board for a sport (optionally filtered to one game).
  // UNAVAILABLE when no prop lines exist (NBA offseason, missing feed).
  getPropsBoard: (sport: string, gameId?: string, s?: AbortSignal) => {
    const q = gameId ? `?game_id=${encodeURIComponent(gameId)}` : "";
    return getExt<PropsBoardEnvelope>(`/api/predict/props/${sport}${q}`, s);
  },

  // W4 -- Live boxscore for a game (player pts/reb/ast/min).
  // UNAVAILABLE when game is not live or ESPN feed is absent.
  getBoxscore: (sport: string, gameId: string, s?: AbortSignal) =>
    getExt<BoxscoreEnvelope>(`/api/boxscore/${sport}/${gameId}`, s),

  // W4 -- Combined in-game full (score + win-prob + box + prop-proj + CLV state).
  // clv_status = INSUFFICIENT_DATA when no liquid in-play prices exist (NBA
  // offseason). The caller MUST show INSUFFICIENT_DATA honestly, never fabricate.
  getInGameFull: (sport: string, gameId: string, s?: AbortSignal) =>
    getExt<InGameFull>(`/api/ingame/${sport}/${gameId}/full`, s),

  // W5 -- PM paper trail (Kalshi/Polymarket channel only).
  // Filters by venue=pm; optional tier/result params.
  getPmTrail: (
    params?: { venue?: string; result?: string; tier?: string; limit?: number },
    s?: AbortSignal,
  ) => {
    const q = new URLSearchParams();
    q.set("channel", "prediction_market");
    if (params?.venue) q.set("venue", params.venue);
    if (params?.result) q.set("result", params.result);
    if (params?.tier) q.set("tier", params.tier);
    if (params?.limit != null) q.set("limit", String(params.limit));
    return getExt<PmTrailEnvelope>(`/api/paper/pm/trail?${q.toString()}`, s);
  },

  // W5 -- Per-trade execution detail for a PM bet (full context + CLV).
  getPmTradeDetail: (betId: string, s?: AbortSignal) =>
    getExt<PmTradeDetail>(`/api/paper/pm/trade/${encodeURIComponent(betId)}`, s),
};
