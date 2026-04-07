# Project State: NBA AI System

## Current Status

**Active Phase**: Pre-F — Full Game Collection (Phase G active)
**Last Updated**: 2026-04-07 (Session 31)
**Test suite**: 1040 passing, 2 skipped
**Last Fixed**: ISSUE-065 ball detector bypass + ISSUE-066 team_abbrev fallback (2026-04-07)
**CV games**: 5 clean / 20 target (Phase F gate)
**Season 2025-26**: 0 / 50 games processed

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
| Play-by-play | 3,102 files | ✅ ~84% complete (3,102/3,685) — ISSUE-018 closed |
| Boxscores | 13 games | |
| Lineup on/off splits | 0 | No CLI in lineup_data.py — needs entry point before bulk scrape |
| Coverage score | 0% avg | coverage_score field unpopulated in scraper_coverage.json |
| Win prob model | ✅ Retrained | 67.7% val acc, sklearn 1.7.2, ISSUE-016 closed |

---

## Open Issues

| ID | Issue | Status |
|---|---|---|
| ISSUE-054 | Shot overcounting 2-3x | Code-fixed, unvalidated — needs batch run |
| ISSUE-065 | Ball detector bypass | ✅ Fixed 2026-04-07 |
| ISSUE-066 | team_abbrev fallback | ✅ Fixed 2026-04-07 |
| — | CV features not wired into ML models | Open — core moat unused |
| — | Possession simulator unbuilt | Blocked on 20 clean games |
| — | Gamelog 2023-24 stalled ~200/600 | Open — props retrain blocked |
| — | Homography low on newer games | Needs reprocess |
| ISSUE-009 | 0 shots enriched — no --game-id runs | 🔴 Phase F |
| ISSUE-010 | PostgreSQL writes not fully wired | 🟡 _pg_write_tracking_rows added; needs DATABASE_URL |
| ISSUE-018 | PBP coverage gaps | 🟡 3,627/3,685 (98.4%) |

---

## Next Actions (Priority Order)

1. **NOW**: Validate shot overcounting fix — run batch on 3 clean games, check shot_log counts (ISSUE-054)
2. **Phase F**: `select_season_games.py` → `batch_season.py` — reach 20 clean games
3. **Phase G**: Season 2025-26 batch — 50 games, 2 per team
4. **Phase 7**: Wire CV spatial features (defender_distance, spacing_index) into xFG v2 and prop models
5. **Phase 8**: Build possession simulator — 7-model chain, 10K Monte Carlo per game
6. **Later**: Gamelog 2023-24 completion (200/600) → props retrain

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
