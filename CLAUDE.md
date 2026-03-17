<!-- AUTO-GENERATED — DO NOT EDIT BELOW THIS LINE -->

## Resume From Here — Last Updated: 2026-03-16 22:35

### Pick Up Where We Left Off
1. Run `python src/prediction/win_probability.py --train` — immediate win
2. Find NBA game IDs for the 16 videos and re-run enrichment
3. Wire PostgreSQL writes into run_clip.py
4. Start Phase 3.5: injury_monitor.py first (highest prediction impact)

---

### This Session — Files Changed
- `C:/Users/neelj/nba-ai-system/.planning/phases/02-tracking-improvements/02-06-PLAN.md`
- `C:/Users/neelj/nba-ai-system/.planning/phases/02-tracking-improvements/02-07-PLAN.md`
- `C:/Users/neelj/nba-ai-system/.planning/phases/02-tracking-improvements/02-08-PLAN.md`
- `C:/Users/neelj/nba-ai-system/.planning/ROADMAP.md`
- `C:/Users/neelj/nba-ai-system/run_clip.py`
- `C:/Users/neelj/nba-ai-system/tests/test_phase2.py`
- `C:/Users/neelj/nba-ai-system/src/tracking/advanced_tracker.py`
- `C:/Users/neelj/nba-ai-system/src/pipeline/unified_pipeline.py`
- `C:/Users/neelj/nba-ai-system/CLAUDE.md`
- `C:/Users/neelj/nba-ai-system/.planning/STATE.md`
- `C:/Users/neelj/nba-ai-system/.planning/phases/02-tracking-improvements/02-07-SUMMARY.md`
- `C:/Users/neelj/nba-ai-system/.planning/phases/02-tracking-improvements/02-06-SUMMARY.md`
- `C:/Users/neelj/nba-ai-system/.planning/REQUIREMENTS.md`

### Open Priority Issues
- 1. 🔴 Win probability / game prediction models — data pipeline now ready, model still TBD
- 2. 🔴 Analytics + tracking dashboards (not built yet)
- 3. 🟡 HSV re-ID upgrades (jersey confusion on similar-colored uniforms)
- 4. 🔴 Real game clip needed — tracker has plateaued on Short4Mosaicing calibration clip; need actual NBA broadcast footage to benchmark further
- 5. 🟢 Pano validation + fallback — fixed 2026-03-12

### Analytics Module Status (src/)
- ✅ `src/analytics/defense_pressure.py`
- ✅ `src/analytics/momentum.py`
- ✅ `src/analytics/shot_quality.py`
- ✅ `src/data/db.py`
- ✅ `src/data/game_matcher.py`
- ✅ `src/data/injury_monitor.py`
- ✅ `src/data/lineup_data.py`
- ✅ `src/data/nba_enricher.py`
- ✅ `src/data/nba_stats.py`
- ✅ `src/data/player_identity.py`
- ✅ `src/data/player_scraper.py`
- ✅ `src/data/prop_validator.py`
- ✅ `src/data/schedule_context.py`
- ✅ `src/data/video_fetcher.py`
- ✅ `src/detection/detection/models/detection_model.py`
- 🔲 `src/detection/detection/tools/classes.py`
- ✅ `src/detection/detection/tools/inference.py`
- ✅ `src/detection/detection/tools/train.py`
- ✅ `src/features/feature_engineering.py`
- 🔲 `src/pipeline/data_loader.py`
- 🔲 `src/pipeline/feature_pipeline.py`
- ✅ `src/pipeline/model_pipeline.py`
- 🔲 `src/pipeline/run_pipeline.py`
- 🔲 `src/pipeline/tracking_pipeline.py`
- ✅ `src/pipeline/unified_pipeline.py`
- ✅ `src/prediction/game_prediction.py`
- ✅ `src/prediction/player_props.py`
- ✅ `src/prediction/win_probability.py`
- ✅ `src/re_id/data/download_data.py`
- ✅ `src/re_id/models/model.py`
- ✅ `src/re_id/module/cbam.py`
- ✅ `src/re_id/module/loss.py`
- ✅ `src/re_id/module/reid.py`
- ✅ `src/re_id/module/transform.py`
- ✅ `src/re_id/tools/inference.py`
- ✅ `src/re_id/tools/train.py`
- ✅ `src/stats_tracker/tracker.py`
- ✅ `src/tracking/advanced_tracker.py`
- ✅ `src/tracking/ball_detect_track.py`
- ✅ `src/tracking/color_reid.py`
- ✅ `src/tracking/evaluate.py`
- ✅ `src/tracking/event_detector.py`
- ✅ `src/tracking/jersey_ocr.py`
- ✅ `src/tracking/player.py`
- ✅ `src/tracking/player_detection.py`
- ✅ `src/tracking/player_identity.py`
- ✅ `src/tracking/rectify_court.py`
- ✅ `src/tracking/tracker_config.py`
- ✅ `src/tracking/utils/plot_tools.py`
- ✅ `src/tracking/video_handler.py`
- 🔲 `src/utils/__init__ .py`
- ✅ `src/utils/bbox_crop.py`
- ✅ `src/utils/frame.py`
- ✅ `src/utils/visualize.py`
- 🔲 `src/visualization/analytics_dashboard.py`
- 🔲 `src/visualization/tracking_dashboard.py`

