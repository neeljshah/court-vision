export type Bet = {
  game_id: string;
  player_id: string | number;
  name: string;
  team?: string;
  stat: string;
  side: "over" | "under";
  line: number;
  book: string;
  odds: number;
  projected_final: number;
  current?: number;
  delta?: number;
  ev: number;
  kelly: number;
  tier: "S" | "A" | "B" | "C";
  why?: string;
  reason?: string;
};

export type PBPEvent = {
  game_id: string;
  topic: string;
  action_number?: number;
  period?: number;
  clock?: string;
  description?: string;
  player_id?: number;
  player_name?: string;
  team_tricode?: string;
  score_home?: number;
  score_away?: number;
  ts?: number;
};

export type Snapshot = {
  game_id: string;
  game_status?: string;
  home_team?: string;
  away_team?: string;
  home_score?: number;
  away_score?: number;
  period?: number;
  clock?: string;
  players?: Array<{
    player_id?: number;
    name?: string;
    team?: string;
    min?: number;
    pts?: number;
    reb?: number;
    ast?: number;
    pf?: number;
  }>;
};

export type Projection = {
  player_id: number | string;
  name?: string;
  team?: string;
  stat: string;
  current?: number;
  projected_final: number;
  delta?: number;
  projection_source?: string;
  foul_factor?: number;
  blow_factor?: number;
  heat_check_shrinkage?: number;
  matchup_reason?: string;
};

export type BusMessage =
  | { topic: "hello"; event: HelloPayload; ts: number }
  | { topic: "pong"; event: Record<string, never>; ts: number }
  | { topic: "snapshot.updated"; event: { game_id: string; snapshot: Snapshot }; ts: number }
  | { topic: "projection.updated"; event: { game_id: string; rows: Projection[]; reason?: string; source?: string }; ts: number }
  | { topic: "bet.recommended"; event: Bet; ts: number }
  | { topic: "lines.refreshed"; event: { date: string; counts: Record<string, number> }; ts: number }
  | { topic: string; event: PBPEvent; ts: number };

export type HelloPayload = {
  snapshots: Record<string, Snapshot>;
  projections: Record<string, Projection[]>;
  recent_bets: Bet[];
  recent_alerts: { ts: number; severity: string; msg: string }[];
};

export type Explanation = {
  summary: string;
  sections: Array<{ kind: string; title: string; body: string }>;
};

// ---------------------------------------------------------------------------
// P5 Auto-API (:8099) response types. Moved here from p5api.ts to keep that
// client module under the 300-LOC rail; p5api.ts re-exports these so existing
// `import { X } from "@/lib/p5api"` call sites keep working unchanged.
// READ-ONLY contract: every panel renders exactly what the API returns.
// UNITS / probability only -- NO $/pnl/roi field anywhere in these shapes.
// ---------------------------------------------------------------------------

export type Unavailable = { status: "unavailable"; reason?: string };

export type ReportList = {
  status: string;
  sport: string;
  game_ids: string[];
  count: number;
  generated_at: string | null;
  honest_note?: string;
  reason?: string;
};

export type Market = {
  market_type: string;
  side: string;
  line: number | null;
  odds: number;
  book: string;
  devigged_prob: number;
  captured_at: string;
  is_close: boolean;
  clv_is_proxy: boolean;
};

export type LiveState = {
  status: string;
  state?: string;
  detail?: string;
  clock?: string;
  period?: number;
  home_score?: number;
  away_score?: number;
  home_abbr?: string;
  away_abbr?: string;
  as_of?: string;
  reason?: string;
};

export type Report = {
  status: string;
  sport: string;
  game_id: string;
  pregame?: {
    home: string;
    away: string;
    tipoff?: string;
    model_probs?: Record<string, number>;
    leak_guard?: { in_sample?: boolean };
    produced_at?: string;
    note?: string;
  } | null;
  markets?: Market[];
  edges?: Array<Record<string, unknown>>;
  live?: LiveState;
  intel?: Record<string, unknown> | null;
  meta?: {
    as_of?: string | null;
    freshness?: { status?: string; age_sec?: number | null };
    clv_is_proxy?: boolean;
    honest_note?: string;
    schema_version?: string;
  };
  reason?: string;
};

