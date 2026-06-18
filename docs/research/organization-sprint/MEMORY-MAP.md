---
name: memory-map
description: Index-of-the-index -- each cluster in MEMORY.md, what it covers, and the file count.
metadata:
  type: reference
  created: 2026-06-16
---

# MEMORY-MAP -- Cluster Overview

Total memory files: 172 (including MEMORY.md index). Organized into 11 clusters.

---

## Cluster 1: START HERE -- current state + north star
**Covers:** north star resets, productization campaign status, best-predictions loop outcomes, deep-data funnel directive, binding invariants, gotchas (cwd, brain rebuilds, ASCII, pytest-freeze).
**Files (6 explicitly listed + inline invariants text):**
- feedback-north-star-best-predictions-not-no-edge.md
- project-productize-sellable-2026-06-15.md
- project-best-predictions-loop-2026-06-15.md
- project-north-star-deepest-data-best-predictions-per-sport.md
- project-pivot-quant-intelligence-2026-06-13.md
- project-platform-intelligence-robustness-wave-2026-06-13.md

---

## Cluster 2: Load-bearing discipline
**Covers:** accuracy-vs-edge distinction, AST as the only real model edge, CLV vs ROI, no-edge-claims, gated/leak-free process, model validation gotchas (single-fold, seed stability, train/inference parity, recency over volume).
**File count: 23**
- feedback_accuracy_is_not_edge.md
- feedback_ast_edge_is_real_not_underbias.md
- feedback_pregame_edge_is_market_follow_artifact.md
- feedback_edge_publish_pressure_hold_honest_line.md
- feedback_clv_over_roi.md
- feedback_clv_sign_record_clv_backwards.md
- feedback_feature_ceiling_locked.md
- feedback_no_season_final_features.md
- feedback_single_fold_lifts_are_artifacts.md
- feedback_seed_stability_check.md
- feedback_train_inference_parity.md
- feedback_pkl_integrity_check.md
- feedback_nba_recency_beats_volume.md
- feedback_retro_full_surface_validation.md
- feedback_iter57_filter_loses_bet_policy.md
- feedback_segment_filter_pattern.md
- feedback_consistency_cv_orthogonal_interval_signal.md
- feedback_prop_interval_sigma_too_tight.md
- feedback_winprob_push_to_ceiling.md
- feedback_betting_books_not_sharper.md
- feedback_grade_intelligence_not_execution.md
- feedback-tests-mirror-real-not-parallel.md
- feedback-north-star-best-predictions-not-no-edge.md (also in Cluster 1)

---

## Cluster 3: Platform & multi-sport kernel
**Covers:** kernel/adapter pivot (sport-blind kernel + domains/<sport>/), 4-sport thesis proof (NBA/tennis/soccer/MLB adapter-only), kernel + harness promotions (K-PM, K-PR), LOC discipline, platformkit rename, deep-data roadmap, intelligence master plan, vault reorg plan.
**File count: 16**
- project_platform_vision_2026-06-11.md
- project_platform_h0_built_2026-06-11.md
- project_platform_build_session_2026-06-12.md
- project-platform-kernel-built-2026-06-12.md
- project-platform-soccer-third-domain-2026-06-12.md
- project-platform-mlb-fourth-domain-2026-06-12.md
- project-platform-kernel-promotion-2026-06-13.md
- project-platform-harness-promotion-2026-06-13.md
- project-platform-loc-discipline-2026-06-13.md
- project-platform-platformkit-rename-2026-06-13.md
- feedback-scripts-platform-shadows-stdlib.md
- project-deep-data-roadmap-per-sport-2026-06-13.md
- project-intelligence-master-plan-2026-06-13.md
- project-vault-reorg-plan-2026-06-13.md
- feedback-graph-playstyles-not-people.md
- feedback-fable-model-unavailable.md

---

