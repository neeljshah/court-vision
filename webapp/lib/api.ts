// api.ts -- the ONE typed client surface for every CourtVision page.
//
// This module EXTENDS lib/p5api.ts (it re-exports the full `api` object, every
// type, and the helpers) so that all pages can `import { api, ... } from
// "@/lib/api"` and consume a single client. p5api.ts remains the low-level
// transport; this file adds:
//   * a combined "honest product status" fetcher that the cohesive shell shows
//     (the all_honest bit + the self-improve INERT/READY flag + the real-money
//     DENY flag), each derived ONLY from real endpoints, never fabricated.
//   * small typed fetchers for the read-only honest FINDINGS surfaced on the
//     Home / How-it-works / System pages.
//
// HONESTY RAILS (mirrored from the backend): NO $ field anywhere; edge_claimed
// is always false; vs_close is UNPROVEN where unproven; an unreachable endpoint
// degrades to an explicit Unavailable sentinel, NEVER green-on-missing and never
// a fabricated slate/number. READ-ONLY. Paper mode only. Local only.

import { api, isUnavailable, P5_BASE, SPORTS } from "./p5api";
import { fetchHonest } from "./fetchHonest";
import type {
  Sport,
  AllHonest,
  ImproveTimeline,
  GateStatus,
  Parity,
  QuantRisk,
  Unavailable,
} from "./p5api";

// Re-export the entire p5api surface so "@/lib/api" is the single import point.
export * from "./p5api";

// Local read-only fetch helper for the endpoints this module adds on top of the
// p5api `api` object (p5api keeps its getJson private). Mirrors the SAME honesty
// contract: a non-2xx / non-JSON / network error degrades to the explicit
// Unavailable sentinel, NEVER a fabricated body and never green-on-missing.
async function getJsonViaP5<T>(
  path: string,
  signal?: AbortSignal,
): Promise<T | Unavailable> {
  // Routes through the hardened fetchHonest primitive (bounded timeout + capped
  // backoff retry, never-throws). Same honesty contract as p5api's getJson.
  return fetchHonest<T>(`${P5_BASE}${path}`, { signal });
}

// ---------------------------------------------------------------------------
// Combined honest product status (drives the shell indicators)
// ---------------------------------------------------------------------------

export type SelfImproveMode = "READY_INERT" | "ENABLED" | "UNKNOWN";

export interface ProductStatus {
  // The single product-wide honesty bit (true ONLY if no face violates a rail).
  allHonest: boolean | null; // null == endpoint unreachable (degrade, not green)
  allHonestReason: string;
  // Self-improve loop: this build ships it READY but INERT (human-gated OFF).
  selfImprove: SelfImproveMode;
  selfImproveLabel: string;
  // Real-money execution: always DENY in this build (paper only).
  realMoney: "DENY";
  // Which sports have a live, fresh, ok snapshot right now (honest empty == []).
  liveSports: Sport[];
  edgeClaimed: false;
}

const SELF_IMPROVE_LABELS: Record<SelfImproveMode, string> = {
  READY_INERT: "self-improve: READY (not enabled)",
  ENABLED: "self-improve: ENABLED",
  UNKNOWN: "self-improve: status unknown",
};

/**
 * Fetch the combined honest product status from real endpoints only.
 * - allHonest    <- /api/status.all_honest
 * - selfImprove  <- /api/improve/status (enabled flag; INERT here)
 * - liveSports   <- /api/predict/{sport} per sport (status === "ok")
 * Any unreachable endpoint degrades to a null/UNKNOWN/[] -- never green.
 */
export async function getProductStatus(signal?: AbortSignal): Promise<ProductStatus> {
  const [honest, timeline, ...preds] = await Promise.all([
    api.getAllHonest(signal),
    api.getImproveTimeline(signal),
    ...SPORTS.map((s) => api.getPredict(s, signal)),
  ]);

  let allHonest: boolean | null = null;
  let allHonestReason = "all_honest endpoint unreachable";
  if (!isUnavailable(honest)) {
    const h = honest as AllHonest & { ok?: boolean; all_honest?: boolean };
    const bit = h.ok ?? h.all_honest;
    if (typeof bit === "boolean") {
      allHonest = bit;
      allHonestReason = bit
        ? "no face serves a $ field / fabricated edge / stale-green / real money"
        : "a face violated an honesty rail -- shown RED, never hidden";
    }
  }

  // Self-improve: READY but INERT unless the timeline reports enabled === true.
  // The loop is MEASUREMENT-ONLY and human-gated OFF in this build, so the
  // honest default is READY_INERT even when the endpoint is unreachable.
  let selfImprove: SelfImproveMode = "READY_INERT";
  if (!isUnavailable(timeline)) {
    const tl = timeline as ImproveTimeline & { enabled?: boolean };
    selfImprove = tl.enabled === true ? "ENABLED" : "READY_INERT";
  }

  const liveSports: Sport[] = [];
  SPORTS.forEach((s, i) => {
    const env = preds[i];
    if (!isUnavailable(env) && (env as { status?: string }).status === "ok") {
      liveSports.push(s);
    }
  });

  return {
    allHonest,
    allHonestReason,
    selfImprove,
    selfImproveLabel: SELF_IMPROVE_LABELS[selfImprove],
    realMoney: "DENY",
    liveSports,
    edgeClaimed: false,
  };
}

