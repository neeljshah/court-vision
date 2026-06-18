// Typed client + types for the FastAPI decision-support service
// (scripts.platformkit.frontend.serve). Shapes mirror slate.build_row exactly.
// HONEST: every field comes from the real predictor or is null (never fabricated).

export interface SlateRow {
  sport: string;
  matchup: string;
  status: "ok" | "unavailable" | "error";
  model: string | null;
  p_home_win?: number | null;
  market: string | null;
  edge: number | null; // model P(home) - market-implied P(home); decision support only
  verdict: Verdict;
  note: string | null;
  // Multi-book block (null when no odds corpus present -- never faked):
  best_home_book: string | null;
  best_home_price: number | null;
  best_away_book: string | null;
  best_away_price: number | null;
  arb_pct: number | null; // execution edge (line-shopping/arb), NOT a model money edge
  model_ev_best: number | null;
}

export type Verdict =
  | "MATCH"
  | "BEHIND"
  | "AHEAD"
  | "CALIBRATED"
  | "UNAVAILABLE"
  | "UNKNOWN";

export interface SlatePayload {
  sport: string;
  status: string;
  rows: SlateRow[];
  honest_note: string;
  predictor_available?: boolean;
  note?: string;
}

// ---------------------------------------------------------------------------
// Game detail (full ranked bet board for ONE game).
// Mirrors the GET /api/game contract EXACTLY. Every number comes from the real
// predictor or is null (never fabricated). model_prob is a probability in 0..1;
// fair_odds/best_price are DECIMAL odds; ev_pct is a percent (e.g. 4.2 = +4.2%),
// computed vs the best AVAILABLE price -- not vs the close. line is the market
// line (points/total) or null. A null best_price/ev_pct means "model view only".
export interface BetRow {
  group: string;
  selection: string;
  model_prob: number | null; // 0..1
  line: number | null;
  fair_odds: number; // decimal
  best_book: string | null;
  best_price: number | null; // decimal
  ev_pct: number | null; // percent vs best available price (NOT the close)
  verdict: string;
  note: string;
}

export interface BetGroup {
  name: string;
  bets: BetRow[];
}

export interface GameLive {
  state: string;
  home_score: number;
  away_score: number;
  clock: string;
}

export interface GameBoard {
  sport: string;
  home: string;
  away: string;
  status: string; // "ok" | "unavailable" | "error" (mirrors the slate)
  as_of: string;
  live: GameLive | null;
  best_bets: BetRow[];
  groups: BetGroup[];
  honest_note: string;
}

export interface GameLiveParams {
  state?: string;
  home_score?: number;
  away_score?: number;
  clock?: string;
}

/**
 * Fetch the full ranked bet board for ONE game. Codes to GET /api/game
 * (?sport=&home=&away= plus optional live params). Works once that endpoint is
 * live; until then it surfaces a normal error/unavailable state (never blank).
 */
export function getGame(
  sport: string,
  home: string,
  away: string,
  live?: GameLiveParams
): Promise<GameBoard> {
  const q = new URLSearchParams({ sport, home, away });
  if (live) {
    if (live.state) q.set("state", live.state);
    if (live.home_score !== undefined) q.set("home_score", String(live.home_score));
    if (live.away_score !== undefined) q.set("away_score", String(live.away_score));
    if (live.clock) q.set("clock", live.clock);
  }
  return getJson<GameBoard>(`/api/game?${q.toString()}`);
}

export interface IntentRecord {
  sport: string;
  matchup: string;
  model: string | null;
  market: string | null;
  edge: number | null;
  verdict: string;
  side?: string;
  price?: number | null;
  book?: string | null;
}

export interface SportOption {
  value: string;
  label: string;
}

// World Cup (soccer_intl) is listed FIRST per the product spec.
export const SPORTS: SportOption[] = [
  { value: "soccer_intl", label: "World Cup" },
  { value: "nba", label: "NBA" },
  { value: "mlb", label: "MLB" },
  { value: "soccer", label: "Soccer (club)" },
  { value: "tennis", label: "Tennis" },
];

async function getJson<T>(url: string): Promise<T> {
  const res = await fetch(url, { headers: { Accept: "application/json" } });
  if (!res.ok) throw new Error(`${url} -> HTTP ${res.status}`);
  return (await res.json()) as T;
}

export function fetchSlate(sport: string): Promise<SlatePayload> {
  return getJson<SlatePayload>(`/api/slate?sport=${encodeURIComponent(sport)}`);
}

export function fetchHealth(): Promise<{ status: string }> {
  return getJson<{ status: string }>(`/health`);
}

export interface IntentResponse {
  status: string;
  record: Record<string, unknown>;
  note: string;
}

// Logs a NON-BINDING "I placed this" record to the local JSONL. NO real bet is
// placed and there is NO sportsbook connection -- the human executes manually.
export async function postIntent(record: IntentRecord): Promise<IntentResponse> {
  const res = await fetch(`/api/intent`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(record),
  });
  if (!res.ok) throw new Error(`/api/intent -> HTTP ${res.status}`);
  return (await res.json()) as IntentResponse;
}

/**
 * Parse a slate matchup label ("Home vs Away") into {home, away}. Returns null
 * if it cannot be parsed (we never guess a fake split). The slate builds the
 * label as `${home} vs ${away}`, so this is the inverse used to drive getGame.
 */
export function parseMatchup(matchup: string): { home: string; away: string } | null {
  const parts = matchup.split(/\s+vs\.?\s+/i);
  if (parts.length !== 2) return null;
  const home = parts[0].trim();
  const away = parts[1].trim();
  if (!home || !away) return null;
  return { home, away };
}

/** External convenience link to the human's own book search -- NOT auto-execution. */
export function bookSearchUrl(sport: string, matchup: string): string {
  const q = encodeURIComponent(`${sport} ${matchup} odds`);
  return `https://www.google.com/search?q=${q}`;
}
