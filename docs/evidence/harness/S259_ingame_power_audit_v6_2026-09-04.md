# S259 in-game power audit v6

Calibration power audit only.

Preregistration: `S259_ingame_power_audit_v2_prereg_2026-09-04.md`
Prereg seal: b0e6c0160209b975d3e8ef5890ae16eb895d8e54f3d405a31c24b92f835c2fe1

S210 attempt 2b literal before-condition count: 29
Source grep count: 42
Excluded S06 reason: legacy `in-game` matched `within-game`; the boundary-aware screen excludes it.

Source file list:
- S08_replication_gate_2026-09-03.md
- S100_microstructure_2026-09-03.md
- S102_nba_pod_sweep_2026-09-03.md
- S103_nba_sigma_2026-09-03.md
- S108_pregame_full_model_2026-09-03.md
- S112_nba_mlb_close_2026-09-03.md
- S113_close_incumbent_2026-09-03.md
- S114_ingame_ensemble_2026-09-03.md
- S115_ingame_models_2026-09-03.md
- S116_pooled_ingame_2026-09-03.md
- S117_soccer_ingame_screen_2026-09-03.md
- S119_mlb_ingame_supply_2026-09-03.md
- S121_tick_partition_2026-09-03.md
- S124_S125_S126_S131_ingame_guards_2026-09-03.md
- S126_rerun_S124_gate_2026-09-03.md
- S128_S129_asof_supply_leaks_2026-09-03.md
- S132_close_contamination_fix_2026-09-03.md
- S136_tennis_roundgrain_builders_2026-09-03.md
- S137_rebaseline_2026-09-03.md
- S143_archive_read_2026-09-03.md
- S148_live_requote_2026-09-03.md
- S152_s116_rerun_2026-09-03.md
- S206_wnba_ingame_first_score_2026-09-04.md
- S219_nba_tail_guard_screen_2026-09-04.md
- S225_ingame_intel_conditioning_rerun_2026-09-04.md
- S247_nba_sim_engine_vs_line_v2_2026-09-04.md
- S58_trial1_e2_slice_2026-09-03.md
- S58_trialA_clamp_family_2026-09-03.md
- S58_trialB_nba_halftime_asof_2026-09-03.md
- S79_family_combo_2026-09-03.md
- S80_player_grain_2026-09-03.md
- S81_market_move_2026-09-03.md
- S82_ingame_screen_2026-09-03.md
- S83_mlb_join_player_ids_2026-09-03.md
- S84_nba_lineup_at_tick_2026-09-03.md
- S85_refused_families_2026-09-03.md
- S86_nba_every_tick_2026-09-03.md
- S92_nba_lineup_dynamic_2026-09-03.md
- S94_nba_early_shrinkage_2026-09-03.md
- S96_nba_overreaction_2026-09-03.md
- S97_nba_sensor_fusion_2026-09-03.md
- S98_nba_better_prior_2026-09-03.md

Anchors (maximum absolute difference <= 1e-9):
- S117_soccer_ingame_screen_2026-09-03: n_ticks=163 clusters=2 improvement=+0.025071328021
- S82_ingame_screen_2026-09-03: n_ticks=15702 clusters=41 improvement=+0.003332296267

