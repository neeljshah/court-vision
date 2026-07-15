// p5api.ts -- typed client for the P5 predict-service Auto-API (:8099).
// READ-ONLY. Never recomputes; every panel renders exactly what the API
// returns, and degrades to an explicit "unavailable" sentinel on any error.
//
// The response TYPES live in lib/types.ts (moved there to keep this client
// module under the 300-LOC rail). They are re-exported below so existing
// `import { Report, api, ... } from "@/lib/p5api"` call sites keep working
// unchanged -- this module stays the single import surface for the client.

import type {
  Unavailable,
  ReportList,
  Report,
  BestBetsEnvelope,
  GameEdge,
  ClvScoreboard,
  PaperOpen,
  ImproveStatus,
  ImproveTimeline,
  AutonomyStatus,
  Parity,
  OpsStatus,
  SupervisorStatus,
  InGameGates,
  InGameServed,
  PaperTrail,
  ClvSeries,
  PaperPlacePayload,
  PaperPlaceResult,
  LinesBoard,
  LineHistory,
  GateStatus,
  Results,
  ProduceStatus,
  PredictEnvelope,
  PredictGame,
  Catalog,
  AllHonest,
  QuantValidate,
  QuantRisk,
  QuantClv,
  // W12 new endpoint types
  BestBetsBoard,
  PropsBoard,
  LinesMatrix,
  Boxscore,
  InGameFull,
  PmTrail,
  ImproveLedger,
  // WS4: prediction history
  PaperPredictions,
  RawPaperEnvelope,
  // Paper equity-curve + bankroll
  PnlSeries,
  PaperBankroll,
} from "./types";

// Re-export every P5 API type (including W12 types re-exported by types.ts from
// types_w12.ts) so consumers can keep importing from "@/lib/p5api" unchanged.
export type * from "./types";

export const P5_BASE =
  process.env.NEXT_PUBLIC_P5_BASE || "/p5";

import { fetchHonest } from "./fetchHonest";

// getJson / postJson keep their EXACT signatures and honesty contract (a non-2xx
// / non-JSON / network error degrades to the Unavailable sentinel, never a thrown
// exception or a fabricated body). They now route through fetchHonest, which adds
// a bounded per-attempt timeout + capped-backoff retry on TRANSIENT transport
// failures only -- a server 4xx/5xx still degrades immediately. POST behaviour is
// preserved: a JSON 4xx body (e.g. a 422/409 rejection) is surfaced to the caller.
async function getJson<T>(path: string, signal?: AbortSignal): Promise<T | Unavailable> {
  return fetchHonest<T>(`${P5_BASE}${path}`, { signal });
}

async function postJson<T>(
  path: string,
  body: unknown,
  signal?: AbortSignal,
): Promise<T | Unavailable> {
  // retries:0 -- a placement is not idempotent, so never auto-resend it; the
  // timeout + honest degradation still apply.
  return fetchHonest<T>(`${P5_BASE}${path}`, { signal, body, retries: 0 });
}

// ---------------------------------------------------------------------------
// normalizeRawEnvelope -- maps real backend envelope (trades/total) to the
// normalized PaperPredictions shape (predictions/count) that all UI components
// read.  Also maps per-row field aliases:
//   result -> outcome  |  clv -> clv_pct  |  group -> market_type
//   event_id -> game_id  |  logged_at -> ts  |  selection -> side
// Never throws; returns status="unavailable" on any error.
// ---------------------------------------------------------------------------
import type { PaperPredictionRow as NormRow } from "./types";

