# Project State: NBA AI System

## Current Status

**Active Phase**: Phase 2 — Critical Tracker Bug Fixes (REVISED — see audit findings)
**Last Updated**: 2026-03-16
**Milestone**: Fix tracker before training any CV-dependent models; maximize NBA API data in parallel
**Roadmap revised**: 11 → 14 phases; new Phase 3 (NBA API Data Maximization) inserted before ML models

## Completed Work

### Phase 1 — Data Infrastructure ✅ (2026-03-12)
- PostgreSQL schema (9 tables, 2 views): `database/schema.sql`
- `src/data/schedule_context.py` — rest days, back-to-back, travel distance
- `src/data/lineup_data.py` — 5-man lineup splits, on/off, game rotation
- `src/data/nba_stats.py` — opponent features: `fetch_matchup_features(home, away, season)`
- `src/data/db.py` — PostgreSQL connection helper

### Phase 2 — Tracking Improvements ✅ (2026-03-17)
- 02-00: Wave 0 test infrastructure — pytest.ini, conftest.py fixtures, test_phase2.py stubs
- 02-01: Jersey OCR — EasyOCR dual-pass + JerseyVotingBuffer
- 02-02: Tracker integration — `_jersey_buf` per slot, `reset_slot()` on eviction
- 02-03: Referee filtering — NaN sentinel for spatial columns, string label "referee"
- 02-04: Player identity persistence — `player_identity_map` schema + `persist_identity_map()`
- 02-05: `download_batch()` in video_fetcher + `scripts/loop_processor.py`
- 02-07: Clip duration validator (MIN_CLIP_SECONDS=60, sys.exit(2)) + 5 EventDetector unit tests (shot/dribble/pass/none/duration) — REQ-02B/C/D/E validated without video processing

### Phase 3 — ML Models 🟡 (code built + hardened, untrained)
- `src/prediction/win_probability.py` — WinProbModel (XGBoost, **26 features** after zero-variance removal), WinProbabilityModel alias
- `src/prediction/game_prediction.py` — predict_game(), predict_today(), _estimate_total()
- `src/prediction/player_props.py` — predict_props(), train_props(), rolling fallback
- `src/pipeline/model_pipeline.py` — unified train/eval/save pipeline
- `tests/test_phase3.py` — **85 tests**, all passing

### Phase 3 Loop Session — Data Quality Fixes ✅ (2026-03-16)
Ten bugs fixed across the ML data pipeline (Loops 26–40):
- **Loop 26**: evaluate.py `team_imbalance_frames` dead code (impossible condition)
- **Loop 27**: `home_travel_miles` zero-variance feature removed from FEATURE_COLS (26 features)
- **Loop 28**: `fetch_playbyplay` partial-cache bug — stale mid-game PBP frozen forever
- **Loop 29**: `_get_recent_form` gamelog no TTL → 24h TTL added
- **Loop 30**: `_get_last5_wins` iterating over versioned cache dict keys (not rows)
- **Loop 31**: `get_recent_form` avg_rest denominator counted 99-day openers
- **Loop 32**: rest_days not capped in training (cap=10 added to match inference)
- **Loop 33**: Label leakage in `train_props` — target stat in own feature set
- **Loop 34**: Brooklyn Nets abbreviation BRK→BKN in ARENA_COORDS
- **Loop 35**: Random `train_test_split` replaced with chronological split
- **Loop 36**: Traded player TOT row selection — highest-GP row wins
- **Loop 37**: `_get_opp_def_rating` always 113.0 — secondary cache + API fetch
- **Loop 38**: `player_avgs_{season}.json` no TTL → 24h TTL
- **Loop 39**: `_fetch_team_stats` no TTL → 24h TTL (14/26 features were frozen)
- **Loop 40**: `get_season_schedule` no TTL → 24h TTL via `_load_cache(ttl_hours=)`

### Tracking Core ✅
- YOLOv8n + Kalman + Hungarian + HSV re-ID (AdvancedFeetDetector)
- Similar-color re-ID: TeamColorTracker (color_reid.py), k-means k=2
- Ball tracking: Hough circles + CSRT + optical flow
- Court rectification: SIFT homography + three-tier EMA drift correction
- Event detection: shot/pass/dribble (EventDetector)
- 60+ ML-ready features per frame

## Key Decisions

- **02-06 Slot layout**: 5+5+1 split (IDs 1-5 green, 6-10 white, 0 referee) — static allocation matching HSV classifier's two output labels; slot count stays 11
- **02-06 Unification block**: deleted unconditionally — no conditional flag needed since 5+5+1 slot layout makes the block invalid; test_no_all_green_unification guards against regression
- **02-07 Clip guard**: sys.exit(2) for short clips (distinct from sys.exit(1) for missing file); MIN_CLIP_SECONDS=60 at module level for testability via import
- **02-07 Test geometry**: EventDetector shot test uses ball moving toward basket_left (x=32) — nearest basket to current ball_pos determines direction, not nearest to shooter position
- **Detector**: YOLOv8n (migrated from Detectron2 2026-03-12)
- **Tracker**: AdvancedFeetDetector (Kalman + Hungarian) — globally optimal assignment
- **Re-ID**: 96-dim HSV histogram (EMA) + k-means color tiebreaker when similar uniforms
- **Jersey OCR**: EasyOCR dual-pass; JerseyVotingBuffer deque(maxlen=3)
- **Referee filtering**: NaN sentinel, not row removal
- **Court rectification**: Three-tier homography — reject/EMA/hard-reset based on SIFT inlier count
- **ML models**: XGBoost (win probability + props); no tracking data required for Phase 3

