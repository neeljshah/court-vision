# Model Deployment Audit — R20_M7 (R30_W6 refresh)

**Date:** 2026-05-26 (R30_W6 refresh)  
**Original ship:** R20_M7 (round 20)  
**Refresh ship:** R30_W6 (round 30, after the R21-R29 wave)  
**Worktree (original):** `agent-a29341ca816d8067d`  
**Worktree (refresh):** `agent-a29f374f14a49a823`  
**Probe script (original):** `scripts/improve_loop/probe_R20_M7_model_audit.py`  
**Probe script (refresh):** `scripts/improve_loop/probe_R30_W6_audit_refresh.py`  
**State source:** `scripts/improve_loop/state.json` (71+ ships across rounds 0-29)

## R30_W6 refresh result — headline

- **0 regressions** in the wire layer vs the R20_M7 baseline (22 surfaces wired, 6 probe-only ships with no persisted artifact).
- All 5 R21-R29 wire-layer touches still present and active:
  - **R21_N1** — `prop_pergame._resolve_model_dir` worktree fallback for gitignored prop-model artifacts.
  - **R21_N5** — per-(game_id, models_mtime) m2_family prediction cache.
  - **R22_O8** — `injury_availability` parquet-first lookup.
  - **R23_P2** — `inplay_bet_ranker` injury-kill guard (drops OUT players from ranked output).
  - **R28_U2** + **R29_V3** — pace + residual-drift triage patches (data layer, no wire-layer change).
- 5/5 smoke tests pass: m2_family pregame predict, per-stat heads, injury factor, endQ3 residual head load, R21_N5 cache byte-identity.

R30_W6 refresh payload: `data/cache/probe_R30_W6_results.json`

## Headline

The improvement loop tracks 51 shipped artifacts. **R20_M7 audited the
production prediction path (`predict_slate.py` -> `prop_pergame.predict_pergame`
and `live_bet_ranker.py` -> `ModelCache.predict_player`) plus the game-level
path (`game_orchestrator -> game_models.predict`) and identified the M2-family
multi5 ensemble (R11 BATCH-6/7, 20 fitted models on disk) as the single
highest-value un-wired ship**. The ensemble was callable only from
`scripts/predict_game.py` CLI; every production caller still loaded the legacy
single-XGB `game_game_total.json` / `game_spread.json` heads. R20_M7 wires the
ensemble into `src/prediction/game_models.predict()` with a feature-rich
season_games row lookup so all callers (api/predictions_router,
game_orchestrator, run_daily_slate, betting_portfolio) pick it up
transparently.

## Ship-vs-Wired Matrix

### Per-stat player props (live path)

| Stat | Predictor | Artifact | Loader | Round/Ship | Wired? |
|------|-----------|----------|--------|------------|--------|
| pts  | sqrt+Huber blend (3-way NNLS) | `props_pg_pts.json` + `props_pg_lgb_pts.pkl` + `props_pg_mlp_pts.pkl` | `prop_pergame.load_pergame_model` | cycle 18 | **YES** |
| reb  | LGB q50 | `quantile_pergame_lgb_reb_q50.pkl` | `prop_pergame._load_q50_model` | cycle 29 | **YES** |
| ast  | multitask MLP blend | `props_pg_mlp_ast.pkl` + NNLS weights | `prop_pergame.load_pergame_model` | cycle 23 | **YES** |
| fg3m | XGB q50 | `quantile_pergame_fg3m_q50.json` | `prop_pergame._load_q50_model` | cycle 27 | **YES** |
| stl  | XGB q50 | `quantile_pergame_stl_q50.json` | `prop_pergame._load_q50_model` | cycle 27 | **YES** |
| blk  | XGB q50 | `quantile_pergame_blk_q50.json` | `prop_pergame._load_q50_model` | cycle 27 | **YES** |
| tov  | XGB q50 | `quantile_pergame_tov_q50.json` | `prop_pergame._load_q50_model` | cycle 27 | **YES** |

All 7 player-prop stats are correctly loaded by `predict_pergame()` called
from `predict_slate.py` and `live_bet_ranker.py`. **Player-prop family is fully
wired.**

### Per-stat residual heads (post-prediction correction)

| Stat | Pregame | EndQ1 | EndQ2 | EndQ3 | EndQ3 streak (M16) | EndQ3 xstat (F3) | Wired? |
|------|---------|-------|-------|-------|---------------------|------------------|--------|
| pts  | -- (gate-fail) | yes | yes | yes | -- (gate-fail) | -- (gate-fail) | YES |
| reb  | yes | yes | yes | yes | -- (gate-fail) | -- (gate-fail) | YES |
| ast  | yes | yes | yes | yes | -- (gate-fail) | -- (gate-fail) | YES |
| fg3m | yes | yes | yes | yes | yes | yes | YES |
| stl  | yes | yes | yes | yes | yes | yes | YES |
| blk  | yes | yes | yes | yes | yes | yes | YES |
| tov  | yes | yes | yes | yes | yes | yes | YES |