export type BestBet = {
  market_type: string;
  side: string;
  model_prob: number;
  market_prob: number;
  best_book: string;
  best_odds: number;
  line: number | null;
  edge: number | null;
  ev: number;
  tier: string | null;
  decision: string; // "bet" | "no_bet"
  stake_units: number;
  flat_unit: number;
  kelly_units: number;
  clv_is_proxy: boolean;
  reason?: string;
  // Prop identity (market_type=="prop") -- optional until frontend/exec_decision.py
  // whitelists them through (see docs/research/organization-sprint/
  // PROPOSED-exec_decision-prop-fields.md). Harmless when absent.
  prop_player?: string | null;
  prop_stat?: string | null;
  prop_side?: string | null;
};

// Per-sport CLV breakdown entry (clv_ledger.clv_summary by_sport bucket).
// n = graded bets for the sport; mean_clv_pct + pct_beat_close per sport.
export type ClvBySport = {
  n: number;
  mean_clv_pct: number | null;
  pct_beat_close: number | null;
  // median_clv_pct/basis: true-close-preferred headline (basis omitted on older
  // server builds -- always guard with `?? null` / optional chaining).
  median_clv_pct?: number | null;
  basis?: "true_close" | "proxy_only" | null;
  n_proxy?: number;
};

export type ClvScoreboard = {
  n_bets: number;
  pct_beat_close: number | null;
  // mean_clv_pct is the ALL-rows mean -- CONTEXT ONLY, may include proxy closes.
  mean_clv_pct: number | null;
  // median_clv_pct is the true-close-preferred headline; basis says which rows it
  // came from ("true_close" normally, "proxy_only" only when zero true-close rows
  // exist yet). Optional: older server builds may omit these.
  median_clv_pct?: number | null;
  basis?: "true_close" | "proxy_only" | null;
  n_proxy?: number;
  by_sport: Record<string, ClvBySport> | null;
  clv_is_proxy: boolean;
  note?: string;
  // Raw-ledger tallies from frontend.paper_trail.clv_summary (optional -- older
  // server builds may omit). n_no_close = settled rows with no gradeable close
  // (excluded from n_bets); n_bets + n_no_close == true settled-bet count.
  // n_open here counts RAW open-status ledger rows (NOT collapsed) -- prefer
  // /api/paper/open's `count` for the true current-open figure.
  n_no_close?: number;
  n_open?: number;
  n_total_rows?: number;
};

export type GameEdge = {
  game_id: string;
  home?: string;
  away?: string;
  tipoff?: string;
  status: string;
  candidates?: BestBet[];
  best_bets?: BestBet[];
  live?: LiveState;
  reason?: string;
};

export type BestBetsEnvelope = {
  sport: string;
  generated_at: string;
  status: string;
  count: number;
  n_best_bets: number;
  games: GameEdge[];
  clv?: ClvScoreboard;
  decision_note?: string;
  honest_note?: string;
  edge_claimed?: boolean;
  reason?: string;
};

// /api/paper/open reuses frontend.paper_trail.read_trail (collapsed, UNCAPPED --
// no `limit` query param) filtered to status=="open", so `count`/`open` here are
// the TRUE current-open figures, unlike the capped /api/paper/trail response.
export type PaperOpen = {
  status: string;
  count: number;
  open: PaperTrailRow[];
  reason?: string;
};

export type ImproveStatus = {
  status: string;
  ratchet: {
    state: string;
    last_decision?: string | null;
    shipped_version?: number | null;
    history?: Array<Record<string, unknown>>;
    reason?: string;
  };
  kinds: Array<{ kind: string; current_version: number | null; versions: number[] }>;
  n_kinds?: number;
  n_promoted?: number;
  honest_note?: string;
  reason?: string;
};

