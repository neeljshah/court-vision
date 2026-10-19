// desk.server.ts -- the single build-time reader for the /desk pages.
// Reads webapp/public/data/desk/latest.json, written by
//   python -m scripts.platformkit.frontend.desk_export --date <D> --stage
// Same pattern as showcase.server.ts: readFileSync at build time, no client
// fetch. A missing or unreadable file returns null and every page renders an
// explicit "not available" chip; a section the exporter could not build is
// null in the JSON and its reason is in `refusals` -- never a blank or a zero.
// PAPER ONLY: simulated maker quotes on the recorded Kalshi tape; not a verdict.

import { readFileSync } from "node:fs";
import { join } from "node:path";

export const DESK_FILE = join(process.cwd(), "public", "data", "desk", "latest.json");

export type Refusal = { section: string; reason: string };
export type Num = number | null;

export type ScoreRow = {
  sport: string; segment: string; target: string; arm: string;
  brier: Num; logloss: Num; brier_minus_A: Num; logloss_minus_A: Num;
  n_ticks: Num; n_games: Num; verdict: string | null; reason: string | null;
};
export type LedgerRow = {
  date: string; quote_life_s: string | null; fills: Num; settled_fills: Num; unsettled_fills: Num;
  contracts: string | null; fee_cents: string | null; mode?: string | null; note?: string | null;
};
export type NightRow = {
  date: string;
  fill_realism?: { quotes_placed: Num; fills_ttl30: Num; fills_ttl5: Num; quote_life_expiry: Num } | null;
  fills_rows?: number;
  reconciled?: Record<string, boolean | null>;
};
export type CoverageSport = {
  sport: string; enabled: boolean | null; listed: Num; selected: Num; served: Num;
  qualified: Record<string, number> | null; scored_games?: Record<string, number> | null;
  scored_ticks?: Record<string, number> | null;
};
export type LiveArm = {
  n_rows: Num; n_intervals: Record<string, number> | null; n_games: Num; verdict: string | null;
  quote_hours: Num; queue_unknown: Num;
  fills: Record<string, unknown> | null;
  markout_through: Record<string, { n: Num; mean_prob_points: Num }>;
};
export type Figure = {
  key: string; market?: string | null; metric?: string | null; devig?: string | null;
  n?: Num; n_unit?: string | null; model?: Num; close?: Num; gap?: Num; ci95?: [number, number] | null;
  verdict?: string | null; as_of?: string | null; source?: string | null; licenses?: string | null;
};
export type ModelCard = {
  sport: string; pregame: string; daily_fit: boolean; fit_note: string;
  ingame_live_arms: { arm: string; what: string | null }[] | null; figures: Figure[];
};
export type Step = {
  name: string; step_status: string | null; exit_code: Num; reason: string | null; wall_s: Num; peak_mb: Num;
};

export type Desk = {
  schema: string;
  date: string;
  header: string;
  generated_at_utc: string;
  command?: string;
  record: { ledger: LedgerRow[]; nights: NightRow[] } | null;
  scoreboard: {
    date: string; scope: string | null; arm_order: string[] | null; reference_arm: string;
    rows: ScoreRow[]; refusal_counts: Record<string, number>; games: number; ticks: number;
    contrasts: Record<string, Record<string, Record<string, { mean: Num; n_ticks: Num; n_games: Num; verdict: string | null }>>>;
  } | null;
  coverage: { date: string; scope: string | null; listed_definition: string | null; sports: CoverageSport[];
    refusals: Record<string, number>; refusal_total: Num } | null;
  ingame: {
    date: string; status: string | null; reason: string | null; gap_s: Num;
    receipt_lag_s: { n: Num; p50: Num; max: Num; p90: Num; p90_note: string };
    arms: Record<string, LiveArm>; refusals: Record<string, number>; section_refusals: Record<string, number>;
    incomplete_tickers: number; unpaired_games: Num; assumptions: Record<string, unknown>;
    sport_arms: Record<string, string[]> | null;
  } | null;
  execution: {
    fill_realism?: {
      date: string; source: string; quotes_placed: Num; fills_ttl30: Num; fills_ttl5: Num; quote_life_expiry: Num;
      by_side: Record<string, number>; by_fill_basis: Record<string, number>;
      grid_table: { ttl_s: string; units: string; quotes_placed: Num; fills_credited: Num }[];
      markout_cents_by_horizon_s: Record<string, { n: number; mean: Num }>;
    };
    latency?: { source: string; pooled: { sport: string; feed: string; games: Num; flagged_games: Num;
      book_moved_first_share: Num; first_mid_change_minus_event_s: Record<string, number> | null }[] };
    exec_quality?: { source: string; days: string[] | null; census: Record<string, unknown> | null;
      estimand_version: string | null; refusals: Record<string, number> | null; not_verified: string[] | null };
  } | null;
  models: { cards: ModelCard[]; scoreboard_arms: Record<string, string>; desk_figures: Record<string, unknown>[];
    canonical_as_of: string | null; canonical_source: string } | null;
  health: {
    nights: { date: string; status: string | null; reasons: string[] | null; steps: Step[] }[];
    desk_status: Record<string, { decision: string | null; reason: string | null; ts: string | null; subject: string | null }> | null;
    issues: { total: number; open: number; open_by_severity: Record<string, number>;
      open_by_kind: Record<string, number>; by_status: Record<string, number> } | null;
  } | null;
  sources: { path: string; sha256: string | null; mtime_utc: string | null }[];
  refusals: Refusal[];
  retracted_token_hits: string[];
};

/** Parse a desk export; anything without the schema tag is treated as absent. */
export function parseDesk(text: string): Desk | null {
  try {
    const d = JSON.parse(text) as Desk;
    return d && d.schema === "desk_export_v1" ? d : null;
  } catch {
    return null;
  }
}

/** Build-time load of the staged export; null when it was never staged. */
export function loadDesk(file: string = DESK_FILE): Desk | null {
  try {
    return parseDesk(readFileSync(file, "utf-8"));
  } catch {
    return null;
  }
}

/** Every refusal whose section is `prefix` or starts with `prefix.`. */
export function refusalsFor(desk: Desk | null, prefix: string): Refusal[] {
  if (!desk) return [{ section: prefix, reason: "desk export not staged (webapp/public/data/desk/latest.json)" }];
  return desk.refusals.filter((r) => r.section === prefix || r.section.startsWith(prefix + "."));
}

/** Format a nullable number; null renders as an em-free ASCII dash. */
export function fmt(v: Num | undefined, dp = 4): string {
  return v == null ? "-" : v.toFixed(dp);
}
