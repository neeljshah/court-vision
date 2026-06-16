// Mirrors the FastAPI /api/board contract (apps/live_board/server.py). This file
// is the single source of truth for the row shape; do NOT change field names --
// the backend owns the contract. Scores are ints for MLB/soccer and set-strings
// (e.g. "6 4 7") for tennis, hence `number | string | null`.

export type Sport = "mlb" | "soccer" | "tennis";

export type GameState = "in" | "pre" | "post";

// Provenance of the win-prob / odds shown for a row -- drives the source badge.
//  model       calibrated pregame model (in-corpus)
//  live-model  calibrated in-game model (in-corpus, live)
//  market      devigged market-implied probability
//  live-market devigged market-implied, live
//  unavailable no model + no usable odds -> score/clock only
export type RowSource =
  | "model"
  | "live-model"
  | "market"
  | "live-market"
  | "unavailable";

export interface BoardRow {
  sport: Sport;
  league: string;
  state: GameState;
  start_time: string | null; // ISO 8601
  home: string;
  away: string;
  home_score: number | string | null;
  away_score: number | string | null;
  clock_text: string | null;
  win_home: number | null; // 0..1
  win_away: number | null; // 0..1
  draw: number | null; // 0..1, soccer only
  total: number | null;
  market_odds: string | null;
  provider: string | null;
  source: RowSource;
  market_implied: boolean;
  note: string | null;
}

export interface BoardResponse {
  sport: Sport;
  leagues: string[] | null;
  generated_at: string; // ISO 8601
  rows: BoardRow[];
}

export interface SoccerLeague {
  value: string;
  label: string;
}

export const SOCCER_LEAGUES: SoccerLeague[] = [
  { value: "fifa.world", label: "World Cup" },
  { value: "uefa.champions", label: "Champions League" },
  { value: "eng.1", label: "Premier League" },
  { value: "esp.1", label: "La Liga" },
  { value: "ita.1", label: "Serie A" },
  { value: "ger.1", label: "Bundesliga" },
  { value: "usa.1", label: "MLS" },
];

export const SPORTS: { value: Sport; label: string }[] = [
  { value: "mlb", label: "MLB" },
  { value: "soccer", label: "Soccer" },
  { value: "tennis", label: "Tennis" },
];