// Ops status -- the single supervised-stack health doc (ops.health_aggregator).
// Lets the UI render per-service liveness/freshness + the real-money-gate state.
export type OpsService = {
  name: string;
  critical: boolean;
  live: boolean | null;
  fresh: string | null;
  breaker: string | null;
  last_seen: string | null;
  age_sec: number | null;
  port: number | null;
  reason: string | null;
};
export type OpsStatus = {
  generated_at?: string;
  overall: string; // "ok" | "degraded" | "down"
  services: OpsService[];
  notes?: string[];
  reason?: string;
};

// SupervisorStatus -- the REAL supervisor process roster from the same-origin
// read-only route GET /api/ops/supervisor (reads supervisor_status.json off
// disk + enforces the stale SLA). `live` is TRUE only when the feed is FRESH and
// all_ready and no proc is degraded -- a stale/dead/degraded feed is NEVER green
// (live:false, overall='down'/'degraded'). uptime_sec/restarts are honest reads
// from started_at + procs[].restarts; null when the file is missing/stale. NO $.
export type SupervisorProc = {
  name: string;
  state: string;
  ready: boolean | null;
  restarts: number;
  degraded: boolean;
  heartbeat_age_sec: number | null;
  heartbeat_fresh_sec: number | null;
  kind: string | null;
};
export type SupervisorStatus = {
  status: string; // "ok" | "unavailable"
  live: boolean;
  overall: string; // "ok" | "degraded" | "down"
  profile?: string | null;
  all_ready?: boolean;
  any_degraded?: boolean;
  n_procs?: number;
  restarts_total: number;
  uptime_sec: number | null;
  started_at?: number | null;
  updated_at?: number | null;
  age_sec: number | null;
  procs: SupervisorProc[];
  reason?: string;
  edge_claimed?: boolean; // ALWAYS false
};

export type ParityCell = { status: string; detail: string };
export type Parity = {
  status: string;
  green: boolean;
  dimensions: string[];
  sports: Array<{ sport: string; cells: Record<string, ParityCell> }>;
  reason?: string;
};

// InGameGates -- 4-sport calibration gate verdicts from /api/ingame/gates.
// verdict = raw gate decision (REPLICATED/REJECT/SHIP_PRIOR_LAYER/null).
// vs_close = market-benchmark label (always UNPROVEN where no in-play odds).
// honest_label = always "CALIBRATION only -- not a market edge".
export type GateSport = {
  sport: string;
  verdict: string | null;
  vs_close: string | null;
  honest_label: string;
};
export type InGameGates = {
  status: string;
  sports: GateSport[];
  honest_note?: string;
  edge_claimed: boolean;
  reason?: string;
};

// InGameServed -- calibrated win-prob from /api/ingame/{sport}/{game_id}.
// served.p_win = calibrated P(home win); provenance is string[] (join for display).
// live_state uses home/away (team abbreviations) and status (detail string).
export type InGameServed = {
  status: string;
  sport: string;
  game_id: string;
  p0?: number | null;
  live_state?: {
    state_diff?: number | null;
    frac_elapsed?: number | null;
    p0?: number | null;
    // BUG2 fix: backend emits home/away (not home_abbr/away_abbr)
    home?: string;
    away?: string;
    // legacy shape aliases -- component reads both
    home_abbr?: string;
    away_abbr?: string;
    // status is the live detail string (e.g. "Q3 7:42"); no separate clock/period fields
    status?: string;
    clock?: string;
    period?: number;
  } | null;
  served?: {
    // BUG1 fix: backend returns p_win (not p_home)
    p_win?: number | null;
    // BUG3 fix: provenance is string[] not string
    provenance?: string[];
    model?: string;
    verdict?: string;
    vs_close?: string;
    note?: string;
  } | null;
  reason?: string;
};

