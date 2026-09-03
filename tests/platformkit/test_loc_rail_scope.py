"""S163 import-free LOC rail for every non-test PlatformKit Python module."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from time import perf_counter


LOC_CAP = 300
ALLOWLIST: dict[str, int] = {
    "scripts/platformkit/analytics_showcase/micro_absorption.py": 361,
    "scripts/platformkit/analytics_showcase/micro_closing_decay.py": 349,
    "scripts/platformkit/analytics_showcase/share_chart.py": 305,
    "scripts/platformkit/analytics_showcase/stage_webapp_assets.py": 304,
    "scripts/platformkit/analytics_verify/sentinel.py": 304,
    "scripts/platformkit/answers/claims_resolver.py": 313,
    "scripts/platformkit/answers/contracts.py": 312,
    "scripts/platformkit/answers/leaderboard_resolver.py": 432,
    "scripts/platformkit/answers/qa_bank.py": 532,
    "scripts/platformkit/answers/resolver_registry.py": 1323,
    "scripts/platformkit/autoloop/autoloop_runner.py": 376,
    "scripts/platformkit/autoloop/maintenance_templates.py": 398,
    "scripts/platformkit/autoloop/standing_prereg.py": 318,
    "scripts/platformkit/autonomy/freshness_sla.py": 343,
    "scripts/platformkit/benchmarks/crps_market/ingame_mlb.py": 394,
    "scripts/platformkit/bestbets/props_paper_placer.py": 362,
    "scripts/platformkit/bestbets/prop_cards.py": 411,
    "scripts/platformkit/brain_activity.py": 306,
    "scripts/platformkit/brain_pipeline.py": 323,
    "scripts/platformkit/calibrator_blend.py": 358,
    "scripts/platformkit/claims/card_registry.py": 331,
    "scripts/platformkit/clv/clv_result_reconciler.py": 436,
    "scripts/platformkit/clv_ledger.py": 537,
    "scripts/platformkit/clv_ledger_enrich.py": 339,
    "scripts/platformkit/combo/run_nba_teamadv_stack_v1.py": 326,
    "scripts/platformkit/composition/composition_gate.py": 319,
    "scripts/platformkit/defender_matchup_gate_run.py": 320,
    "scripts/platformkit/econ/greenlight_trust_honesty.py": 306,
    "scripts/platformkit/eval_gate/calibration_report.py": 358,
    "scripts/platformkit/eval_gate/close_join.py": 315,
    "scripts/platformkit/eval_gate/close_join_nba_mlb.py": 337,
    "scripts/platformkit/eval_gate/family_bars.py": 355,  # 324 -> 355 via S174 (frozen spec v2 support, verified landing 2cc58675e); raised by the orchestrator 2026-09-04
    "scripts/platformkit/eval_gate/run_gate.py": 314,
    "scripts/platformkit/eval_gate/s116_pooled_ingame.py": 302,
    "scripts/platformkit/eval_gate/s137_rebaseline.py": 379,
    "scripts/platformkit/eval_gate/s148_live_requote.py": 415,
    "scripts/platformkit/eval_gate/s84_nba_lineup_at_tick.py": 303,
    "scripts/platformkit/footage_bridge.py": 771,
    "scripts/platformkit/frontend/feed_espn.py": 304,
    "scripts/platformkit/frontend/live_board.py": 419,
    "scripts/platformkit/frontend/serve.py": 403,
    "scripts/platformkit/g120_fragment_merge.py": 301,
    "scripts/platformkit/gate_run_mlb_sp_fatigue_kprop.py": 308,
    "scripts/platformkit/gate_run_soccer_statsbomb.py": 304,
    "scripts/platformkit/geo/city_geo_table.py": 720,
    "scripts/platformkit/improve/ingame_baseout_gate.py": 323,
    "scripts/platformkit/improve/ledger_reconcile.py": 307,
    "scripts/platformkit/improve/prop_calibration_ratchet.py": 336,
    "scripts/platformkit/improve/prop_line_distance_calib.py": 374,
    "scripts/platformkit/improve/recalibrator.py": 320,
    "scripts/platformkit/improve/selfimprove_daemon.py": 307,
    "scripts/platformkit/ingame/exec_calibration.py": 309,
    "scripts/platformkit/ingame/freshness_premium.py": 309,
    "scripts/platformkit/ingame/ingame_atbat_layer_gate_mlb.py": 343,
    "scripts/platformkit/ingame/ingame_grading_multi_runner.py": 313,
    "scripts/platformkit/ingame/ingame_id_resolver_mlb.py": 305,
    "scripts/platformkit/ingame/ingame_live_state.py": 543,
    "scripts/platformkit/ingame/ingame_outcome_verdict_multi.py": 312,
    "scripts/platformkit/ingame/ingame_paper_settle.py": 359,
    "scripts/platformkit/ingame/ingame_pitch_layer_gate_mlb.py": 313,
    "scripts/platformkit/ingame/ingame_pred_tick_runner.py": 301,
    "scripts/platformkit/ingame/ingame_prop_trader.py": 305,
    "scripts/platformkit/ingame/ingame_segment_trust.py": 303,
    "scripts/platformkit/ingame/inplay_aggregate_grade.py": 374,
    "scripts/platformkit/ingame/inplay_capture_loop.py": 1234,
    "scripts/platformkit/ingame/inplay_derivative_mlb.py": 313,
    "scripts/platformkit/ingame/live_grade.py": 303,
    "scripts/platformkit/ingame/live_loop.py": 358,
    "scripts/platformkit/ingame/nba_mechanism_ladder.py": 340,
    "scripts/platformkit/ingame/paper_ingame.py": 344,
    "scripts/platformkit/ingame/tick_segment_backfill.py": 306,
    "scripts/platformkit/ingame/xg_market_awareness.py": 314,
    "scripts/platformkit/intel_query/ask.py": 389,
    "scripts/platformkit/intel_query/ask_index.py": 673,
    "scripts/platformkit/intel_query/compose_best.py": 303,
    "scripts/platformkit/intel_query/compose_scout.py": 303,
    "scripts/platformkit/intel_validation/basketball_claims.py": 309,
    "scripts/platformkit/intel_validation/build_verdict_claims_coverage.py": 443,
    "scripts/platformkit/intel_validation/claims_factory.py": 318,
    "scripts/platformkit/intel_validation/claims_validator.py": 393,
    "scripts/platformkit/intel_validation/claims_validator_batch.py": 312,
    "scripts/platformkit/intel_validation/tennis_ranking_claims.py": 310,
    "scripts/platformkit/interaction_factory/generator.py": 920,
    "scripts/platformkit/interaction_factory/knowledge_intake.py": 331,
    "scripts/platformkit/interaction_factory/runner.py": 613,
    "scripts/platformkit/live_edge/evidence/dossier.py": 326,
    "scripts/platformkit/live_edge/replay/apex.py": 318,
    "scripts/platformkit/meta/improvement_finder.py": 424,
    "scripts/platformkit/models/registry.py": 305,
    "scripts/platformkit/nba_travel_gate_run.py": 325,
    "scripts/platformkit/odds_provider/aggregate.py": 425,
    "scripts/platformkit/odds_provider/capture_quality.py": 375,
    "scripts/platformkit/odds_provider/feed_health.py": 476,
    "scripts/platformkit/odds_provider/inplay_capture_quality.py": 328,
    "scripts/platformkit/odds_provider/inplay_kalshi.py": 327,
    "scripts/platformkit/odds_provider/inplay_snapshot_daemon.py": 356,
    "scripts/platformkit/odds_provider/kalshi_rate_governor.py": 324,
    "scripts/platformkit/odds_provider/line_snapshot_daemon.py": 321,
    "scripts/platformkit/odds_provider/line_store.py": 310,
    "scripts/platformkit/odds_provider/markets.py": 345,
    "scripts/platformkit/odds_provider/oddsapi_team_backfill.py": 359,
    "scripts/platformkit/odds_provider/pinnacle.py": 305,
    "scripts/platformkit/odds_provider/schema_snapshot.py": 330,
    "scripts/platformkit/odds_shop.py": 312,
    "scripts/platformkit/omni/k_stage_b.py": 324,
    "scripts/platformkit/ops/pod_bootstrap_check.py": 311,
    "scripts/platformkit/paper/bankroll_daemon.py": 307,
    "scripts/platformkit/pm_trading/auto_loop.py": 434,
    "scripts/platformkit/pm_trading/pm_paper_tick_runner.py": 303,
    "scripts/platformkit/pm_trading/run_paper_today.py": 444,
    "scripts/platformkit/predictive_validity/mlb_adapters.py": 334,
    "scripts/platformkit/predict_matchup.py": 321,
    "scripts/platformkit/profiles/ask.py": 413,
    "scripts/platformkit/profiles/attribute_gate.py": 301,
    "scripts/platformkit/progress/progress_ledger.py": 366,
    "scripts/platformkit/proof_common/runner.py": 332,
    "scripts/platformkit/proof_harness/system_proof.py": 345,
    "scripts/platformkit/proof_tennis/ingame_bo5.py": 305,
    "scripts/platformkit/proof_tennis/kernel_manifest.py": 305,
    "scripts/platformkit/props_eval.py": 379,
    "scripts/platformkit/prop_edge.py": 312,
    "scripts/platformkit/prop_paper.py": 307,
    "scripts/platformkit/receipts/build_receipts.py": 316,
    "scripts/platformkit/reprocess/reprocess_harness.py": 304,
    "scripts/platformkit/self_improve.py": 372,
    "scripts/platformkit/specs/anticipationreads_mlb.py": 712,
    "scripts/platformkit/specs/disciplinecontrol_mlb.py": 620,
    "scripts/platformkit/specs/disciplinecontrol_nba.py": 648,
    "scripts/platformkit/specs/dueloutcomes_soccer.py": 701,
    "scripts/platformkit/specs/efficiencycurves_soccer.py": 743,
    "scripts/platformkit/specs/efficiencycurves_tennis.py": 694,
    "scripts/platformkit/specs/predictabilitytendencies_mlb.py": 751,
    "scripts/platformkit/specs/predictabilitytendencies_nba.py": 732,
    "scripts/platformkit/specs/predictabilitytendencies_tennis.py": 678,
    "scripts/platformkit/tracking_harness.py": 331,
    "scripts/platformkit/track_daemon.py": 437,
    "scripts/platformkit/venue_history/nba_close_corpus.py": 326,
}
DATA_MODULES = frozenset(
    {
        "scripts/platformkit/answers/qa_bank.py",
        "scripts/platformkit/geo/city_geo_table.py",
    }
)


def _allowlist_reason(path: str) -> str:
    if path in DATA_MODULES or path.startswith("scripts/platformkit/specs/"):
        return "DATA: frozen literal table or specification retained at measured size."
    return "CODE: legacy code retained at measured size pending an explicit split."


ALLOWLIST_REASONS = {path: _allowlist_reason(path) for path in ALLOWLIST}


def _platformkit_sources(root: Path) -> list[Path]:
    source_root = root / "scripts" / "platformkit"
    return sorted(
        path
        for path in source_root.rglob("*.py")
        if "tests" not in path.relative_to(source_root).parts
        and not path.name.startswith("test_")
    )


def _line_count(path: Path) -> int:
    return path.read_bytes().count(b"\n")


def test_every_non_test_platformkit_module_stays_within_the_loc_rail():
    started = perf_counter()
    root = Path(__file__).resolve().parents[2]
    paths = _platformkit_sources(root)
    with ThreadPoolExecutor(max_workers=32) as executor:
        counts = executor.map(_line_count, paths)
        measured = {
            path.relative_to(root).as_posix(): loc
            for path, loc in zip(paths, counts)
        }

    for path, loc in measured.items():
        if path in ALLOWLIST:
            assert loc <= ALLOWLIST[path], (
                f"{path} grew to {loc} LOC; allowlist limit is {ALLOWLIST[path]}"
            )
        else:
            assert loc <= LOC_CAP, f"{path} is {loc} LOC and is not allowlisted"

    assert set(ALLOWLIST_REASONS) == set(ALLOWLIST)
    assert all(
        reason and "\n" not in reason and reason.startswith(("DATA:", "CODE:"))
        for reason in ALLOWLIST_REASONS.values()
    )
    elapsed = perf_counter() - started
    print(f"LOC rail walked {len(measured)} files in {elapsed:.3f}s")
    assert elapsed < 5.0
