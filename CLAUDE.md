<!-- AUTO-GENERATED — DO NOT EDIT BELOW THIS LINE -->

## Resume From Here — Last Updated: 2026-03-17 22:26

### Pick Up Where We Left Off
**Priority order for next session:**
1. `python src/prediction/win_probability.py --train` — retrain with sklearn 1.7.2 (2 min)
2. Wire PostgreSQL writes — fix ISSUE-018 before processing more games
3. Scrape ShotChartDetail — 50K+ shots, unlocks shot quality v1 model
4. Finish gamelog scrape — 209 players remaining (run scraper --loop --max 569)
5. Fix per-video homography (ISSUE-017) — needs per-clip M1 calibration


---
*Session note auto-created by new_session.py*

---

### This Session — Files Changed
- `C:/Users/neelj/nba-ai-system/vault/Project Vision.md`
- `C:/Users/neelj/nba-ai-system/CLAUDE.md`
- `C:/Users/neelj/nba-ai-system/.planning/ROADMAP.md`

### Open Priority Issues
- 1. 🔴 Win probability / game prediction models — data pipeline now ready, model still TBD
- 2. 🔴 Analytics + tracking dashboards (not built yet)
- 3. 🟡 HSV re-ID upgrades (jersey confusion on similar-colored uniforms)
- 4. 🔴 Real game clip needed — tracker has plateaued on Short4Mosaicing calibration clip; need actual NBA broadcast footage to benchmark further
- 5. 🟢 Pano validation + fallback — fixed 2026-03-12

### Analytics Module Status (src/)
- ✅ `src/analytics/betting_edge.py`
- ✅ `src/analytics/defense_pressure.py`
- ✅ `src/analytics/momentum.py`
- ✅ `src/analytics/shot_quality.py`
- ✅ `src/data/db.py`
- ✅ `src/data/game_matcher.py`
- ✅ `src/data/injury_monitor.py`
- ✅ `src/data/line_monitor.py`
- ✅ `src/data/lineup_data.py`
- ✅ `src/data/nba_enricher.py`
- ✅ `src/data/nba_stats.py`
- ✅ `src/data/news_scraper.py`
- ✅ `src/data/pbp_scraper.py`
- ✅ `src/data/player_identity.py`
- ✅ `src/data/player_scraper.py`
- ✅ `src/data/prop_validator.py`
- ✅ `src/data/ref_tracker.py`
- ✅ `src/data/schedule_context.py`
- ✅ `src/data/shot_chart_scraper.py`
- ✅ `src/data/video_fetcher.py`
- ✅ `src/detection/detection/models/detection_model.py`
- 🔲 `src/detection/detection/tools/classes.py`
- ✅ `src/detection/detection/tools/inference.py`
- ✅ `src/detection/detection/tools/train.py`
- ✅ `src/features/feature_engineering.py`
- ✅ `src/pipeline/data_loader.py`
- ✅ `src/pipeline/feature_pipeline.py`
- ✅ `src/pipeline/model_pipeline.py`
- ✅ `src/pipeline/run_pipeline.py`
- ✅ `src/pipeline/tracking_pipeline.py`
- ✅ `src/pipeline/unified_pipeline.py`
- ✅ `src/prediction/clutch_efficiency.py`
- ✅ `src/prediction/game_models.py`
- ✅ `src/prediction/game_prediction.py`
- ✅ `src/prediction/player_props.py`
- ✅ `src/prediction/shot_zone_tendency.py`
- ✅ `src/prediction/win_probability.py`
- ✅ `src/prediction/xfg_model.py`
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
- ✅ `src/tracking/court_detector.py`
- ✅ `src/tracking/evaluate.py`
- ✅ `src/tracking/event_detector.py`
- ✅ `src/tracking/jersey_ocr.py`
- ✅ `src/tracking/osnet_reid.py`
- ✅ `src/tracking/play_type_classifier.py`
- ✅ `src/tracking/player.py`
- ✅ `src/tracking/player_detection.py`
- ✅ `src/tracking/player_identity.py`
- ✅ `src/tracking/possession_classifier.py`
- ✅ `src/tracking/rectify_court.py`
- ✅ `src/tracking/scoreboard_ocr.py`
- ✅ `src/tracking/tracker_config.py`
- ✅ `src/tracking/utils/plot_tools.py`
- ✅ `src/tracking/video_handler.py`
- ✅ `src/utils/bbox_crop.py`
- ✅ `src/utils/frame.py`
- ✅ `src/utils/visualize.py`