Pregame heads via `src/prediction/pregame_residual_heads.apply_residual_correction`
called from `predict_pergame()`. In-play heads (endQ1/Q2/Q3 + streak + xstat)
via `src/prediction/residual_heads.*` called from `src/prediction/live_engine.py`.
**Residual head family is fully wired.**

### Game-level family

| Surface | Legacy artifact | M2-family artifact | Loader (before R20_M7) | Wired (before) | Wired (after R20_M7) |
|---------|-----------------|--------------------|------------------------|----------------|----------------------|
| game_total       | `game_game_total.json` | `m2_family/total_*.joblib` (5 models) | `game_models.load_models` | legacy single-XGB | **M2 multi5 ensemble** |
| spread           | `game_spread.json`     | `m2_family/spread_*.joblib` (5 models) | `game_models.load_models` | legacy single-XGB | **M2 multi5 ensemble** |
| home_pts         | (none)                 | `m2_family/home_pts_*.joblib` (5 models) | not exposed | **NOT WIRED** | **wired (new key)** |
| away_pts         | (none)                 | `m2_family/away_pts_*.joblib` (5 models) | not exposed | **NOT WIRED** | **wired (new key)** |
| blowout          | `game_blowout.json`    | (no m2 ship)                              | `game_models.load_models` | yes (legacy) | yes (legacy) |
| first_half_total | `game_first_half.json` | (no m2 ship)                              | `game_models.load_models` | yes (legacy) | yes (legacy) |
| pace             | `game_pace.json`       | (no m2 ship)                              | `game_models.load_models` | yes (legacy) | yes (legacy) |
| Q1/H1 + AH/PH thresholds | (none)         | (no persisted ship — R11 v15-v34 are probe-only) | -- | **NOT WIRED (no artifact)** | still not wired |
| binary O/U & ATS | (none)                 | (no persisted ship — R11 v11-v30 are probe-only) | -- | **NOT WIRED (no artifact)** | still not wired |

The 95 M2v* probe variants (R11 BATCH3-8) and R11_BATCH8_M2x_extra_thresholds
in state.json never produced persisted artifacts beyond what
`scripts/train_final_M2_family.py` consolidated into the m2_family bundle
(total / spread / home_pts / away_pts).

### Other notable ships

| Ship | Artifact | Loader | Wired? |
|------|----------|--------|--------|
| R10_M5_inplay_winprob (endQ1/Q2/Q3) | `inplay_winprob_endq{1,2,3}.lgb` | `src/prediction/inplay_winprob.load_booster` | YES |
| R12_F1_inplay_winprob_v2 (ensemble + anchor) | `inplay_winprob_endq2_v2.lgb` + meta | `inplay_winprob.load_v2_bundle` | YES |
| R13_G2_endq1_winprob_v3 (pregame-anchored) | `inplay_winprob_endq1_v3.lgb` + anchor meta | `inplay_winprob.load_v3_bundle` | YES |
| R10_M14_playtype (prior-season join, pts+fg3m ship) | `data/playtypes.parquet` + retrained pts/fg3m heads | `prop_pergame` `_PLAYTYPE_PRIOR_SEASON_JOIN=True` flag | YES |
| R10_M16_streak_per_stat (fg3m/stl/blk/tov) | streak features computed at predict-time + endQ3 head meta | `src/prediction/streak_features` + `residual_heads.apply_residual_correction` | YES (endQ3 only) |
| R10_M13_tracking_pts_per_stat | no persisted retrain artifact | (probe-only) | **NOT WIRED (no artifact)** |
| R11_BATCH6_M2v81-90 + R11_BATCH7_M2v91-100 | `m2_family/*` (consolidated 20 models) | `predict_game.py` CLI only | NOT WIRED (before R20_M7) -> **WIRED (after)** |
| R12_BATCH6_bagging_oof_fivefold | OOF parquet at `data/cache/pregame_oof.parquet` (used by xstat head training) | indirectly via xstat heads | YES (indirect) |
| R7_A_pregame_residual_heads_per_stat (reb/ast/fg3m/stl/blk/tov) | `pregame_residual_heads/{stat}.lgb` | `pregame_residual_heads.apply_residual_correction` -> called from `predict_pergame` | YES |

## Counts