// PaperTrailRow -- one collapsed (open->settled merged) ledger row from
// frontend/paper_trail._build_trail_row. executed is ALWAYS false (paper-only).
// A settled bet with no real close -> clv_unavailable=true (render VOID/pending,
// NEVER a 0-fill). model_ev is a probability ratio (p*odds-1), never a $ amount.
export type PaperTrailRow = {
  game_id: string;
  matchup: string;
  sport: string;
  side: string; // "home" | "away"
  market_type: string | null;
  // prop selection identity (market_type==="prop" only; null otherwise) -- lets the
  // trail render "<player> <stat> <over/under>" instead of an opaque "prop / home".
  prop_player?: string | null;
  prop_stat?: string | null;
  prop_side?: string | null; // "over" | "under"
  line: number | null;
  taken_book: string;
  taken_decimal: number | null;
  model_prob: number | null;
  market_prob?: number | null; // devigged market probability (optional -- absent from some trail sources)
  model_ev: number | null;
  tier: string | null;
  stake_units: number | null;
  status: string; // "open" | "settled"
  graded: boolean;
  outcome: string | null; // "win" | "loss" | "push" | "void" | null
  clv_pct: number | null;
  beat_close: boolean | null;
  clv_is_proxy: boolean;
  clv_status: string | null; // "true_close" | "proxy" | "no_close" | null
  clv_unavailable: boolean;
  clv_note: string | null;
  executed: boolean; // ALWAYS false
  channel?: string | null; // "paper" always for this trail
  ts: string;
  settled_at: string | null;
};

export type PaperTrail = {
  status: string;
  count: number;
  trail: PaperTrailRow[];
  honest_note?: string;
  reason?: string;
};

// One point of the CLV-over-time series (settled bets with a real close only;
// VOID/pending bets are excluded by the backend, never plotted as a 0).
export type ClvSeriesPoint = {
  ts: string | null;
  matchup: string | null;
  sport: string | null;
  clv_pct: number;
  beat_close: boolean | null;
  clv_is_proxy: boolean;
  cumulative_mean_clv_pct: number;
};

export type ClvSeries = {
  status: string;
  count: number;
  series: ClvSeriesPoint[];
  honest_note?: string;
  reason?: string;
};

// Manual paper-bet placement payload (POST /api/paper/place). Stake is sized
// server-side in UNITS (flat_unit + quarter_kelly); there is NO $ field here.
export type PaperPlacePayload = {
  sport: string;
  game_id: string;
  market_type: string;
  side: string; // "home" | "away"
  book: string;
  taken_decimal: number; // decimal odds, must be > 1.0
};

export type PaperPlaceResult = {
  status: string; // "ok" | "rejected" | "error"
  idempotent?: boolean;
  bet?: Record<string, unknown>;
  honest_note?: string;
  reason?: string;
};

// LineRow -- one captured MarketRow projected onto the all-books board, plus the
// home/away/tipoff game context. A stale/absent feed -> status='unavailable' on
// the envelope; a missing quote is "--", NEVER a guessed price.
export type LineRow = {
  sport: string;
  game_id: string;
  market_type: string;
  side: string;
  line: number | null;
  odds: number | null; // decimal price as quoted
  book: string;
  devigged_prob: number | null;
  captured_at: string | null; // per-book freshness source
  is_close: boolean;
  clv_is_proxy: boolean;
  // game context merged from the prediction record:
  home?: string;
  away?: string;
  tipoff?: string | null;
};

export type LinesBoard = {
  status: string;
  sport: string;
  generated_at: string | null; // freshness age computed from THIS, not fetch time
  lines: LineRow[];
  count: number;
  honest_note?: string;
  edge_claimed?: boolean;
  reason?: string;
};

// One captured tick from the append-only line history.
export type LineTick = {
  captured_at: string | null;
  book: string;
  market_type: string | null;
  side: string | null;
  line: number | null;
  odds: number | null;
};

export type LineHistory = {
  status: string;
  sport: string;
  game_id: string;
  ticks: LineTick[];
  count: number;
  is_close: boolean;
  is_true_close: boolean;
  clv_is_proxy: boolean; // a proxy close is the last-seen pre-tip line, flagged
  honest_note?: string;
  edge_claimed?: boolean;
  reason?: string;
};