### Session Log
- Latest: `vault/Sessions/Session-2026-03-16.md`
- Full log: `vault/Sessions/`

<!-- END AUTO-GENERATED -->

# NBA AI Tracking System — Claude Context File

## Resume From Here — Last Updated: 2026-03-16

### Current Phase
**Phase 3 — First ML Models** (in progress)
- ML model code built: `win_probability.py`, `game_prediction.py`, `player_props.py`, `model_pipeline.py` ✅
- Models need to be **trained** — run `python src/prediction/win_probability.py --train`
- Phase 3.5 planned: External Factors Scraper (injury reports, referee tendencies, line movement)

### Open Priority Issues
1. 🔴 **Label existing 16 games** — run each video with `--game-id` flag so NBA API attaches shot outcomes. 0 shots enriched currently. Blocks shot quality model.
2. 🔴 **Connect PostgreSQL** — `db.py` exists but nothing writes to it. Every run overwrites `data/tracking_data.csv`, losing history. Fix before processing more games.
3. 🔴 **Train win probability model** — code is ready. Just run: `python src/prediction/win_probability.py --train`
4. 🔴 **Build external factors scraper** (Phase 3.5) — injury reports, referee assignments, line movement. High prediction impact.
5. 🔴 **Analytics + tracking dashboards** — not built yet (Phase 8)

### CRITICAL: Never Run Videos
**DO NOT run** `run_clip.py`, `loop_processor.py`, `run.py`, `yt-dlp`, or any subprocess that touches `.mp4` files. The computer cannot handle video processing. Tests and import checks only.

---

## What This Project Is — Full Vision

**Goal: Build the world's best NBA analytics and prediction system.**

Combines computer vision player tracking, NBA statistics, external context (injuries, refs, odds), and ML to predict game outcomes, player performance, and identify betting edges.

### Final Product — Three Interfaces
1. **Betting Dashboard** — model predictions vs live sportsbook lines, surface highest-edge bets
2. **Analytics Dashboard** — court heatmaps, win probability charts, spacing, shot quality, lineup splits, ball movement
3. **AI Chat Interface** — Claude API with tool use, ask any basketball question and get data-backed answers

### How The System Works
```
NBA Games (video)
    ↓
CV Tracking Pipeline
    → positions, spacing, possession, shot context, defensive pressure
    ↓
External Context (Phase 3.5)
    → injury status, referee assignments, line movement, weather/travel
    ↓
NBA API Enrichment
    → shot outcomes, possession results, lineups, box scores, schedule
    ↓
ML Models
    → shot quality, possession outcome, player props, win probability
    ↓
Betting Edge Detection
    → model probability vs sportsbook implied probability → flag value bets
    ↓
Web App + AI Chat (Claude API with tool use)
```

---

## Roadmap Status (Revised 2026-03-16 — 14 phases)

