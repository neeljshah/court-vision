# Project State: NBA AI System

## Current Status

**Active Phase**: Phase 15.5 — Uncertainty Wiring + Alt-Line Ladder (COMPLETE — all 3 plans done)
**Last Updated**: 2026-04-23 (Session 46 — Phase 15.5 Plan 03 complete)
**Phase 15.5 Plan 03 complete (2026-04-23)**:
- `src/prediction/bet_selector.py` — 284 LOC; _conformal_cache + _has_conformal guard, _get_ci() inner helper, ci_lo_80/ci_hi_80/alt_line/alt_line_ev fields in every bet dict
- `scripts/run_daily_slate.py` — --build-ladder CLI flag; Step 8 ladder block loops edge_rows + appends top-EV alt bets before bet_selector (Step 9)
- 2 TestBetSelectorCI xfail tests (ci_fields, alt_bets_json_schema) XPASS — Phase 15.5 requirements complete
- Decision: _get_ci as inner function to access module-level _conformal_cache naturally
- Decision: alt_line/alt_line_ev via row.get() passthrough — None for main-line bets, schema uniformity
**Phase 15.5 Plan 02 complete (2026-04-24)**:
- `src/prediction/alt_line_ladder.py` — 196 LOC; build_alt_line_ladder(), ladder_to_bets(), _compute_ev(), _kelly_fraction()
- 11 alt-line offsets [-2.5..+2.5]; 22 rows per call (over + under per offset), sorted EV desc
- Pinnacle decay: 12%/pt overs, 8%/pt unders from main line; quarter-Kelly capped at 0.02
- 4 xfail tests (test_ladder_offsets, test_ev_computation, test_pinnacle_decay, test_kelly_cap) → all XPASS
- Decision: IQR sigma fit: (hi-lo)/1.349, floor 0.3 — matches POC convention, avoids z-score inversion
- Decision: Do not import alt_line_ev_model in production code — math extracted cleanly
**Phase 14-5a Plan 04 complete (2026-04-24)**:
- `src/prediction/prop_validation.py` — 100 LOC; write_registry(), validate_gap_threshold(), generate_report()
- `data/models/model_registry.json` — v3 schema, all 7 stats, retrain_version=v3_temporal_cv_gridtuned_2026-04
- `data/models/hyperparams_{stat}.json` — 7 files, best GridSearchCV params per stat
- `data/models/props_{stat}.json` — 7 updated model files (best_estimator_ refitted on 2025-26 data)
- pts/reb/ast pass gap threshold (0.034, 0.027, 0.046); fg3m/stl/blk/tov exceed (84-row holdout, single season)
- Decision: document fg3m/stl/blk/tov gap failures as known exception (count-data noise + single-season holdout)
- Decision: Phase 15 bet-selector should filter on needs_retrain=False (pts/reb/ast eligible)
**Phase 14-5a Plan 03 complete (2026-04-23)**:
- `src/prediction/prop_grid_search.py` — 109 LOC; run_grid_search(), REGRESSION_PARAM_GRID, POISSON_PARAM_GRID
- `scripts/retrain_props_temporal.py` — 178 LOC; CLI with --stats/--dry-run/--threshold/--seasons/--exclude; holdout gap reporting
- 5 tests XPASS (3 grid-search + 2 retrain); LR constraint verified (Poisson max 0.05)
- Decision: sort_chronologically separate from make_temporal_split (Plan 02 contract: returns TimeSeriesSplit only)
- Decision: GridSearchCV refit=True returns best_estimator_ refitted on full training set
**Phase 14-5a Plan 02 complete (2026-04-23)**:
- `src/prediction/prop_cv_split.py` — 123 LOC; make_temporal_split, sort_chronologically, filter_excluded_players, _objective_for_stat
- `src/prediction/player_props.py` — train_props() wired: exclude_player_ids param, TimeSeriesSplit holdout, _objective_for_stat dispatch
- 6 xfail tests now XPASS (4 temporal CV + 2 player exclusion)
- Decision: make_temporal_split returns TimeSeriesSplit only (not tuple) to match Plan 01 test contract
**Phase 14-5a Plan 01 complete (2026-04-23)**:
- `tests/test_prop_temporal_cv.py` — 4 xfail stubs (temporal split, no leakage, rolling features, Poisson objective)
- `tests/test_player_exclusion.py` — 2 xfail stubs (exclusion honored, empty-list noop)
- `tests/test_prop_grid_search.py` — 3 tests (best_params, holdout gap <0.08, Poisson grid tighter)
- `tests/test_model_registry.py` — 3 tests (holdout fields, all 7 stats, needs_retrain flag logic)
- `tests/test_prop_retrain.py` — 2 xfail stubs (produces model files, updates registry)
- `scripts/validate_holdout_gap.py` — CLI gate: exits 1 when gap > threshold (real registry: 6/7 stats failing)
**Test suite**: 960+ passing, 93 skip (excl PG tests)
**CV games**: 17 with usable tracking data; pod run deferred to Phase 20

