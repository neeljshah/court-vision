// gateVerdicts.ts -- the honest gate-verdict snapshot for the How-it-works page.
//
// READ-ONLY snapshot transcribed from the on-disk verdict artifacts in
// data/frontend/funnel/*.json (the deep-data gate runs). These are NOT live API
// numbers and are NOT recomputed in the browser -- they are the recorded honest
// verdicts, surfaced so the page can show WHY most signals reject and which one
// survived. Every field below is copied verbatim from the corresponding JSON.
//
// HONESTY RAILS: exactly ONE survivor (soccer corners) and it is CALIBRATION,
// NOT a market edge -- vs_close is UNPROVEN. Every other deep-data layer is a
// recorded REJECT (a SUCCESS, not a failure). NO $ field; no edge claimed.

export type Verdict = "SHIP" | "REJECT" | "BLOCKED";

export interface GateVerdict {
  sport: string;
  layer: string;
  /** Plain-language description of the data point that was gated. */
  what: string;
  verdict: Verdict;
  /** verbatim vs_close framing from the artifact (always UNPROVEN where shown). */
  vsClose: string;
  /** one-line honest reason. */
  reason: string;
}

// Source artifacts: data/frontend/funnel/{layer}.json (transcribed 2026-06-19).
export const GATE_VERDICTS: GateVerdict[] = [
  {
    sport: "soccer",
    layer: "soccer_espn28_discipline_possession_asof",
    what: "as-of corners differential (diff_corners_asof) as a pre-match prior",
    verdict: "SHIP",
    vsClose: "UNPROVEN -- CALIBRATION only (held-out home-win Brier), not edge",
    reason:
      "The ONLY survivor: feat_better in BOTH disjoint league pairs (E0/E1 and " +
      "SP1/I1), clustered-DM p ~= 0.0015, base skillful, planted-null rejects. " +
      "Kept as a PROPOSAL / scouting prior -- never force-fed.",
  },
  {
    sport: "soccer",
    layer: "soccer_statsbomb_real_xg_event_asof",
    what: "as-of StatsBomb real event-xG pre-match prior",
    verdict: "REJECT",
    vsClose: "n/a -- did not beat base calibration",
    reason: "Real event-xG is absorbed by the attack/defense strength already in the engine.",
  },
  {
    sport: "soccer",
    layer: "soccer_redcard_ingame",
    what: "in-game red-card / man-advantage (red_diff) repricer prior",
    verdict: "REJECT",
    vsClose: "n/a -- in-game micro-state rejects vs (margin, time)",
    reason: "Red cards are sparse; goal-difference base already moves on the margin.",
  },
  {
    sport: "nba",
    layer: "nba_possession_ingame",
    what: "in-game possession / pace / run-diff micro-state repricer prior",
    verdict: "REJECT",
    vsClose: "n/a -- in-game micro-state rejects vs (margin, time)",
    reason: "Confirms the cross-sport meta-finding: coarse in-game micro-state rejects.",
  },
  {
    sport: "nba",
    layer: "nba_travel",
    what: "pre-game travel_home / travel_away feature",
    verdict: "REJECT",
    vsClose: "n/a -- team strength already prices rest/travel",
    reason: "Recorded REJECT-scouting; team strength already absorbs the schedule.",
  },
  {
    sport: "mlb",
    layer: "mlb_atbat_re24_leverage",
    what: "per-at-bat RE24 + leverage-bucket in-game state",
    verdict: "REJECT",
    vsClose: "n/a -- in-game micro-state rejects vs (margin, time)",
    reason: "Coarse base-out / leverage state rejects against the score-and-clock base.",
  },
  {
    sport: "mlb",
    layer: "mlb_statcast_winprob",
    what: "as-of Statcast spin + estimated_woba + release_speed win-prob",
    verdict: "REJECT",
    vsClose: "n/a -- did not beat base calibration",
    reason: "Pitch-quality aggregates are re-expressed by the run-rate Elo already served.",
  },
  {
    sport: "tennis",
    layer: "tennis_setdetail",
    what: "per-set tiebreak_win_pct / close_set_rate trailing as-of",
    verdict: "REJECT",
    vsClose: "n/a -- collinear with serve/return as-of strength",
    reason: "Per-set perf re-expresses serve+return already captured by asof_hold / Elo.",
  },
  {
    sport: "tennis",
    layer: "tennis_pbp",
    what: "point-by-point / rally / pressure-point signal class",
    verdict: "BLOCKED",
    vsClose: "n/a -- INSUFFICIENT_DATA (Tier-3 acquisition, not on disk)",
    reason: "The genuinely-new signal class is off-disk; recorded as TIER3_BLOCKED, not green.",
  },
];

export const SURVIVOR = GATE_VERDICTS.find((g) => g.verdict === "SHIP")!;

export function countByVerdict(v: Verdict): number {
  return GATE_VERDICTS.filter((g) => g.verdict === v).length;
}
