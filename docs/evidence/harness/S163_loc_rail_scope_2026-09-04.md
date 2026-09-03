# S163 LOC rail scope - 2026-09-04

## Result

ATTEMPT 1 was rejected. Its widened legacy test imported three heavy PlatformKit
modules, ran above the five-second bar, froze a stale worktree count for
footage_bridge.py, and asserted a fixed file count. ATTEMPT 2 restores the
legacy S140 test exactly from master and places the import-free rail in
tests/platformkit/test_loc_rail_scope.py.

## Attempt 1 record (rejected)

The S163 premise was re-measured before the change. The prior rail checked only
three named modules. Reproduction command:

    find scripts/platformkit -type f -name '*.py' ! -name 'test_*.py' ! -path '*/tests/*' -print0 | xargs -0 wc -l

The command enumerated N = 2199 non-test modules. It found 137 modules above
300 LOC. The rail enumerates the same scope, requires exactly N files, requires
the over-cap set to equal the explicit allowlist, and rejects any listed module
whose count exceeds its recorded allowance. This historical attempt is
superseded by the ATTEMPT 2 measurement below.

## ATTEMPT 2 (current)

The current-master reference was measured read-only at
C:/Users/neelj/nba-ai-system commit 2dc69a80ef55856315c4449340e1d269d3282ba5:

    git -C C:/Users/neelj/nba-ai-system ls-files scripts/platformkit

The tracked-path list was filtered to non-test Python modules and counted with
wc -l on the corresponding main-repository files. N = 2200 and 137 modules
were over 300 LOC. The new test uses pathlib only (plus standard-library timing)
and byte newline counts matching wc -l. It asserts only that every observed
over-cap module is allowlisted and no larger than its frozen current-master
count, and that every non-allowlisted module is at most 300 LOC. It intentionally
does not freeze a file total or require every allowlisted file to remain over cap.

## Over-cap allowlist (ATTEMPT 2 current-master measurement)

