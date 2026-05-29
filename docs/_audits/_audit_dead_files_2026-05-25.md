# Dead-File / Cruft Audit — 2026-05-25

Repository: `nba-ai-system` (court-vision on GitHub)
Audit scope: untracked scratch, scripts/, tests/, data/, imports, naming.
Mode: READ-ONLY inventory. No files were moved or deleted.

---

## Section 1 — Root-level `.tmp_*` files (47 files)

All 47 are untracked (`?? .tmp_*`). They were dropped by prior Claude sessions during interactive patching of `src/pipeline/unified_pipeline.py`, `src/tracking/player_resolver.py`, and `scripts/run_phase_g.py`. The narrative is in `.tmp_memory_v*.sh` (incremental commit messages appended to `docs/tracker_memory.md`).

The corresponding code changes (v1-v24) have already been applied directly to source files via these scripts, so the patch scripts themselves are essentially **post-hoc receipts**, not pending work. The memory shell scripts are even more obsolete (they only ever wrote a single block to `docs/tracker_memory.md` and exited).

Legend: **OBSOLETE** = the work is shipped, this is just leftover narration. **STILL USEFUL** = appears not to have been committed/applied. **READ-ONLY DIAG** = inspection script with no side effects, kept only as a reference snippet.

| File | Purpose | Verdict |
|---|---|---|
| `.tmp_analysis.py` | Audits training-grade shooter-name match rate against PBP after quarantine filter | OBSOLETE (diagnostic only) |
| `.tmp_check_boxscore.py` | Prints structure of `data/nba/boxscore_*.json` files | OBSOLETE (one-shot diag) |
| `.tmp_clockfix_patch.py` | v6 patch — shot_clock_est str/float coercion in unified_pipeline.py | OBSOLETE (shipped per `.tmp_memory_v5v6.sh`) |
| `.tmp_collectvideos_patch.py` | v4 patch — run_phase_g._collect_videos fallback discovery paths | OBSOLETE (shipped per `.tmp_memory_v4.sh`) |
| `.tmp_commit_memory.sh` | v1: appends homography early-resume notes to `docs/tracker_memory.md` | OBSOLETE |
| `.tmp_cycle6_close.sh` | Bash status dump (df, tracked_games, csv rows) at cycle-6 close | OBSOLETE |
| `.tmp_cycle7_instrument.py` | v8 patch — adds suspend/resume counters to UnifiedPipeline | OBSOLETE (shipped per `.tmp_memory_v8.sh`) |
| `.tmp_dedup_patch.py` | v5 patch — `--reprocess` bypasses hash dedup in run_phase_g | OBSOLETE (shipped per `.tmp_memory_v5v6.sh`) |
| `.tmp_deeper_diag.py` | READ-ONLY: which games got rebuilt vs not, shooter assignment per game | OBSOLETE (diag) |
| `.tmp_extract_jersey_teamaware.py` | v9 patch — extract_pbp_shot_context team-aware `_by_team` lookup | OBSOLETE (shipped per `.tmp_memory_v9.sh`) |
| `.tmp_gl_test.py` | Speed-test gamelog index build for `retro_inplay_mae` | OBSOLETE (speed probe) |
| `.tmp_grade_inspect.py` | One-shot grade=1 row dump for game 0022500260 | OBSOLETE (diag) |
| `.tmp_homo_patch.py` | v1 patch — homography early-resume SIFT probe in unified_pipeline.py | OBSOLETE (shipped) |
| `.tmp_inspect.py` | READ-ONLY: inspect tracking_data.csv columns for a single game | OBSOLETE (diag) |
| `.tmp_jerseymap_patch.py` | v9 patch — player_resolver nested `_by_team` save/load | OBSOLETE (shipped) |
| `.tmp_memory_v10.sh` ... `.tmp_memory_v13.sh` | Append `## vN ($TS): ...` blocks to `docs/tracker_memory.md` | OBSOLETE (already appended) |
| `.tmp_memory_v2.sh` ... `.tmp_memory_v9_validation.sh` | Same: incremental memory commits v2-v9 | OBSOLETE (already appended) |
| `.tmp_memory_v12b.sh` | Memory note: v12 cycle-10 code-load validation | OBSOLETE |
| `.tmp_overnight_setup.sh` | One-shot pod setup (install Claude CLI, persist ANTHROPIC_API_KEY) | OBSOLETE (one-time bootstrap) |
| `.tmp_probe_check.py` / `_check2.py` / `_check3.py` | Probe parquet loading + `build_snapshot` speed for `retro_inplay_mae` | OBSOLETE (perf probes) |
| `.tmp_proj_speed.py` | Projection speed test (100 games via `predict_in_game.project_snapshot`) | OBSOLETE (perf probe) |
| `.tmp_rebuild_jersey_maps.py` | v10 batch — rebuild 59 jersey_name_map.json from CommonTeamRoster | **POSSIBLY STILL USEFUL** — but note: the canonical `scripts/rebuild_jersey_maps.py` referenced in `.tmp_memory_v10.sh` does not exist on disk; this `.tmp_` file is the only copy. If the v10 rebuild logic is needed again, this is the source. |
| `.tmp_snap_speed.py` | `build_snapshot` 10-game speed test | OBSOLETE (perf probe) |
| `.tmp_stage_test.py` | Stage-by-stage timing probe (parquet load, date index, gamelog) | OBSOLETE (perf probe) |
| `.tmp_team_inspect.py` | One-shot read of `(player_id, team_abbrev, team)` for game 0022500260 | OBSOLETE (diag) |
| `.tmp_v12_patch.py` | v12 patch — `_REPLAY_SUSPEND_FRAMES` 20 → 150 | OBSOLETE (shipped per memory v12) |
| `.tmp_v13_patch.py` | v13 patch — separate `_REPLAY_EARLY_RESUME_INLIERS = 20` constant | OBSOLETE (shipped per memory v13) |
| `.tmp_v20_relocate.py` | v20.1 — relocate team-color prune hook in unified_pipeline.py | OBSOLETE (likely shipped — no v20 memory script present; check git diff before deleting) |
| `.tmp_v20_team_map.py` | v20 — jersey_name_map team-segmentation fix (`apply_team_color_map`) | OBSOLETE (likely shipped) |
| `.tmp_v21_guard.py` | v21 — substitution guard in advanced_tracker.py (`_slot_free_frames`) | OBSOLETE (likely shipped) |
| `.tmp_v22_debug.py` | v22 — diagnostic prints in `apply_team_color_map` | **POSSIBLY STILL USEFUL** — adds debug prints; verify whether prints are in source before discarding |
| `.tmp_v23.py` | v23 — narrow jersey window vote ±30 → ±10 frames | OBSOLETE (likely shipped) |
| `.tmp_v24.py` | v24 — `_backfill_player_names_team_aware` force-overwrites tracking_data.csv | OBSOLETE (likely shipped) |
| `.tmp_validate_jersey_patch.py` | v9 validation — manual `_by_team` build for game 0022500568 | OBSOLETE (one-shot validation) |
| `.tmp_validator_patch.py` | v2 patch — prefer `pbp_shot_distance` over `shot_distance_ft` in validate_cv_signal | OBSOLETE (shipped per `.tmp_memory_v2.sh`) |
| `.tmp_verify_maps.py` | One-shot: print `_by_team` sizes for 4 sample games | OBSOLETE (diag) |