// ---------------------------------------------------------------------------
// Honest FINDINGS (read-only, surfaced on Home / How-it-works / System)
// ---------------------------------------------------------------------------

export interface ParityHeadline {
  green: boolean | null; // null == unreachable
  nSports: number;
  reason: string;
}

/** Parity headline (FULLY GREEN is the honest finding). Degrades to null. */
export async function getParityHeadline(signal?: AbortSignal): Promise<ParityHeadline> {
  const p = await api.parity(signal);
  if (isUnavailable(p)) {
    return { green: null, nSports: 0, reason: "parity endpoint unreachable" };
  }
  const par = p as Parity & { green?: boolean; sports?: unknown[] };
  return {
    green: typeof par.green === "boolean" ? par.green : null,
    nSports: Array.isArray(par.sports) ? par.sports.length : 0,
    reason:
      par.green === true
        ? "cross-sport coverage / loop-health grid is FULLY GREEN"
        : "parity not green -- see the System page for the red cell",
  };
}

export interface RealMoneyHeadline {
  enabled: boolean | null;
  label: string;
}

/** Real-money gate (default-DENY). Degrades to null (treated as DENY in UI). */
export async function getRealMoneyHeadline(signal?: AbortSignal): Promise<RealMoneyHeadline> {
  const g = await api.getGateStatus(signal);
  if (isUnavailable(g)) {
    return { enabled: null, label: "real-money: DENY (gate unreachable -> default DENY)" };
  }
  const gs = g as GateStatus;
  const en = gs.real_money_enabled ?? false;
  return { enabled: en, label: en ? "real-money: ENABLED" : "real-money: DENY (paper only)" };
}

// ---------------------------------------------------------------------------
// Static honest narrative (the funnel + findings). These are NOT numbers -- they
// are the documented honest framing pulled from the funnel/meta artifacts, kept
// here so every page renders ONE consistent story. Numbers are always fetched
// live from the endpoints above; this is prose framing only.
// ---------------------------------------------------------------------------

export const FUNNEL_STAGES = [
  { key: "data", label: "DATA", blurb: "CV tracking + box/PBP + keyless odds, ingested per game." },
  { key: "signals", label: "SIGNALS", blurb: "Hundreds of per-player/team signals, leak-free gated." },
  { key: "models", label: "MODELS", blurb: "Prop XGB + win-prob + MOV-Elo, Shin/Platt calibrated." },
  { key: "engines", label: "ENGINES", blurb: "Possession Monte-Carlo sim -> coherent markets." },
  { key: "prediction", label: "ONE PREDICTION", blurb: "One anchor spines every market for a game." },
  { key: "validation", label: "VALIDATION", blurb: "Walk-forward + parity gate; CLV is the only yardstick." },
] as const;

export const HONEST_FINDINGS = [
  {
    title: "Parity grid (live status below)",
    body:
      "The cross-sport coverage / loop-health grid is tracked below in real time. " +
      "A present-but-broken cell would be red and fail the gate. See the ParityGrid panel for current status.",
  },
  {
    title: "Depth plateau (honest)",
    body:
      "Deeper data rejects for the close across all sports and tiers. Adding more " +
      "historical depth does not beat the devigged close -- the honest finding, recorded as a success.",
  },
  {
    title: "Confirmed corners survivor -- CALIBRATION, not a market edge",
    body:
      "One signal (soccer corners) survived the leak-free gate. It is a CALIBRATION " +
      "improvement, not a profit edge. No $ edge is claimed anywhere.",
  },
  {
    title: "In-game prior-conditioning is the measured edge",
    body:
      "Conditioning the in-game forecast on the pre-game prior is the proven, MEASURED " +
      "calibration improvement (static -> conditional Brier). Calibration, not currency.",
  },
] as const;

export const PRODUCT_NAME = "CourtVision";
export const HONEST_DISCLAIMER =
  "Calibrated decision-support only. Markets are efficient; no dollar edge is claimed. " +
  "The confirmed survivor is calibration, not a market edge. Paper mode only. Local only.";