### Session Log
- Latest: `vault/Sessions/Session-2026-03-17.md`
- Full log: `vault/Sessions/`

<!-- END AUTO-GENERATED -->

# NBA AI Tracking System — Claude Context File

## What This Project Is Building

A **self-improving possession-by-possession game simulator** combining CV tracking + NBA API + 50 ML models to simulate any NBA game 10,000 times, produce stat distributions for every player, compare against sportsbook lines, and surface edges — accessible via conversational AI that renders charts inline.

**Three products:**
1. **Betting Dashboard** — prop edges by EV, Kelly sizing, live injury alerts
2. **Analytics Dashboard** — 96 metrics, shot charts, lineup matrices, win prob timelines, 10 chart types
3. **AI Chat** — "Show me Murray's shot quality vs guards and his prop tonight" → Claude calls tools, renders charts, synthesizes insight

**The moat:** Spatial CV data (defender distance, spacing, fatigue) that no public tool has. Simulator self-improves with every game. Closest competitor is Second Spectrum ($1M+/yr, teams only).

**Full plan:** `.planning/ROADMAP.md` — 17 phases, 50 models, 96 analytics metrics, complete simulator architecture

---

## Current Phase: Phase 4 — Tier 1 ML Models

**Phase 3 COMPLETE as of 2026-03-17:**
- Gamelogs: 622/569 ✅ | Advanced stats: 569/569 ✅ | Shot charts: 569/569 ✅
- PBP: 1,602 games cached (600 × 2024-25, 500 × 2023-24, 500 × 2022-23)
- Tier 2 models done: xFG v1 ✅ | Shot zone tendency ✅ | Clutch efficiency ✅

**Next priorities:**
1. ✅ Retrained win prob — 67.7% acc, Brier 0.204 (ISSUE-016 CLOSED 2026-03-17)
2. ✅ Trained player prop models — 7 models (pts/reb/ast/fg3m/stl/blk/tov) saved to data/models/props_*.json
3. ✅ Trained game-level models — 5 models: total/spread/blowout/first_half/pace (src/prediction/game_models.py)
4. ✅ Pipeline speed: 5.1→5.7 fps (+12%), embedding crash bug fixed (2026-03-17 session 4)
5. 🔲 **Run full game** — `conda run -n basketball_ai python run_full_game.py` (2016 Finals G7, ~6h) OR shorter: `--video cavs_vs_celtics_2025.mp4 --game-id 0022400710` (~45-90min). Then `python quality_report.py`
6. 🔲 Wire PostgreSQL — fix ISSUE-010 (every run overwrites tracking_data.csv)
7. 🔲 Phase 5 — Wire injury_monitor.py into prop model inputs (+1-2% accuracy)

---

## Open Priority Issues

| ID | Issue | Fix |
|---|---|---|
| ISSUE-016 | sklearn mismatch — win prob needs retrain | ✅ CLOSED 2026-03-17 — retrained, 67.7% acc |
| ISSUE-018 | PBP at 43% — 1,602/3,685 games | ✅ CLOSED 2026-03-17 — 3,100/3,685 (84%), clutch rebuilt |
| ISSUE-010 | PostgreSQL not wired — overwrites CSV | Phase 6 |
| ISSUE-009 | 0 shots enriched — no --game-id runs | Phase 6 |
| ISSUE-019 | 0 shot charts | ✅ CLOSED 2026-03-17 — 569/569, xFG v1 trained |
| ISSUE-020 | Gamelogs missing | ✅ CLOSED 2026-03-17 — 622/569 complete |

