"""S57: the 151 ``data/intelligence`` artifacts, their producers, and what may run.

The intelligence layer sat outside freshness governance: 0 of 151 artifacts
appeared in ``gate_manifest.json`` and nothing ever re-ran their producers.
This module is the DATA half of the fix -- a measured artifact -> producer map
plus the run-scope classification -- so ``artifact_refresh`` can carry
intelligence targets without re-deriving anything at runtime.

MEASURED 2026-09-03 (re-derive with the scan described below; do not hand-edit):
  151 artifacts, 143 with a producer, 8 with none (``NO_PRODUCER``),
  95 distinct producers, ALL under ``scripts/`` -- 0 gated. ``intel/*.py`` only
  READ these artifacts (the one ``data/intelligence`` string in ``intel/`` is a
  docstring in ``team_three_pt_defense.py:274``), so no producer needs a
  human-gated edit today. The gated branch is kept live because a future
  producer may land in a gated tree, and a gated producer must be reported
  NO_RUN by name, never skipped silently.

  Scan: for each file under ``data/intelligence``, the modules under
  ``scripts|intel|src|api|kernel`` whose text contains the artifact's exact
  basename AND a write call (``to_parquet``/``json.dump``/``write_text``/...);
  a single candidate wins outright, otherwise the closest name match.

INPUT_REBUILT is the run scope. Re-running a producer whose inputs are OLDER
than its own artifact reproduces the same content from the same inputs, so it
is not a freshness fix -- it is churn. Only the producers reading at least one
input newer than the artifact they write can actually advance anything, and
those are the ones this module offers to run. Every other producer is reported
with its named reason, never dropped.

This is an audit/calibration tool. It states no $ edge / ROI. ASCII + stdlib.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

INTEL_DIR = "data/intelligence"

# Human-gated trees (.claude/rules/human-gated-paths.md): a producer here is
# reported NO_RUN with its path, never edited and never silently skipped.
GATED_PREFIXES = ("src/", "kernel/", "api/", "intel/", "scripts/team_system/")

# A producer gets this long before it is recorded as a FAILED row. Knob, not a
# bar: these are batch builders, not services.
#
# S69 raised it 300 -> 900 on MEASURED walls, after the five S57 failures were
# repaired (build_quarter_momentum 132 s, build_tipoff_predictability 108 s,
# build_cv_fatigue_trajectories 275 s, build_ingame_momentum 77 s,
# build_lineup_chemistry 179 s -- all one full pass over the 357-game,
# 4.56 GB data/tracking corpus). The slowest sits 25 s under the old 300 s, and
# this box's read throughput varies by more than an order of magnitude with
# antivirus scanning, so 300 s was killing runs that were merely slow.
# ponytail: one global knob. The ceiling is that a genuinely hung builder now
# wastes 15 min instead of 5 -- give a per-producer timeout only if one of these
# ever hangs rather than crawls.
PRODUCER_TIMEOUT_S = 900.0

PRODUCERS = {
    "scripts/audit_retro_bets.py": ("retro_bet_audit.parquet",),
    "scripts/build_absence_impact.py": ("absence_cv_impact.parquet",
        "star_absence_effects.json"),
    "scripts/build_ai_chat_corpus.py": ("active_trend_signals.json", "ai_chat_index.json",
        "breakout_signals.json"),
    "scripts/build_ai_chat_facts_v2.py": ("ai_chat_facts.json", "ai_chat_facts_v2.json",
        "compound_candidates.parquet"),
    "scripts/build_anomaly_intel.py": ("anomaly_log.parquet",),
    "scripts/build_archetype_drift.py": ("archetype_drift.parquet",
        "archetype_drift_signals.json"),
    "scripts/build_archetype_outlier_signal.py": ("archetype_outlier_signals.parquet",),
    "scripts/build_archetype_scheme_matrix.py": ("archetype_scheme_advantages.json",
        "archetype_scheme_interactions.parquet"),
    "scripts/build_bench_starter_split.py": ("bench_starter_signatures.json",
        "bench_starter_split.parquet"),
    "scripts/build_clutch_cv.py": ("clutch_cv_split.parquet", "clutch_rankings.json"),
    "scripts/build_coaching_adjustments.py": ("coaching_adjustments.parquet",
        "team_adjustment_tendencies.json"),
    "scripts/build_confidence_ensemble.py": ("confidence_ensemble.parquet",),
    "scripts/build_confidence_intervals.py": ("confidence_curves.json",),
    "scripts/build_current_form.py": ("current_form_profiles.parquet",
        "form_vs_baseline_deltas.json"),
    "scripts/build_cv_anomaly_v2.py": ("cv_anomaly_v2_validation.json",),
    "scripts/build_cv_consistency_kelly.py": ("cv_consistency_kelly.parquet",),
    "scripts/build_cv_coverage_gates.py": ("cv_coverage_gates.parquet",),
    "scripts/build_cv_coverage_interactions.py": ("cv_coverage_interactions.parquet",),
    "scripts/build_cv_fatigue_trajectories.py": ("cv_fatigue_trajectories.parquet",),
    "scripts/build_cv_pace_features.py": ("cv_pace_features_sidecar.parquet",
        "cv_pace_per_game.parquet"),
    "scripts/build_cv_quality_confidence.py": ("cv_quality_confidence_curves.json",
        "cv_quality_per_game.parquet"),
    "scripts/build_cv_shot_clock_features.py": ("cv_shot_clock_per_game.parquet",),
    "scripts/build_cv_shot_clock_features_sidecar.py":
        ("cv_shot_clock_features_sidecar.parquet",),
    "scripts/build_cv_shot_range_features.py": ("cv_shot_range_features_sidecar.parquet",
        "cv_shot_range_per_game.parquet"),
    "scripts/build_cv_shot_type_features.py": ("cv_shot_type_features_sidecar.parquet",),
    "scripts/build_cv_shot_types.py": ("cv_shot_types_per_game.parquet",),
    "scripts/build_daily_picks.py": ("anti_correlation_parlay_candidates.parquet",
        "parlay_scores_v2_demo.parquet"),
    "scripts/build_daily_slate.py": ("per_player_confidence.parquet",),
    "scripts/build_defensive_schemes.py": ("defensive_schemes.parquet",
        "scheme_indicators.json"),
    "scripts/build_ft_rate_model.py": ("ft_rate_predictions.parquet",),
    "scripts/build_game_similarity.py": ("game_neighbors.json",
        "game_similarity_index.parquet"),
    "scripts/build_garbage_time_gates.py": ("garbage_time_player_aggregates.parquet",
        "garbage_time_segments.parquet"),
    "scripts/build_gt_weighted_forms.py": ("gt_weighted_forms.parquet",),
    "scripts/build_h1_to_h2_projection.py": ("h1_h2_projections.parquet",
        "h2_projection_signals.json"),
    "scripts/build_ingame_momentum.py": ("ingame_momentum.parquet",),
    "scripts/build_lineup_chemistry.py": ("lineup_chemistry.parquet", "lineup_signatures.json"),
    "scripts/build_matchup_grid.py": ("matchup_grid.parquet",),
    "scripts/build_matchup_intel.py": ("matchup_deviations.parquet",
        "opponent_imposed_profiles.json"),
    "scripts/build_momentum_signals.py": ("momentum_signals.parquet",),
    "scripts/build_non_gt_rolling_features.py": ("non_gt_forms_sidecar.parquet",),
    "scripts/build_officials_cv_impact.py": ("officials_cv_impact.parquet",
        "officials_player_sensitivity.parquet", "officials_signals.json"),
    "scripts/build_opp_defensive_intensity.py": ("opp_defensive_intensity.parquet",),
    "scripts/build_opp_minutes_v2.py": ("opp_minutes_predictions.parquet",),
    "scripts/build_opp_normalized_cv.py": ("opp_normalized_cv.parquet",),
    "scripts/build_opp_paint_allowance.py": ("opp_paint_allowance.parquet",),
    "scripts/build_pace_adjusted_cv.py": ("pace_adjusted_cv.parquet",
        "pace_adjusted_rankings.json"),
    "scripts/build_pair_chemistry.py": ("pair_chemistry.parquet", "pair_signatures.json"),
    "scripts/build_per_player_calibration.py": ("per_player_calibration.parquet",),
    "scripts/build_player_atlas.py": ("player_archetype_definitions.json",
        "player_atlas_feature_list.json", "player_atlas_viz.png",
        "player_fingerprints.parquet"),
    "scripts/build_player_betting_profile.py": ("daily_picks_2026-05-29.json",
        "per_book_edge_audit_2026-05-29.parquet", "player_betting_profile.parquet"),
    "scripts/build_player_def_archetype.py": ("player_def_archetype_sidecar.parquet",),
    "scripts/build_player_development.py": ("player_development.parquet",),
    "scripts/build_player_development_v2.py": ("player_development_v2.parquet",
        "player_development_v2_signals.json"),
    "scripts/build_player_opp_splits.py": ("player_opp_splits_sidecar.parquet",),
    "scripts/build_player_similarity.py": ("player_similarity.parquet",),
    "scripts/build_position_scheme_matrix.py": ("position_scheme_interactions.parquet",
        "position_scheme_signals.json"),
    "scripts/build_position_vs_position.py": ("pos_vs_pos_matchups.parquet",
        "pos_vs_pos_signals.json"),
    "scripts/build_possession_type_intel.py": ("possession_type_profiles.parquet",
        "possession_type_signatures.json"),
    "scripts/build_q1_extrapolation_signals.py": ("q1_extrapolation_signals.parquet",),
    "scripts/build_quarter_momentum.py": ("quarter_profiles.parquet",
        "quarter_signatures.json"),
    "scripts/build_rest_cv_intel.py": ("rest_cv_impact.parquet", "rest_cv_signatures.json"),
    "scripts/build_rolling_trends.py": ("rolling_trends.parquet",),
    "scripts/build_schedule_strength.py": ("schedule_strength_7d.parquet",),
    "scripts/build_sequential_possession.py": ("sequential_patterns.parquet",
        "sequential_signatures.json"),
    "scripts/build_shot_clock_buckets.py": ("shot_clock_buckets.parquet",
        "shot_clock_player_profiles.json"),
    "scripts/build_similarity_engine.py": ("similar_neighbors.json",
        "similarity_matrix.parquet"),
    "scripts/build_stat_correlations.py": ("stat_correlation_matrix.parquet",),
    "scripts/build_streak_signatures.py": ("streak_excluded_players.json",
        "streak_signatures.parquet", "streak_signatures_summary.json"),
    "scripts/build_team_tempo_spacing.py": ("team_tempo_spacing.parquet",),
    "scripts/build_teammate_correlation.py": ("teammate_correlation.parquet",),
    "scripts/build_time_of_day_cv.py": ("dow_cv_profiles.parquet", "dow_signals.json",
        "time_of_day_cv.parquet"),
    "scripts/build_tipoff_predictability.py": ("tipoff_predictability.parquet",
        "tipoff_predictability_signals.json"),
    "scripts/build_trade_intel.py": ("team_change_log.json", "trade_profile_shifts.parquet"),
    "scripts/check_bookmaker_consistency.py": ("bookmaker_consistency.parquet",),
    "scripts/diagnose_atlas_redundancy.py": ("atlas_redundancy_matrix.parquet",),
    "scripts/eval_kelly_with_cv_consistency.py": ("cv_consistency_eval.json",),
    "scripts/eval_live_shot_quality.py": ("shot_quality_live_validation.json",),
    "scripts/hunt_compound_signals_v3.py": ("compound_signal_hunt_v3.parquet",),
    "scripts/hunt_compound_signals_v4.py": ("compound_signal_hunt_v4.parquet",),
    "scripts/int116_wrapper.py": ("multitask_residual_head_predictions.parquet",),
    "scripts/int90_blk_residual_head.py": ("blk_residual_head_v1.parquet",),
    "scripts/int95_per_archetype_residual.py": ("archetype_label_sidecar.parquet",
        "per_archetype_residual_v1.parquet"),
    "scripts/prop_pergame_walk_forward_atlas.py": ("atlas_features_sidecar.parquet",),
    "scripts/prop_pergame_walk_forward_built.py": ("built_signals_sidecar.parquet",),
    "scripts/refit_atlas_k_sweep.py": ("player_fingerprints_kbest.parquet",),
    "scripts/run_daily_picks_retro.py": ("daily_picks_retro_2026-04-25_to_2026-05-24.parquet",),
    "scripts/run_daily_picks_retro_v2.py": ("daily_picks_retro_v1_vs_v2_comparison.parquet",),
    "scripts/score_multi_leg_v2.py": ("parlay_scores_v2_demo_with_calibration.parquet",),
    "scripts/simulate_v6_deployment.py": ("v6_simulation_results.json",),
    "scripts/test_c1_clean_backtest.py": ("c1_clean_backtest_results.json",),
    "scripts/test_int41_int23_compound_v8.py": ("int_v8_results.json",),
    "scripts/test_v8_clean_subset.py": ("v8_clean_subset_results.json",
        "v9_unified_results.json"),
    "scripts/train_pts_decomposition.py": ("pts_decomposition_predictions.parquet",),
    "scripts/validate_cv_coverage_interactions.py": ("int60_validation_results.json",),
    "scripts/validate_parlay_correlation_retro.py": ("parlay_correlation_retro_buckets.parquet",
        "parlay_correlation_retro_validation.parquet"),
}

NO_PRODUCER = (
    "_pid_date_teams.pkl",
    "daily_picks_2026-05-29_v2.json",
    "daily_slate_2025-02-28.json",
    "int99_v1_vs_v2_diff.parquet",
    "parlay_correlation_retro_validation_v2.parquet",
    "parlay_scores_v2_legacy_calibrated.parquet",
    "player_def_archetype_sidecar_null.parquet",
    "pra_arbitrage_opportunities_2026-05-29.parquet",
)

# The 19 producers measured to read at least one input NEWER than the artifact
# they write (30 of the 143 mapped artifacts). Everything else is reported with
# the reason in ``_SCOPE_REASON``: inputs_not_rebuilt 38, all_inputs_missing 35,
# no_inputs_detected 3 producers.
INPUT_REBUILT = (
    "scripts/build_clutch_cv.py",
    "scripts/build_coaching_adjustments.py",
    "scripts/build_cv_fatigue_trajectories.py",
    "scripts/build_cv_pace_features.py",
    "scripts/build_cv_shot_types.py",
    "scripts/build_game_similarity.py",
    "scripts/build_ingame_momentum.py",
    "scripts/build_lineup_chemistry.py",
    "scripts/build_possession_type_intel.py",
    "scripts/build_q1_extrapolation_signals.py",
    "scripts/build_quarter_momentum.py",
    "scripts/build_sequential_possession.py",
    "scripts/build_shot_clock_buckets.py",
    "scripts/build_tipoff_predictability.py",
    "scripts/build_trade_intel.py",
    "scripts/int90_blk_residual_head.py",
    "scripts/run_daily_picks_retro.py",
    "scripts/run_daily_picks_retro_v2.py",
    "scripts/test_c1_clean_backtest.py",
)

_SCOPE_REASON = "inputs older than the artifact -- re-running reproduces it"


def _runner(script: str):
    """Producer callable: run the builder as its own process, from the repo root.

    These builders are CLI scripts with no importable ``build()``, so they are
    invoked the documented way. A non-zero rc (or a timeout) raises, which
    ``artifact_refresh`` records as a FAILED row without killing the pass.
    """

    def run(root: Path) -> None:
        # PYTHONIOENCODING: these builders print non-ASCII progress lines and
        # the child inherits the cp1252 console codec, so the FIRST such print
        # killed the builder with UnicodeEncodeError after it had already
        # written part of its output -- a half-refreshed artifact reported as
        # a clean failure. The encoding belongs to the pipe, not to the data.
        env = dict(os.environ, PYTHONIOENCODING="utf-8")
        proc = subprocess.run([sys.executable, script], cwd=str(root), env=env,
                              capture_output=True, timeout=PRODUCER_TIMEOUT_S)
        if proc.returncode != 0:
            tail = proc.stderr.decode("utf-8", "replace").strip().splitlines()
            raise RuntimeError("rc={0}: {1}".format(
                proc.returncode, tail[-1][:200] if tail else "no stderr"))

    return run


def classify(script: str, root: Path, scope: str = "rebuilt") -> Optional[str]:
    """Return the NO_RUN reason for ``script``, or None when it may run."""
    if script.startswith(GATED_PREFIXES):
        return "gated tree (human-gated, read-only): " + script
    if not (root / script).exists():
        return "producer script absent: " + script
    if scope == "rebuilt" and script not in INPUT_REBUILT:
        return _SCOPE_REASON
    return None


def targets(root: Path, scope: str = "rebuilt") -> Sequence:
    """Build one ``artifact_refresh.Target`` per producer, plus the orphans.

    Imported lazily: ``artifact_refresh`` imports this module, so a top-level
    import back would be a cycle.
    """
    from scripts.platformkit.mcp_server.artifact_refresh import Target

    out: List = []
    for script, names in sorted(PRODUCERS.items()):
        rels = tuple(INTEL_DIR + "/" + n for n in names)
        reason = classify(script, root, scope)
        out.append(Target("intel:" + Path(script).stem, rels,
                          None if reason else _runner(script), reason))
    for name in NO_PRODUCER:
        out.append(Target("intel:" + Path(name).stem, (INTEL_DIR + "/" + name,), None))
    return tuple(out)


def counts(root: Path, scope: str = "rebuilt") -> Tuple[Dict[str, int], int]:
    """(reason -> n producers, n artifacts registered) -- what the memo prints."""
    tally: Dict[str, int] = {}
    n_artifacts = len(NO_PRODUCER)
    for script, names in PRODUCERS.items():
        n_artifacts += len(names)
        reason = classify(script, root, scope)
        key = "RUNNABLE" if reason is None else reason.split(":")[0]
        tally[key] = tally.get(key, 0) + 1
    tally["no_producer_artifacts"] = len(NO_PRODUCER)
    return tally, n_artifacts