export function normalizeRawEnvelope(
  raw: RawPaperEnvelope | Unavailable,
): PaperPredictions | Unavailable {
  if (!raw || (raw as { status?: string }).status === "unavailable") {
    return raw as Unavailable;
  }
  const env = raw as RawPaperEnvelope;
  const predictions: NormRow[] = (env.trades ?? []).map((t) => ({
    game_id:     t.event_id ?? null,
    matchup:     t.matchup  ?? null,
    sport:       t.sport    ?? null,
    market_type: t.group    ?? null,
    side:        t.selection ?? t.side ?? null,
    model_prob:  t.model_prob  ?? null,
    market_prob: t.market_prob ?? null,
    tier:        t.tier    ?? null,
    outcome:     t.result  ?? null,
    clv_pct:     t.clv     ?? null,
    clv_status:  t.clv_status ?? null,
    ts:          t.logged_at  ?? null,
    // fields absent from the real backend -- kept null so callers render '--'
    stake_units:   null,
    line:          null,
    beat_close:    null,
    clv_is_proxy:  false,
    edge_vs_market: null,
    final_score:   null,
    decision:      null,
  }));
  return {
    status:      env.status      ?? "ok",
    count:       env.total       ?? 0,
    generated_at: null,          // not in the real envelope
    predictions,
    edge_claimed: env.edge_claimed ?? false,
    honest_note:  env.honest_note,
  };
}