---

## Roadmap (17 phases — full detail in .planning/ROADMAP.md)

| Phase | Status | Goal |
|---|---|---|
| 1 — Data Infrastructure | ✅ | PostgreSQL, schedule, lineup, NBA stats |
| 2 — Tracker Bug Fixes | ✅ | Team color, EventDetector, 431 tests |
| 2.5 — CV Tracker Upgrades | 🔲 | Pose estimation, ByteTrack, per-clip homography |
| 3 — NBA API Data | ✅ | 622 gamelogs, 221K shots, 1,602 PBP games |
| 4 — Tier 1 ML Models | 🟡 Active | 13 models: win prob retrain + all props + game models |
| 5 — External Factors | 🔲 | Injury, refs, line movement |
| 6 — Full Game Processing | 🔲 | 20+ games, PostgreSQL, shots enriched |
| 7 — Tier 2-3 ML Models | 🔲 | xFG v2, play type, pressure, spacing (20 games) |
| 8 — Possession Simulator v1 | 🔲 | 7-model chain, 10K Monte Carlo |
| 9 — Feedback Loop | 🔲 | Nightly process → auto-retrain → better predictions |
| 10 — Tier 4-5 ML Models | 🔲 | Fatigue, lineup chemistry, matchup matrix (50-100 games) |
| 11 — Betting Infrastructure | 🔲 | Odds API, Kelly, CLV backtesting |
| 12 — Full Monte Carlo | 🔲 | All 50 models, full stat distributions |
| 13 — FastAPI Backend | 🔲 | 12 endpoints, Redis, WebSocket |
| 14 — Analytics Dashboard | 🔲 | Next.js, D3 shot charts, 10 chart types |
| 15 — AI Chat | 🔲 | Claude API + 10 tools + render_chart inline |
| 16 — Live Win Prob | 🔲 | 200+ games, LSTM, real-time WebSocket |
| 17 — Infrastructure | 🔲 | Docker, CI/CD, cloud GPU |

---

## The Feedback Loop

```
Process game → CV features + NBA API enrichment
    → label possessions → retrain 7 simulator models
    → Monte Carlo 10K sims → stat distributions
    → compare vs book lines → flag edges → bet
    → outcome → retrain → repeat
```

Every game processed improves every model. At 200 games the full 50-model stack is running.

---

## Video Processing

Running on RTX 4060 (8.6 GB VRAM).
- Use `run_clip.py` for clips; always pass `--game-id`
- Do NOT run `loop_processor.py` unattended (fills disk)

---

## System Architecture

```
CV Tracker (broadcast feed)          NBA API (stats, PBP, shots)
positions, pressure, spacing    +    gamelogs, outcomes, lineups
fatigue, play types, events          refs, injuries, schedule
        ↓                                       ↓
        └──────────── 50 ML Models ─────────────┘
                            ↓
              Possession Simulator (7-model chain)
                10,000 Monte Carlo per game
                            ↓
            Stat distributions for every player
                            ↓
        Compare vs sportsbook lines → flag +EV edges
                            ↓
    FastAPI → Next.js Dashboard + Claude AI Chat
        render_chart tool → charts render inline in conversation
```
| Phase 13 — Live Win Probability | 🔲 Needs 200+ full games | LSTM on possession sequences, WebSocket real-time |
| Phase 14 — Infrastructure | 🔲 | Docker, CI/CD, cloud GPU, drift monitoring |

---

## Dataset Status (Audited 2026-03-17)