| Phase | Status | Summary |
|---|---|---|
| Phase 1 — Data Infrastructure | ✅ Done 2026-03-12 | PostgreSQL schema, schedule context, lineup data, NBA stats |
| Phase 2 — Critical Tracker Bug Fixes | 🔴 Active | Fix team color (all-green bug), event detector (0 shots/dribbles detected across all clips) |
| Phase 3 — NBA API Data Maximization | 🔲 Next (no video needed) | Advanced stats + gamelogs all 569 players, 50K+ shot charts, PBP 1225 games, lineups, refs |
| Phase 4 — First ML Models | 🟡 Code built | Win prob (train now), props (needs Phase 3 data), shot quality from NBA API shot charts |
| Phase 5 — External Factors Scraper | 🔲 | Injury monitor, ref tracker, line movement, news scraper |
| Phase 6 — Full Game Video Processing | 🔲 GPU machine req'd | 20+ full broadcast games, PostgreSQL wired, shots + possessions enriched with game IDs |
| Phase 7 — CV-Enhanced ML Models | 🔲 Needs Phase 6 | Shot quality v2 (+ spatial context), possession outcome, player movement analytics |
| Phase 8 — Automated Processing | 🔲 | Nightly pipeline, dataset versioning, model readiness alerts |
| Phase 9 — Betting Infrastructure | 🔲 | The Odds API, betting_edge.py, CLV backtesting, Kelly criterion |
| Phase 10 — Backend API | 🔲 | FastAPI: 8 endpoints incl. /shot-chart, /player-movement |
| Phase 11 — Frontend | 🔲 | React + Next.js, shot chart hex-bin, movement heatmaps, player profiles |
| Phase 12 — AI Chat | 🔲 | Claude API with 8 tools, natural language shot chart + movement queries |
| Phase 13 — Live Win Probability | 🔲 Needs 200+ full games | LSTM on possession sequences, WebSocket real-time |
| Phase 14 — Infrastructure | 🔲 | Docker, CI/CD, cloud GPU, drift monitoring |

---

## Dataset Status (Audited 2026-03-16)

### CV Tracking Data — CAUTION: All rows suspect until Phase 2 bugs fixed
| Metric | Count | Notes |
|---|---|---|
| Game clips processed | 17 | BUT: 1–21 second clips, not full games |
| Tracking rows | 29,220 | ⚠️ All players labeled 'green' — team separation broken |
| Shots detected | 0 | ⚠️ EventDetector not firing — ISSUE-013 |
| Dribbles detected | 0 | ⚠️ ball_pos None in 2D path — ISSUE-011 |
| Possessions labeled | 124 | result=NaN for all — no outcomes enriched |
| Shots with outcomes | 0 | No --game-id runs yet |

### NBA API Data — Reliable, Ready to Use
| Metric | Count | Notes |
|---|---|---|
| Season games (3 seasons) | 3,675+ | Full game results + team features for win prob |
| Team stats | 30 teams × 3 seasons | off_rtg, def_rtg, net_rtg, pace, eFG%, TS%, TOV% |
| Player base stats | 569 players | pts, reb, ast, min, fg%, 3pt%, ft% ONLY |
| Player advanced stats | 0 / 569 | ⚠️ Scraper never run — usg%, TS%, off_rtg all missing |
| Player gamelogs | 3 players | LeBron, Curry, Jokic only — everyone else missing |
| Shot charts | 0 | ⚠️ ShotChartDetail never scraped — 50K+ shots available |
| Play-by-play | 2 games | 1,223 games never scraped |
| Boxscores | 13 games | Full per-player stats |
| Injury report | 126 players | Current, refreshed 2026-03-16 |
| Pre-game win prob model | ✅ TRAINED | data/models/win_probability.pkl — 2026-03-16 |

### Model Readiness
| Model | Status | Unlocked By |
|---|---|---|
| Win probability (pre-game) | ✅ Trained | NBA API data only — done |
| Player prop models | 🔴 Needs Phase 3 | Need advanced stats + gamelogs for all 569 players |
| Shot quality v1 (NBA API) | 🔴 Needs Phase 3 | Need ShotChartDetail scraping — 50K+ shots available |
| Shot quality v2 (CV-enhanced) | 🔲 Needs Phase 6+7 | Need 200+ enriched CV shots |
| Possession outcome | 🔲 Needs Phase 6+7 | Need 500+ labeled possessions |
| Lineup chemistry | 🔲 Needs Phase 3+7 | NBA API lineups (Phase 3) + CV validation (Phase 7) |
| Live win prob LSTM | 🔲 Needs Phase 13 | Needs 200+ full games |