// Real-money MODE gate state (default-DENY). paper_only is read from the ACTUAL
// governance gate, never hardcoded. NO $ field -- counts/booleans only.
export type GateStatus = {
  status: string;
  paper_only: boolean;
  real_money_enabled: boolean;
  eligible: boolean;
  n_settled_true_close: number | null; // settled-game count, NOT a $ figure
  threshold: number | null; // pre-registered min settled-N (count)
  reasons: string[];
  honest_note?: string;
  edge_claimed?: boolean;
};

// Settled game final for outcome display (real reported scores or nothing).
export type ResultRow = {
  game_id: string;
  home?: string;
  away?: string;
  home_score?: number | null;
  away_score?: number | null;
  completed?: boolean;
  state?: string;
  status_detail?: string;
  commence_time?: string;
};

export type Results = {
  status: string;
  sport: string;
  results: ResultRow[];
  count: number;
  honest_note?: string;
  edge_claimed?: boolean;
  reason?: string;
};

// Per-sport producer freshness. ok=true requires a real 'ok' snapshot; a stale
// or absent producer reads ok=false (stale-never-green). NO $ field.
export type ProduceSportStatus = {
  sport: string;
  ok: boolean;
  status: string;
  generated_at: string | null;
  age_seconds: number | null;
  n_games: number;
  n_markets: number;
  reason?: string | null;
};

export type ProduceStatus = {
  status: string;
  sports: ProduceSportStatus[];
  n_sports: number;
  any_fresh: boolean;
  honest_note?: string;
  edge_claimed?: boolean;
  reason?: string;
};

// Full latest SnapshotEnvelope for a sport (GET /api/predict/{sport}). Carries
// the unavailable sentinel verbatim when no snapshot exists.
export type PredictMarket = {
  sport: string;
  game_id: string;
  market_type: string;
  side: string;
  line: number | null;
  odds: number | null;
  book: string;
  devigged_prob: number | null;
  captured_at: string | null;
  is_close: boolean;
  clv_is_proxy: boolean;
};
export type PredictRecord = {
  sport: string;
  game_id: string;
  home: string;
  away: string;
  tipoff: string | null;
  pregame_probs: Record<string, number>;
  markets: PredictMarket[];
  leak_guard: { in_sample?: boolean };
  produced_at: string | null;
  note?: string;
};
export type PredictEnvelope = {
  status: string;
  schema_version?: string;
  sport: string;
  generated_at: string | null;
  predictions?: PredictRecord[];
  markets?: PredictMarket[];
  edges?: Array<Record<string, unknown>>;
  honest_note?: string;
  reason?: string;
  note?: string;
};

// ImproveTimeline -- the self-improve loop's OWN per-cycle decisions from
// GET /api/improve/timeline. The loop is MEASUREMENT-ONLY: `enabled` reflects the
// human-managed PIPELINE_ENABLED sentinel (False on this box -> the loop ships
// NOTHING and the UI must label it 'measurement-only / not-enabled', never
// 'shipping'/'learning'). n_promoted counts ONLY real version promotions; a faked
// decision label can never inflate it. edge_claimed is ALWAYS false. NO $ field.
export type ImproveTimelineCycle = {
  cycle: number;
  decision: string | null;
  reason: string | null;
  at: string | number | null;
};
export type ImproveTimeline = {
  status: string;
  cycles: ImproveTimelineCycle[];
  n_cycles?: number;
  cycle_counter?: number;
  n_promoted: number;
  enabled: boolean;
  edge_claimed: boolean; // ALWAYS false
  honest_note?: string;
  reason?: string;
};

