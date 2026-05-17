// API response types — mirrors FastAPI endpoint shapes

export interface HealthResponse {
  status: string;
  model_status: Record<string, string>;
}

export interface SimGameRequest {
  team_a: string;
  team_b: string;
  n_sims?: number;
  team_a_stats?: Record<string, unknown>;
  team_b_stats?: Record<string, unknown>;
}

export interface SimGameResponse {
  win_prob_a: number;
  win_prob_b: number;
  player_distributions?: Record<string, Record<string, { mean: number; std: number; _values?: number[] }>>;
  score_distribution?: { a: number[]; b: number[] };
  [key: string]: unknown;
}

export interface OverProbRequest {
  player_id: string;
  stat: string;
  line: number;
  team_a: string;
  team_b: string;
  roster_a: string[];
  roster_b: string[];
  n_sims?: number;
}

export interface OverProbResponse {
  player_id: string;
  stat: string;
  line: number;
  over_prob: number;
  mean: number;
}

export interface PropStackResult {
  [stat: string]: number;
}

export interface EdgeResponse {
  game_id: string;
  edges: Array<{
    team: string;
    edge: number;
    kelly: number;
    ev: number;
    implied_prob: number;
    model_prob: number;
    [key: string]: unknown;
  }>;
  error?: string;
}

export interface WinProbResponse {
  game_id: string;
  home_win_prob: number;
  win_prob_home: number;
  source: string;
  confidence: number;
  inference_ms: number;
  confidence_interval: [number, number];
  error?: string;
}

export interface LineupResponse {
  team: string;
  dnp: string[];
  active_count: string;
  error?: string;
}

export interface BacktestResponse {
  stat: string;
  n: number;
  mae: number;
  hit_rate_over: number;
  roi_at_break_even_odds: number;
  passed_gate: boolean;
  edge_buckets: Record<string, unknown>;
}

export interface ShotProbResponse {
  probability: number;
  model: string;
  inputs: Record<string, unknown>;
}

export interface WinProbModelResponse {
  win_probability: number;
}

export interface PlayerImpactResponse {
  epa_per_100: number;
  track_id: number;
  model: string;
  note?: string;
}

export interface InjuryRiskResponse {
  player_id: number;
  player_name: string;
  injury_risk_score: number;
  risk_level: string;
  load_management_prob: number;
  games_missed_recent: number;
  drivers: Record<string, unknown>;
}

export interface BreakoutResponse {
  player_id: number;
  player_name: string;
  breakout_score: number;
  predicted_pts_above_avg: number;
  key_factors: string[];
  signals: Record<string, unknown>;
}

export interface GamePredictionRequest {
  home_team: string;
  away_team: string;
  season?: string;
  player_ids?: string[];
  lines?: Record<string, unknown>;
  bankroll?: number;
  game_date?: string;
}

export interface GamePrediction {
  home_team: string;
  away_team: string;
  win_prob?: number;
  home_win_prob?: number;
  kelly_edges?: unknown[];
  props?: unknown[];
  [key: string]: unknown;
}

export interface TodayPredictionsResponse {
  games: GamePrediction[];
  season: string;
}

export interface PlayerPropsResponse {
  player_id: number;
  player_name: string;
  props: Record<string, number>;
  dnp_prob: number;
  injury_risk: number;
  suppressed: boolean;
  suppression_reason?: string;
  confidence: number;
  edges: Record<string, number | null>;
}

export interface ShotChartResponse {
  game_id: string;
  shots: Array<{
    player_id: string;
    x: number;
    y: number;
    made: boolean;
    court_zone: string;
    nearest_defender_dist: number;
    shot_angle: number;
    fatigue_proxy: number;
  }>;
}

export interface TrackingResponse {
  game_id: string;
  frame_range: [number, number];
  rows: Array<{
    frame_number: number;
    track_id: number;
    x: number;
    y: number;
    vx: number;
    vy: number;
    direction: number;
    object_type: string;
  }>;
}

export interface EdgeDetectorEdge {
  player?: string;
  stat?: string;
  direction?: string;
  line?: number;
  projection?: number;
  edge?: number;
  ev?: number;
  kelly?: number;
  confidence?: number;
  ci_low?: number;
  ci_high?: number;
  stars?: number;
  team?: string;
  game_id?: string;
  [key: string]: unknown;
}

export interface EdgesTodayResponse {
  edges: EdgeDetectorEdge[];
  count: number;
}

export interface CLVSummaryResponse {
  [key: string]: unknown;
}

export interface ChatResponse {
  response: string;
}

export interface DashboardOverviewResponse {
  today_games: unknown[];
  betting_edges: unknown[];
  injuries: unknown[];
  performance: {
    win_probability_accuracy: number;
    shots_analyzed: number;
    games_processed: number;
    models_trained: number;
    last_update: string;
  };
  timestamp: string;
}

export interface ModelPerformanceResponse {
  win_probability: { accuracy: number; brier_score: number; games_trained: number };
  player_props: { points_mae: number; rebounds_mae: number; assists_mae: number; r_squared: number };
  xfG_model: { brier_score: number; shots_analyzed: number };
  matchup_model: { r_squared: number; mae: number };
  timestamp: string;
}

// Portfolio / execution types (new endpoints)
export interface PortfolioSummary {
  bankroll: number;
  total_pnl: number;
  roi: number;
  clv_avg: number;
  open_count: number;
  drawdown_pct: number;
  win_rate: number;
  sharpe: number;
}

export interface OpenBet {
  id: string;
  player: string;
  stat: string;
  direction: "over" | "under";
  line: number;
  stake: number;
  odds: number;
  current_line?: number;
  est_pnl?: number;
  clv?: number;
  status: "open" | "settled";
  game_id?: string;
  placed_at: string;
}

export interface LogBetRequest {
  player: string;
  stat: string;
  direction: "over" | "under";
  line: number;
  stake: number;
  odds: number;
  game_id?: string;
}

export interface AltLineLadderRow {
  line: number;
  over_prob: number;
  fair_odds: number;
  ev: number;
  kelly: number;
  stake?: number;
}

export interface AltLadderResponse {
  player: string;
  stat: string;
  rows: AltLineLadderRow[];
}

export interface SignalRouterRequest {
  slate: unknown[];
}

export interface SignalRouterResponse {
  signals: unknown[];
  count: number;
}

export interface CorrMatrixResponse {
  stats: string[];
  matrix: number[][];
}

export interface ExecutionQuoteRequest {
  player: string;
  stat: string;
  direction: "over" | "under";
  stake: number;
  line: number;
}

export interface ExecutionQuoteResponse {
  venues: Array<{
    venue: string;
    available: number;
    price: number;
    slippage_bps: number;
  }>;
  total_fillable: number;
  weighted_price: number;
}