Data volume milestones: Phase 3 → shot quality v1 + props; Phase 6 (20 full games) → shot quality v2 + possession outcome; Phase 8 (100 games) → lineup chemistry; Phase 13 (200+ games) → live LSTM

---

## Module Status

### Tracking (all ✅)
- ✅ `src/tracking/advanced_tracker.py` — AdvancedFeetDetector (Kalman+Hungarian+ReID)
- ✅ `src/tracking/ball_detect_track.py` — BallDetectTrack (Hough+CSRT+optical flow)
- ✅ `src/tracking/color_reid.py` — TeamColorTracker, similar-color k-means re-ID
- ✅ `src/tracking/event_detector.py` — shot/pass/dribble detection
- ✅ `src/tracking/jersey_ocr.py` — EasyOCR dual-pass, JerseyVotingBuffer
- ✅ `src/tracking/player.py`, `player_detection.py`, `player_identity.py`
- ✅ `src/tracking/rectify_court.py` — SIFT panorama + three-tier homography
- ✅ `src/tracking/tracker_config.py`, `evaluate.py`, `video_handler.py`
- ✅ `src/tracking/utils/plot_tools.py`

### Data / Pipeline
- ✅ `src/data/db.py` — PostgreSQL connection helper
- ✅ `src/data/game_matcher.py`, `lineup_data.py`, `nba_enricher.py`, `nba_stats.py`
- ✅ `src/data/player_scraper.py` — 63-metric player scraper, self-improving loop, coverage tracker
- ✅ `src/data/player_identity.py` — player_identity_map schema + persistence
- ✅ `src/data/schedule_context.py` — rest days, back-to-back, travel distance
- ✅ `src/data/video_fetcher.py` — yt-dlp downloader + download_batch()
- ✅ `src/features/feature_engineering.py` — 60+ ML features
- ✅ `src/pipeline/unified_pipeline.py`, `model_pipeline.py`
- 🔲 `src/pipeline/data_loader.py`, `feature_pipeline.py`, `tracking_pipeline.py`

### Analytics
- ✅ `src/analytics/defense_pressure.py`, `momentum.py`, `shot_quality.py`

### Prediction (code built, untrained)
- ✅ `src/prediction/win_probability.py` — XGBoost, WinProbModel + WinProbabilityModel alias
- ✅ `src/prediction/game_prediction.py` — predict_game(), predict_today()
- ✅ `src/prediction/player_props.py` — predict_props(), train_props()
- 🔲 `src/prediction/game_prediction.py` — needs trained model to run
- 🔲 `src/data/injury_monitor.py` — Phase 3.5
- 🔲 `src/data/ref_tracker.py` — Phase 3.5
- 🔲 `src/data/line_monitor.py` — Phase 3.5
- 🔲 `src/analytics/betting_edge.py` — Phase 6

### Visualization / Frontend
- 🔲 `src/visualization/analytics_dashboard.py`, `tracking_dashboard.py`
- 🔲 `api/`, `frontend/` — Phases 7–8

---

## Architecture

```
Video Input (.mp4)
    ↓
Court Rectification (SIFT + homography → resources/Rectify1.npy)
    ↓
AdvancedFeetDetector (src/tracking/advanced_tracker.py)
  - YOLOv8n → person bboxes
  - HSV + k-means color → team classification (similar-color aware)
  - Kalman filter per player slot
  - Hungarian assignment (IoU + appearance cost)
  - Jersey OCR (EasyOCR) → named player identity
  - Appearance re-ID gallery (TTL=300 frames)
    ↓
BallDetectTrack (Hough circles + CSRT + possession IoU)
    ↓
EventDetector (shot / pass / dribble)
    ↓
Feature Engineering (60+ spatial + temporal features)
    ↓
Analytics (shot quality, defensive pressure, momentum)
    ↓
NBA API Enrichment (shot outcomes, score context, lineup)
    ↓
data/tracking_data.csv → PostgreSQL (schema ready, writes TBD)
```

---

## Key Technical Details

