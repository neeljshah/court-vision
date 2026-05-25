# CourtVision — Current State

> Loaded by Claude on demand. Update this file at session start or when state changes.
> Platform identity: **The Renaissance of Sports** — agentic AI sports intelligence, not a betting tool.

## Session State (2026-05-24)
- Branch: `master` | Tests: 1040 pass, 2 skip. Phase 8-13 suites all green.
- Phase 13.5 done. Validation infra shipped 2026-05-17 (temporal CV, model registry, regression gates, e2e tests, CV benchmark, CI).
- CV games: 17 quality / 29 usable (9 CLEAN + 20 PARTIAL on quality gate) / 75 attempted. Goal: 80 CLEAN.
- Models: 85 .pkl/.json in `data/models/`. 7 prop models registered (pts/reb/ast/fg3m/blk/tov/stl).
- Props MAE (walk-forward, N=99,818): PTS 4.62 (sqrt+Huber), REB 1.90 (LGB-q50), AST 1.36 (multitask MLP), FG3M 0.89 (XGB-q50), TOV 0.89 (XGB-q50), STL 0.72 (XGB-q50), BLK 0.44 (XGB-q50, -16% session win).
- Win prob (5-way NNLS stack): 0.7094 acc / 0.193 Brier on 3-fold walk-forward; 0.717 acc / 0.188 Brier on single-split. xFG: Brier 0.226 (221K shots). Source: `data/models/win_prob_metrics.json`
- Prediction: 73 modules in `src/prediction/`. API: 6 endpoints. Stack fully functional on NBA API data.
- Calibration: CalibrationLayer.win_prob() added. Needs prop_residuals.json to train.

## Gate Status
| Gate | Status | Blocker |
|------|--------|---------|
| Gate 1: CLV vs Pinnacle close (≥50 bets, beat rate ≥55%, ROI ≥3%) | **NOT YET RUN** | Top priority — run this week |
| Gate CV: 80 clean games | In progress (29/80 usable) | RunPod run next |
| Gate G: paper-trading harness | Scaffolded | Needs Gate 1 first |

## Open Issues
1. **Gate 1 not run** — no CLV validation against real closing lines yet. Everything else is theory.
2. `betting_portfolio.kelly_corr` — correlation matrix not populated. Run `--build-residuals` then `--compute-corr`.
3. CV registry sparse (17 quality, 29 usable) — target 80 CLEAN to meaningfully improve R².
4. `ball_valid_pct=0%` on some games: `ball_track_suspended` stays True entire video — investigate after 80-game run.
5. Underprediction bias — all 7 prop models predict below closing line. Needs calibration pass.
6. News ingestion pipe — unbuilt. Missing injury/lineup reaction window edge.

## Recent Fixes Applied
- `unified_pipeline.py`: max_frames stride bug — `gameplay_frames` (decoded) vs `max_frames` (source units) mismatch at 60fps. Fix: `self.max_frames //= _stride` after stride computed.
- `fetch_games.py`: archive.org fallback (Pass 2.5), android player client for YouTube bot bypass, highlights min_dur=1800s, PREFLIGHT retry loop reads `phase_g_processed.txt` at startup.
- Ingest discovery bridge: `scripts/ingest_discover.py` enumerates games (3 seasons) → resolves YouTube URLs (channels + per-game search) → enqueues `queue.db`. Closes the gap where `ingest_fetch.py` had zero `queued` rows. **200 games queued 2026-05-22** (36/38/126 across 2023-24/24-25/25-26); 32 orphan videos reclaimed.
- `ingest_fetch.py --parallel N` for concurrent downloads; `ingest_backfill_quality.py` now reconciles disk tracking output → `queue.db` `processed` (pod's `run_phase_g.py` isn't queue-aware).

## Next Pod Run: RTX 3090 → 80 games
```bash
bash scripts/ingest_preflight.sh && bash scripts/launch_single_3090_pod.sh
```

### Ingest commands
```bash
python -m src.ingest.manifest migrate          # import legacy games to SQLite
python scripts/ingest_fetch.py --count N       # download + verify
python scripts/ingest_process.py --max-games N --parallel K
python scripts/ingest_backfill_quality.py      # score all processed
python scripts/ingest_status.py                # dashboard
python scripts/sync_remote.py --push           # push to B2
python scripts/reset_stale_jobs.py [--hours N] # unstick crashed jobs
```

### Pod settings
PARALLEL=4, OMP=4, BATCH=12, TARGET=90, CUDA_VISIBLE_DEVICES=0
Est: 7-9 hrs | $2.50-4.50 on 3090 (~$0.35-0.50/hr)

### Data sync after run
```bash
scp -P <PORT> root@<IP>:/workspace/nba-ai-system/data/ingest/queue.db data/ingest/
rsync -az -e "ssh -p <PORT>" root@<IP>:/workspace/nba-ai-system/data/tracking/ data/tracking/
rsync -az -e "ssh -p <PORT>" root@<IP>:/workspace/nba-ai-system/data/events/ data/events/
```