// ---------------------------------------------------------------------------
// PROGRESS (the honest "getting better" data spine -- /api/progress)
// ---------------------------------------------------------------------------
// PROGRESS is validation COVERAGE growth + COMPLETENESS + a proven-READY-but-INERT
// improvement engine. The MODEL ITSELF IS STATIC: nothing here is a live accuracy /
// edge climb. model_static is always true; engine_enabled mirrors the human
// PIPELINE_ENABLED sentinel (false in this build). NO $ field anywhere.

export interface ProgressPerSport {
  coverage_pct: number;          // #verdicts / (#verdicts + #untested-remaining)
  n_tested: number;
  n_ship: number;
  n_reject: number;              // a REJECT is a SUCCESS (markets are efficient)
  n_insufficient: number;
  n_untested_remaining: number;
}

export interface ProgressSnapshot {
  ts: number;
  date_et: string;
  per_sport: Record<string, ProgressPerSport>;
  parity_green: boolean | null;  // null == matrix unbuildable (never green-on-error)
  backlog_total: number;
  backlog_remaining: number;
  engine_ready: boolean;         // ratchet proven-ready on a sealed fixture
  engine_enabled: boolean;       // ALWAYS false while the sentinel is absent
  model_static: true;            // the model never moves until the gate is enabled
  edge_claimed: false;
  honest_note?: string;
}

export interface ProgressHistoryPoint {
  ts: number;
  date_et: string;
  n_verdicts_cumulative: number; // REAL trend: verdicts recorded over time
  backlog_total: number;
  model_static: true;
  edge_claimed: false;
}

export interface ProgressPayload {
  status: string;                // "ok" | "unavailable"
  snapshot: ProgressSnapshot | null;
  series: ProgressSnapshot[];    // append-only ledger (cadence-day cadence)
  reconstructed_history: ProgressHistoryPoint[]; // verdict-mtime fallback trend
  model_static: true;
  model_static_note?: string;
  engine_enabled: boolean;       // ALWAYS false here
  edge_claimed: false;
  reason?: string;               // present on the unavailable sentinel
}

/**
 * Fetch the honest progress snapshot + time series from /api/progress.
 * Degrades to an explicit unavailable sentinel (model_static true, engine_enabled
 * false, empty series) on any error -- NEVER green-on-missing, never fabricated.
 * NO $ field is ever present.
 */
export async function getProgress(signal?: AbortSignal): Promise<ProgressPayload> {
  const r = await getJsonViaP5<ProgressPayload>("/api/progress", signal);
  if (isUnavailable(r)) {
    return {
      status: "unavailable",
      snapshot: null,
      series: [],
      reconstructed_history: [],
      model_static: true,
      model_static_note:
        "Progress endpoint unreachable -- the trend is coverage/verdicts, never " +
        "a live accuracy climb, and the model is STATIC until the gate is enabled.",
      engine_enabled: false,
      edge_claimed: false,
      reason: (r as Unavailable).reason,
    };
  }
  // Honesty belt-and-braces: the model is ALWAYS static and edge is NEVER claimed
  // from this surface, regardless of what the body says.
  return { ...r, model_static: true, edge_claimed: false };
}

// ---------------------------------------------------------------------------
// RISK (descriptive UNIT-space portfolio risk -- /api/quant/risk)
// ---------------------------------------------------------------------------
// RISK is DESCRIPTIVE unit-space variance / exposure, never prescriptive $ advice.
// The live endpoint (/api/quant/risk) is sport-agnostic (one open paper book); we
// accept a `sport` arg for the page's selector and echo it back, while always
// reading the real book. RoR is a model-conditional descriptive stat, NOT a
// profit/safety guarantee. NO $ field; real_money_enabled is always false.

export interface RiskView extends QuantRisk {
  sport: Sport | "all"; // echoed for the page selector; the book is global
}

/**
 * Fetch the descriptive UNIT-space portfolio risk for a sport selector.
 * The underlying book is global (the open paper trail); `sport` is echoed for the
 * page. Degrades to an explicit unavailable sentinel (zeros, RoR-not-a-guarantee)
 * on any error. NO $ field; real_money_enabled is always false.
 */
export async function getRisk(
  sport: Sport | "all" = "all",
  signal?: AbortSignal,
): Promise<RiskView> {
  const r = await api.getQuantRisk(signal);
  if (isUnavailable(r)) {
    return {
      sport,
      status: "unavailable",
      n_open: 0,
      total_exposure_units: 0,
      max_single_units: 0,
      mean_units: 0,
      variance_units2: 0,
      ror_descriptive: true,
      ror_is_guarantee: false,
      edge_claimed: false,
      real_money_enabled: false,
      units: "probability",
      reason: (r as Unavailable).reason,
    };
  }
  // Re-stamp the standing honesty rails irrespective of the body.
  return {
    ...(r as QuantRisk),
    sport,
    ror_is_guarantee: false,
    edge_claimed: false,
    real_money_enabled: false,
  };
}

export { P5_BASE };
