import type {
  HealthResponse,
  SimGameRequest,
  SimGameResponse,
  OverProbRequest,
  OverProbResponse,
  PropStackResult,
  EdgeResponse,
  WinProbResponse,
  LineupResponse,
  BacktestResponse,
  ShotProbResponse,
  WinProbModelResponse,
  PlayerImpactResponse,
  InjuryRiskResponse,
  BreakoutResponse,
  GamePredictionRequest,
  GamePrediction,
  TodayPredictionsResponse,
  PlayerPropsResponse,
  ShotChartResponse,
  TrackingResponse,
  EdgesTodayResponse,
  CLVSummaryResponse,
  ChatResponse,
  DashboardOverviewResponse,
  ModelPerformanceResponse,
  PortfolioSummary,
  OpenBet,
  LogBetRequest,
  AltLadderResponse,
  SignalRouterRequest,
  SignalRouterResponse,
  CorrMatrixResponse,
  ExecutionQuoteRequest,
  ExecutionQuoteResponse,
} from "@/lib/types/api";

const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...init?.headers },
    ...init,
  });
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText);
    throw new Error(`API ${res.status}: ${text}`);
  }
  return res.json() as Promise<T>;
}

function post<T>(path: string, body: unknown): Promise<T> {
  return apiFetch<T>(path, { method: "POST", body: JSON.stringify(body) });
}

// ── Health ────────────────────────────────────────────────────────────────────
export const getHealth = () => apiFetch<HealthResponse>("/health");

// ── Simulation ────────────────────────────────────────────────────────────────
export const simulateGame = (req: SimGameRequest) =>
  post<SimGameResponse>("/simulate_game", req);

export const getOverProb = (req: OverProbRequest) =>
  post<OverProbResponse>("/over_prob", req);

export const simulate = (req: { team_a: string; team_b: string; n_sims?: number; player_stats?: Record<string, unknown> }) =>
  post<SimGameResponse>("/simulate", req);

// ── Props ─────────────────────────────────────────────────────────────────────
export const getProps = (playerId: string, params?: { opp_team?: string; season?: string }) => {
  const qs = new URLSearchParams(params as Record<string, string>).toString();
  return apiFetch<PropStackResult>(`/props/${playerId}${qs ? "?" + qs : ""}`);
};

// ── Edge / Betting ────────────────────────────────────────────────────────────
export const getEdge = (
  gameId: string,
  params?: { home?: string; away?: string; home_odds?: number; away_odds?: number }
) => {
  const qs = new URLSearchParams(params as Record<string, string>).toString();
  return apiFetch<EdgeResponse>(`/edge/${gameId}${qs ? "?" + qs : ""}`);
};

// ── Win Probability ───────────────────────────────────────────────────────────
export const getWinProb = (
  gameId: string,
  params?: { home?: string; away?: string; season?: string }
) => {
  const qs = new URLSearchParams(params as Record<string, string>).toString();
  return apiFetch<WinProbResponse>(`/win-prob/${gameId}${qs ? "?" + qs : ""}`);
};

// ── Lineup ────────────────────────────────────────────────────────────────────
export const getLineup = (team: string) =>
  apiFetch<LineupResponse>(`/lineup/${team}`);

// ── Backtest ──────────────────────────────────────────────────────────────────
export const backtest = (stat: string, req?: { seasons?: string[]; edge_threshold?: number }) =>
  post<BacktestResponse>(`/backtest/${stat}`, req ?? {});

// ── Models (predictions router) ───────────────────────────────────────────────
export const getShotProb = (params: {
  defender_dist: number;
  shot_angle: number;
  fatigue_proxy?: number;
  court_zone?: string;
}) => {
  const qs = new URLSearchParams(params as unknown as Record<string, string>).toString();
  return apiFetch<ShotProbResponse>(`/predictions/shot?${qs}`);
};

export const getWinProbModel = (params: {
  convex_hull_area: number;
  avg_inter_player_dist?: number;
  scoring_run?: number;
  possession_streak?: number;
  swing_point?: number;
}) => {
  const qs = new URLSearchParams(params as unknown as Record<string, string>).toString();
  return apiFetch<WinProbModelResponse>(`/predictions/win?${qs}`);
};

export const getPlayerImpact = (params: { track_id: number; made_rate?: number; shots_taken?: number }) => {
  const qs = new URLSearchParams(params as unknown as Record<string, string>).toString();
  return apiFetch<PlayerImpactResponse>(`/predictions/player-impact?${qs}`);
};