- **ships_total:** 51
- **ships_with_callable_artifact:** ~40 (probe-only ships excluded)
- **ships_wired_in_prod (before R20_M7):** 39
- **ships_unwired (before R20_M7):** 12 (per-batch m2v probe ships, R10_M13 tracking, and the M2-family consolidated bundle)
- **ships_wired_in_prod (after R20_M7):** 40 (M2-family bundle now reachable from `game_models.predict`)

The 11 v* batch ships and R10_M13 remain "shipped to ledger but unwired"
because they have no consolidated artifact on disk separate from m2_family —
they were merged into the multi5 bundle during the R11 BATCH-7 freeze.

## Top 3 Un-Wired (Pre-R20_M7) by Production Impact

1. **R11 M2-family (multi5 ensemble for total/spread/home_pts/away_pts)** — 20
   trained models on disk, only the standalone `predict_game.py` CLI used them.
   Every other caller (run_daily_slate team-total normalization,
   game_orchestrator, betting_portfolio, api) loaded legacy single-XGB heads.
   **WIRED IN R20_M7.**
2. **R10_M13_tracking_pts_per_stat** — probe shipped (PTS WF 4/4 + mean
   -0.00736) but no retrained PTS artifact was persisted with the tracking
   features baked in. Cannot wire without a retraining step. Flagged for
   follow-up.
3. **R11 individual M2v* threshold/spread variants (O220, O230, AH3, AH7,
   etc.)** — 95 probe shipped but consolidated into m2_family; the
   per-threshold/per-spread classifier surfaces (binary O/U, binary ATS)
   require their own training+wiring round. Flagged for follow-up.

## What R20_M7 Wired

File touched: `src/prediction/game_models.py` (single file).
Function: `predict(...)`.

Added:
- `_try_load_m2_family()` — lazy-load 20 m2_family joblibs + manifest + cols
- `_lookup_season_games_row(...)` — resolve a 74-feature row from
  `data/nba/season_games_*.json` by `game_id` OR `(home_team, away_team,
  game_date)` tuple
- `_predict_m2_family(row)` — equal-weight average across the 5 models per
  target, returns `{total_est, spread_est, home_pts_est, away_pts_est}`
- New optional `game_id` kwarg on `predict(...)` (default None, back-compat)
- Override path: when the m2 ensemble succeeds, `total_est` and `spread_est`
  switch from legacy single-XGB to the multi5 ensemble; the result dict gains
  `home_pts_est`, `away_pts_est`, `ensemble`, `m2_family_used=True` and the
  `confidence` field becomes `"model+m2_family"`.

Untouched:
- `src/dfs/*`, `src/execution/*`, `src/exchanges/*`, `scripts/execute_loop/*`
- `game_models.train()`, `load_models()` — unchanged
- All existing callers' signatures — unchanged (game_id is optional)

## Before/After Evidence

Game id `0022400061` (BOS vs NYK, 2024-10-22):

| Field | Before (legacy single-XGB) | After (M2 multi5 ensemble) | Delta |
|-------|----------------------------|----------------------------|-------|
| `total_est` | 224.0 | 231.0 | +7.0 |
| `spread_est` | 7.9 | 16.6 | +8.7 |
| `home_pts_est` | (absent) | 124.6 | new |
| `away_pts_est` | (absent) | 107.4 | new |
| `confidence` | `"model"` | `"model+m2_family"` | -- |

Saved to `data/cache/probe_R20_M7_before_after.json`.

## Tests

- `tests/test_new_models.py` — 80 passed, 0 failed (existing tests stub
  `game_models.predict`; the new code path is exercised only when an unstubbed
  caller passes a `game_id` or matches a season_games row)
- `tests/test_pergame_live_wiring.py` + `tests/test_prop_pergame.py` —
  22 passed, 0 failed
- `tests/test_R30_W6_audit_refresh.py` — 12 passed, 0 failed (refresh-round
  regression suite covering R20_M7 wire + R21_N1/N5 + R22_O8 + R23_P2)

## R30_W6 refresh — R21-R29 patches per stage

This section documents the post-R20_M7 wire-layer touches and their
current status, verified by `probe_R30_W6_audit_refresh.py`.

### R21_N1 — prop_pergame worktree-fallback resolver

- **File:** `src/prediction/prop_pergame.py`
- **Symbol added:** `_resolve_model_dir()` (lines 62-105)
- **Why:** PTS + AST were the only two stats whose 3-way blend depends on
  multi-file pkl/json artifacts that ARE gitignored. In a worktree
  without these, `load_pergame_model` silently returns 0 learners and
  `predict_pergame` returned None for PTS+AST — but produced values for
  the other 5 stats whose q50 backends are checked into git as JSON.
- **Wire test:** `tests/test_R21_N1_pts_ast_load.py` + new
  `test_R21_N1_resolver_*` in `tests/test_R30_W6_audit_refresh.py`.