### AdvancedFeetDetector (src/tracking/advanced_tracker.py)
- **Kalman filter**: 6D state [cx, cy, vx, vy, w, h]
- **Hungarian algorithm**: globally optimal assignment via scipy
- **Cost matrix**: (1-IoU)×0.75 + appearance_distance×0.25; weights shift +0.10 when teams have similar uniform colors
- **Appearance embeddings**: 96-dim L1-normalised HSV histogram (EMA updated)
- **Similar-color handling**: `TeamColorTracker` (color_reid.py) — k-means k=2 per detection; jersey number tiebreaker when hue centroids within 20 units
- **Gallery TTL**: 300 frames; MAX_LOST=90

### Court Rectification (src/tracking/rectify_court.py)
- SIFT panorama stitching; three-tier homography: reject <8 inliers, EMA blend 8–39, hard-reset ≥40
- Court-line drift check every 30 frames (`_check_court_drift`)
- Homography saved to `resources/Rectify1.npy`

### Win Probability Model (src/prediction/win_probability.py)
- XGBoost classifier, 27 features (team ratings, pace, rest, travel, recent form)
- `WinProbModel` is the class; `WinProbabilityModel` is an alias
- Training: `python src/prediction/win_probability.py --train` (3 seasons, NBA API only)
- Backtesting: `--backtest` (walk-forward, CLV proxy metric)

### External Factors (Phase 3.5 — not yet built)
- Injury monitor → poll NBA official report + Rotowire every 30 min
- Ref tracker → historical tendencies (pace, foul rate, home win%) + daily assignment
- Line monitor → The Odds API, opening vs closing line, sharp money signal

### Data Schema
```python
tracking_data = {
    "game_id": str,
    "timestamp": float,        # seconds from video start
    "frame": int,
    "player_id": int,          # 0-9 players, 10 referee
    "team_id": int,            # 0=team_a, 1=team_b, 2=referee
    "x_position": float,       # 2D court coordinates
    "y_position": float,
    "speed": float,
    "acceleration": float,
    "ball_possession": bool,
    "event": str,              # "dribble","pass","shot","none"
    "jersey_number": int,      # from OCR, -1 if unknown
    "player_name": str,        # from NBA API roster lookup
}
```

---

## How To Run

```bash
conda activate basketball_ai
cd C:/Users/neelj/nba-ai-system

# Tests only (NO VIDEO PROCESSING)
python -m pytest tests/ -q

# Train win probability model (safe — no video)
python src/prediction/win_probability.py --train

# Predict a game (safe — no video, needs trained model)
python src/prediction/game_prediction.py --predict GSW BOS

# Check dataset status
python -m pytest tests/ -v
```

**Never run**: `run.py`, `run_clip.py`, `scripts/loop_processor.py`

---

## Environment

- Python 3.9, conda env: `basketball_ai`
- PyTorch 2.0.1 + CUDA 11.8 + cuDNN 8.9
- YOLOv8n (ultralytics), OpenCV, NumPy, Pandas
- nba_api, XGBoost, scikit-learn, scipy, EasyOCR
- PostgreSQL (schema ready at `database/schema.sql`)

---

## Platform Engineer Protocols

### 1. Session Start — Project Pulse
```
• Architecture:  <3-word summary of active subsystem>
• Branch:        <git branch>
• Last Modified: <3 most recently touched files>
```

### 2. Response Navigation — Breadcrumb Format
```
[Module > Submodule > filename.py]
```

### 3. Token Efficiency Rules
- Use `# ... existing code ...` for unchanged logic in snippets
- Never re-read large data directories unless asked
- Strip doc comments from code blocks unless the docstring itself is being edited

### 4. Autonomous Improvement Protocol
When asked to improve the system:
1. Read `CLAUDE.md` Open Priority Issues
2. Read `tests/` — find failing or missing tests
3. Implement fix (code changes only — no video runs)
4. Run `pytest tests/` to confirm
5. Update CLAUDE.md and STATE.md

---

## Code Rules

- Python 3.9, modular functions, max 300 lines per file
- All functions need docstrings + type hints
- Save model outputs to `data/` as CSV or JSON
- Log improvements in `vault/Improvements/Tracker Improvements Log.md`
- No background agents that spawn video processing subprocesses

---

## Known Issues