| memo | n_ticks | clusters | n_eff | improvement | CI half-width | MDE80 | label |
|---|---:|---:|---:|---:|---:|---:|---|
| S08_replication_gate_2026-09-03.md | - | - | - | - | - | - | NO SERIES ARCHIVED: no unambiguous paired Brier archive rule. |
| S100_microstructure_2026-09-03.md | - | - | - | - | - | - | NO SERIES ARCHIVED: no unambiguous paired Brier archive rule. |
| S102_nba_pod_sweep_2026-09-03.md | 192635 | 673 | 26657.332852 | +0.000139440475 | 0.000085506487 | 0.000122180704 | REFUTED-AT-BAR |
| S103_nba_sigma_2026-09-03.md | - | - | - | - | - | - | NO SERIES ARCHIVED: no unambiguous paired Brier archive rule. |
| S108_pregame_full_model_2026-09-03.md | - | - | - | - | - | - | NO SERIES ARCHIVED: no unambiguous paired Brier archive rule. |
| S112_nba_mlb_close_2026-09-03.md | - | - | - | - | - | - | NO SERIES ARCHIVED: no unambiguous paired Brier archive rule. |
| S113_close_incumbent_2026-09-03.md | - | - | - | - | - | - | NO SERIES ARCHIVED: no unambiguous paired Brier archive rule. |
| S114_ingame_ensemble_2026-09-03.md | - | - | - | - | - | - | NO SERIES ARCHIVED: no unambiguous paired Brier archive rule. |
| S115_ingame_models_2026-09-03.md | - | - | - | - | - | - | NO SERIES ARCHIVED: no unambiguous paired Brier archive rule. |
| S116_pooled_ingame_2026-09-03.md | - | - | - | - | - | - | NO SERIES ARCHIVED: no unambiguous paired Brier archive rule. |
| S117_soccer_ingame_screen_2026-09-03.md | 163 | 2 | 14.681646 | +0.025071328021 | 0.362929445877 | 0.402243272317 | UNDERPOWERED |
| S119_mlb_ingame_supply_2026-09-03.md | 15702 | 41 | 214.827112 | +0.003332296267 | 0.005303660238 | 0.007536047364 | UNDERPOWERED |
| S121_tick_partition_2026-09-03.md | - | - | - | - | - | - | NO SERIES ARCHIVED: no unambiguous paired Brier archive rule. |
| S124_S125_S126_S131_ingame_guards_2026-09-03.md | - | - | - | - | - | - | NO SERIES ARCHIVED: no unambiguous paired Brier archive rule. |
| S126_rerun_S124_gate_2026-09-03.md | - | - | - | - | - | - | NO SERIES ARCHIVED: no unambiguous paired Brier archive rule. |
| S128_S129_asof_supply_leaks_2026-09-03.md | - | - | - | - | - | - | NO SERIES ARCHIVED: no unambiguous paired Brier archive rule. |
| S132_close_contamination_fix_2026-09-03.md | - | - | - | - | - | - | NO SERIES ARCHIVED: no unambiguous paired Brier archive rule. |
| S136_tennis_roundgrain_builders_2026-09-03.md | - | - | - | - | - | - | NO SERIES ARCHIVED: no unambiguous paired Brier archive rule. |
| S137_rebaseline_2026-09-03.md | - | - | - | - | - | - | NO SERIES ARCHIVED: no unambiguous paired Brier archive rule. |
| S143_archive_read_2026-09-03.md | - | - | - | - | - | - | NO SERIES ARCHIVED: no unambiguous paired Brier archive rule. |
| S148_live_requote_2026-09-03.md | - | - | - | - | - | - | NO SERIES ARCHIVED: no unambiguous paired Brier archive rule. |
| S152_s116_rerun_2026-09-03.md | - | - | - | - | - | - | NO SERIES ARCHIVED: no unambiguous paired Brier archive rule. |
| S206_wnba_ingame_first_score_2026-09-04.md | - | - | - | - | - | - | NO SERIES ARCHIVED: no unambiguous paired Brier archive rule. |
| S219_nba_tail_guard_screen_2026-09-04.md | - | - | - | - | - | - | NO SERIES ARCHIVED: no unambiguous paired Brier archive rule. |
| S225_ingame_intel_conditioning_rerun_2026-09-04.md | - | - | - | - | - | - | NO SERIES ARCHIVED: no unambiguous paired Brier archive rule. |
| S247_nba_sim_engine_vs_line_v2_2026-09-04.md | - | - | - | - | - | - | NO SERIES ARCHIVED: no unambiguous paired Brier archive rule. |
| S58_trial1_e2_slice_2026-09-03.md | 6579 | 157 | 467.272882 | +0.048272196858 | 0.023850415315 | 0.034040382412 | UNDERPOWERED |
| S58_trialA_clamp_family_2026-09-03.md | 47104 | 158 | 566.181701 | -0.000866166276 | 0.001230029883 | 0.001755570794 | REFUTED-AT-BAR |
| S58_trialB_nba_halftime_asof_2026-09-03.md | - | - | - | - | - | - | NO SERIES ARCHIVED: no unambiguous paired Brier archive rule. |
| S79_family_combo_2026-09-03.md | 800 | 30 | 800.000000 | -0.003873663613 | 0.004824678573 | 0.006839709886 | UNDERPOWERED |
| S80_player_grain_2026-09-03.md | 2267 | 13 | 79.251785 | +0.003759465553 | 0.030638865461 | 0.042909657298 | UNDERPOWERED |
| S81_market_move_2026-09-03.md | - | - | - | - | - | - | NO SERIES ARCHIVED: no unambiguous paired Brier archive rule. |
| S82_ingame_screen_2026-09-03.md | 15702 | 41 | 214.827112 | +0.003332296267 | 0.005303660238 | 0.007536047364 | UNDERPOWERED |
| S83_mlb_join_player_ids_2026-09-03.md | - | - | - | - | - | - | NO SERIES ARCHIVED: no unambiguous paired Brier archive rule. |
| S84_nba_lineup_at_tick_2026-09-03.md | 33713 | 284 | 894.356175 | -0.000455338664 | 0.003464438658 | 0.004947967696 | UNDERPOWERED |
| S85_refused_families_2026-09-03.md | - | - | - | - | - | - | NO SERIES ARCHIVED: no unambiguous paired Brier archive rule. |
| S86_nba_every_tick_2026-09-03.md | 232951 | 797 | 3260.070012 | -0.004856640630 | 0.002497941012 | 0.003569517036 | REFUTED-AT-BAR |
| S92_nba_lineup_dynamic_2026-09-03.md | - | - | - | - | - | - | NO SERIES ARCHIVED: no unambiguous paired Brier archive rule. |
| S94_nba_early_shrinkage_2026-09-03.md | 192635 | 673 | 4029.334648 | -0.000242825969 | 0.000756138356 | 0.001080450378 | REFUTED-AT-BAR |
| S96_nba_overreaction_2026-09-03.md | - | - | - | - | - | - | NO SERIES ARCHIVED: no unambiguous paired Brier archive rule. |
| S97_nba_sensor_fusion_2026-09-03.md | - | - | - | - | - | - | NO SERIES ARCHIVED: no unambiguous paired Brier archive rule. |
| S98_nba_better_prior_2026-09-03.md | - | - | - | - | - | - | NO SERIES ARCHIVED: no unambiguous paired Brier archive rule. |