export const api = {
  reportList: (sport: string, s?: AbortSignal) =>
    getJson<ReportList>(`/api/report/${sport}`, s),
  report: (sport: string, gid: string, s?: AbortSignal) =>
    getJson<Report>(`/api/report/${sport}/${gid}`, s),
  bestbets: (sport: string, s?: AbortSignal) =>
    getJson<BestBetsEnvelope>(`/api/v1/bestbets/${sport}`, s),
  bestbetsGame: (sport: string, gid: string, s?: AbortSignal) =>
    getJson<GameEdge & { clv?: ClvScoreboard }>(`/api/v1/bestbets/${sport}/${gid}`, s),
  paperOpen: (s?: AbortSignal) => getJson<PaperOpen>(`/api/paper/open`, s),
  paperClv: (s?: AbortSignal) => getJson<ClvScoreboard>(`/api/paper/clv`, s),
  improve: (s?: AbortSignal) => getJson<ImproveStatus>(`/api/improve/status`, s),
  // Self-improve loop per-cycle timeline -- MEASUREMENT-ONLY / INERT. `enabled`
  // reflects the human PIPELINE_ENABLED sentinel (False here); n_promoted counts
  // only real version promotions; edge_claimed is always false. No $ field.
  getImproveTimeline: (s?: AbortSignal) =>
    getJson<ImproveTimeline>(`/api/improve/timeline`, s),
  // The ONE canonical autonomy status doc (verbatim). A missing/torn/stale feed
  // degrades to the Unavailable sentinel (overall='down'); never green-on-missing.
  getAutonomyStatus: (s?: AbortSignal) =>
    getJson<AutonomyStatus>(`/api/ops/autonomy`, s),
  parity: (s?: AbortSignal) => getJson<Parity>(`/api/parity`, s),
  // Single supervised-stack health doc (per-service liveness + freshness).
  opsStatus: (s?: AbortSignal) => getJson<OpsStatus>(`/api/ops/status`, s),
  // REAL supervisor roster from the SAME-ORIGIN read-only Next route (reads
  // supervisor_status.json off disk + enforces a stale SLA). Note: NOT prefixed
  // with P5_BASE -- this is the webapp's own /api route. `live` is TRUE only when
  // the feed is FRESH + all_ready + no proc degraded; stale/dead -> never green.
  getSupervisorStatus: (s?: AbortSignal) =>
    fetchHonest<SupervisorStatus>(`/api/ops/supervisor`, { signal: s }),
  // 4-sport in-game calibration gate verdicts (CALIBRATION only, no $ claimed).
  ingameGates: (s?: AbortSignal) => getJson<InGameGates>(`/api/ingame/gates`, s),
  // Per-game calibrated in-game win-prob (degrades to p0 when no live state).
  ingame: (sport: string, gid: string, s?: AbortSignal) =>
    getJson<InGameServed>(`/api/ingame/${sport}/${gid}`, s),

  // -- Phase-4 additive client methods (paper history, live lines, system) ----

  // Full collapsed paper trail (open+settled). Optional sport filter + row cap.
  // result is a client-side filter convenience (the API has no result param).
  getPaperTrail: (
    params?: { sport?: string; date?: string; result?: string; limit?: number },
    s?: AbortSignal,
  ) => {
    const q = new URLSearchParams();
    if (params?.sport) q.set("sport", params.sport);
    if (params?.limit != null) q.set("limit", String(params.limit));
    const qs = q.toString();
    return getJson<PaperTrail>(`/api/paper/trail${qs ? `?${qs}` : ""}`, s);
  },
  // Aggregate CLV scoreboard (units/probability only; no $).
  getPaperClv: (s?: AbortSignal) => getJson<ClvScoreboard>(`/api/paper/clv`, s),
  // Paper P&L equity-curve series ("how much I would have made" in UNITS).
  // points[] = cumulative-units curve; daily[] = per-day net; summary carries
  // mean_clv_pct_or_INSUFFICIENT (number or "INSUFFICIENT_DATA"). No $ field.
  // edge_claimed/executed ALWAYS false. Degrades to Unavailable sentinel.
  getPaperPnlSeries: (s?: AbortSignal) =>
    getJson<PnlSeries>(`/api/paper/pnl/series`, s),
  // Paper bankroll snapshot (start_units / current_units in UNITS). No $.
  getPaperBankroll: (s?: AbortSignal) =>
    getJson<PaperBankroll>(`/api/paper/bankroll`, s),
  // CLV-over-time series for the trend chart (settled-with-close bets only).
  getPaperClvSeries: (params?: { sport?: string }, s?: AbortSignal) => {
    const q = new URLSearchParams();
    if (params?.sport && params.sport !== "all") q.set("sport", params.sport);
    const qs = q.toString();
    return getJson<ClvSeries>(`/api/paper/clv/series${qs ? `?${qs}` : ""}`, s);
  },
  // Open paper positions (collapsed trail filtered to status='open').
  paperOpenSport: (sport?: string, s?: AbortSignal) => {
    const q = sport ? `?sport=${encodeURIComponent(sport)}` : "";
    return getJson<PaperOpen>(`/api/paper/open${q}`, s);
  },
  // Place a MANUAL paper bet (paper-only, executed always false; no $ field).
  placePaper: (payload: PaperPlacePayload, s?: AbortSignal) =>
    postJson<PaperPlaceResult>(`/api/paper/place`, payload, s),

  // All-books line board for a sport (optionally one game). Freshness from the
  // envelope generated_at, never the browser fetch time.
  getLines: (sport: string, gameId?: string, s?: AbortSignal) => {
    const q = gameId ? `?game_id=${encodeURIComponent(gameId)}` : "";
    return getJson<LinesBoard>(`/api/lines/${sport}${q}`, s);
  },
  // Per-prop line-move history (Dialog only). market_type/side narrow the series.
  getLineHistory: (
    sport: string,
    gameId: string,
    params?: { market_type?: string; side?: string },
    s?: AbortSignal,
  ) => {
    const q = new URLSearchParams();
    if (params?.market_type) q.set("market_type", params.market_type);
    if (params?.side) q.set("side", params.side);
    const qs = q.toString();
    return getJson<LineHistory>(
      `/api/lines/${sport}/${gameId}/history${qs ? `?${qs}` : ""}`,
      s,
    );
  },

  // Real-money MODE gate state (default-DENY; always PAPER ONLY in this build).
  getGateStatus: (s?: AbortSignal) => getJson<GateStatus>(`/api/gate/status`, s),
  // Settled finals for outcome display (real scores or nothing).
  getResults: (sport: string, gameId?: string, s?: AbortSignal) => {
    const q = gameId ? `?game_id=${encodeURIComponent(gameId)}` : "";
    return getJson<Results>(`/api/results/${sport}${q}`, s);
  },
  // Per-sport producer freshness (stale-never-green; no $ field).
  getProduceStatus: (sport?: string, s?: AbortSignal) => {
    const q = sport ? `?sport=${encodeURIComponent(sport)}` : "";
    return getJson<ProduceStatus>(`/api/produce/status${q}`, s);
  },

  // Full latest snapshot envelope for a sport (predict surface).
  getPredict: (sport: string, s?: AbortSignal) =>
    getJson<PredictEnvelope>(`/api/predict/${sport}`, s),
  // Single game projection from the latest snapshot.
  getPredictGame: (sport: string, gid: string, s?: AbortSignal) =>
    getJson<PredictGame>(`/api/predict/${sport}/${gid}`, s),

  // -- Unified-gateway catalog + the single honesty bit -----------------------

  // The contracted gateway faces (prediction/execution/lines/intelligence) with
  // version + capabilities + routes + honest_note. units only; edge_claimed false.
  getCatalog: (s?: AbortSignal) => getJson<Catalog>(`/api/catalog`, s),
  // THE single product-wide honesty bit. ok=true ONLY if NO face violates a
  // rail; it flips false the instant any does (the UI shows RED, never hides it).
  getAllHonest: (s?: AbortSignal) =>
    getJson<AllHonest>(`/api/status.all_honest`, s),

  // -- Quant EXECUTION surface (transparency only; UNITS/probability, no $) ----

  // Per-game, per-market auditable bet-validation verdicts (tier/units/edge/ev/
  // clv/gate_proven). MOST verdicts are no_bet / match-the-close -- a SUCCESS.
  getQuantValidate: (sport: string, s?: AbortSignal) =>
    getJson<QuantValidate>(`/api/quant/${sport}/validate`, s),
  // UNIT-space variance / exposure descriptors over the open paper book. RoR is
  // a model-conditional descriptive stat, NOT a profit/safety guarantee. No $.
  getQuantRisk: (s?: AbortSignal) => getJson<QuantRisk>(`/api/quant/risk`, s),
  // The sign-audited beat-the-close CLV scoreboard. vs_close defaults UNPROVEN.
  getQuantClv: (s?: AbortSignal) => getJson<QuantClv>(`/api/quant/clv`, s),

  // -- W12 new typed clients (W3/W2/W1/W4/W5/W10 API endpoints) -------------

  // Best Bets board: ranked calibrated divergence cards across sports.
  // status filter: "live" | "pregame" | "done" | undefined (all).
  // tier filter: "S" | "A" | "B" | "C" | undefined (all). No $ field.
  bestbetsBoard: (
    params?: { sport?: string; tier?: string; status?: string },
    s?: AbortSignal,
  ) => {
    const q = new URLSearchParams();
    if (params?.sport) q.set("sport", params.sport);
    if (params?.tier) q.set("tier", params.tier);
    if (params?.status) q.set("status", params.status);
    const qs = q.toString();
    return getJson<BestBetsBoard>(
      `/api/bestbets/board${qs ? `?${qs}` : ""}`,
      s,
    );
  },

  // Player-prop predictions board per sport.
  // Degrades to UNAVAILABLE in offseason (no live prop lines). No $ field.
  propsBoard: (sport: string, gameId?: string, s?: AbortSignal) => {
    const q = gameId ? `?game_id=${encodeURIComponent(gameId)}` : "";
    return getJson<PropsBoard>(`/api/predict/props/${sport}${q}`, s);
  },

  // Per-book odds matrix for a game: market_type -> side -> [{book,odds,line,...}].
  // best = best price per market/side across books. No $ field.
  linesMatrix: (sport: string, gameId: string, s?: AbortSignal) =>
    getJson<LinesMatrix>(
      `/api/lines/${sport}/${encodeURIComponent(gameId)}/matrix`,
      s,
    ),

  // Composite in-game payload: score + win_prob + boxscore + prop_proj + CLV status.
  // clv_status may be "INSUFFICIENT_DATA" -- never fabricated. No $ field.
  ingameFull: (sport: string, gid: string, s?: AbortSignal) =>
    getJson<InGameFull>(`/api/ingame/${sport}/${encodeURIComponent(gid)}/full`, s),

  // Live player boxscore (pts/reb/ast/min). Degrades to UNAVAILABLE when not live.
  boxscore: (sport: string, gid: string, s?: AbortSignal) =>
    getJson<Boxscore>(
      `/api/boxscore/${sport}/${encodeURIComponent(gid)}`,
      s,
    ),

  // PM (Kalshi/Polymarket) paper-trail browse. CLV may be null (no_close) --
  // rendered honestly, never a 0-fill. No $ P&L field.
  pmTrail: (
    params?: { venue?: string; result?: string; tier?: string },
    s?: AbortSignal,
  ) => {
    const q = new URLSearchParams();
    if (params?.venue) q.set("venue", params.venue);
    if (params?.result) q.set("result", params.result);
    if (params?.tier) q.set("tier", params.tier);
    const qs = q.toString();
    return getJson<PmTrail>(
      `/api/paper/pm/trail${qs ? `?${qs}` : ""}`,
      s,
    );
  },

  // Per-sport Brier/ECE/BSS per self-improve cycle from the improve ledger.
  // edge_claimed ALWAYS false. No $ field.
  improveLedger: (s?: AbortSignal) =>
    getJson<ImproveLedger>(`/api/improve/ledger`, s),

  // WS4 -- Model prediction history from GET /api/paper/predictions.
  // Returns calibrated pregame predictions (model_prob, tier, stake_units).
  // UNITS / probability only -- NO $ field. edge_claimed ALWAYS false.
  // Degrades to UNAVAILABLE sentinel when the predict service is offline or
  // no predictions have been recorded yet; UI shows honest empty state.
  paperPredictions: (
    params?: { sport?: string; limit?: number },
    s?: AbortSignal,
  ) => {
    const q = new URLSearchParams();
    if (params?.sport) q.set("sport", params.sport);
    if (params?.limit != null) q.set("limit", String(params.limit));
    const qs = q.toString();
    return getJson<PaperPredictions>(
      `/api/paper/predictions${qs ? `?${qs}` : ""}`,
      s,
    );
  },

  // W1-records-surface -- paged variant of /api/paper/predictions.
  // Adds offset for server-style pagination. All honesty rails from
  // paperPredictions apply: UNITS only, NO $ field, edge_claimed=false.
  // Degrades to UNAVAILABLE sentinel on error; never fabricates rows.
  // normalizeRawEnvelope maps the real wire shape (trades/total/result/clv/
  // group/event_id) to the normalized PaperPredictions shape that all UI
  // components read (predictions/count/outcome/clv_pct/market_type/game_id).
  getPaperPredictions: async (
    params?: { sport?: string; offset?: number; limit?: number },
    s?: AbortSignal,
  ): Promise<PaperPredictions | Unavailable> => {
    const q = new URLSearchParams();
    if (params?.sport) q.set("sport", params.sport);
    if (params?.offset != null) q.set("offset", String(params.offset));
    if (params?.limit  != null) q.set("limit",  String(params.limit));
    const qs = q.toString();
    const raw = await getJson<RawPaperEnvelope>(
      `/api/paper/predictions${qs ? `?${qs}` : ""}`,
      s,
    );
    return normalizeRawEnvelope(raw as RawPaperEnvelope | Unavailable);
  },

  // WS6 / SI-06 -- CLV corpus candidate rows from GET /api/improve/clv-corpus.
  // Each row carries replication_label (REPLICATION_PENDING | REPLICATED) and
  // vs_close (UNPROVEN) surfaced VERBATIM.  Missing file -> status=unavailable.
  // UNITS / probability only -- NO $ / edge / profit field.  edge_claimed=false.
  getClvCorpus: (
    params?: { limit?: number; name_filter?: string },
    s?: AbortSignal,
  ) => {
    const q = new URLSearchParams();
    if (params?.limit != null) q.set("limit", String(params.limit));
    if (params?.name_filter) q.set("name_filter", params.name_filter);
    const qs = q.toString();
    return getJson<import("./types").ClvCorpus>(
      `/api/improve/clv-corpus${qs ? `?${qs}` : ""}`,
      s,
    );
  },
};

export function isUnavailable(x: unknown): x is Unavailable {
  return (
    !!x &&
    typeof x === "object" &&
    (x as { status?: string }).status === "unavailable"
  );
}

export const SPORTS = ["nba", "mlb", "soccer", "soccer_intl", "tennis"] as const;
export type Sport = (typeof SPORTS)[number];

// SSE stream URL for one game's report (poll fallback handled in components).
export const streamUrl = (sport: string, gid: string) =>
  `${P5_BASE}/api/stream/game/${sport}/${gid}`;