// ── Extended predictions ───────────────────────────────────────────────────────
export const getInjuryRisk = (playerId: number, season?: string) =>
  post<InjuryRiskResponse>("/predictions/injury-risk", { player_id: playerId, season: season ?? "2025-26" });

export const getBreakout = (playerId: number, params?: { opponent_team?: string; season?: string }) =>
  post<BreakoutResponse>("/predictions/breakout", { player_id: playerId, ...params });

export const predictGame = (req: GamePredictionRequest) =>
  post<GamePrediction>("/predictions/game", req);

export const getPredictionsToday = (season?: string) => {
  const qs = season ? `?season=${season}` : "";
  return apiFetch<TodayPredictionsResponse>(`/predictions/today${qs}`);
};

export const getPlayerPropsByID = (playerId: number, params?: { season?: string; opp_team?: string }) => {
  const qs = new URLSearchParams(params as Record<string, string>).toString();
  return apiFetch<PlayerPropsResponse>(`/predictions/props/${playerId}${qs ? "?" + qs : ""}`);
};

// ── Analytics ─────────────────────────────────────────────────────────────────
export const getShotChart = (gameId: string) =>
  apiFetch<ShotChartResponse>(`/analytics/shot-chart?game_id=${gameId}`);

export const getTracking = (params: {
  game_id: string;
  frame_start?: number;
  frame_end?: number;
  object_type?: string;
}) => {
  const p: Record<string, string> = { game_id: params.game_id };
  if (params.frame_start !== undefined) p.frame_start = String(params.frame_start);
  if (params.frame_end !== undefined) p.frame_end = String(params.frame_end);
  if (params.object_type) p.object_type = params.object_type;
  const qs = new URLSearchParams(p).toString();
  return apiFetch<TrackingResponse>(`/analytics/tracking?${qs}`);
};

// ── Dashboard ──────────────────────────────────────────────────────────────────
export const chat = (message: string, gameId?: string) =>
  post<ChatResponse>("/chat", { message, game_id: gameId });

export const getCLVSummary = () =>
  apiFetch<CLVSummaryResponse>("/analytics/clv-summary");

export const getEdgesToday = (minEv?: number) => {
  const qs = minEv !== undefined ? `?min_ev=${minEv}` : "";
  return apiFetch<EdgesTodayResponse>(`/analytics/edges/today${qs}`);
};

// ── Stitch ─────────────────────────────────────────────────────────────────────
export const getDashboardOverview = () =>
  apiFetch<DashboardOverviewResponse>("/stitch/dashboard/overview");

export const getStitchGamesToday = () =>
  apiFetch<{ games: unknown[]; timestamp: string }>("/stitch/games/today");

export const getModelPerformance = () =>
  apiFetch<ModelPerformanceResponse>("/stitch/models/performance");

// ── Portfolio (new execution_router endpoints) ────────────────────────────────
export const getPortfolioSummary = () =>
  apiFetch<PortfolioSummary>("/api/portfolio/summary");

export const getOpenBets = () =>
  apiFetch<{ bets: OpenBet[] }>("/api/portfolio/open");

export const logBet = (req: LogBetRequest) =>
  post<{ id: string; status: string }>("/api/portfolio/log", req);

export const closeBet = (req: { id: string; result: number; closing_line: number }) =>
  post<{ clv: number; pnl: number }>("/api/portfolio/close", req);

// ── Alt line ladder ───────────────────────────────────────────────────────────
export const getAltLadder = (player: string, stat: string) =>
  apiFetch<AltLadderResponse>(`/api/alt-ladder/${encodeURIComponent(player)}/${stat}`);

// ── Signal router ─────────────────────────────────────────────────────────────
export const routeSignals = (req: SignalRouterRequest) =>
  post<SignalRouterResponse>("/api/signals/route", req);

// ── Correlation matrix ────────────────────────────────────────────────────────
export const getCorrMatrix = () =>
  apiFetch<CorrMatrixResponse>("/api/corr-matrix");

// ── Execution ─────────────────────────────────────────────────────────────────
export const getExecutionQuote = (req: ExecutionQuoteRequest) =>
  post<ExecutionQuoteResponse>("/api/execution/quote", req);

export const submitExecution = (req: ExecutionQuoteRequest & { venue?: string }) =>
  post<{ status: string; order_id?: string; dry_run: boolean }>("/api/execution/submit", req);