## ATTEMPT 2

| correction | before | after |
|---|---:|---:|
| Output-excluded legacy premise count | 30 | 29 |
| Legacy aliases | absent | screen, source_bytes, delta, paired_loss_se present |
| screen instance IDs | absent | stem plus sorted per-file ordinal; duplicate stems add path SHA |

## ATTEMPT 2b

- Uniqueness rule: `S259:<memo-stem>:<sorted per-file ordinal>`; exact duplicate stems append a SHA-256 prefix of the harness-relative path.
- Legacy `screen`, `aliases`, `source_bytes`, `delta`, and `paired_loss_se` fields are retained.
- Real-corpus counts can differ between this worktree and the landing main checkout; this worktree run has 42 screens and the known main count is unknown (not inspected from this worktree).

## ATTEMPT 2c

- Field rule: `screen_id` remains the frozen legacy `_screen_id(stem)` value.
- Field rule: `screen_instance_id` is corpus-unique for any corpus size.

## ATTEMPT 2d

- Restored the legacy v3 memo and JSON to candidate-parent bytes; corrected output is written only to v5 and v6 paths.

## NOT VERIFIED

- No new scored comparison, predictor fit, or deployment was performed.
- NO SERIES ARCHIVED rows remain archive-availability findings, not performance results.

Verification: python -m pytest tests/platformkit/ingame/test_s259_ingame_power_audit.py -q -p no:cacheprovider -> 1 passed.
Schema assertion: full additive fields are present and every screen_instance_id is unique.