// AutonomyStatus -- the ONE canonical autonomy doc from GET /api/ops/autonomy,
// returned VERBATIM (written by status_composer) or an honest unavailable sentinel
// (overall='down') when the file is missing / torn / STALE. A stale/dead feed is
// NEVER green. overall is the monotone-DOWN rollup. NO $ field anywhere.
export type AutonomyLoop = {
  cycle?: number;
  last_decision?: string | null;
  current_candidate?: string | null;
  last_status?: Record<string, unknown> | null;
  liveness_severity?: string;
  liveness_missing?: boolean;
};
export type AutonomyStatus = {
  status: string; // "ok" | "unavailable"
  overall: string; // "ok" | "degraded" | "down"
  generated_at?: number | string | null;
  services?: OpsService[];
  loop?: AutonomyLoop | null;
  ratchet?: Record<string, unknown> | null;
  high_water?: Record<string, unknown> | null;
  idle_reason?: string | null;
  notes?: string[];
  honest_note?: string;
  edge_claimed?: boolean; // ALWAYS false
  reason?: string;
};

// ---------------------------------------------------------------------------
// Unified-gateway CATALOG + single honesty bit (GET /api/catalog,
// GET /api/status.all_honest) and the quant EXECUTION surface (GET
// /api/quant/{sport}/validate, /api/quant/risk, /api/quant/clv). UNITS /
// probability only -- NO $/pnl/roi field anywhere in these shapes. all_honest
// is the single product-wide bit: ok=true ONLY when NO face violates a rail; it
// flips false the instant any does (and the UI must show RED, never hide it).
// ---------------------------------------------------------------------------

// One contracted gateway face (gateway.FaceSpec.to_dict). version + capability
// list + route prefixes + a one-line honest_note. units is always "probability".
export type CatalogFace = {
  face: string;
  version: string;
  title?: string;
  capabilities: string[];
  routes: string[];
  units: string;
  edge_claimed: boolean; // ALWAYS false
  real_money_enabled: boolean; // ALWAYS false
  honest_note: string;
};

export type Catalog = {
  status: string;
  faces: CatalogFace[];
  count: number;
  units?: string;
  edge_claimed: boolean; // ALWAYS false
  real_money_enabled: boolean; // ALWAYS false
  honest_note?: string;
  reason?: string;
};

// One rail violation surfaced by all_honest (face id + a one-line reason). The
// presence of ANY violation flips ok=false; the UI renders these honestly (RED).
export type HonestyViolation = { face: string; reason: string };

export type AllHonest = {
  ok: boolean; // single product-wide honesty bit
  violations: HonestyViolation[];
  n_faces: number;
  honest_note?: string;
  reason?: string;
};

// One auditable bet-validation verdict (quant_exec BetValidation.as_dict). NO
// $ field -- units/probability only. tier=null => decision is no_bet (the model
// matches the efficient close -- a SUCCESS). gate_proven defaults FALSE and is
// shown honestly; clv is the sign-audited record (or null when not gradeable).
export type QuantValidation = {
  side: string;
  market: string;
  model_prob: number | null;
  devigged_close: number | null;
  edge: number | null;
  ev: number | null;
  tier: string | null;
  decision: string; // "bet" | "no_bet"
  flat_unit: number;
  kelly_units: number;
  stake_units: number;
  clv: Record<string, unknown> | null;
  gate_proven: boolean; // mostly false; rendered honestly
  clv_is_proxy: boolean;
  units: string; // "probability"
  edge_claimed: boolean; // ALWAYS false
  real_money_enabled: boolean; // ALWAYS false
  note?: string;
};

export type QuantValidateGame = {
  game_id: string | null;
  home?: string | null;
  away?: string | null;
  status: string;
  validations: QuantValidation[];
  n_bet: number;
  n_no_bet: number;
};

export type QuantValidate = {
  sport: string;
  status: string;
  count: number;
  generated_at?: string;
  games: QuantValidateGame[];
  units?: string;
  edge_claimed: boolean; // ALWAYS false
  real_money_enabled: boolean; // ALWAYS false
  honest_note?: string;
  reason?: string;
};

