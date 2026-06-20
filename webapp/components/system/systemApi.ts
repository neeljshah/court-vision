// systemApi.ts -- page-local typed fetchers for the System page's two artifact
// surfaces (gate-verdict ledger + improvement backlog). These read the new
// read-only endpoints mounted on the canonical :8099 service:
//   GET /api/funnel/ledger  -- every signal run through the leak-free gate
//   GET /api/meta/backlog   -- the ranked "what we'll get better at next" list
//
// HONESTY RAILS: READ-ONLY; any non-2xx / non-JSON / empty response degrades to
// the explicit Unavailable sentinel (never green-on-missing, never a fabricated
// row). NO $ field -- verdicts are CALIBRATION-only and vs_close stays UNPROVEN;
// the backlog is MEASUREMENT-ONLY (it ranks, it never ships or flips a flag).
//
// We reuse P5_BASE + isUnavailable from the FROZEN shared client (@/lib/api) and
// do NOT edit it -- this keeps page-local concerns out of the shared surface.

import { P5_BASE, isUnavailable, type Unavailable } from "@/lib/api";

export interface LedgerRow {
  id: string;
  sport: string | null;
  layer: string | null;
  verdict: string;
  vs_close: string;
  source: string;
  edge_claimed: false;
}

export interface GateLedger {
  status: string;
  rows: LedgerRow[];
  n: number;
  counts: Record<string, number>;
  honest_note?: string;
  edge_claimed: false;
}

export interface BacklogCandidate {
  id: string;
  category?: string;
  sport?: string;
  what?: string;
  where?: string;
  expected_outcome?: string;
  gate_action?: string;
  priority?: number;
}

export interface Backlog {
  status: string;
  note?: string;
  categories: string[];
  candidates: BacklogCandidate[];
  n: number;
  edge_claimed: false;
}

async function getJson<T>(path: string, signal?: AbortSignal): Promise<T | Unavailable> {
  try {
    const r = await fetch(`${P5_BASE}${path}`, { signal, cache: "no-store" });
    if (!r.ok) return { status: "unavailable", reason: `HTTP ${r.status}` };
    const ctype = r.headers.get("content-type") || "";
    if (!ctype.includes("application/json")) {
      return { status: "unavailable", reason: `non-JSON (${ctype || "none"})` };
    }
    return (await r.json()) as T;
  } catch (e) {
    return { status: "unavailable", reason: `fetch failed: ${String(e)}` };
  }
}

export interface ClvPoint {
  game_id?: string;
  sport?: string;
  clv?: number;
  settled_at?: string | number;
}

export interface ClvOverTime {
  status: string;
  pool_verdict: string; // BEAT / MATCH / BEHIND / INSUFFICIENT_DATA
  n_games?: number;
  n_settled_games?: number;
  pooled_mean_clv?: number;
  clv_ci95?: [number, number];
  clv_over_time: ClvPoint[];
  vs_close?: string;
  label?: string;
  units?: string;
  edge_claimed: false;
}

// --- Rich on-disk artifact surface (page-local Next route reads the files) ----
// The /api/funnel/ledger + /api/meta/backlog endpoints above need the live :8099
// service. The route below reads the SAME on-disk artifacts directly through a
// same-origin Next route handler (app/system/funnel-artifacts), so the rich
// ledger + backlog render even when the Python service is down. Same honesty
// rails: READ-ONLY, CALIBRATION verdicts, vs_close UNPROVEN, NO $ field.

export interface RichLedgerRow {
  id: string;
  sport: string;
  layer: string;
  verdict: string; // SHIP | REJECT | PARTIAL | TIER3_BLOCKED | INSUFFICIENT_DATA | COHERENCE
  deciding_stat: string;
  corpora: number;
  vs_close: string;
  base: string;
  source: string;
}

export interface RichBacklogCandidate {
  id: string;
  category?: string;
  sport?: string;
  what?: string;
  where?: string;
  expected_outcome?: string;
  gate_action?: string;
  priority?: number;
}

export interface FunnelArtifacts {
  status: string;
  ledger: { rows: RichLedgerRow[]; counts: Record<string, number> };
  backlog: {
    note?: string;
    categories?: string[];
    count?: number;
    candidates?: RichBacklogCandidate[];
  } | null;
  honest_note?: string;
  edge_claimed: false;
}

// Same-origin Next route (no P5_BASE) -- always reachable when the page renders.
async function getLocalJson<T>(path: string, signal?: AbortSignal): Promise<T | Unavailable> {
  try {
    const r = await fetch(path, { signal, cache: "no-store" });
    if (!r.ok) return { status: "unavailable", reason: `HTTP ${r.status}` };
    return (await r.json()) as T;
  } catch (e) {
    return { status: "unavailable", reason: `fetch failed: ${String(e)}` };
  }
}

export const systemApi = {
  ledger: (s?: AbortSignal) => getJson<GateLedger>("/api/funnel/ledger", s),
  backlog: (s?: AbortSignal) => getJson<Backlog>("/api/meta/backlog", s),
  clvOverTime: (s?: AbortSignal) => getJson<ClvOverTime>("/api/clv/over-time", s),
  // Rich, always-on-disk artifact surface (same-origin Next route).
  artifacts: (s?: AbortSignal) =>
    getLocalJson<FunnelArtifacts>("/system/funnel-artifacts", s),
};

export { isUnavailable };