### CV Tracking Data — Phase 2 bugs fixed; ready for full game runs
| Metric | Count | Notes |
|---|---|---|
| Game clips processed | 17 | BUT: 1–21 second clips, not full games |
| Tracking rows | 29,220 | ✅ Team separation fixed (2026-03-17) |
| Shots detected | 17 | ✅ EventDetector fixed — ball fallback added |
| Dribbles detected | 14 passes | ✅ EventDetector firing |
| Possessions labeled | 124 | result=NaN — no --game-id runs yet (ISSUE-009) |
| Shots with outcomes | 0 | No --game-id runs yet |

### NBA API Data — Phase 3 Complete (2026-03-17)
| Metric | Count | Notes |
|---|---|---|
| Season games (3 seasons) | 3,675+ | Full game results + team features for win prob |
| Team stats | 30 teams × 3 seasons | off_rtg, def_rtg, net_rtg, pace, eFG%, TS%, TOV% |
| Player base stats | 569 players | pts, reb, ast, min, fg%, 3pt%, ft% |
| Player advanced stats | 569 / 569 | ✅ All scraped 2026-03-17 |
| Player gamelogs | 622 / 569 | ✅ Complete 2026-03-17 |
| Shot charts | 569 / 569 | ✅ 221,866 shots scraped 2026-03-17 |
| Play-by-play | 1,602 games | ✅ 600 × 2024-25, 500 × 2023-24, 500 × 2022-23 |
| Clutch scores | 3 seasons | ✅ 228–255 qualified players/season |
| Boxscores | 13 games | Full per-player stats |
| Injury report | 126 players | Current, refreshed 2026-03-16 |

### Model Readiness
| Model | Status | Notes |
|---|---|---|
| Win probability (pre-game) | ✅ Retrained 2026-03-17 | 67.7% acc, Brier 0.204, data/models/win_probability.pkl |
| xFG v1 | ✅ Trained 2026-03-17 | 221K shots, Brier 0.226, data/models/xfg_v1.pkl |
| Shot zone tendency | ✅ Built 2026-03-17 | 566 players, 42-dim features, data/nba/shot_zone_tendency.json |
| Clutch efficiency | ✅ Built 2026-03-17 | 3 seasons scored, data/nba/clutch_scores_*.json |
| Player prop models | ✅ Trained 2026-03-17 | 7 models (pts/reb/ast/fg3m/stl/blk/tov), data/models/props_*.json |
| Game total / spread / blowout | ✅ Trained 2026-03-17 | 5 models (total/spread/blowout/first_half/pace), src/prediction/game_models.py |
| Shot quality v2 (CV-enhanced) | 🔲 Phase 6+7 | Needs 200+ enriched CV shots |
| Possession outcome | 🔲 Phase 6+7 | Needs 500+ labeled possessions |
| Lineup chemistry | 🔲 Phase 7 | NBA API lineups + CV validation |
| Live win prob LSTM | 🔲 Phase 16 | Needs 200+ full games |

Data volume milestones: **Phase 4 (now)** → all 13 Tier 1 models; **Phase 6** (20 full games) → xFG v2 + possession outcome; **Phase 10** (100 games) → lineup chemistry; **Phase 16** (200+ games) → live LSTM

---

## Complete Data Catalog

> Full reference: `vault/Concepts/Complete Data Sources.md`

### CV Tracker — Currently Extracting ✅
positions (x,y), speed, acceleration, team classification, jersey OCR, player identity, ball position, possession, events (shot/pass/dribble), court homography, scoreboard OCR, play type, possession type

### CV Tracker — Not Yet Extracting 🔲 (Phase 2.5/6)
spacing index (convex hull), paint density, defensive alignment, PnR coverage type (drop/hedge/switch/ICE), zone vs man detection, double team, screen detection, shot arc (parabola), ball trajectory, contest arm angle, player speed vs baseline (real-time fatigue), movement asymmetry (injury proxy), crowd noise level (audio RMS), announcer keyword detection (speech-to-text), forced shot flag