## Cluster 4: NBA engine, ratings & pregame prediction
**Covers:** Monte Carlo possession sim, role-aware 2K ratings, PBP-driven team system, signal factory, pregame/PTS-REB ceiling, playstyle correlation edge, vacated-load, prediction integration, intelligence campaign, outcome impact, finetune audit, hardening, brain architecture, G4 full system, market validation, legacy roadmaps.
**File count: 21**
- project_monte_carlo_engine_2026-06-06.md
- project_role_aware_ratings_2026-06-06.md
- project_nyk_sas_team_system_2026-06-06.md
- project_signal_factory_2026-06-06.md
- project_pregame_model_ceiling_2026-06-04.md
- project_pts_reb_at_data_ceiling.md
- project_playstyle_correlation_edge_2026-06-04.md
- project_vacated_load_feature_2026-06-01.md
- project_prediction_integration_2026-06-01.md
- project_intel_campaign_2026-06-01.md
- project_outcome_impact_campaign_2026-06-01.md
- project_finetune_audit_2026-06-01.md
- project_hardening_campaign_2026-06-02.md
- project_brain_architecture_2026-06-08.md
- project_g4_full_system_2026-06-09.md
- project_market_validation_oddsapi.md
- project_momentum_worse_than_null.md
- project_realmoney_triage_2026-06-01.md
- project_persistent_profile_factory.md
- project_nba_data_vision.md
- project_prediction_improvement_roadmap.md

---

## Cluster 5: In-game (live) layer
**Covers:** PBP replay validation (Finals G1-G3, per-player projector validated), MAE-vs-RMSE artifact (keystone: shrink-toward-current is a trap), overnight build infrastructure, unified in-game shadow (CV_INGAME_SBS), fast harness.
**File count: 5**
- project_pbp_replay_validation_2026-06-10.md
- project_ingame_mae_rmse_artifact_2026-06-05.md
- project_ingame_overnight_build_2026-06-03.md
- project_unified_ingame_shadow.md
- reference_ingame_fast_harness.md

---

## Cluster 6: Edge / betting discipline & market-efficiency proofs
**Covers:** EDGE MAPS (per-sport, pregame+in-game); full-season leak-free walk-forward backtest; LLM scheme-prior layer (REJECTED for betting); full-market intelligence stack (372 markets, CV_MIN_VAR, LLM scout).
**File count: 4**
- reference-edge-maps-2026-06-15.md
- project_season_backtest_2026-06-10.md
- project_llm_scheme_prior_layer_2026-06-10.md
- project_full_market_intelligence_2026-06-10.md

---

## Cluster 7: Autonomous loop & ops protocols
**Covers:** self-improving loop architecture (Arm-A signals + Arm-B atlases), Loop 7 status, bot-loop conventions, queue visibility, concurrent write/rebuild cautions, local machine pytest-freeze, GPU protocols, RunPod environment (all operational notes: timing, cookie perms, youtube block, SQL INSERT gotcha, download skip bug).
**File count: 17**
- project_self_improving_loop.md
- project_loop7_status.md
- reference_bot_loop_pattern.md
- bot-queue-visibility.md
- feedback_sonnet_concurrent_write_collisions.md
- feedback-no-concurrent-brain-rebuilds.md
- feedback_local_machine_pytest_freeze.md
- feedback_always_use_gpu_for_training.md
- feedback_platform_engineer_protocols.md
- reference_runpod_environment.md
- feedback_runpod_pipeline_timing.md
- feedback_runpod_fetcher_cookie_perms.md
- feedback_youtube_datacenter_block.md
- feedback_cap_regen_backfill_gap.md
- feedback_download_script_doesnt_check_done.md
- feedback_runpod_insert_or_replace_doesnt_clean.md
- planning-corpus-audit.md

---

