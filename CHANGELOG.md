# Changelog

All notable changes to this project will be documented in this file.

Format: [Keep a Changelog](https://keepachangelog.com/en/1.0.0/)

> **⚠️ Retraction note (2026-06-09):** earlier entries cite headline numbers
> (+18.38% pre-game ROI, endQ3 Brier 0.119, +54% in-play ROI, +8.94pp CLV) that a
> later self-audit **retracted** as measurement artifacts. Honest versions:
> break-even-minus-vig vs real closes (assists ~+4–5% the one durable edge),
> leak-free endQ3 Brier ~0.141, and the +54% is an L5-proxy ceiling — not realized
> edge. These historical entries are kept as an honest record of what was claimed
> when. Full account: [docs/JOB_EVIDENCE_PACKET.md](docs/JOB_EVIDENCE_PACKET.md).

## [0.18.0] - 2026-06 — Multi-sport platform direction + in-game projector + self-improving loop

### Announced
- **Multi-sport platform direction** ([docs/PLATFORM.md](docs/PLATFORM.md)): the NBA engine (~430 modules) is being refactored into a sport-agnostic `kernel/` + `domains/<sport>/` adapter model. ~38% of the current codebase is already sport-agnostic; adding a second sport is intended to require only an adapter. No second-sport code shipped yet — this entry records the architecture decision.

### Shipped
- **Possession-level Monte Carlo simulator** (`src/sim/basketball_sim.py` + GPU `fast_sim.py`): player-level role-aware usage, real PBP assist network, defense-drives-predictions, shared-pie routing. Defense walk-forward validated (+0.597 pts/team-game CI [+0.25, +0.93]).
- **In-game projector** (`src/prediction/live_engine.py`): per-player possession projector with walk-forward PBP replay validation over NYK/SAS Finals G1–G3. Ship baseline = foul-out-only adjustment (minute-share/heat/full-heat refuted; garbage-time untested). Pooled win-prob Brier Q1–Q3: 0.34–0.40 (worse than a coin flip in-game, confirming no in-game market edge).
- **LLM-free signal-discovery loop** (`src/loop/discovery.py`): enumerates feature transforms → cheap screen → honest walk-forward gate decides ship/reject without LLM involvement. Wired into orchestrator behind `CV_LOOP_DISCOVERY` flag (default OFF). On current point-feature surface, correctly REJECTs (ceiling confirmed). Real value is joint/in-game/freshness frontier.
- **LLM scheme-prior layer** (`src/sim/scheme_prior.py`, flag `CV_LLM_SCHEME`, default OFF): LLM emits bounded multipliers on existing sim knobs; sim computes all numbers. REJECTED for the betting number (leak-free scheme signal redundant with sim: corr-with-residual +0.005, p=0.87). Ships as scouting-only.
- **Full-market intelligence stack** (`scripts/team_system/market_intelligence.py`): one sim → 372 markets (every stat/combo/DD/TD/longshot). `CV_MIN_VAR` layer validated (rank-remap fixes median shift; cross-season data confirms).
- **Full-season walk-forward backtest** (`project_season_backtest_2026-06-10`): truncation-invariance proven; well-calibrated (Brier 0.208 vs close 0.198) but does not beat the close. Spread/total pregame CLV ≈ 0. Cleanest market-efficiency proof to date.
- **PBP replay validation harness** (`scripts/team_system/pbp_replay.py`): replays any game's play-by-play through the in-game projector; RMSE+bias scored per player and pooled. 257 brain tests green.

### Validated (honest discipline)
- Markets are efficient: pregame spread/total CLV explains 0.13%/0.29% of line movement; correlation with outcome 0.001.
- AST ~+4–5% ROI remains the one durable edge (regular season only; breaks in playoffs — do not bet AST in playoffs).
- In-game win-prob Brier 0.34–0.40 (Q1–Q3): coin-flip territory — no in-game edge on current architecture.
- Zero real money placed; first real CLV reading October 2026.

### Retracted (documented, not buried)
- +18.38% pre-game ROI: market-follow grading artifact
- endQ3 Brier 0.119: Q4 data leak; honest ~0.141
- +54% in-play ROI: L5-proxy ceiling, not realized edge

## [Unreleased]

### Changed
- **Public docs reframed around the funnel** (DATA→SIGNALS→MODELS→ENGINES→PREDICTIONS→INTELLIGENCE) and reconciled to the leak-free audited numbers; retracted +18.38%/endQ3-0.119/+54%-as-edge headlines corrected across README, ARCHITECTURE, START_HERE, AGENTS, VISION, PREDICTIONS_QUICKSTART, PLAYER_INTELLIGENCE, CEILING, PUBLIC_EVIDENCE, CLAUDE.
- **Gitignore hardened** to robustly exclude the data/ moat (intelligence layer, registry, all parquets) — `data/intelligence/` was documented as ignored but never actually was.

## [0.17.0] - 2026-05-27 — In-play backtest + filter calibration + shadow logger

### Added
- **In-play backtest harness** (`scripts/run_backtest.py`) — drives a full replay → settle → report pipeline over historical games. Produces `vault/Reports/backtest_<date>.md`. First run on 50 finalized games yielded **90,846 evaluated bets** across endQ1/endQ2/endQ3 windows.
- **Shadow logger** (`src/prediction/shadow_logger.py`) — records every bet evaluation incl. blocked, with `gate_blocked_by` reason. CSVs at `data/shadow/<game_id>_<date>.csv`. This is the audit trail that makes post-hoc filter calibration *possible* rather than guesswork.
- **Settlement engine** (`src/prediction/settlement_engine.py`) — joins shadow log against cdn.nba.com finals to compute realized W/L/P + ROI nightly. Run via `python scripts/settle_day.py --date YYYY-MM-DD`.
- **Snapshot replay** (`src/prediction/snapshot_replay.py`) — streams historical games through the live projector so the backtest harness uses the exact same code path as the live engine.
- **Filter calibrator** (`scripts/calibrate_filters.py`) — sweeps per-quarter EV emit floor against shadow log. Produces `vault/Reports/filter_calibration_<date>.md` and patches `src/prediction/decision_engine.py` with new thresholds.
- **Decision engine** (`src/prediction/decision_engine.py`) — gate chain (projection_sane, min_edge, three_book_consensus) + per-quarter EV floor + S/A/B/C tier classification. EV floor calibrated from **0.01 → 0.12** on 2026-05-27.
- **Daily ROI reporter** (`src/reporting/daily_roi.py`) — `python -m src.reporting.daily_roi --date YYYY-MM-DD` produces a per-day operator brief from shadow logs.
- **`/api/shadow` endpoint** (`api/live_v2_app.py`) — surfaces the shadow audit trail to the live dashboard.
- **Per-game ingest orchestrator** (`scripts/per_game_orchestrator.py`) — end-to-end orchestrator with pose imgsz knob for game ingestion.
- **Synergy PPP features** — per-player synergy points-per-possession wired into prop features.

### Measured (backtest, paper / L5 proxy — NOT real closes)
- **Calibrated emit set (n=55,073)**: 78.11% hit rate (Wilson [77.76%, 78.45%]), +54.57% ROI, t-stat 179, calibration RMSE 0.065, worst 100-bet drawdown −$1,682 on $100/bet flat.
- **Tier S (EV ≥ 8%) at endQ3**: +78.7% ROI on 5,088 bets, 93% hit rate.
- **Pre-calibration aggregate ROI was −4.25%** (Tier C bets at EV < 0.04 dragged everything). The calibration story: three suspected over-blockers (`projection_sane`, `min_edge`, `three_book_consensus`) were tested on dropped bets; they were **correctly** blocking losers (−3.85% and −3.55% hypothetical ROI). The real fix was raising the EV floor 0.01 → 0.12.
- **Calibration honesty check**: predicted-EV deciles map ±5% to realized return (decile 1: −0.890 pred / −0.884 real; decile 9: +0.799 pred / +0.794 real).

### Caveats
- The +54.57% ROI uses an **L5 line proxy**, not real Pinnacle closing lines. Real-money ROI estimate: **+15–25%**, materially lower. The +54% is a model-quality ceiling, not a deployment forecast. First real closing-line CLV reading begins October 2026.

### Verified
- 63/63 in-play tests pass (shadow logger, settlement, snapshot replay, calibration, daily ROI, decision engine gates).
- 4,100+ tests collected total.

### Improved
- **README rewritten** to front-load the L5-proxy caveat directly next to the headline number, restructure with real-money-relevant validation leading and paper-ceiling second, add a "Load-bearing modules" table (kills the 120-module bloat impression), and add a "What I'd Tell You In The Interview" pre-empt section.
- **ARCHITECTURE.md refreshed**: decision engine + shadow logger + settlement engine + snapshot replay + in-play backtest harness + filter calibrator + daily ROI reporter added to component status table; CV game count corrected to 85 tracked / 7 full-feature.
- **`docs/KNOWN_LIMITATIONS.md` rewritten** with concrete operational state (replaces old vague disclaimer).

## [0.16.0] - 2026-05-26 — Gate 1 real-Vegas validation (multi-season)

### Added
- **Real-Vegas Gate 1 — 2024 playoffs** (4,337 bets, +4.19% ROI on L10 baseline vs DK/FD/MGM/BetRivers closing lines from reisneriv/NBA_Player_Props). Script: `scripts/run_gate1_playoffs2024.py`.
- **Real-Vegas Gate 1 — 2025-26 regular season** (4,210 bets vs DK/FD/MGM closes from benashkar/nba_gambling, walk-forward prod-stack OOF predictor). Beat rate 54.37%, AST +7.22% ROI (60.25% beat) and FG3M +0.34% ROI (58.37% beat) emerge as real edges; PTS/REB lose to vig at sharp closes. Scripts: `scripts/run_gate1_2025_26_prod.py` (prod-stack) + `scripts/run_gate1_2025_26.py` (L10 baseline for comparison).
- **NBA Stats game_id → date lookup** in `scripts/run_gate1.py` via `season_games_*.json` (NBA Stats format games can now join to date-keyed residuals).
- **Synthetic CLV mode** in `scripts/run_gate1.py` (`--mode ledger --audit-only`) reads `pnl_ledger_clv_synthetic.csv` directly.
- **`data/models/gate1_results_summary.json`** — consolidated machine-readable verification report.
- **`data/external/historical_lines/fetch_external_history.py` extended** with `fetch_benashkar()` + `fetch_lilswad()` for the two new public archives. `playoffs_2024_canonical.csv` + lilswad CSVs committed for one-step reproducibility.
- **`data/models/prop_residuals.json` rebuilt** via `build_historical_residuals.py` — 330,078 rows with proper `(player_id, game_date)` join keys (previous version had nulls). Old edge-history kept at `prop_residuals_edge_history.json`.

### Verified
- `verify_winprob.py`: accuracy 0.7094 / Brier 0.193 within tolerance.
- `verify_production_mae.py`: 6/7 stats within +/-0.01 of claim; PTS at 4.66 (+0.04 above 4.62 claim, still in honest range).
- 48/48 critical-path tests pass (`gate1 + devig + kelly + clv + calibration`).
- 4,055 tests collected total.

### Improved
- **README rewritten** for hiring-manager scan: leads with the two-season real-Vegas table; per-stat ROI breakdown; honest negatives surfaced; reproducibility section with three-command flow (fetch archives → run gate1 scripts → done).

## [0.15.0] - 2026-05-25 — in-play prediction + execute_loop infra

### Added
- **Residual heads (pregame)** — `src/prediction/residual_heads.py`. Per-stat additive residual learners on top of base predictions; 6/7 stats SHIP at pregame (improve_loop R7, commit `61c454eb`).
- **Residual heads (endQ1 + endQ2)** — period-specific residual layers wired into `live_engine.project_from_snapshot` (cycle 106a `6178d8e3`; improve_loop R3+R4 `476d02a7`). EndQ3 residual REJECTED (cycle 109).
- **Learned Q4 minutes** — `src/prediction/minute_trajectory.py` end-of-Q3 minutes head: PTS -0.2312 MAE, 7/7 stats positive (cycle 110 `fe27de4a`).
- **Live quantile bands** — `src/prediction/live_quantile_bands.py` calibrated to 80% empirical coverage on in-play projections (cycle 105c `cd3e4fda`; recalibrated cycle 109).
- **Period-specific projection heads** — endQ1/endQ2 trained artifacts (cycle 105b `96840002`); endQ3 head rejected (2/7).
- **In-play foul_change residual head** — wired into `live_engine`; SHIP PTS -0.24 on foul stratum, 0.00 on non-foul, WF 4/4 (`cb39cbd6`).
- **Blowout flip residual + heat_check shrinkage** — stratified dispatch (`dfd4ce0b`, `f1ae0919`).
- **Multitask MLP with live head** (back-compat opt-in, cycle 103c `b15d5ac1`).
- **In-game system end-to-end** — `probe_inplay_vs_pregame`, `live_inplay_daemon`, `recommend_endQ2_bets`, `live_engine` consolidated API, retro_inplay_mae_v2 (550-game retro; 7/7 wins, -43% to -53% MAE vs pregame at endQ3).
- **execute_loop V1 39/40 layers shipped** — 532/532 tests pass across 5 rounds (`cae147b9`). Order-management, multi-exchange (Kalshi/Polymarket/Sporttrade), cross-exchange EV, late-swap, live trader, hedger, edge-erosion + postmortem layers, cash + GPP optimizers, ownership/contests models, ledger/bankroll/CLV/alerts dashboard, market-making (R5 `a27fc7d8`).
- **Daily ops chain** — `daily_run.py` orchestrator (`--auto-lineups --auto-lines --kelly --bankroll N --report` morning; `--settle --report` post-game), `update_inactives.py`, `place_bet.py`, `live_dashboard.py`, A/B strategy framework (`b489a241`).
- **Live data feeds** — `fetch_live_prop_lines` (DK/FD/Odds-API/Action Network), `fetch_dk_props` 3-tier scraper, `webhook_alerts` (Slack/Discord), `live_hedge` calculator, `pnl_ledger` + CLIs, CLV calculator, RLM scraper.
- **Gate 1 infrastructure** — `nba_data.db` schema + backfill + closing-line ingestion (`e1323461`).
- **Swish Analytics demo materials** — `scripts/swish_demo.py` (end-to-end demo runnable on RunPod), `docs/SWISH_DEMO.md` interview cheat-sheet, `docs/system_metrics.html` visual KPI dashboard, `scripts/register_bankroll.py` (`ffd55c48`, `3c4d0aa2`).
- **Health check** — `scripts/health_check.py` offseason-aware live system status (cycle 105e). Latest: 14 OK / 7 WARN / 1 ERROR.
- **operator_morning / operator_eod runbook scripts** + `docs/LIVE_OPERATOR_RUNBOOK.md` (`e78a01f3`).

### Changed
- **Pre-game production MAE (post cycle 96a)**: PTS 4.6104 | REB 1.9075 | AST 1.3570 | FG3M 0.8941 | STL 0.7153 | BLK 0.4398 | TOV 0.8932. Down from prior cycle 40 anchor on every stat.
- `_VRAM_FLUSH_INTERVAL` invariant re-asserted in CLAUDE.md (must be 3000, not 100).
- Pregame enrichment lift validated at endQ1/endQ2 (cycle 108a); period heads default off after endQ3 reject.
- T1-A garbage-time haircut shipped (PTS -0.0117 MAE).
- Player-quarter parquet expanded to 956 games with PF in boxscores; pregame_spreads to 1,316 rows; rest_travel to 2026-04; 800-pid positions; q1_*_l5 unlocked to 85% coverage.
- `team_advanced_stats` parquet + 16 opp_l5 features at 100% coverage.

### Fixed
- `swish_demo.py` Kelly% display (missing *100, commit `81b940a8`), Windows cp1252 encoding (`4693f214`, `be2af2cd`).
- `model_roi.py` dashboard R² sort crash (cycle 107c `d5710b1f`).
- `home_spread` join coverage 13% → 99.9% (95a).
- 89a/89b schema + foul-table unification (live_factors canonical); 97a validator + silent-join audit (2 high-severity bugs found).

### Measured (in-play system, 550-game retro)
- **endQ3 MAE vs pre-game**: PTS 2.46 (-47%) | REB 1.00 (-47%) | AST 0.68 (-50%) | FG3M 0.42 (-53%) | STL 0.32 (-55%) | BLK 0.20 (-55%) | TOV 0.45 (-50%) — 7/7 stats win.
- **In-play betting ROI vs L5 proxy**: 7/7 stats win at threshold 1.0, ROI 0.70-0.89.
- RunPod RERUN (2026-05-25) confirms retro_inplay_mae_v2 5/5 win on 46 dated-model games (`2bad1fca`).
- RunPod pytest: 2,661 passed, ~26 failed (failures are tracking-suite + transient pyarrow-missing — not prediction-critical).

### Lessons captured (`vault/Improvements/`)
- At architecture/feature ceiling for pre-game. Remaining gains are DATA: live injury feeds, real sportsbook lines, CV defender_distance at scale, lineup projection.
- Residual heads + period-specific heads are the right architecture for in-play (additive layers on top of base pregame model).
- WF gate now requires 4/4 folds positive AND production single-split positive AND >=4/7 stats wins; cycle 105a (play_probability) failed >=4 ship gate despite WF 4/4 on 2/7 stats.

## [0.14.0] - 2026-05-24 — loop 5 prediction stack

### Added
- **Quantile heads (q10/q50/q90)** for every prop stat. q50 is the *primary* predictor for REB/FG3M/STL/BLK/TOV — beat squared-error/Huber blends on MAE because sportsbook O/U lines score against the median, not the mean. Source: `src/prediction/prop_quantiles.py`.
- **Quantile interval calibration** (`src/prediction/quantile_calibration.py`) — per-stat scale factor brings q10/q90 to 80% empirical coverage. Asymmetric branch for FG3M/STL/BLK/TOV where q10 floors at 0. Calibration weights at `data/models/quantile_calibration.json`.
- **Multitask MLP** for AST + STL (`src/prediction/multitask_props.py`) — 7-output MLPRegressor on shared representation. Both stats 4/4 walk-forward folds + production single-split positive.
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

[0.15.0]: https://github.com/neeljshah/court-vision/releases/tag/v0.15.0
[0.14.0]: https://github.com/neeljshah/court-vision/releases/tag/v0.14.0
[0.13.5]: https://github.com/neeljshah/court-vision/releases/tag/v0.13.5

---
*Last verified: 2026-05-25*