### NBA API — Not Yet Pulling 🔲 (Phase 3.5)
`BoxScorePlayerTrackV2` (speed/distance/touches), `PlayerDashPtShots` (contested%/C+S%/pull-up%), `LeagueDashPtDefend` (defender zone FG% allowed), `MatchupsRollup` (who guards whom), `LeagueHustleStatsPlayer` (deflections/screens), `SynergyPlayTypes` (pts/possession by play type — ground truth for classifier), `LeaguePlayerOnDetails` (on/off net rtg), `VideoEvents` (free labeled training clips for CV play type classifier)

### External Sources — Not Yet Integrated 🔲 (Phase 3.5)
- **Basketball Reference**: BPM/VORP/WS, historical injuries, coaching records, contracts, transactions, historical lines
- **Action Network**: public bet% + money% → sharp vs public signal on every prop
- **OddsPortal**: 15yr historical closing lines → CLV backtesting
- **Pinnacle**: sharpest opening lines → market benchmark, steam detection
- **DraftKings/FanDuel**: current player props → soft book lag detection
- **NBA official injury PDF**: ~5pm ET daily — faster than ESPN
- **RotoWire RSS**: injury/lineup feed (feedparser)
- **Reddit r/nba** (praw): injury threads, lineup news — free
- **HoopsHype + Spotrac**: contracts, salary, transactions

---

## Complete Model Catalog — 90 Models

> Full detail: `vault/Concepts/Complete Model Catalog.md`
> Prediction formula: `vault/Concepts/Prediction Pipeline.md`

### Trained ✅ (18 models)
M1-M6: Win prob (67.7%) / game total / spread / blowout / first half / pace
M7-M13: Props pts/reb/ast/3pm/stl/blk/tov
M14: xFG v1 (Brier 0.226, 221K shots)
M15-M18: Zone tendency / shot volume / clutch efficiency / shot creation type

### Phase 3.5 — Untapped Data 🔲 (10 models)
M19-M24: Defensive effort / ball movement / screen ROI / touch dependency / play type efficiency / defender zone xFG adjust (nba_api hustle + synergy + matchup)
M25-M28: Age curve / injury recurrence / coaching adjustment / ref tendency extended (BBRef)

### Phase 4.5 — Betting + Lifecycle 🔲 (12 models)
M29-M34: Sharp money detector / CLV predictor / public fade / prop correlation matrix / SGP optimizer / soft book lag
M35-M40: DNP predictor / load management / return-from-injury curve / injury risk / breakout predictor / contract year effect

### Phase 7 — 20 CV Games 🔲 (10 models)
M41-M50: xFG v2 (with defender + spacing) / shot selection quality / play type classifier / defensive pressure / spacing rating / drive frequency / open shot rate / transition frequency / off-ball movement / possession value

### Phase 9 — NLP 🔲 (4 models)
M66-M69: Injury report severity NLP / injury news lag / team chemistry sentiment / beat reporter credibility

### Phase 10 — 50-100 CV Games 🔲 (15 models)
M51-M65: Fatigue curve / rebound positioning / late-game efficiency / closeout quality / help defense frequency / ball stagnation / screen effectiveness / turnover under pressure / lineup chemistry / matchup matrix / substitution timing / momentum / foul drawing rate / second chance / pace per lineup

### Phase 11 — Live 🔲 (6 models)
M70-M75: Live prop updater / comeback probability / garbage time predictor / foul trouble / Q4 star usage / momentum run

### Phase 12/16 — Full Stack 🔲 (7 models)
M76-M82: Full possession simulator / live win prob LSTM / true player impact / lineup optimizer / prop pricing engine / regression detector / injury impact