## Cluster 8: Intelligence vault & auto-atlases
**Covers:** quarter intel atlases (2026-05-30), intelligence-layer Wave 9 + Waves 10-15 sessions, atlas redundancy (2 pairs found), and all 44 individual atlas files (28 player + 16 team).
**File count: 48 (4 narrative + 44 atlas files)**
- project_quarter_intel_atlases_2026-05-30.md
- project_intelligence_layer_2026-05-29_session.md
- project_intelligence_layer_2026-05-29_overnight_wave10.md
- project_atlas_redundancy_2026-05-29.md
- project_atlas_player_*.md (28 files: catch_shoot_vs_pullup through vs_scheme_splits)
- project_atlas_team_*.md (16 files: bench_production through turnover_forcing)

---

## Cluster 9: CV / tracking moat
**Covers:** CV edges playbook, identity moat status (jersey OCR dead end, scoreboard OCR keystone), PBP-anchored recall strategy, bug magnitudes (Bugs 6/30/1), per-bug root causes (26/33/39/INT-56/Q1-NaN), BLK signal, xAST inversion, shot quality suspend, made-join bottleneck, tracker extraction roadmap, and CV-pipeline feedback notes.
**File count: 19**
- project_cv_edges_playbook.md
- project_cv_identity_moat_status.md
- project_pbp_anchored_cv_recall.md
- project_cv_bug_magnitudes.md
- project_bug26_enricher_origin.md
- project_bug33_eventdetector_root_cause.md
- project_bug39_10slot_ceiling.md
- project_int56_player_id_zero_bug.md
- project_tracking_q1_period_nan_bug.md
- project_blk_cv_strong_signal.md
- project_xast_potential_assists_inverted.md
- project_shot_quality_suspend_recommendation.md
- project_made_join_is_not_the_bottleneck.md
- project_tracker_extraction_roadmap.md
- feedback_cv_attribution_vs_eventdetection.md
- feedback_osnet_ghost_slot_pattern.md
- feedback_percentile_fill_defeats_quarter_signals.md
- feedback_signal_selectors_use_names_not_cluster_ids.md
- (project_session_handoff_2026-05-30.md -- archival, also in Products cluster)

---

## Cluster 10: Products & job search
**Covers:** CourtVision live go-live (one-command script), when-to-bet timing engine, G4 in-game live overlay fixes, CourtVision project state, Game-7 readiness, live page fixes G1, HF demo, job-search kit (21 files at job-search/), CourtVision QA loop pattern, Railway deploy pattern, archival session handoff.
**File count: 11**
- project_courtvision_live_night_wiring.md
- project_courtvision_when_to_bet_engine.md
- project_courtvision_ingame_live_overlay_2026-06-10.md
- project_courtvision.md
- project_courtvision_game7_live_readiness.md
- project_courtvision_live_page_fixes_2026-06-03.md
- project_courtvision_hf_demo_2026-06-02.md
- project_job_search_kit_2026-06-02.md
- feedback_courtvision_qa_loop.md
- feedback_railwayignore_whitelist_pattern.md
- project_session_handoff_2026-05-30.md (archival)

---

## Cluster 11: References, data & paths
**Covers:** data inventory (163 parquets + 50 JSONs), NBA data caches (untapped per-game caches), NBA system history archive (loops 3-7 cycle-by-cycle, moved from MEMORY.md index 2026-06-08), plus inline paths/preferences block.
**File count: 3**
- reference_data_inventory.md
- reference_nba_data_caches.md
- reference_nba_system_history_archive.md

---

## Summary

| Cluster | Files |
|---|---|
| 1. START HERE | 6 |
| 2. Load-bearing discipline | 23 |
| 3. Platform & multi-sport kernel | 16 |
| 4. NBA engine, ratings & pregame | 21 |
| 5. In-game (live) layer | 5 |
| 6. Edge / betting discipline & proofs | 4 |
| 7. Autonomous loop & ops | 17 |
| 8. Intelligence vault & auto-atlases | 48 |
| 9. CV / tracking moat | 19 |
| 10. Products & job search | 11 |
| 11. References, data & paths | 3 |
| **MEMORY.md index** | 1 |
| **Total** | **174** (includes 2 cross-cluster overlaps) |

Actual unique files on disk: 172 (171 memory files + MEMORY.md).