## Performance Wins Still On Table
- YOLO prefetch batching: `advanced_tracker.py:898-935` (`_yolo_frame_buf`) wired but inactive. Add `prefetch_yolo(frames)` in `unified_pipeline.py` N=8. Expected: +50% fps. ~30 LOC. MUST quality-diff before merging.
- HSV vectorize in `color_reid.py::classify_dyn` — second-largest hotspot.

## Swish Analytics demo session 2026-05-25 (overnight prep)

### Demo artifacts shipped
- `docs/SWISH_DEMO.md` — interview cheat-sheet (headline numbers, architecture, weaknesses, next-builds)
- `scripts/swish_demo.py` — runnable end-to-end demo (pregame→snapshot→projection→EV→Kelly→settle→CLV); runs cleanly on RunPod
- `docs/system_metrics.html` — visual KPI dashboard (7/7 win, ROI table, pre-game MAE table, bar charts)
- `scripts/register_bankroll.py` — fixes health_check WARN; creates `data/pnl_bankroll.csv`
- `scripts/_results/retro_inplay_mae_v2_RERUN_runpod.md` — independent RunPod re-run confirms 5/5 win (46 games)
- Latest master: `2bad1fca` | both origin/master and origin/bot/live pushed

### RunPod health (2026-05-25)
- health_check.py: **16 OK / 6 WARN / 0 ERROR** (6 WARNs are offseason-normal)
- pytest: 2661 passed, ~26 failed (tracking tests + phase9 dependency failures — not prediction-critical)
- Per-quarter boxscore fetch: ~120/1157 games done (running in background)

### AST opp-context probe (directional, needs WF gate)
- `opp_def_ast_l5` (rolling-5 opp AST allowed) shows 0.17 MAE gap on 130-row RunPod sample
- Model under-predicts AST vs pass-friendly defenses — candidate for next wire-in
- NOT yet WF validated — treat as signal, not shipped improvement

## Loop 5 session 2026-05-24 — in-game system + ops infra

### Production state
- **Pre-game prod MAE (post cycle 96a)**: PTS 4.6104 | REB 1.9075 | AST 1.3570 | FG3M 0.8941 | STL 0.7153 | BLK 0.4398 | TOV 0.8932
- **In-game endQ3 MAE (550-game retro)**: PTS 2.46 | REB 1.00 | AST 0.68 | FG3M 0.42 | STL 0.32 | BLK 0.20 | TOV 0.45 (7/7 stats vs prod pergame, -43% to -53%)
- **In-play betting ROI (vs L5 proxy)**: 7/7 stats win at threshold 1.0, ROI 0.70-0.89

### Shipped this session (~30 commits)
- **Infrastructure**: 89a schema unification, 89b foul table unification (live_factors canonical), 95a home_spread join fix (13%->99.9%), 95c `live_engine` consolidated API, 97a validator + silent-join audit (2 high-severity bugs found), 99e `team_advanced_stats` parquet + 16 opp_l5 features at 100% coverage, `df36c17f` season_games_2025-26 + q1_*_l5 unlocked to 85%
- **Live tools**: 88a-n full live system, 89e `probe_inplay_vs_pregame`, 90f `--rolling-cal` flag, 93e `live_inplay_daemon`, 98d `recommend_endQ2_bets` (halftime betting), `8d40558a` `fetch_live_prop_lines` (DK/FD/Odds-API), `ba548e1c` `webhook_alerts` (Slack/Discord), `e4e5c651` `live_hedge` calculator, `8762cd94` `pnl_ledger` + CLIs, `7ccca701` CLV calculator, `7b4b08e0` RLM scraper, `f8954c2a` live pipeline E2E integration test
- **Model improvements**: 96a T1-A garbage-time haircut (PTS -0.0117 MAE), `cb39cbd6` tier1-2 foul_change residual head wired into `live_engine`
- **Data unlocks**: 90e/92b 800-pid positions, 91a/92c/df36c17f 956-game per-quarter, 91b/93a/96b PF in boxscores, 91c/92a 1316-row pregame_spreads, 91d rest_travel to 2026-04, `24fa09e8` DNP-aware projection set

### Rejected (do NOT re-attempt — empirically saturated)
~20 probes rejected with WF 2/4 single-split-passes pattern: garbage-time v1, b2b veteran (selection bias), foul-rate, REB OREB context, top-decile pull, high-min bidirectional, Q1 pace residual, Q4 foul forecast v1/v2/v3 (heuristic), heat-check shrinkage (heuristic), all 8 retrain attempts of cycles 99-101 (BLK/FG3M/REB/PTS/TOV/AST/STL/multitask with various feature combos)

### Operational status (offseason 2026-05-24)
- All live infra ready, awaiting NBA preseason (Oct 2026) for forward data accumulation
- Live API endpoints verified (DK/FD/Odds-API/Action Network) but no active games
- Daemon launch commands documented in `scripts/_results/*_v1.md` files

### Open in-game frontier (highest leverage for next session)
- Wire blowout_residual + heat_check_residual (cycles 102a/b in flight) following foul_residual SHIPPED pattern
- Multitask MLP with live head (cycle 102c) — only major architecture change left
- Per-position stratified models (cycle 102d) — different approach than flat features
- Foul-out is dominant residual endQ3 error — needs per-row P(play) head not factor