**Strategy**: Finish the serving/betting loop on free-tier data (nba_api + ESPN + The Odds API) before spending on CV ingest. Goal: hands-off "inject data → bets out". CV features injected later as model upgrade, not blocker.

**Next up**: Phase 15 — bet selector middleware (`src/prediction/bet_selector.py`, `config/betting.yaml`)
**Phase 14-5a COMPLETE** — All 4 plans done. Registry populated, validation pipeline live.

**Full plan**: `.planning/LIVE_BETTING_PLAN.md` (authoritative for Phases 14-20).

**Phase 14 complete (2026-04-23)**:
- `data/models/prop_residuals.json` — 152,845 rows, 21,835/stat (2023-24 + 2024-25 gamelogs)
- `data/models/calibration_{pts,reb,ast,fg3m,stl,blk,tov}.joblib` — 7 isotonic calibration models
- `data/models/prop_corr_matrix.json` — 7×7 symmetric correlation matrix (pts-tov corr=0.80, reb-blk=0.61)
- `scripts/build_historical_residuals.py` — bootstrap script (idempotent, --append flag)
- `scripts/record_slate_results.py` — T+1 live recorder (fetches box scores, resolves bet_log)
- `scripts/fit_prop_calibration.py` — now has --all-stats / --stat CLI flags

**Known blockers**:
1. No bet-selector middleware → slate emits edges but no "bets to place" list
2. No scheduler → manual runs only

---

## Completed Work

### Phase 1 — Data Infrastructure ✅ (2026-03-12)
- PostgreSQL schema (9 tables, 2 views): `database/schema.sql`
- `src/data/schedule_context.py` — rest days, back-to-back, travel distance
- `src/data/lineup_data.py` — 5-man lineup splits, on/off, game rotation
- `src/data/nba_stats.py` — opponent features
- `src/data/db.py` — PostgreSQL connection helper

### Phase 2 — Tracker Bug Fixes ✅ (2026-03-17)
- Dynamic KMeans team color separation — warm-up 30 frames, recalibrate every 150
- Ball position fallback using possessor 2D coords — EventDetector now fires
- Frozen player eviction — _freeze_age after 20 consecutive frozen frames
- Mean HSV replaces per-crop KMeans — 2fps → ~15fps
- SIFT_INTERVAL=15, SIFT_SCALE=0.5 downscale applied
- 431 tests passing (installed fastapi, python-dotenv, deep-sort-realtime)
- test_tracker.py `__name__ == "__main__"` guard fixed

### Phase 2.5 — CV Tracker Quality Upgrades 🟡 (in progress)
- 025-01 ✅ Broadcast detection mode: `broadcast_mode=True` in config, conf_threshold=0.35 in AdvancedFeetDetector, `count_detections_on_frame()` diagnostic helper
- 025-03 ✅ Test suite: 14 tests for broadcast detection + 3-pass jersey OCR, synthetic images, all green
- 025-04 ✅ `src/tracking/court_detector.py` — detect_court_homography() per-clip M1 from broadcast frames
- 025-05 ✅ unified_pipeline._build_court() wired with per-clip detection + Rectify1.npy fallback (ISSUE-017 closed)
- 025-06 ✅ tests/test_court_detector.py — 7 synthetic tests, all passing

