// types_w12.ts -- W12 endpoint types extracted from types.ts to keep that
// DATA module under the <=300 LOC rail (or the DATA-module ~600-750 ceiling).
// Consumers that imported from "@/lib/types" directly continue to work because
// types.ts re-exports everything from here.  p5api.ts re-exports from types.ts
// so it is also unchanged for callers.
//
// UNITS / probability only -- NO $/pnl/roi field anywhere in these shapes.

// ---------------------------------------------------------------------------
// ClvCorpus -- GET /api/improve/clv-corpus (ws6, SI-06)
// One row per self-improve candidate from proposals.jsonl.  UNITS/probability;
// replication_label and vs_close are surfaced VERBATIM; no $ / edge / profit.
// ---------------------------------------------------------------------------
export type ClvCorpusCandidate = {
  ts: string | null;
  name: string;
  decision: string;         // e.g. "NO_CANDIDATE" | "SHIP" | ...
  n_rep: number;
  replication_label: string; // "REPLICATION_PENDING" | "REPLICATED"
  vs_close: string;          // "UNPROVEN" | "vs_close UNPROVEN" | stored value
  dm_p: number | null;       // DM test p-value (probability); null if not run
  delta: number | null;      // Brier delta (probability space); NOT $
  significant: boolean | null;
  n_new: number | null;
  reasons: string[];
  units: string;             // always "probability"
  edge_claimed: boolean;     // ALWAYS false
  note: string;
};

export type ClvCorpus = {
  status: string;            // "ok" | "unavailable" | "INSUFFICIENT_DATA"
  candidates: ClvCorpusCandidate[];
  n_total: number;
  enabled: boolean;
  edge_claimed: boolean;     // ALWAYS false
  honest_note?: string;
  reason?: string;
};

// BestBetsCLV -- per-card CLV object returned by GET /api/bestbets/board.
// clv_pct / beat_close are null when no liquid in-play prices (offseason).
// clv_status is "INSUFFICIENT_DATA" when unresolved. No $ field.
export type BestBetsCLV = {
  clv_pct: number | null;
  beat_close: boolean | null;
  clv_status: string; // "INSUFFICIENT_DATA" | "ok" | ...
  clv_is_proxy: boolean;
};

// BestBetsCard -- one ranked calibrated divergence card from
// GET /api/bestbets/board. status = "live" | "pregame" | "done" | "post" | "final".
// edge_vs_market and units are probability/unit-space only; no $ field.
// Cards with status "post" or "final" are EXCLUDED from rendered bet cards
// (skip_reason surfaced in honest state).
export type BestBetsCard = {
  game_id: string;
  matchup: string;
  sport: string;
  market_type: string;
  side: string;
  model_prob: number;
  market_prob: number;
  best_book: string;
  best_odds: number;
  all_books: Array<{ book: string; odds: number; line: number | null }>;
  edge_vs_market: number;
  units: number;
  tier: string | null;
  confidence: number;
  // clv is an object from the board endpoint (not a bare number).
  // clv_is_proxy is also surfaced at the card top level for convenience.
  clv: BestBetsCLV | null;
  clv_is_proxy: boolean;
  status: string;
  tipoff_utc?: string | null;   // ISO timestamp; null/absent = not yet scheduled
  honest_note?: string;
  prop_player?: string | null;
  prop_stat?: string | null;
  // UI-side guard fields (optional -- backend may not send them)
  // degenerate_model: true -> render as decision=no_bet explicitly (not silently bet)
  degenerate_model?: boolean;
  // live.state: backend live-game state string; if "post"|"final" card must not render as bet
  live?: { state?: string | null } | null;
};

export type BestBetsBoard = {
  status: string;
  generated_at?: string | null;  // may be absent from board endpoint
  cards: BestBetsCard[];
  count: number;
  sports?: string[] | null;      // board endpoint returns sports[] not sport
  sport?: string | null;         // kept for compat
  filters?: { sport: string | null; tier: string | null; status: string | null };
  honest_note?: string;
  edge_claimed: boolean; // ALWAYS false
  reason?: string;
};