| Path | LOC | Kind | Reason |
| --- | ---: | --- | --- |
| scripts/platformkit/analytics_showcase/micro_absorption.py | 361 | code | Legacy code retained at measured size pending an explicit split. |
| scripts/platformkit/analytics_showcase/micro_closing_decay.py | 349 | code | Legacy code retained at measured size pending an explicit split. |
| scripts/platformkit/analytics_showcase/share_chart.py | 305 | code | Legacy code retained at measured size pending an explicit split. |
| scripts/platformkit/analytics_showcase/stage_webapp_assets.py | 304 | code | Legacy code retained at measured size pending an explicit split. |
| scripts/platformkit/analytics_verify/sentinel.py | 304 | code | Legacy code retained at measured size pending an explicit split. |
| scripts/platformkit/answers/claims_resolver.py | 313 | code | Legacy code retained at measured size pending an explicit split. |
| scripts/platformkit/answers/contracts.py | 312 | code | Legacy code retained at measured size pending an explicit split. |
| scripts/platformkit/answers/leaderboard_resolver.py | 432 | code | Legacy code retained at measured size pending an explicit split. |
| scripts/platformkit/answers/qa_bank.py | 532 | DATA | Frozen literal table or specification retained at measured size. |
| scripts/platformkit/answers/resolver_registry.py | 1323 | code | Legacy code retained at measured size pending an explicit split. |
| scripts/platformkit/autoloop/autoloop_runner.py | 376 | code | Legacy code retained at measured size pending an explicit split. |
| scripts/platformkit/autoloop/maintenance_templates.py | 398 | code | Legacy code retained at measured size pending an explicit split. |
| scripts/platformkit/autoloop/standing_prereg.py | 318 | code | Legacy code retained at measured size pending an explicit split. |
| scripts/platformkit/autonomy/freshness_sla.py | 343 | code | Legacy code retained at measured size pending an explicit split. |
| scripts/platformkit/benchmarks/crps_market/ingame_mlb.py | 394 | code | Legacy code retained at measured size pending an explicit split. |
| scripts/platformkit/bestbets/props_paper_placer.py | 362 | code | Legacy code retained at measured size pending an explicit split. |
| scripts/platformkit/bestbets/prop_cards.py | 411 | code | Legacy code retained at measured size pending an explicit split. |
| scripts/platformkit/brain_activity.py | 306 | code | Legacy code retained at measured size pending an explicit split. |
| scripts/platformkit/brain_pipeline.py | 323 | code | Legacy code retained at measured size pending an explicit split. |
| scripts/platformkit/calibrator_blend.py | 358 | code | Legacy code retained at measured size pending an explicit split. |
| scripts/platformkit/claims/card_registry.py | 331 | code | Legacy code retained at measured size pending an explicit split. |
| scripts/platformkit/clv/clv_result_reconciler.py | 436 | code | Legacy code retained at measured size pending an explicit split. |
| scripts/platformkit/clv_ledger.py | 537 | code | Legacy code retained at measured size pending an explicit split. |
| scripts/platformkit/clv_ledger_enrich.py | 339 | code | Legacy code retained at measured size pending an explicit split. |
| scripts/platformkit/combo/run_nba_teamadv_stack_v1.py | 326 | code | Legacy code retained at measured size pending an explicit split. |
| scripts/platformkit/composition/composition_gate.py | 319 | code | Legacy code retained at measured size pending an explicit split. |
| scripts/platformkit/defender_matchup_gate_run.py | 320 | code | Legacy code retained at measured size pending an explicit split. |
| scripts/platformkit/econ/greenlight_trust_honesty.py | 306 | code | Legacy code retained at measured size pending an explicit split. |
| scripts/platformkit/eval_gate/calibration_report.py | 358 | code | Legacy code retained at measured size pending an explicit split. |
| scripts/platformkit/eval_gate/close_join.py | 315 | code | Legacy code retained at measured size pending an explicit split. |
| scripts/platformkit/eval_gate/close_join_nba_mlb.py | 337 | code | Legacy code retained at measured size pending an explicit split. |
| scripts/platformkit/eval_gate/family_bars.py | 324 | code | Legacy code retained at measured size pending an explicit split. |
| scripts/platformkit/eval_gate/run_gate.py | 314 | code | Legacy code retained at measured size pending an explicit split. |
| scripts/platformkit/eval_gate/s116_pooled_ingame.py | 302 | code | Legacy code retained at measured size pending an explicit split. |
| scripts/platformkit/eval_gate/s137_rebaseline.py | 379 | code | Legacy code retained at measured size pending an explicit split. |
| scripts/platformkit/eval_gate/s148_live_requote.py | 415 | code | Legacy code retained at measured size pending an explicit split. |
| scripts/platformkit/eval_gate/s84_nba_lineup_at_tick.py | 303 | code | Legacy code retained at measured size pending an explicit split. |
| scripts/platformkit/footage_bridge.py | 771 | code | Legacy code retained at measured size pending an explicit split. |
| scripts/platformkit/frontend/feed_espn.py | 304 | code | Legacy code retained at measured size pending an explicit split. |
| scripts/platformkit/frontend/live_board.py | 419 | code | Legacy code retained at measured size pending an explicit split. |
| scripts/platformkit/frontend/serve.py | 403 | code | Legacy code retained at measured size pending an explicit split. |
| scripts/platformkit/g120_fragment_merge.py | 301 | code | Legacy code retained at measured size pending an explicit split. |
| scripts/platformkit/gate_run_mlb_sp_fatigue_kprop.py | 308 | code | Legacy code retained at measured size pending an explicit split. |
| scripts/platformkit/gate_run_soccer_statsbomb.py | 304 | code | Legacy code retained at measured size pending an explicit split. |
| scripts/platformkit/geo/city_geo_table.py | 720 | DATA | Frozen literal table or specification retained at measured size. |
| scripts/platformkit/improve/ingame_baseout_gate.py | 323 | code | Legacy code retained at measured size pending an explicit split. |
| scripts/platformkit/improve/ledger_reconcile.py | 307 | code | Legacy code retained at measured size pending an explicit split. |
| scripts/platformkit/improve/prop_calibration_ratchet.py | 336 | code | Legacy code retained at measured size pending an explicit split. |
| scripts/platformkit/improve/prop_line_distance_calib.py | 374 | code | Legacy code retained at measured size pending an explicit split. |
| scripts/platformkit/improve/recalibrator.py | 320 | code | Legacy code retained at measured size pending an explicit split. |
| scripts/platformkit/improve/selfimprove_daemon.py | 307 | code | Legacy code retained at measured size pending an explicit split. |
| scripts/platformkit/ingame/exec_calibration.py | 309 | code | Legacy code retained at measured size pending an explicit split. |
| scripts/platformkit/ingame/freshness_premium.py | 309 | code | Legacy code retained at measured size pending an explicit split. |
| scripts/platformkit/ingame/ingame_atbat_layer_gate_mlb.py | 343 | code | Legacy code retained at measured size pending an explicit split. |
| scripts/platformkit/ingame/ingame_grading_multi_runner.py | 313 | code | Legacy code retained at measured size pending an explicit split. |
| scripts/platformkit/ingame/ingame_id_resolver_mlb.py | 305 | code | Legacy code retained at measured size pending an explicit split. |
| scripts/platformkit/ingame/ingame_live_state.py | 543 | code | Legacy code retained at measured size pending an explicit split. |
| scripts/platformkit/ingame/ingame_outcome_verdict_multi.py | 312 | code | Legacy code retained at measured size pending an explicit split. |
| scripts/platformkit/ingame/ingame_paper_settle.py | 359 | code | Legacy code retained at measured size pending an explicit split. |
| scripts/platformkit/ingame/ingame_pitch_layer_gate_mlb.py | 313 | code | Legacy code retained at measured size pending an explicit split. |
| scripts/platformkit/ingame/ingame_pred_tick_runner.py | 301 | code | Legacy code retained at measured size pending an explicit split. |
| scripts/platformkit/ingame/ingame_prop_trader.py | 305 | code | Legacy code retained at measured size pending an explicit split. |
| scripts/platformkit/ingame/ingame_segment_trust.py | 303 | code | Legacy code retained at measured size pending an explicit split. |
| scripts/platformkit/ingame/inplay_aggregate_grade.py | 374 | code | Legacy code retained at measured size pending an explicit split. |
| scripts/platformkit/ingame/inplay_capture_loop.py | 1234 | code | Legacy code retained at measured size pending an explicit split. |
| scripts/platformkit/ingame/inplay_derivative_mlb.py | 313 | code | Legacy code retained at measured size pending an explicit split. |
| scripts/platformkit/ingame/live_grade.py | 303 | code | Legacy code retained at measured size pending an explicit split. |
| scripts/platformkit/ingame/live_loop.py | 358 | code | Legacy code retained at measured size pending an explicit split. |
| scripts/platformkit/ingame/nba_mechanism_ladder.py | 340 | code | Legacy code retained at measured size pending an explicit split. |
| scripts/platformkit/ingame/paper_ingame.py | 344 | code | Legacy code retained at measured size pending an explicit split. |
| scripts/platformkit/ingame/tick_segment_backfill.py | 306 | code | Legacy code retained at measured size pending an explicit split. |
| scripts/platformkit/ingame/xg_market_awareness.py | 314 | code | Legacy code retained at measured size pending an explicit split. |
| scripts/platformkit/intel_query/ask.py | 389 | code | Legacy code retained at measured size pending an explicit split. |
| scripts/platformkit/intel_query/ask_index.py | 673 | code | Legacy code retained at measured size pending an explicit split. |
| scripts/platformkit/intel_query/compose_best.py | 303 | code | Legacy code retained at measured size pending an explicit split. |
| scripts/platformkit/intel_query/compose_scout.py | 303 | code | Legacy code retained at measured size pending an explicit split. |
| scripts/platformkit/intel_validation/basketball_claims.py | 309 | code | Legacy code retained at measured size pending an explicit split. |
| scripts/platformkit/intel_validation/build_verdict_claims_coverage.py | 443 | code | Legacy code retained at measured size pending an explicit split. |
| scripts/platformkit/intel_validation/claims_factory.py | 318 | code | Legacy code retained at measured size pending an explicit split. |
| scripts/platformkit/intel_validation/claims_validator.py | 393 | code | Legacy code retained at measured size pending an explicit split. |
| scripts/platformkit/intel_validation/claims_validator_batch.py | 312 | code | Legacy code retained at measured size pending an explicit split. |
| scripts/platformkit/intel_validation/tennis_ranking_claims.py | 310 | code | Legacy code retained at measured size pending an explicit split. |
| scripts/platformkit/interaction_factory/generator.py | 920 | code | Legacy code retained at measured size pending an explicit split. |
| scripts/platformkit/interaction_factory/knowledge_intake.py | 331 | code | Legacy code retained at measured size pending an explicit split. |
| scripts/platformkit/interaction_factory/runner.py | 613 | code | Legacy code retained at measured size pending an explicit split. |
| scripts/platformkit/live_edge/evidence/dossier.py | 326 | code | Legacy code retained at measured size pending an explicit split. |
| scripts/platformkit/live_edge/replay/apex.py | 318 | code | Legacy code retained at measured size pending an explicit split. |
| scripts/platformkit/meta/improvement_finder.py | 424 | code | Legacy code retained at measured size pending an explicit split. |
| scripts/platformkit/models/registry.py | 305 | code | Legacy code retained at measured size pending an explicit split. |
| scripts/platformkit/nba_travel_gate_run.py | 325 | code | Legacy code retained at measured size pending an explicit split. |
| scripts/platformkit/odds_provider/aggregate.py | 425 | code | Legacy code retained at measured size pending an explicit split. |
| scripts/platformkit/odds_provider/capture_quality.py | 375 | code | Legacy code retained at measured size pending an explicit split. |
| scripts/platformkit/odds_provider/feed_health.py | 476 | code | Legacy code retained at measured size pending an explicit split. |
| scripts/platformkit/odds_provider/inplay_capture_quality.py | 328 | code | Legacy code retained at measured size pending an explicit split. |
| scripts/platformkit/odds_provider/inplay_kalshi.py | 327 | code | Legacy code retained at measured size pending an explicit split. |
| scripts/platformkit/odds_provider/inplay_snapshot_daemon.py | 356 | code | Legacy code retained at measured size pending an explicit split. |
| scripts/platformkit/odds_provider/kalshi_rate_governor.py | 324 | code | Legacy code retained at measured size pending an explicit split. |
| scripts/platformkit/odds_provider/line_snapshot_daemon.py | 321 | code | Legacy code retained at measured size pending an explicit split. |
| scripts/platformkit/odds_provider/line_store.py | 310 | code | Legacy code retained at measured size pending an explicit split. |
| scripts/platformkit/odds_provider/markets.py | 345 | code | Legacy code retained at measured size pending an explicit split. |
| scripts/platformkit/odds_provider/oddsapi_team_backfill.py | 359 | code | Legacy code retained at measured size pending an explicit split. |
| scripts/platformkit/odds_provider/pinnacle.py | 305 | code | Legacy code retained at measured size pending an explicit split. |
| scripts/platformkit/odds_provider/schema_snapshot.py | 330 | code | Legacy code retained at measured size pending an explicit split. |
| scripts/platformkit/odds_shop.py | 312 | code | Legacy code retained at measured size pending an explicit split. |
| scripts/platformkit/omni/k_stage_b.py | 324 | code | Legacy code retained at measured size pending an explicit split. |
| scripts/platformkit/ops/pod_bootstrap_check.py | 311 | code | Legacy code retained at measured size pending an explicit split. |
| scripts/platformkit/paper/bankroll_daemon.py | 307 | code | Legacy code retained at measured size pending an explicit split. |
| scripts/platformkit/pm_trading/auto_loop.py | 434 | code | Legacy code retained at measured size pending an explicit split. |
| scripts/platformkit/pm_trading/pm_paper_tick_runner.py | 303 | code | Legacy code retained at measured size pending an explicit split. |
| scripts/platformkit/pm_trading/run_paper_today.py | 444 | code | Legacy code retained at measured size pending an explicit split. |
| scripts/platformkit/predictive_validity/mlb_adapters.py | 334 | code | Legacy code retained at measured size pending an explicit split. |
| scripts/platformkit/predict_matchup.py | 321 | code | Legacy code retained at measured size pending an explicit split. |
| scripts/platformkit/profiles/ask.py | 413 | code | Legacy code retained at measured size pending an explicit split. |
| scripts/platformkit/profiles/attribute_gate.py | 301 | code | Legacy code retained at measured size pending an explicit split. |
| scripts/platformkit/progress/progress_ledger.py | 366 | code | Legacy code retained at measured size pending an explicit split. |
| scripts/platformkit/proof_common/runner.py | 332 | code | Legacy code retained at measured size pending an explicit split. |
| scripts/platformkit/proof_harness/system_proof.py | 345 | code | Legacy code retained at measured size pending an explicit split. |
| scripts/platformkit/proof_tennis/ingame_bo5.py | 305 | code | Legacy code retained at measured size pending an explicit split. |
| scripts/platformkit/proof_tennis/kernel_manifest.py | 305 | code | Legacy code retained at measured size pending an explicit split. |
| scripts/platformkit/props_eval.py | 379 | code | Legacy code retained at measured size pending an explicit split. |
| scripts/platformkit/prop_edge.py | 312 | code | Legacy code retained at measured size pending an explicit split. |
| scripts/platformkit/prop_paper.py | 307 | code | Legacy code retained at measured size pending an explicit split. |
| scripts/platformkit/receipts/build_receipts.py | 316 | code | Legacy code retained at measured size pending an explicit split. |
| scripts/platformkit/reprocess/reprocess_harness.py | 304 | code | Legacy code retained at measured size pending an explicit split. |
| scripts/platformkit/self_improve.py | 372 | code | Legacy code retained at measured size pending an explicit split. |
| scripts/platformkit/specs/anticipationreads_mlb.py | 712 | DATA | Frozen literal table or specification retained at measured size. |
| scripts/platformkit/specs/disciplinecontrol_mlb.py | 620 | DATA | Frozen literal table or specification retained at measured size. |
| scripts/platformkit/specs/disciplinecontrol_nba.py | 648 | DATA | Frozen literal table or specification retained at measured size. |
| scripts/platformkit/specs/dueloutcomes_soccer.py | 701 | DATA | Frozen literal table or specification retained at measured size. |
| scripts/platformkit/specs/efficiencycurves_soccer.py | 743 | DATA | Frozen literal table or specification retained at measured size. |
| scripts/platformkit/specs/efficiencycurves_tennis.py | 694 | DATA | Frozen literal table or specification retained at measured size. |
| scripts/platformkit/specs/predictabilitytendencies_mlb.py | 751 | DATA | Frozen literal table or specification retained at measured size. |
| scripts/platformkit/specs/predictabilitytendencies_nba.py | 732 | DATA | Frozen literal table or specification retained at measured size. |
| scripts/platformkit/specs/predictabilitytendencies_tennis.py | 678 | DATA | Frozen literal table or specification retained at measured size. |
| scripts/platformkit/tracking_harness.py | 331 | code | Legacy code retained at measured size pending an explicit split. |
| scripts/platformkit/track_daemon.py | 437 | code | Legacy code retained at measured size pending an explicit split. |
| scripts/platformkit/venue_history/nba_close_corpus.py | 326 | code | Legacy code retained at measured size pending an explicit split. |