// UNIT-space variance / exposure descriptors over the open paper book. NO $
// field. RoR is a MODEL-CONDITIONAL DESCRIPTIVE stat, never a profit/safety
// guarantee (ror_is_guarantee is always false).
export type QuantRisk = {
  status: string;
  n_open: number;
  total_exposure_units: number;
  max_single_units: number;
  mean_units: number;
  variance_units2: number;
  ror_descriptive: boolean;
  ror_is_guarantee: boolean; // ALWAYS false
  risk_note?: string;
  units?: string;
  edge_claimed: boolean; // ALWAYS false
  real_money_enabled: boolean; // ALWAYS false
  honest_note?: string;
  reason?: string;
};

// The sign-audited beat-the-close CLV scoreboard (quant clv envelope wraps a
// clv_summary). vs_close_proven defaults FALSE (UNPROVEN). NO $ field.
export type QuantClvSummary = {
  n_bets: number;
  pct_beat_close: number | null;
  // mean_clv_pct is the ALL-rows mean -- CONTEXT ONLY, may include proxy closes.
  mean_clv_pct: number | null;
  // true-close-preferred headline; see ClvScoreboard for basis semantics.
  median_clv_pct?: number | null;
  basis?: "true_close" | "proxy_only" | null;
  n_proxy?: number;
  by_sport: Record<string, ClvBySport>;
  clv_is_proxy: boolean;
  vs_close_proven: boolean; // ALWAYS false unless gate-proven
  note?: string;
};

export type QuantClv = {
  status: string;
  clv: QuantClvSummary;
  units?: string;
  edge_claimed: boolean; // ALWAYS false
  real_money_enabled: boolean; // ALWAYS false
  honest_note?: string;
  reason?: string;
};

// Single game projection (GET /api/predict/{sport}/{game_id}).
export type PredictGame = {
  status: string;
  schema_version?: string;
  sport: string;
  generated_at: string | null;
  prediction?: PredictRecord;
  markets?: PredictMarket[];
  edges?: Array<Record<string, unknown>>;
  honest_note?: string;
  reason?: string;
};

// ---------------------------------------------------------------------------
// PaperPredictions -- model prediction history from GET /api/paper/predictions.
//
// REAL backend shape (predict_service/frontend/paper_predictions_routes.py):
//   envelope: { status, total, offset, limit, trades[], edge_claimed, ... }
//   trade:    { logged_at, sport, matchup, group, selection, model_prob,
//               market_prob, side, tier (always null), result, clv,
//               clv_status, executed, event_id, commence_time, channel, note }
//
// RawPaperTrade / RawPaperEnvelope mirror the wire shape exactly.
// PaperPredictionRow / PaperPredictions are the NORMALIZED shapes the UI reads
// (produced by normalizeRawEnvelope in p5api.ts).  Mapped fields:
//   result -> outcome  |  clv -> clv_pct  |  group -> market_type
//   event_id -> game_id  |  logged_at -> ts  |  selection -> side (also kept)
// Fields absent from the real backend (line, stake_units, beat_close,
//   clv_is_proxy, edge_vs_market, final_score, decision) are optional so
//   test fixtures that include them keep compiling.
// ---------------------------------------------------------------------------

/** Raw single trade row as the backend returns it. */
export type RawPaperTrade = {
  logged_at:      string | null;
  sport:          string | null;
  matchup:        string | null;
  group:          string | null;   // market group / type
  selection:      string | null;   // side / selection label
  model_prob:     number | null;
  market_prob:    number | null;
  side:           string | null;
  tier:           string | null;   // always null from the backend currently
  result:         string | null;   // "win" | "loss" | "push" | "pending" | null
  clv:            number | null;
  clv_status:     string | null;
  executed:       boolean;
  event_id:       string | null;
  commence_time:  string | null;
  channel:        string | null;
  note:           string | null;
};

/** Raw envelope exactly as the backend returns it. */
export type RawPaperEnvelope = {
  status:              string;
  total:               number;
  offset:              number;
  limit:               number;
  trades:              RawPaperTrade[];
  edge_claimed:        boolean;
  real_money_enabled:  boolean;
  honest_note?:        string;
};