// PlayerPropRow -- one calibrated prop prediction from
// GET /api/predict/props/{sport}. p_over/p_under in [0,1]; no $ field.
export type PlayerPropRow = {
  player: string;
  stat: string;
  line: number;
  book: string;
  p_over: number;
  p_under: number;
  proj_mean: number;
  proj_sigma: number;
  edge_vs_market: number;
  tier: string | null;
  confidence: number;
  clv_is_proxy: boolean;
};

export type PropsBoard = {
  status: string;
  sport: string;
  generated_at: string | null;
  props: PlayerPropRow[];
  count: number;
  honest_note?: string;
  edge_claimed: boolean; // ALWAYS false
  reason?: string;
};

// LinesMatrix -- per-book odds matrix for a game from
// GET /api/lines/{sport}/{game_id}/matrix.
export type LinesMatrixEntry = {
  book: string;
  odds: number;
  line: number | null;
  captured_at: string | null;
  is_pm: boolean;
};

export type LinesMatrix = {
  status: string;
  sport: string;
  game_id: string;
  generated_at: string | null;
  matrix: Record<string, Record<string, LinesMatrixEntry[]>>;
  best: Record<string, Record<string, { book: string; odds: number }>>;
  honest_note?: string;
  reason?: string;
};

// BoxscoreRow -- one player in the live boxscore.
export type BoxscoreRow = {
  player: string;
  team: string;
  min: number | null;
  pts: number | null;
  reb: number | null;
  ast: number | null;
};

export type Boxscore = {
  status: string;
  sport: string;
  game_id: string;
  generated_at: string | null;
  players: BoxscoreRow[];
  count: number;
  honest_note?: string;
  reason?: string;
};

// InGameFull -- composite in-game payload from
// GET /api/ingame/{sport}/{game_id}/full.
// clv_status may be "INSUFFICIENT_DATA" -- shown honestly, never fabricated.
export type InGameFull = {
  status: string;
  sport: string;
  game_id: string;
  generated_at: string | null;
  score?: {
    home: number | null;
    away: number | null;
    period: number | null;
    clock: string | null;
  };
  win_prob?: {
    p_home: number | null;
    provenance: string[];
    model: string | null;
  } | null;
  boxscore?: BoxscoreRow[];
  prop_proj?: PlayerPropRow[];
  clv_status: string | null; // "INSUFFICIENT_DATA" | "proxy" | "true_close" | null
  honest_note?: string;
  edge_claimed: boolean; // ALWAYS false
  reason?: string;
};

// PmTrailRow -- one PM paper trade from GET /api/paper/pm/trail.
// CLV may be null (no_close) -- rendered honestly, never as a 0-fill.
export type PmTrailRow = {
  bet_id: string;
  venue: string; // "kalshi" | "polymarket"
  market_id: string;
  model_prob: number;
  confidence: number;
  units: number;
  tier: string | null;
  result: string | null; // "win" | "loss" | "push" | "void" | null
  clv: number | null;
  clv_is_proxy: boolean;
  clv_status: string | null; // "INSUFFICIENT_DATA" | "proxy" | "true_close" | null
  price_taken: number | null;
  ts: string;
};

export type PmTrail = {
  status: string;
  generated_at: string | null;
  trades: PmTrailRow[];
  count: number;
  honest_note?: string;
  reason?: string;
};

// ImproveLedger -- per-sport Brier/ECE/BSS per cycle from
// GET /api/improve/ledger. edge_claimed ALWAYS false; no $ field.
export type ImproveLedgerCycle = {
  cycle: number;
  sport: string;
  brier: number | null;
  ece: number | null;
  bss: number | null;
  at: string | null;
};

export type ImproveLedger = {
  status: string;
  generated_at: string | null;
  cycles: ImproveLedgerCycle[];
  count: number;
  honest_note?: string;
  edge_claimed: boolean; // ALWAYS false
  reason?: string;
};