## NOT VERIFIED

- Runtime behavior of allowlisted modules was not evaluated; this construct
  checks LOC scope and frozen size only.
- Test modules were excluded as required by the S163 scope.
- No calibration metric was computed by this construct.

## Contract self-check

- B1-B9: not applicable to this LOC construct; no scored rows, schema changes,
  gates, deployment, or module moves occurred.
- B10: the 300-LOC threshold is preserved.
- Q1-Q6 and Q9: not applicable; no scored comparison or calibration result was
  produced.
- Q7: N is CONSTRUCT and the enumeration is exhaustive for the stated scope.
- Q8: the prior three-module rail premise was re-measured before the change.

## Corrections at landing (Opus verifier, 2026-09-04)

- Timing: the asserted walk ran 4.11 s / 4.32 s cold and 0.75 s / 1.41 s warm; the cold pytest WALL clock was 6.00 s (worktree) / 6.23 s (master), over the 5 s bar by OS page-cache cost, not import cost -- recorded at the limit, not hidden.
- Denominator: the memo measured 2,200 git-tracked files; the test enumerates 2,203 on disk (3 untracked scratch modules); the 137 over-cap set is identical either way. An untracked over-cap .py in a working tree would fail the test for a file not in the repo (verifier NEW GAP).
- 137 legacy modules are frozen at their exact current counts with zero headroom; the register records the 300 cap as advisory for legacy code with the burn-down as later housekeeping rows.
