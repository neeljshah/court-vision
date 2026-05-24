# Changelog

All notable changes to this project will be documented in this file.

Format: [Keep a Changelog](https://keepachangelog.com/en/1.0.0/)

## [Unreleased]

## [0.14.0] - 2026-05-24 — loop 5 prediction stack

### Added
- **Quantile heads (q10/q50/q90)** for every prop stat. q50 is the *primary* predictor for REB/FG3M/STL/BLK/TOV — beat squared-error/Huber blends on MAE because sportsbook O/U lines score against the median, not the mean. Source: `src/prediction/prop_quantiles.py`.
- **Quantile interval calibration** (`src/prediction/quantile_calibration.py`) — per-stat scale factor brings q10/q90 to 80% empirical coverage. Asymmetric branch for FG3M/STL/BLK/TOV where q10 floors at 0. Calibration weights at `data/models/quantile_calibration.json`.
- **Multitask MLP** for AST + STL (`src/prediction/multitask_mlp.py`) — 7-output MLPRegressor on shared representation. Both stats 4/4 walk-forward folds + production single-split positive.
- **Production CLIs**:
  - `scripts/predict_player.py` — single player vs single opponent, 7 stats with q10..q90 intervals + L5/L10 baselines + bet recommendation when |edge| > 0.5.
  - `scripts/predict_slate.py` — every rostered player in every game on a given date, sorted by predicted PTS. Works around `scoreboardv2` nba_api bug (raw HTTP + manual GameHeader parsing).
  - `scripts/compare_to_lines.py` — paste sportsbook lines CSV, get ranked EV + Kelly stakes using calibrated quantile probabilities.
- **Backtest harness**: `scripts/betting_backtest.py` (vs L5 line proxy) and `scripts/betting_backtest_smart_line.py` (vs L5 × opp_def × home_adj). Model wins 25-32% ROI on selective bets vs smart line. Real sportsbook closes are sharper; realistic expected ROI is ~10-20% post-vig.
- **5-way NNLS WinProb stack** (XGB + LGB + LR + 5-seed MLP + GaussianNB) replacing single XGBClassifier. NNLS weights interpretable per-fold.
- Walk-forward harnesses (`scripts/prop_pergame_walk_forward.py`) — every shipped change must clear 4/4 WF folds AND production single-split MAE strictly down.
- Dormant infra: synergy/hustle parquets, prior-season tracking, officials crew features, advanced boxscore v3, rest/travel parquet. All wired and tested; none shipped to production because walk-forward regressed.
- `PREDICTIONS_QUICKSTART.md` — top-level quickstart for the prediction CLIs.

### Changed
- **Loss surfaces, not features.** When additive features saturated (5+ failed wire-ins, see cycles 13-15), the wall broke on loss-surface changes: log1p label transform for 6 stats, sqrt+Huber for PTS, q50 pinball loss for 5 stats.
- **2-season default** for WinProb (cycle 19) — beats 3+ seasons; data recency > data volume.
- Honest holdout post-leak-fix (cycles 3 + 10 + 25 leak audits):
  - PTS  MAE 4.6442 → **4.6210** (−0.50%)
  - REB  MAE 1.9180 → **1.9023** (−0.82%)
  - AST  MAE 1.3735 → **1.3559** (−1.28%)
  - FG3M MAE 0.9205 → **0.8943** (−2.85%)
  - STL  MAE 0.7435 → **0.7153** (−3.79%)
  - BLK  MAE 0.5241 → **0.4398** (**−16.08%** — biggest single-stat win of the loop)
  - TOV  MAE 0.9089 → **0.8932** (−1.73%)
- WinProb leaked → honest: 0.7250 → 0.717 single-split / 0.7176 → 0.7094 walk-forward.

### Fixed
- WinProb primary + secondary leaks (cycles 3 + 10) — `_sim_features` no longer carry season-final aggregates as features for per-game predictions.
- `scoreboardv2` nba_api bug (`KeyError 'WinProbability'`) — `predict_slate.py` calls the raw HTTP endpoint and parses GameHeader manually.

### Lessons captured (`vault/Improvements/`)
- Walk-forward is the only honest gate — six cycles avoided regressions that single-split missed.
- The dual gate (4/4 WF folds positive AND production single-split MAE strictly down) is correct. Cycle 19 Huber-on-log1p had 4/4 WF for FG3M but single-split was wash — correctly rejected. Cycle 23 multitask MLP had 4/4 WF AND single-split positive for AST/STL — shipped.
- Season-level or prior-season features consistently regress walk-forward even when single-split looks fine.
- At the architecture/feature ceiling. Remaining gains are DATA problems (live injury feed, real sportsbook lines, CV defender_distance at scale, lineup projection).

### Measured (cycle-40 production, walk-forward + production single-split)
- 99,818 player-game rows (gamelog_full converter pulled in 4× more rows than the trainer was previously reading).
- Coverage_80 on calibrated intervals: 0.74-0.78 across stats (target 0.80).
- Betting backtest vs smart-line proxy: every stat +15-32% ROI at +0.5 edge threshold.

## [0.13.5] - 2026-04-21

### Added
- Ingest system P1-P6 complete: SQLite work queue, yt-dlp fetcher, parallel processing workers, quality backfill, status dashboard, B2 sync
- `ingest_preflight.sh` + `launch_single_3090_pod.sh` for single-GPU pod runs
- CalibrationLayer: `win_prob()` + `train_win_prob()` methods
- 7 prop models registered (pts/reb/ast/fg3m/blk/tov/stl) with live API serving

### Changed
- `unified_pipeline.py`: fixed max_frames stride bug — `gameplay_frames` (decoded) vs `max_frames` (source units) mismatch caused 60fps games to never stop
- `fetch_games.py`: archive.org fallback (Pass 2.5), android player client for YouTube bot bypass, highlights `min_dur` raised to 1800s, PREFLIGHT retry loop reads `phase_g_processed.txt` at startup to skip already-done game IDs
- `_VRAM_FLUSH_INTERVAL` set to 3000 (was 100) — flushing every 100 frames caused GPU syncs stalling CPU stages ~10×

### Fixed
- H1: memory + connection hygiene for 3090 pod
- H2: cross-filesystem rename + symlink safety
- H3: parallel worker isolation + retry on claim race
- H4: pod preflight script
- H5: final verification + runbook update

### Measured (walk-forward temporal-CV holdout, source `data/models/model_registry.json`)
- Props R²: pts=0.41, reb=0.38, ast=0.36, fg3m=0.29, tov=0.22, stl=0.18, blk=0.16
- CV games ingested: 29 usable (9 CLEAN + 20 PARTIAL) of 75 attempted (target: 80 CLEAN)

### Projected (gated on paper-trading gate ≥50 settled bets — _not yet measured_)
- CLV +14 bps/bet vs Pinnacle Shin-devigged close — backtested edge model
- Realized ROI +3.8% on 1u-Kelly-fractional — dependent on fill prices and book limits
- No live bets placed; paper-trading harness in flight (Phase 3)

[0.14.0]: https://github.com/neeljshah/court-vision/releases/tag/v0.14.0
[0.13.5]: https://github.com/neeljshah/court-vision/releases/tag/v0.13.5