### Phase 5 — External Factors 🟡 (in progress, 2026-03-17)
- `src/data/ref_tracker.py` ✅ — referee tendencies (fouls/game, home win%, pace), `data/nba/ref_tendencies.json` cache
- `src/data/line_monitor.py` ✅ — The Odds API wrapper, sharp signal (opening vs closing), `data/nba/lines_cache.json`
- `src/data/injury_monitor.py` ✅ — ESPN injury report (built prior session), InjuryMonitor class wired into props
- `src/pipeline/unified_pipeline.py` ✅ — PostgreSQL writes added (`_pg_write_tracking_rows`), `game_id` param wired
- `tests/test_phase5.py` ✅ — 18 tests (3 injury, 6 ref, 6 lines, 3 pg_write), 0 failures
- **Pending:** `ref_tracker` real data scrape (needs nba_api officials endpoint), `ODDS_API_KEY` setup for live lines

### Phase 3 — NBA API Data Maximization 🟡 (in progress)
- All 569 players have advanced stats (usg%, TS%, off_rtg, def_rtg, etc.) ✅
- 568/569 player gamelogs scraped ✅ (ISSUE-020 closed — 99.8% done)
- Overall coverage score: 98% avg
- ShotChartDetail: scraper built (`src/data/shot_chart_scraper.py`) — ready to run (ISSUE-019)
- Play-by-play: scraper built (`src/data/pbp_scraper.py`) — ready to run (ISSUE-018)

### ML Models — Trained
- `src/prediction/win_probability.py` — WinProbModel (XGBoost, 27 features, val acc 67.7%)
  - ✅ Retrained 2026-03-17 with sklearn 1.7.2 (ISSUE-016 closed)
- `src/prediction/game_prediction.py` — predict_game(), predict_today()
- `src/prediction/player_props.py` — 7 prop models trained 2026-03-17 ✅
  - PTS MAE=0.32 R²=0.994, REB MAE=0.11 R²=0.995, AST MAE=0.09 R²=0.993
  - FG3M MAE=0.09 R²=0.975, STL MAE=0.07 R²=0.928, BLK MAE=0.05 R²=0.958, TOV MAE=0.08 R²=0.977
- `src/pipeline/model_pipeline.py` — unified train/eval/save

---

## Dataset Status (2026-03-17)

### CV Tracking Data
| Metric | Count | Notes |
|---|---|---|
| Game clips processed | 17 | Short clips, not full games |
| Tracking rows | 29,220 | Team separation now working |
| Shots detected | 17 | EventDetector fixed |
| Passes detected | 14 | |
| Possessions labeled | 124 | result=NaN — no --game-id runs |
| Shots with outcomes | 0 | ISSUE-009 — no --game-id runs yet |

### NBA API Data
| Metric | Count | Notes |
|---|---|---|
| Season games (3 seasons) | 3,675+ | |
| Team stats | 30 × 3 seasons | All advanced metrics |
| Player advanced stats | 569/569 | ✅ Complete |
| Player gamelogs | 568/569 | ✅ ISSUE-020 closed |
| Shot charts | 1,707 files | 2022-23: 569/569 ✅, 2023-24: 569/569 ✅, 2024-25: 569/569 ✅ — COMPLETE |
| Play-by-play | 31 game IDs cached | 76/91 video game IDs missing; data/pbp_missing.txt written |
| Boxscores | 13 games | |
| Lineup on/off splits | 0 | ✅ CLI added: python -m src.data.lineup_data --season 2024-25 --bulk |
| Coverage score | 31.6% | ✅ data/nba/scraper_coverage.json written (gamelog=92%, pbp=2.5%, shotchart=0%) |
| Win prob model | ✅ Retrained | 67.7% val acc, sklearn 1.7.2, ISSUE-016 closed |

---

## Open Issues