/**
 * Normalized prediction row (after normalizeRawEnvelope).
 * All field names match what the UI components already read.
 * Optional fields (line, stake_units, etc.) are absent from the real backend
 * but present in test fixtures -- kept optional so both compile.
 */
export type PaperPredictionRow = {
  game_id:        string | null;   // <- event_id
  matchup:        string | null;
  sport:          string | null;
  market_type:    string | null;   // <- group
  side:           string | null;   // <- selection
  model_prob:     number | null;
  market_prob:    number | null;
  edge_vs_market?: number | null;
  tier:           string | null;
  stake_units?:   number | null;   // not in real backend; optional for tests
  decision?:      string | null;
  outcome:        string | null;   // <- result
  final_score?:   string | null;
  clv_pct:        number | null;   // <- clv
  beat_close?:    boolean | null;
  clv_is_proxy?:  boolean;
  clv_status?:    string | null;
  ts:             string | null;   // <- logged_at
  line?:          number | null;   // not in real backend; optional for tests
};

export type PaperPredictions = {
  status:        string;
  count:         number;           // <- total
  generated_at?: string | null;
  predictions:   PaperPredictionRow[];
  honest_note?:  string;
  edge_claimed:  boolean;          // ALWAYS false
  reason?:       string;
};

// ---------------------------------------------------------------------------
// Paper P&L equity-curve series -- GET /api/paper/pnl/series.
// UNITS only -- NO $ field. mean_clv_pct_or_INSUFFICIENT is a number when proven
// or the literal string "INSUFFICIENT_DATA" otherwise (surfaced verbatim).
// edge_claimed ALWAYS false; executed ALWAYS false (paper simulation).
// ---------------------------------------------------------------------------
export type PnlSeriesPoint = {
  ts: string | null;
  day: string | null;
  balance_units: number;       // running bankroll in UNITS
  daily_units: number;         // that day's net P&L in UNITS
  cumulative_units: number;    // cumulative net P&L vs start (UNITS)
  n_bets: number;
  n_win: number;
  n_loss: number;
};

export type PnlDailyPoint = {
  day: string;
  daily_units: number;
};

export type PnlSummary = {
  total_units: number;         // cumulative net P&L (UNITS) vs start
  n_bets: number;
  n_win: number;
  n_loss: number;
  n_push: number;
  win_rate: number | null;     // [0,1] or null when no settled bets
  // number when proven, or the literal "INSUFFICIENT_DATA"
  mean_clv_pct_or_INSUFFICIENT: number | string | null;
  current_units: number;       // current bankroll balance in UNITS
};

export type PnlSeries = {
  start_units: number;
  points: PnlSeriesPoint[];
  daily: PnlDailyPoint[];
  summary: PnlSummary;
  honest_note?: string;
  edge_claimed: boolean;       // ALWAYS false
  executed: boolean;           // ALWAYS false (paper simulation)
  status?: string;             // "ok" | "unavailable"
  reason?: string;
};

// Paper bankroll snapshot -- GET /api/paper/bankroll. UNITS only; no $.
export type PaperBankroll = {
  start_units: number;
  current_units: number;
  updated_at: string | null;
  honest_note?: string;
  status?: string;             // "ok" | "unavailable"
  reason?: string;
};

// ---------------------------------------------------------------------------
// W12 new endpoint types -- extracted to types_w12.ts to stay under the
// DATA-module LOC ceiling (~600-750). Re-exported here so existing callers
// of "@/lib/types" continue to work without any import-path change.
// ---------------------------------------------------------------------------
export type {
  BookShopEntry,
  BestBetsCard,
  BestBetsBoard,
  PlayerPropRow,
  PropsBoard,
  LinesMatrixEntry,
  LinesMatrix,
  BoxscoreRow,
  Boxscore,
  InGameFull,
  PmTrailRow,
  PmTrail,
  ImproveLedgerCycle,
  ImproveLedger,
  // ws6 / SI-06: CLV corpus candidates panel
  ClvCorpusCandidate,
  ClvCorpus,
} from "./types_w12";
