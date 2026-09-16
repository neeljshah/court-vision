export type PublishedChartPresentation = {
  moduleId: string;
  approved: boolean;
  reason: string;
};

const MODULE_IDS = [
  "agent_fleet_history", "aging_curve_lite", "blowout_dynamics", "bookmaker_accuracy", "box_value_index", "brier_skill_scores", "calibration_by_market_type", "calibration_over_time", "calibration_stability", "cf_pace_variance", "cf_star_removal", "clutch_context", "comeback_atlas", "cross_sport_scoreboard", "ctx_lineup_proxy", "ctx_player_splits", "ctx_team_states", "cv_tracking_stats", "dossier_completeness", "ess_ledger", "fwd_claim_scoreboard", "home_away_anatomy", "honesty_exhibit", "info_arrival_curve", "kernel_transfer", "league_parity_index", "lineup_synergy", "market_convergence", "market_disagreement_profile", "market_favorite_longshot", "market_overreaction", "mechanism_ledger_export", "mechanism_survival", "micro_absorption", "micro_closing_decay", "mlb_count_leverage", "mlb_descriptive_leaderboards", "mlb_shrinkage", "mlb_velo_bands", "murphy_decomposition", "nba_consistency_profiles", "nba_form_curves", "nba_matchup_grid", "nba_momentum_tested", "nba_q4_shift", "novel_line_half_life", "novel_live_clock_fraction", "novel_load_bearing_index", "novel_market_foresight_premium", "novel_overreaction_harvest_gap", "novel_schedule_fatigue_tax", "novel_stats_index", "on_off_showcase", "paper_execution_audit", "pitch_sequencing", "player_metric_landscape", "qa_coverage_stats", "reject_graveyard", "residual_anatomy", "residual_autocorrelation", "rim_deterrence", "schedule_density", "soccer_calibration_pack", "soccer_form_stability", "soccer_home_advantage", "statcast_showcase", "state_conditioned_calibration", "tennis_grain_and_myths", "tennis_showcase", "tennis_surface_transfer", "tick_microstructure", "verdict_flip_anatomy", "why_attribution", "xsport_structure",
] as const;

const DISAPPROVED: Record<string, string> = {
  ctx_team_states: "The image contains prohibited vocabulary and clips its subtitle.",
  micro_absorption: "The image contains prohibited vocabulary in its provenance line.",
};

export const publishedChartPresentation: Record<string, PublishedChartPresentation> = Object.fromEntries(
  MODULE_IDS.map((moduleId) => [moduleId, {
    moduleId,
    approved: !DISAPPROVED[moduleId],
    reason: DISAPPROVED[moduleId] || "Reviewed against the manifest description and available chart presentation.",
  }]),
);

export function getPublishedChartPresentation(moduleId: string): PublishedChartPresentation {
  return publishedChartPresentation[moduleId] || {
    moduleId,
    approved: false,
    reason: "No reviewed chart presentation is recorded for this module.",
  };
}