### The 7-Model Possession Chain (Simulator Core)
```
[1] Play Type → [2] Shot Selector → [3] xFG → [4] TO/Foul
→ [5] Rebound → [6] Fatigue → [7] Substitution
× 10,000 per game = full stat distribution per player
```

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
| ISSUE-013 | All players labeled 'green' — team color separation broken | ✅ Fixed 2026-03-17 — dynamic KMeans warm-up clustering |
| ISSUE-014 | 2fps processing speed — KMeans per crop per frame | ✅ Fixed 2026-03-17 — mean HSV replaces KMeans in _compute_appearance |
| ISSUE-015 | SIFT too slow — 441ms/call × 100 calls = 44s/500 frames | ✅ Fixed 2026-03-17 — _SIFT_INTERVAL=15, _SIFT_SCALE=0.5 downscale |
| ISSUE-016 | sklearn 1.6.1 model pickled, env now 1.7.2 | 🔴 Retrain: python src/prediction/win_probability.py --train |
| ISSUE-017 | Per-video homography wrong — M1 calibrated for pano_enhanced, not broadcast angle | ✅ Fixed 2026-03-17 — detect_court_homography() + 300-frame scan. 3/4 clips detect; 1 still falls back. |
| ISSUE-018 | PostgreSQL not wired — losing tracking history | 🔴 Active — every run overwrites tracking_data.csv |
| ISSUE-019 | 0 shot charts scraped — ShotChartDetail never run | ✅ CLOSED 2026-03-17 — 569/569, xFG v1 trained |
| ISSUE-020 | 209/569 players still missing gamelogs | ✅ CLOSED 2026-03-17 — 622/569 complete |
| ISSUE-021 | Pipeline 5.1fps — YOLO imgsz=1280 bottleneck | ✅ Fixed 2026-03-17 — imgsz=640, 5.7fps (+12%) |
| ISSUE-022 | _match_team crash without lapx — 256-dim vs 99-dim embedding mismatch | ✅ Fixed 2026-03-17 — pre-compute det["deep_emb"] before cost loop |

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

### 2026-03-17 — Full system vision designed: simulator + AI chat + analytics dashboard
- **Decision:** Central architecture is a 7-model possession-by-possession Monte Carlo simulator (10K sims/game) producing stat distributions compared to book lines via Kelly sizing.
- **50 models in 6 tiers:** Tier 1 (NBA API, 13 models) → Tier 2 (shot charts, 5) → Tier 3 (20 CV games, 10) → Tier 4 (50 games, 8) → Tier 5 (100 games, 7) → Tier 6 (200 games, 7 including LSTM).
- **96 analytics metrics:** 36 player, 21 team, 6 lineup, 15 game, 10 predictive, 8 league-wide.
- **AI chat architecture:** Claude API (claude-sonnet-4-6) + 10 tools + `render_chart` tool → frontend renders chart inline in chat. Split panel: chat left, canvas right.
- **10 chart types:** shot chart (D3 hexbin), bar comparison, line trend, distribution curve, radar, heatmap, scatter, win prob waterfall, box plot, lineup matrix.
- **CV quality gap vs Second Spectrum:** ~2-3% on prediction accuracy. Closed by pose estimation (3 days) + data volume (1000+ games). Unbridgeable gaps: ball height, hand contest — worth ~2% total, not worth chasing.
- **Edge markets:** Role player props + minutes + live totals. Books price lazily, your spatial data has genuine edge. Stars props already sharp-moved.
- **Related:** [[possession_simulator]], [[monte_carlo]], [[ai_chat]], [[render_chart]], [[prop_pricing]]

### 2026-03-17 — Phase 2.5 CV upgrades designed
- **Highest ROI:** Pose estimation (ankle keypoints) — 3 days, closes 60% of position gap vs SS. YOLOv8-pose or ViTPose.
- **Critical blocker:** Per-clip homography (ISSUE-017) — M1 calibrated for pano_enhanced angle. Fix: auto-detect court lines per clip, build M1 from intersections.
- **ByteTrack:** Replace Kalman+Hungarian → ID switch rate 15% → 3%.
- **After Phase 2.5:** position ±6-8", xFG ~64%, ID switches ~3% (vs SS: ±3", ~68%, <1%).
- **Related:** [[advanced_tracker]], [[rectify_court]], [[unified_pipeline]]

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
