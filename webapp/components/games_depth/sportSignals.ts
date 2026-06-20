// sportSignals.ts -- the curated, gate-tested signal map per sport.
//
// Mirrors the leak-free gate verdicts in data/frontend/funnel/*.json so a reader
// can see WHICH validated signals feed each sport's prediction and how each fared
// at the gate. The ONLY SHIP across all four sports is soccer's corners-asof
// signal, and it ships as a CALIBRATION prior with vs_close UNPROVEN -- never an
// edge. Everything else is an honest REJECT (recorded as a success, not a
// failure), INSUFFICIENT_DATA, or TIER3_BLOCKED.
//
// HONESTY RAILS: no $ / ROI / payout field anywhere. A SHIP is calibration-only.
// These verdicts are descriptive scouting metadata, NOT a bet recommendation.

import type { SignalVerdict } from "@/components/depth";

export interface SportSignal {
  /** Human-readable signal name. */
  name: string;
  /** Leak-free gate verdict. */
  verdict: SignalVerdict;
  /** The deciding stat / reason, shown on hover. */
  stat: string;
}

// Per-sport gate-tested signal catalog. Keyed by the route sport slug.
// soccer_intl reuses the soccer catalog (same engine family). Sourced from the
// funnel gate JSON verdicts; kept terse and descriptive.
const SIGNALS: Record<string, SportSignal[]> = {
  nba: [
    {
      name: "possession in-game win-prob",
      verdict: "REJECT",
      stat: "per-state columns add nothing over sigmoid((a+b*frac)*state_diff) base; calibration only",
    },
    {
      name: "travel / schedule miles",
      verdict: "REJECT",
      stat: "strictly-prior travel_* over Elo logit -- no proper-score unanimity; planted-null also rejects",
    },
  ],
  mlb: [
    {
      name: "Statcast in-game win-prob",
      verdict: "REJECT",
      stat: "as-of Statcast over (state_diff,frac) base -- no held-out Brier lift; planted-null rejects",
    },
    {
      name: "at-bat micro-state",
      verdict: "REJECT",
      stat: "per-at-bat conditioning does not beat the base in-game curve; calibration only",
    },
  ],
  soccer: [
    {
      name: "corners diff (as-of)",
      verdict: "SHIP",
      stat: "diff_corners_asof beats EW-Poisson base on held-out Brier across 2 corpora -- CALIBRATION prior, single-fold scouting",
    },
    {
      name: "ESPN-28 native feed (offsides/saves)",
      verdict: "INSUFFICIENT_DATA",
      stat: "~185 rows on disk -- too thin to gate; dense football-data mirror still gated",
    },
    {
      name: "StatsBomb event features",
      verdict: "REJECT",
      stat: "largely subsumed by attack/defense strength; no leak-free lift over base",
    },
    {
      name: "red-card in-game",
      verdict: "REJECT",
      stat: "red-card state does not beat the in-game base curve on held-out Brier",
    },
  ],
  tennis: [
    {
      name: "point-by-point aggregates",
      verdict: "TIER3_BLOCKED",
      stat: "0 corpora reachable (Sackmann slam-pbp repo 404 from this env); needs >=2 slam-year corpora + Elo base",
    },
    {
      name: "set-detail features",
      verdict: "TIER3_BLOCKED",
      stat: "blocked at tier-3 gate -- not promoted; honest-empty until corpora acquired",
    },
  ],
};

/** Validated signal catalog for a sport (soccer_intl -> soccer). Empty if none. */
export function sportSignals(sport: string): SportSignal[] {
  const key = sport === "soccer_intl" ? "soccer" : sport;
  return SIGNALS[key] ?? [];
}