| ID | Issue | Status |
|---|---|---|
| ISSUE-001 | Ball detection on fast shots | ✅ Fixed 2026-03-12 |
| ISSUE-002 | Team color classification in poor lighting | ✅ Fixed 2026-03-12 |
| ISSUE-003 | Player re-ID when leaving/re-entering frame | ✅ Fixed 2026-03-12 |
| ISSUE-004 | Homography drift on long videos | ✅ Fixed 2026-03-12 |
| ISSUE-005 | HSV re-ID on similar-colored uniforms | ✅ Fixed 2026-03-16 |
| ISSUE-006 | Anonymous player IDs (no jersey OCR) | ✅ Fixed 2026-03-16 |
| ISSUE-007 | Referees in analytics calculations | ✅ Fixed 2026-03-16 |
| ISSUE-008 | No shot clock from video | 🔲 Phase 5 |
| ISSUE-009 | 0 shots enriched — no --game-id runs yet | 🔴 Active |
| ISSUE-010 | PostgreSQL not wired — losing tracking history | 🔴 Active |
| ISSUE-011 | 0 dribble events — event_detector ball_pos/possessor_pos likely None in 2D | ✅ Fixed by EventDetector rewrite (validated by 02-07) |
| ISSUE-012 | autonomous_loop fix suggestions were stale (hardcoded 0.5→0.4) | ✅ Fixed 2026-03-16 |

---

## Files To Know

| File | Purpose |
|---|---|
| `CLAUDE.md` | This file — project context for Claude |
| `ROADMAP.md` | Full 11-phase build plan |
| `.planning/STATE.md` | Current sprint state, dataset counts |
| `src/tracking/advanced_tracker.py` | AdvancedFeetDetector — main tracker |
| `src/tracking/color_reid.py` | TeamColorTracker — similar-color re-ID |
| `src/tracking/jersey_ocr.py` | EasyOCR jersey number reader |
| `src/pipeline/unified_pipeline.py` | Tracking → possession → spatial metrics → CSV |
| `src/data/nba_enricher.py` | NBA API enrichment (shot labels, outcomes) |
| `src/data/db.py` | PostgreSQL connection helper |
| `src/prediction/win_probability.py` | Pre-game win prob (XGBoost) |
| `src/prediction/player_props.py` | Player prop projections |
| `src/features/feature_engineering.py` | 60+ ML features |
| `src/analytics/shot_quality.py` | Shot quality score (0–1) |
| `database/schema.sql` | PostgreSQL schema (9 tables, 2 views) |
| `tests/test_phase2.py` | Phase 2 tracking tests |
| `tests/test_phase3.py` | Phase 3 ML model tests |
| `data/videos/` | 16 broadcast clips downloaded |
| `resources/Rectify1.npy` | Precomputed homography |
| `vault/` | Obsidian knowledge vault |

---

## Knowledge Debt

> Complex decisions and bug fixes. Use `[[Wikilinks]]`. Newest first.

### 2026-03-16 — player_scraper.py: 63-metric self-improving player data loop
- **Built:** [[player_scraper]] `src/data/player_scraper.py`
- **Tiers:** Base (25 cols), Advanced (16: usg_pct/ts_pct/off_rtg/def_rtg/net_rtg/pie/ast_pct/reb_pct/efg_pct...), Scoring (14: pct_pts_paint/mid_range/3pt/ft...), Misc (10: pts_off_tov/pts_paint/pts_fb...)
- **Tier 2 per-player:** full gamelog (24 cols: all box score + plus_minus) + last-5/10/15/20 splits via PlayerDashboardByLastNGames
- **Self-improving loop:** `run_improvement_loop(season, max_players)` — detects stale/missing metric groups, fills gaps in priority order (Advanced → Scoring → Misc → Base → GameLog → Splits), logs delta to vault
- **Coverage tracking:** `data/nba/scraper_coverage.json` — per-player score 0–1, updated each run
- **Profile lookup:** `get_player_profile("LeBron James")` → flat dict with all metrics + gamelog + splits + l5 computed stats
- **CLI:** `python src/data/player_scraper.py --loop --max 100` or `--player "Jayson Tatum"`
- **TTLs:** batch=24h, gamelog=6h, splits=12h — respects NBA API rate limits (0.8s delay)
- **Related:** [[player_props]], [[nba_stats]], [[win_probability]]