| ID | Issue | Status |
|---|---|---|
| ISSUE-054 | Shot overcounting 2-3x | ✅ Validated 2026-04-15 — 3 tests in test_shot_dedup.py pass |
| ISSUE-065 | Ball detector bypass | ✅ Fixed 2026-04-07 |
| ISSUE-066 | team_abbrev fallback | ✅ Fixed 2026-04-07 |
| ISSUE-010 | _pg_write_tracking_rows silent no-op | ✅ Fixed 2026-04-15 — WARN+skip when DATABASE_URL unset |
| ISSUE-009 | 0 shots enriched — no --game-id runs | 🟡 Wiring confirmed; tests added; enricher mocked test passes |
| — | CV features null (defender_distance=0/26) | BLOCKED — see .planning/ISSUE_CV_FEATURES.md |
| — | STL prop R²=0.07 | 🟡 Poisson obj → R²=0.47 (5-fold CV); needs full retrain on pod |
| — | CV registry sparsity | DIAGNOSED — root cause: --game-id not passed; OCR is 100% when used |
| — | Possession simulator | ✅ Built Phase 8 — sim_models.py + possession_simulator.py, 16 tests passing |
| — | Gamelog 2023-24 stalled ~200/600 | Open — props retrain blocked |
| — | Homography low on newer games | 🟡 No metadata.json in dirs; manifest has no confidence field — add to pipeline |
| ISSUE-018 | PBP coverage gaps | 🟡 76/91 video game IDs missing PBP (data/pbp_missing.txt) |

---

## Next Actions (Priority Order)

1. ✅ **Phase 8**: Possession Simulator v1 — COMPLETE (sim_models.py + possession_simulator.py, 16/16 tests, <30s 10K sims)
2. ✅ **Phase 9**: Feedback loop + NLP injury models — code complete, pipeline wired
3. ✅ **Phase 10**: Tier 4-5 models — 15 models built (8 Tier4 + 7 Tier5), FatigueCurveModel wired into FatigueModel, 37 tests pass
4. ✅ **Phase 10.5**: Advanced CV signal extractors — code complete
5. ✅ **Phase 11**: Betting infra — live_models.py (M70-M75), betting_edge.py (BettingEdge/CLVTracker/ArbDetector), 16 tests passing
6. ✅ **Phase 12**: Full Monte Carlo — FoulTrouble/GarbageTime/Q4Usage wired, 7-stat player_distributions, 4/4 tests pass
7. ✅ **Phase 13**: FastAPI backend — 6 new endpoints, in-process TTL cache, 5/5 tests pass (2026-04-14)

8. **FULL SEASON RUN**: RunPod full 2025-26 season → retrain everything → production-ready

## Completed Phases (summary)

| Phase | Completed | Key Output |
|-------|-----------|------------|
| 1 | 2026-03-12 | PostgreSQL schema, schedule context, lineup data |
| 2 | 2026-03-17 | CV tracker: Kalman/Hungarian, HSV team color, 431 tests |
| 2.5 | 2026-03-25 | OSNet 512-dim re-ID, per-clip homography, pose estimation |
| 3 | 2026-03-18 | 221K shots, 98.4% PBP, 3 seasons NBA API data |
| 4 | 2026-03-20 | 23 ML models: win prob, 7 props, xFG v1, DNP, matchup |
| 4.5–4.9 | 2026-03-22 | Betting infra: Kelly, CLV, backtester, paper trading |
| 5 | 2026-03-23 | External factors: injury, refs, line monitor |
| 4.6 | 2026-04-07 | ISSUE-065/066 fixes, spatial gap-fill, team abbrev |

---

## Technology Stack

- Python 3.9, PyTorch 2.0.1 + CUDA 11.8
- YOLOv8n (ultralytics), OpenCV, NumPy, Pandas, EasyOCR
- nba_api, XGBoost, scikit-learn 1.7.2, scipy
- FastAPI, PostgreSQL, Redis (planned Phase 13)
- Next.js + React, D3.js, Recharts (planned Phase 14)
- Claude API claude-sonnet-4-6, tool use (planned Phase 15)
- Conda env: basketball_ai

---

## Key Architecture Decisions

- **Detector**: YOLOv8n → upgrade to YOLOv8x in Phase 2.5
- **Tracker**: AdvancedFeetDetector → migrate to ByteTrack in Phase 2.5
- **Re-ID**: 96-dim HSV histogram → OSNet deep re-ID in Phase 2.5
- **Position**: Bbox bottom edge → YOLOv8-pose ankle keypoints in Phase 2.5
- **Court coords**: pano_enhanced M1 → per-clip homography in Phase 2.5
- **ML models**: XGBoost base, LSTM for live win prob (Phase 16)
- **Simulator**: 7-model possession chain, 10,000 Monte Carlo simulations
- **AI chat**: Claude API + 10 tools + render_chart inline in frontend
- **Frontend**: Next.js, split chat + canvas panel, 10 chart types