**Recommendation for Section 1:** Move all 47 `.tmp_*` files to `_archive/throwaway_scripts/` (the existing convention) or delete outright. The only ones worth a second look before deletion:
- `.tmp_rebuild_jersey_maps.py` — appears to be the canonical copy of the batch rebuild logic.
- `.tmp_v20_*` through `.tmp_v24.py` — no v14-v19 or v20+ memory log was found in the `.tmp_memory_*` series, so confirm via `git diff` on the touched source files that the patches were applied before discarding.

Also notable: `agent_ball_poss_logic.log` in repo root is a stray runtime log — should not be committed.

---

## Section 2 — Scripts likely dead

### 2a. Underscore-prefix scratch scripts in `scripts/` (~55 files)

These were created as session-local scratch and never wired up. None are imported by anything outside their own family (verified via grep of `from scripts._*` — only `_m25_helpers` is referenced, by `tests/test_pregame_oof_pts_join.py` and the M25 probe family, so it's a **keep**).

Confirmed dead (no references from `src/`, `tests/`, `scripts/`, or `docs/`):

| File | Last touched | Reason suspect dead |
|---|---|---|
| `scripts/_check_linescores.py` | 2026-05-22 | One-shot data check, no callers |
| `scripts/_check_zero_games.py` | 2026-05-22 | One-shot data check, no callers |
| `scripts/_debug_probe.py` / `_debug_probe2.py` / `_debug_quarters.py` | 2026-05-25 | Debug scratch from this session |
| `scripts/_diag_enrich_run.py`, `_diag_flag_distribution.py`, `_diag_mapper_fallback.py`, `_diag_pbp_absolute_clock.py`, `_diag_shot_recall_gaps.py`, `_diag_team_flip.py` | 2026-05-24 | Diagnostic scratch |
| `scripts/_extract_pbp_linescores.py`, `_fetch_linescores.py`, `_fetch_linescores_browser.py`, `_fetch_linescores_fast.py`, `_fix_zero_linescores.py`, `_probe_period_scores.py` | 2026-05-22 | Linescore exploration — superseded by `fetch_per_quarter_boxscores.py` |
| `scripts/_fetch_team_stats_warmup.py` | 2026-04-16 | Stale warmup script |
| `scripts/_legacy_fetch_games.py` | 2026-05-17 | Header literally says **"DEPRECATED: Use scripts/ingest_fetch.py + scripts/ingest_process.py instead"** |
| `scripts/_patch_*.py` (18 files: `_patch_3more`, `_patch_adaptive_poss_threshold`, `_patch_auto_ingest_move_safety`, `_patch_auto_ingest_pending`, `_patch_auto_loop_oom_retry`, `_patch_batch_5fixes`, `_patch_defender_min_window`, `_patch_defender_team_check`, `_patch_enricher_speed`, `_patch_extract_skip_swaps`, `_patch_fixes_1_2`, `_patch_lookback_step4`, `_patch_ocr_separators`, `_patch_player_audit`, `_patch_score_ocr`, `_patch_scoreboard_ocr`, `_patch_shot_clock_parser`, `_patch_shot_debounce`, `_patch_shot_window`, `_patch_tg_v2`, `_patch_training_grade`, `_patch_xnorm_unclamped`) | 2026-05-24 | One-shot patch scripts — patches already applied. Same pattern as root `.tmp_*` files but inside `scripts/`. |
| `scripts/_pod_launch_no_expand.sh`, `_pod_launch_test.sh`, `_pod_sampler.sh` | 2026-05-18 | One-shot pod launch experiments |
| `scripts/_quick_test.py`, `_rate_limit_test.py`, `_run_pbp_backfill.py`, `_smoke_R5H.py` | mixed | Tiny throwaway scripts |
| `scripts/_test_bulk_endpoints.py`, `_test_collect.py`, `_test_enrichment.py`, `_test_live_engine_snap.py`, `_test_nba_api.py`, `_test_v3_quick.py`, `_test_v3_single_row.py`, `_test_v3_time_each.py` | 2026-05-22/25 | Ad-hoc test scripts (not in `tests/`) |
| `scripts/_tmp_check_gametime.py`, `_tmp_check_scoreboard.py`, `_tmp_check_v3.py` | 2026-05-21 | Same `.tmp_` pattern — should not be in `scripts/` at all |

**Keep:** `scripts/_m25_helpers.py` — actually imported by `tests/test_pregame_oof_pts_join.py`, `scripts/probe_M25_pts_*`, `scripts/train_pregame_residual_heads_pts.py`.

### 2b. Superseded retrain scripts

The retrain v-chain pattern: `retrain_X_q50_v2.py` -> `_v3.py` -> `_v4.py`. v2/v3 are kept on disk and have corresponding tests in `tests/`, but the production winners according to user memory are q50 quantile heads (cycles 26-29). Tests for the older versions don't test current behavior, they test the older scripts themselves.

| Older version | Newer version on disk | Note |
|---|---|---|
| `scripts/retrain_blk_q50_v2.py` (+ `tests/test_blk_q50_v2_retrain.py`) | `_v3.py`, `_v4.py` exist | Only test refs older versions |
| `scripts/retrain_fg3m_q50_v2.py` (+ test) | `_v3.py`, `_v4.py` exist | Same |
| `scripts/retrain_reb_q50_v2.py` (+ test) | `_v3.py` exists (per memory, REB uses LGB-q50 — possibly a different module) | Same |
| `scripts/retrain_pts_v2_opp_features.py` (+ `tests/test_pts_v2_retrain.py`) | `retrain_pts_v3.py` exists | Same |

Not necessarily dead, but the v2/v3 generations are unreferenced by anything except their own tests and may be safely retired.

### 2c. Sweep scripts whose results are already captured

User memory states "Per-stat HP sweeps (25-31, 35-36): -0.025 MAE across 5 knobs (lr/subsample/colsample/reg_alpha/gamma/reg_lambda/max_depth/n_est)" — i.e., these sweeps already produced production-locked hyperparameters in Loop 3 (ending cycle 38). They are not referenced by any other script.

| File | Last touched | Status |
|---|---|---|
| `scripts/sweep_learning_rate.py` | 2026-05-23 | Results shipped |
| `scripts/sweep_colsample.py` | 2026-05-23 | Results shipped |
| `scripts/sweep_subsample.py` | 2026-05-23 | Results shipped |
| `scripts/sweep_reg_alpha.py` | 2026-05-23 | Results shipped |
| `scripts/sweep_reg_lambda.py` | 2026-05-23 | Results shipped |
| `scripts/sweep_gamma.py` | 2026-05-23 | Results shipped |
| `scripts/sweep_max_depth.py` | 2026-05-23 | Results shipped |
| `scripts/sweep_n_estimators.py` | 2026-05-23 | Results shipped |
| `scripts/sweep_winprob_*` (8 files + `sweep_winprob_common.py` shared lib + `sweep_winprob_combined.py`) | 2026-05-23 | WinProb HP sweeps shipped, NNLS stack locked |

These could be archived under `_archive/sweeps/` rather than deleted — they're useful as templates if any sweep needs to be re-run.

### 2d. Root-level `agent_*.py` and `scratch_ball_poss_logic.py` (16 files)

All untracked, all created 2026-05-24, all are **READ-ONLY diagnostic scripts** with `/workspace/nba-ai-system/...` hard-coded paths (they were dropped on the pod, then synced to the laptop). None are referenced by any other code in the repo.

| File | Last touched | Purpose |
|---|---|---|
| `agent_audit_agg.py` | 2026-05-24 19:18 | Audit aggregate features in all_pbp_shot_context.csv |
| `agent_audit_ball.py` | 2026-05-24 19:19 | Audit ball-tracking outputs |
| `agent_audit_event.py` | 2026-05-24 19:27 | Audit event recall |
| `agent_audit_homo.py` | 2026-05-24 19:22 | Audit homography drift |
| `agent_audit_models.py` | 2026-05-24 19:31 | Audit models |
| `agent_ball_poss.py` | 2026-05-24 18:16 | Classify why shooter_id missing |
| `agent_ball_poss_logic.py` | 2026-05-24 18:22 | Ball-possession logic probe |
| `agent_dist_consistent.py`, `agent_dist_followup.py` | 2026-05-24 17:55-56 | Shot-distance consistency probes |
| `agent_pbp_dist.py` | 2026-05-24 17:58 | PBP distance probe |
| `agent_r_clean.py` | 2026-05-24 18:41 | Cleaning probe |
| `agent_shooter_who.py` | 2026-05-24 18:16 | Shooter identification probe |
| `agent_team_match_local.py`, `agent_team_match_v2.py`, `agent_team_match_v3.py` | 2026-05-24 18:06-08 | Team-match diagnostic v1/v2/v3 chain |
| `scratch_ball_poss_logic.py` | 2026-05-24 18:16 | Ball-possession scratch |
| `agent_ball_poss_logic.log` | runtime log | Should not be committed |

These should not live in the repo root. Move to `_archive/throwaway_scripts/` or delete.

### 2e. Duplicate / overlapping reprocess scripts

Multiple scripts have nearly identical purpose:

| File | mtime | Note |
|---|---|---|
| `scripts/reprocess_20_games.py` | 2026-03-30 | One-shot batch of 20 — likely done |
| `scripts/reprocess_safe.sh` | 2026-03-30 | Wrapper, likely superseded |
| `scripts/reprocess_tracking_only.py` | 2026-03-30 | Tracking-only mode |
| `scripts/batch_reprocess.py` | 2026-03-30 | Generic batch |
| `scripts/batch_reprocess_games.py` | 2026-03-30 | Generic batch (duplicate?) |
| `scripts/reprocess_failed_games.py` | recent | **Active per MEMORY.md (ISSUE-009)** — keep |

Recommend consolidating the four older ones once user confirms they're unused.

### 2f. `posthoc_resolve_names.py` + `posthoc_resolve_names_v2.py`

Older `posthoc_resolve_names.py` is only referenced by `.tmp_memory_v9.sh` (a scratch memory commit script). v2 exists. v1 is likely superseded.

### 2g. `measure_shooter_match.py` / `measure_shooter_match_v2.py`

Both exist in `scripts/`. The v1 is only referenced from `.tmp_memory_v9.sh` and `.tmp_overnight_setup.sh` (both scratch). v2 is referenced from nowhere outside its own family. These are diagnostic-only and may be retired once the jersey-segmentation work concludes.

---

## Section 3 — Tests likely dead

Tests track the retrain v-chains and probe families, so when a retrain script is retired the test usually goes with it.

| Test file | Why suspect dead |
|---|---|
| `tests/test_blk_q50_v2_retrain.py` | Tests `retrain_blk_q50_v2.py` — superseded by v3 and v4 |
| `tests/test_blk_q50_v3_retrain.py` | Tests `retrain_blk_q50_v3.py` — superseded by v4 |
| `tests/test_fg3m_q50_v2_retrain.py` | Tests `retrain_fg3m_q50_v2.py` — superseded by v3/v4 |
| `tests/test_fg3m_q50_v3_retrain.py` | Tests `retrain_fg3m_q50_v3.py` — superseded by v4 |
| `tests/test_reb_q50_v2_retrain.py` | Tests `retrain_reb_q50_v2.py` — superseded |
| `tests/test_pts_v2_retrain.py` | Tests `retrain_pts_v2_opp_features.py` — superseded by v3 |
| `tests/test_backtest_inplay_edge.py` vs `test_backtest_inplay_edge_v2.py` | Both kept — v1 may be retirable depending on user choice |
| `tests/test_retro_inplay_mae.py` vs `test_retro_inplay_mae_v2.py` | Same pattern |
| `tests/test_live_quantile_bands.py` vs `test_live_quantile_bands_v2.py` | Same pattern |
| `tests/test_q4_foul_forecast.py` / `_v2.py` / `_v3.py` | v3 likely current |
| `tests/test_probe_*` (many) | These test one-shot probe scripts — each is essentially `assert script ran without crashing`. Lifecycle is "ship gains -> retire probe + its test". |

No `.disabled` / `_skip` / `legacy` patterns were found in `tests/`. No tests import deleted modules (grep for `tracking_v1`, `BasketTracking`, `old_pipeline`, `deprecated_*` returned empty).

---

## Section 4 — Data files

### 4a. Files > 100 MB (9 files)

| File | Size (MB) | mtime |
|---|---|---|
| `data/tracking/0022401156/features.csv` | 411 | 2026-04-07 19:06 |
| `data/games/0022400625/features.csv` | 396 | 2026-03-23 21:50 |
| `data/tracking/0022500002/features.csv` | 148 | 2026-04-07 19:29 |
| `data/tracking/0022400625/features.csv` | 144 | 2026-04-07 19:28 |
| `data/tracking_archive/0022400430/features.csv` | 136 | 2026-04-07 19:28 |
| `data/tracking/0022500053/tracking_data.csv` | 129 | 2026-05-22 19:38 |
| `data/tracking/0022401185/features.csv` | 133 | 2026-04-07 19:29 |
| `data/tracking_archive/0022400537/features.csv` | 113 | 2026-04-07 19:28 |
| `data/tracking/0022500064/tracking_data.csv` | 107 | 2026-05-22 21:14 |

`data/games/0022400625/features.csv` (396 MB) plus its duplicate at `data/tracking/0022400625/features.csv` (144 MB) is suspicious — same game ID lives in two paths. The `data/games/` tree is older (2026-04 or earlier) and is likely the previous canonical layout before the move to `data/tracking/`.

### 4b. Stale data (mtime < 2025-09 was the brief, but the repo is on 2026 dates throughout so the practical "stale" threshold here is pre-2026-04)

| File / dir | mtime | Size | Note |
|---|---|---|---|
| `data/ball_tracking.csv` | 2026-04-01 17:44 | 348 KB | Stale single-game CSV (per-game tracking now under `data/tracking/<game_id>/`) |
| `data/events_log.csv` | 2026-04-01 17:44 | 96 KB | Stale (memory says root-level data CSVs were deleted, but this one remains) |
| `data/features.csv` | 2026-04-01 17:49 | 34 MB | Stale top-level features dump |
| `data/tracking_data.csv` | 2026-04-01 17:55 | 102 KB | Stale top-level (now under per-game dirs) |
| `data/shot_log.csv`, `data/shot_log_enriched.csv` | 2026-04-01 17:49 | 7 KB each | Stale top-level (per-game now) |
| `data/possessions.csv`, `data/possessions_enriched.csv` | 2026-04-01 17:49 | 25 KB each | Stale top-level |
| `data/momentum.csv` | 2026-03-27 | 158 KB | Stale |
| `data/defense_pressure.csv` | 2026-03-27 | 96 KB | Stale |
| `data/shot_quality.csv` | 2026-03-27 | 1.7 KB | Stale |
| `data/shot_heatmap.json` | 2026-03-27 | 1.3 KB | Stale |
| `data/scoreboard_log.csv` | 2026-04-01 | 205 B | Stale |
| `data/player_clip_stats.csv` | 2026-04-01 | 902 B | Stale |
| `data/improvement_runs.csv` | 2026-03-12 | 162 B | Predates current improvement log |
| `data/jersey_name_map.json` | 2026-03-30 | 618 B | Top-level — now stored per-game in `data/tracking/<gid>/` |
| `data/fetch_trad_box_cycle93a.log` | 2026-05-24 | 0 B | Empty log file |
| `data/full_game_results.json` | 2026-04-01 | 130 KB | Stale |
| `data/processed_games.txt` | 2026-03-15 | 309 B | Predates `data/phase_g_processed.txt` |
| `data/backtest_results.json` | 2026-04-08 | 627 B | Stale |
| `data/games/` | 2026-04-01 (mtime) | 759 MB | **Old canonical layout** — superseded by `data/tracking/` |
| `data/tracking_archive/` | 2026-04-13 (mtime) | 713 MB | 41 game dirs |

These are inventoried, **not** recommended for deletion. The user should decide whether `data/games/`, `data/tracking_archive/`, and the root-level pre-April 2026 CSVs are safe to drop.

---

## Section 5 — Broken imports / refactor remnants

No truly broken imports were found.

Searched for: `from src.tracking_v1`, `from src.legacy`, `from old_`, `from deprecated_`, `BasketTracking` — all returned empty.

Notable:
- `scripts/_legacy_fetch_games.py` has a literal `DEPRECATED` header pointing callers to `scripts/ingest_fetch.py + scripts/ingest_process.py`. No callers found in the repo.
- `legacy/` directory in repo root: contains `features/`, `models/`, `pipelines/`, `tracking/`. Per `MEMORY.md`, current architecture lives in `src/`. Did not deep-inspect — likely safe-to-archive but should be confirmed.
- `_archive/` is the existing convention for retiring code; many candidates above could go there.

No tests import modules that don't exist (confirmed via grep on all `tests/test_*.py` imports).

---

## Section 6 — Naming inconsistencies

Project predominantly uses `snake_case`, but a few patterns deviate:

### CamelCase / MixedCase fragments in script names

These are the `probe_<period>_*` scripts that bake snapshot-window labels into the filename:

- `decompose_endQ3_mae.py`, `backtest_midQ3_snapshot.py`, `probe_endq3_period_head.py` (note inconsistent caps — `endQ3` vs `endq3` in same family)
- `probe_R1_A_endq2_learned_minutes.py` ... `probe_R8_*` — Roman-numeralish round identifiers (`R1`, `R2`, ..., `R8`) plus letter suffixes (`_A`, `_B`, ...) plus snake_case description
- `probe_M22_baseline_widths.py` ... `probe_M31_*` — Milestone identifiers `M22`–`M31`
- `_smoke_R5H.py`

Two markdown placeholders also break the `.py` pattern: `probe_R3_F_pregame_residual_heads_SKIPPED.md`, `probe_R5_C_BLOCKED_midquarter.md` — these document why a probe was not executed.

### Inconsistent capitalization within the same concept

| Variant 1 | Variant 2 |
|---|---|
| `endQ3` (in `decompose_endQ3_mae.py`, `backtest_midQ3_snapshot.py`) | `endq3` (in `probe_endq3_period_head.py`, `train_residual_heads_endq1.py`, `_endq2.py`) |
| `winprob` (most scripts) | `WinProb` (in MEMORY.md narrative) |

### Mixed prefix conventions in `scripts/`

- `_*.py` (underscore-prefix) — scratch, ~55 files
- `probe_*.py` — research probes, ~70+ files
- `train_*.py` — training scripts
- `retrain_*.py` — retraining
- `sweep_*.py` — HP sweeps
- `backtest_*.py`, `validate_*.py`, `verify_*.py` — eval
- `fetch_*.py`, `build_*.py`, `aggregate_*.py` — data
- Some root-level `agent_*.py` (which shouldn't be in root at all)

The conventions are mostly fine internally but the **root** of the repo is messy:
- 16 `agent_*.py` + 1 `scratch_*.py` + 1 `.log` should not live there
- 47 `.tmp_*` files should not live there

`go.bat`, `start.sh`, `yolov8n*.pt` are reasonable for repo root, but `example_lines.csv` is awkward (could go in `data/examples/`).

---

## Section 7 — Recommended cleanup priority (safest first)

Ranked by safety. "Safe" = high confidence the file is dead and removal cannot break anything. "Caution" = quick verification recommended before removal.

1. **SAFE** — all 47 `.tmp_*.py` and `.tmp_*.sh` files in repo root, EXCEPT `.tmp_rebuild_jersey_maps.py` (it's the only copy of the v10 batch-rebuild logic) and `.tmp_v20_*`/`.tmp_v22_debug.py`/`.tmp_v24.py` (no v14-v24 memory log was committed, so verify the patches were applied to source first). After move/delete, also add `.tmp_*` to `.gitignore` to prevent recurrence.

2. **SAFE** — `agent_ball_poss_logic.log` (stray runtime log in repo root).

3. **SAFE** — `scripts/_tmp_check_*.py` (3 files: `_tmp_check_gametime`, `_tmp_check_scoreboard`, `_tmp_check_v3`) — `.tmp_` pattern in the wrong folder.

4. **SAFE** — `scripts/_legacy_fetch_games.py` — header literally marks it deprecated; no callers.

5. **SAFE with quick verify** — 16 root-level `agent_*.py` + `scratch_ball_poss_logic.py`. All are read-only diagnostics with hard-coded `/workspace/...` paths. Spot-check that no Makefile / bot loop calls them.

6. **SAFE** — `scripts/_patch_*.py` (~22 files in `scripts/`). Same pattern as the root `.tmp_*` files — one-shot patches that were applied. The patches are in source already.

7. **CAUTION** — `scripts/_diag_*.py`, `scripts/_debug_*.py`, `scripts/_check_*.py`, `scripts/_fetch_linescores*.py` (linescore family), `scripts/_test_*.py`, `scripts/_pod_launch_*.sh`. All scratch with no callers, but some users keep diagnostic scripts around as runbooks. Confirm with user.

8. **CAUTION** — Stale top-level `data/*.csv` and `data/*.json` files dated 2026-03 to 2026-04 (listed in Section 4b). They predate the per-game-directory layout. Per MEMORY.md note "Root-level `data/*.csv` stale files **deleted** (700MB freed)" some have already been cleaned — these are the leftovers.

9. **CAUTION** — `scripts/sweep_*.py` (non-winprob, 8 files): results captured in Loop 3 production hyperparameters. Could archive to `_archive/sweeps/` rather than delete, since they're useful as templates.

10. **CAUTION (largest disk wins)** — `data/games/0022400625/features.csv` (396 MB, duplicate of a file already in `data/tracking/`) and the broader `data/games/` directory (759 MB) which appears to be a pre-migration canonical layout now superseded by `data/tracking/`. Verify by spot-checking that no script reads from `data/games/<gid>/`.

### Disk-savings estimate (if everything in priority 1-10 is removed):
- Priority 1-3 (47 + 3 + 1 + 16 + 1 = ~68 small scratch files): negligible disk, big readability win
- Priority 4-6 (~40 small Python files): negligible
- Priority 7 (~20 small files): negligible
- Priority 8: ~50 MB across stale CSVs
- Priority 9: ~150 KB
- Priority 10: **~759 MB** from `data/games/` alone, possibly **~1.5 GB total** including older `data/tracking_archive/` if also retired

### Not in this audit's recommendation set (deliberately):
- `legacy/` directory — needs human inspection
- `_archive/` — already the destination for retired code, leave as is
- `data/tracking_archive/` (713 MB, 41 games) — clearly intended as archive, user should decide
- `data/videos/` (56 GB) — source data, out of scope

---

End of audit. No files were modified or moved.
