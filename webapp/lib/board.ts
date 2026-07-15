// board.ts -- typed client for the mobile Bet Board (:8098 boards API).
//
// Decision-support only: the board shows our calibrated forecast next to each
// book's price and logs the human's OWN stated intent to the paper ledger.
// It never places a bet and never claims a money edge.

// Same-origin Next proxy routes (app/api/board/*) so the board works from
// phones/tunnels with a single exposed origin and no CORS.
export const BOARD_BASE = process.env.NEXT_PUBLIC_BOARD_BASE || "";

export const BOARD_SPORTS = ["nba", "mlb", "soccer", "soccer_intl", "tennis"] as const;
export type BoardSport = (typeof BOARD_SPORTS)[number];

export type SlateMarket = {
  market_type: string;
  side: "home" | "away" | string;
  line: number | null;
  odds: number | null;          // decimal odds
  book: string;
  devigged_prob: number | null;
  captured_at: string | null;
};

export type SlateGame = {
  game_id: string;
  home: string;
  away: string;
  tipoff: string | null;
  pregame_probs?: { home_ml?: number | null; away_ml?: number | null } | null;
  note?: string;
  markets?: SlateMarket[];
};

export type Slate = {
  sport: string;
  status: string;               // "ok" | "unavailable" | ...
  games: SlateGame[];
  honest_note?: string;
  generated_at?: string | null;
};

export async function fetchSlate(sport: BoardSport): Promise<Slate> {
  const res = await fetch(`${BOARD_BASE}/api/board/slate?sport=${sport}`, {
    cache: "no-store",
  });
  if (!res.ok) throw new Error(`slate ${sport}: HTTP ${res.status}`);
  return res.json();
}

/** Best (highest decimal odds) moneyline price per side across books. */
export function bestPrice(
  markets: SlateMarket[] | undefined,
  side: "home" | "away",
): SlateMarket | null {
  let best: SlateMarket | null = null;
  for (const m of markets ?? []) {
    if (m.side !== side || m.market_type !== "moneyline" || m.odds == null) continue;
    if (best === null || (best.odds ?? 0) < m.odds) best = m;
  }
  return best;
}

/** Decimal odds -> American string ("+142" / "-165"). */
export function american(odds: number | null | undefined): string {
  if (odds == null || odds <= 1) return "--";
  const a = odds >= 2 ? (odds - 1) * 100 : -100 / (odds - 1);
  return `${a >= 0 ? "+" : ""}${Math.round(a)}`;
}

/** Newest captured_at across a game's markets (freshness stamp source). */
export function newestCapture(markets: SlateMarket[] | undefined): Date | null {
  let newest: Date | null = null;
  for (const m of markets ?? []) {
    if (!m.captured_at) continue;
    const d = new Date(m.captured_at);
    if (!Number.isNaN(d.getTime()) && (newest === null || d > newest)) newest = d;
  }
  return newest;
}

export const STALE_AFTER_MS = 15 * 60 * 1000;