### 2026-03-16 — Phase 3 ML models built (untrained)
- **Built:** [[win_probability]] `WinProbModel` (XGBoost, 27 features), [[game_prediction]] `predict_game()`, [[player_props]] `predict_props()` with rolling fallback, [[model_pipeline]] unified train/eval/save pipeline.
- **Tests:** `tests/test_phase3.py` — 21 tests passing, isolated with monkeypatch, no NBA API calls needed.
- **Key alias:** `WinProbabilityModel = WinProbModel` added for backward compat.
- **Next:** Run `--train` to produce `data/models/win_probability.pkl`.
- **Related:** [[model_pipeline]], [[player_props]], [[game_prediction]]

### 2026-03-16 — Phase 3.5 planned: External Factors Scraper
- **Decision:** Add external context layer between NBA API enrichment and ML models.
- **Why:** Injury status, referee assignments, and line movement are underpriced in sportsbooks and not in current feature set. Injury alone worth ~1-2% accuracy on prop models.
- **Priority order:** (1) `injury_monitor.py` — poll NBA official report + Rotowire, (2) `ref_tracker.py` — historical pace/foul tendencies + daily assignments, (3) `line_monitor.py` — The Odds API opening vs closing line, (4) `news_scraper.py` — ESPN headline keyword monitor.
- **Related:** [[win_probability]], [[player_props]], [[betting_edge]]

### 2026-03-16 — Phase 2 complete: ISSUE-005 similar-color re-ID fixed
- **Change:** Added `src/tracking/color_reid.py`: `TeamColorTracker`, `dominant_team_color()`, `similar_team_colors()`.
- **k-means k=2** per detection updates per-team EMA color signature. When team hue centroids within 20 hue units: appearance weight raised +0.10 in Hungarian cost; jersey-number tiebreaker window widened +0.10 in gallery re-ID.
- **Related:** [[AdvancedFeetDetector]], [[advanced_tracker]]

### 2026-03-16 — Phase 2 complete: Jersey OCR + player identity
- **02-01:** EasyOCR dual-pass (normal + inverted binary crop) for dark-on-light and light-on-dark jerseys. `JerseyVotingBuffer` deque(maxlen=3) for noise-free confirmation. KMeans small-crop mean fallback.
- **02-02:** `_jersey_buf` attr added per tracker slot; `reset_slot()` clears buffer on eviction. Jersey number feeds into re-ID tiebreaker.
- **02-04:** `player_identity_map` schema in PostgreSQL; `persist_identity_map()` in `src/data/player_identity.py`.
- **Related:** [[jersey_ocr]], [[advanced_tracker]], [[player_identity]]

### 2026-03-16 — Phase 2 complete: Referee filtering
- **Change:** Referee spatial columns (spacing, pressure) set to NaN sentinel — not row removal. String label `"referee"` used, not `team_id==2`. `compute_spatial_features()` in [[feature_engineering]] and [[shot_quality]] both guard on this.
- **Related:** [[feature_engineering]], [[shot_quality]], [[defense_pressure]]

### 2026-03-12 — ISSUE-004: Three-tier homography + court-line drift check
- **Change:** [[unified_pipeline]] `_get_homography`: (1) reject <8 inliers, (2) EMA blend 8–39, (3) hard-reset ≥40. `_check_court_drift()` runs every 30 frames — checks white-pixel alignment of projected court boundary lines; if <0.35 → force hard-reset.
- **Constants:** `_H_RESET_INLIERS=40`, `_REANCHOR_INTERVAL=30`, `_REANCHOR_ALIGN_MIN=0.35`
- **Related:** [[rectify_court]], [[AdvancedFeetDetector]]

### 2026-03-12 — Detectron2 → YOLOv8n migration
- **Decision:** Replaced Mask R-CNN with YOLOv8n. `detectron2` not installable on Python 3.10 + PyTorch 2.1.
- **Detection change:** `model(frame, classes=[0], conf=0.5)` → `boxes.xyxy`. Keypoint: `head_x=(x1+x2)//2`, `foot_y=y2`.
- **Related:** [[FeetDetector]], [[AdvancedFeetDetector]]

### 2026-03-12 — Re-ID spatial gate bug fix
- **Bug:** `_reid` spatial IoU gate blocked valid re-IDs (players off-screen have low IoU with Kalman prediction). Gate removed — appearance threshold alone sufficient.
- **Schema fix:** `timestamp` (seconds) and `velocity` (court px/frame) added to CSV output.
- **Related:** [[AdvancedFeetDetector]], [[video_handler]]