## Dataset Status

| Metric | Count | Notes |
|---|---|---|
| Games fully processed | 16 | First pass 2026-03-15 |
| Tracking rows | 29,220 | |
| Shots enriched | **0** | Blocked — need `run_clip.py --game-id` per clip |
| Possessions labeled | 124 | |
| Videos in data/videos/ | 16 | Broadcast clips |
| Test suite | **161 tests** | 159 pass, 2 skipped (DB-gated) |

**Data milestones**: 20 games → shot quality model, 50 → possession outcome, 100 → lineup chemistry, 200+ → live win probability LSTM

## Open Issues

| ID | Issue | Status |
|---|---|---|
| ISSUE-005 | HSV re-ID similar uniforms | ✅ Fixed 2026-03-16 — TeamColorTracker |
| ISSUE-006 | Anonymous player IDs | ✅ Fixed 2026-03-16 — jersey OCR pipeline |
| ISSUE-007 | Referees in analytics | ✅ Fixed 2026-03-16 — NaN sentinel |
| ISSUE-008 | No shot clock from video | 🔲 Phase 8 |
| ISSUE-009 | 0 shots enriched | 🔴 Active — Phase 6 (GPU machine required) |
| ISSUE-010 | PostgreSQL not wired | 🔴 Active — Phase 6 plan |
| ISSUE-011 | 0 dribble events (ball_pos/possessor_pos None in 2D) | ✅ Fixed by EventDetector rewrite (validated by 02-07) |
| ISSUE-012 | ALL players labeled 'green' — team color separation broken | ✅ Fixed by 02-06 — removed unification block + 5+5+1 slot layout |
| ISSUE-013 | 0 shot events detected across all 17 clips | 🔴 Phase 2 CRITICAL — event detector threshold or call path broken |
| ISSUE-014 | All 17 "game" clips are 1–21 seconds — not full games | 🔴 Phase 6 — need full 48-min broadcast footage on GPU machine |
| ISSUE-015 | 0/569 players have advanced stats scraped | 🔴 Phase 3 — run player_scraper.py --loop --max 569 |
| ISSUE-016 | Only 3 player gamelogs (LeBron/Curry/Jokic) | 🔴 Phase 3 — scrape all active players |
| ISSUE-017 | No shot chart data (ShotChartDetail not scraped) | 🔴 Phase 3 — blocks NBA API shot quality model |
| ISSUE-018 | No play-by-play for 1,220+ games | 🔴 Phase 3 — blocks possession outcome model and LSTM |

## Data Audit Findings (2026-03-16)

Critical findings from full data audit that change the build order:

1. **All CV tracking data is suspect** — team color classification assigns all 10 players to 'green', meaning team_spacing, nearest_opponent, paint_count_opp, and all team-vs-team metrics are computed incorrectly for all 29,220 rows.
2. **0 shots/dribbles detected** — EventDetector never fires across all 17 clips. Root cause: likely ball_pos/possessor_pos None in 2D path.
3. **Clips are 1–21 seconds, not full games** — current data/games/ clips are test/calibration clips. Shot quality and possession outcome models need full 48-min broadcast footage.
4. **NBA API shot charts are a massive unlocked resource** — ShotChartDetail endpoint provides 50,000+ shots with court coordinates, made/missed, shot type, game context. This unblocks shot quality model without any CV data.
5. **Advanced stats completely unscraped** — player_scraper.py exists but has never run for advanced/scoring/misc tiers. 0/569 players have usg%, TS%, off_rtg, etc.

## Next Actions (Priority Order)

1. **Phase 2**: Fix team color bug (ISSUE-012) and event detector (ISSUE-013) — these invalidate all current tracking data
2. **Phase 3**: Run `python src/data/player_scraper.py --loop --max 569` — no video, pure NBA API, unlocks all player prop models
3. **Phase 3**: Scrape ShotChartDetail for all active players × 3 seasons — unlocks shot quality model without CV
4. **Phase 4**: Train win probability (`python src/prediction/win_probability.py --train`) — already ready
5. **Phase 6**: On GPU machine — process 20+ full broadcast games with `--game-id` flags

## Technology Stack

- Python 3.9, PyTorch 2.0.1 + CUDA 11.8
- YOLOv8n (ultralytics), OpenCV, NumPy, Pandas, EasyOCR
- nba_api, XGBoost, scikit-learn, scipy
- PostgreSQL (schema ready, writes TBD)
- Conda env: basketball_ai