- **R30_W6 status:** WIRED. Resolver returns host-repo `data/models/`
  when called from a worktree without local PTS artifacts; all 7 stats
  predict non-None.

### R21_N5 — m2_family per-(game_id, mtime) prediction cache

- **File:** `src/prediction/game_models.py`
- **Symbols added:** `_M2_PRED_CACHE_PATH`, `_m2_family_models_mtime()`,
  `_load_m2_pred_cache()`, `_save_m2_pred_cache()`, `clear_m2_pred_cache()`.
- **Why:** R20_M7 wired the m2_family bundle but the cold path runs 20
  joblib `.predict` calls per game per request. Same (game_id, models_mtime)
  reads return byte-identical values, so caching is safe and saves ~150ms
  per warm call.
- **Wire test:** `test_R21_N5_m2_family_cache_still_present` +
  `test_R21_N5_cache_byte_identical_repeat`.
- **R30_W6 status:** WIRED. Second predict() call on the same game_id
  returns byte-identical total/spread/home_pts/away_pts.

### R22_O8 — injury_availability parquet-first lookup

- **File:** `src/prediction/injury_availability.py`
- **Symbols added:** `_latest_parquet_path()`, `_load_parquet_indices()`.
- **Why:** ESPN JSON snapshot lags behind the NBA-PDF-derived parquet
  written by `scripts/nba_injury_report_scraper.py`. R22_O8 makes the
  parquet authoritative (consulted first); legacy JSON is the fallback.
- **Wire test:** `test_R22_O8_injury_parquet_wire_still_present` +
  `test_R22_O8_injury_wire_returns_zero_for_OUT`.
- **R30_W6 status:** WIRED. Today's parquet shows 126 OUT players; all
  sampled lookups return factor=0.0.

### R23_P2 — inplay_bet_ranker injury-kill guard

- **File:** `scripts/inplay_bet_ranker.py`
- **Symbols added:** `_availability_factor()` helper; per-bet kill loop
  with `n_killed_by_injury` telemetry.
- **Why:** Before R23_P2, a player declared inactive 30 min before tip
  would still surface in ranked output because the in-play ranker had no
  injury awareness. Now bets with availability_factor < 1.0 are tracked,
  factor==0.0 bets are dropped, and the killed-list is returned in the
  payload for downstream auditing.
- **Wire test:** `test_R23_P2_inplay_injury_kill_still_present`.
- **R30_W6 status:** WIRED.

### R28_U2 — pace feature reference-mean patch

- **File:** `scripts/patch_R28_U2_pace.py` (data layer, no wire-layer change).
- **Why:** R27_T3 residual-drift triage flagged pace as MAJOR-drifted; R28_U2
  patched the reference computation.
- **R30_W6 status:** N/A for wire audit (this round was data-only); pace
  feature still consumed by m2_family + per-stat heads as before.

### R29_V3 — synergy / sim residual-drift triage

- **File:** `scripts/patch_R29_V3_residual_drift.py` (data layer).
- **Why:** Triaged 35 → 28 MAJOR-drifted features into 3 artifact categories
  (computation_artifact / data_source_drift / window_artifact).
- **R30_W6 status:** N/A for wire audit. No production loaders touched.

## R30_W6 summary table

| Wire / surface | R20_M7 status | R30_W6 status | Test |
|---|---|---|---|
| m2_family multi5 ensemble (total/spread/home/away) | WIRED | WIRED | test_m2_family_predict_all_nonzero |
| 7 per-stat prop heads (pts/reb/ast/fg3m/stl/blk/tov) | WIRED | WIRED | test_per_stat_heads_all_predict_nonzero |
| Pregame residual heads (6 stats) | WIRED | WIRED | (covered by audit table) |
| In-play residual heads (endQ1/Q2/Q3 + xstat) | WIRED | WIRED | test_endq3_residual_heads_loadable_and_callable |
| Inplay winprob v1/v2/v3 | WIRED | WIRED | (covered by audit table) |
| Legacy game heads (blowout/first_half/pace) | WIRED | WIRED | (covered by audit table) |
| R21_N1 worktree resolver | new | WIRED | test_R21_N1_resolver_returns_populated_dir |
| R21_N5 m2_family cache | new | WIRED | test_R21_N5_cache_byte_identical_repeat |
| R22_O8 injury parquet | new | WIRED | test_R22_O8_injury_wire_returns_zero_for_OUT |
| R23_P2 inplay injury kill | new | WIRED | test_R23_P2_inplay_injury_kill_still_present |
| Probe-only ships (binary O/U + ATS + Q1/H1 + tracking_pts) | NO_ARTIFACT | NO_ARTIFACT | (expected — no persisted artifact) |
