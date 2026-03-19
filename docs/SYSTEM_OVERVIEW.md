# System Overview — NBA AI Basketball System

This document describes the full architecture of the system: how data flows from raw inputs through processing layers to model outputs and products.

---

## High-Level Data Flow

```
┌──────────────────────────────────────────────────────────────────┐
│  INPUTS                                                          │
│                                                                  │
│  Broadcast Video (.mp4)        NBA API + External Sources        │
│  broadcast footage,            gamelogs, shot charts, PBP,       │
│  game clips (30s–48min)        advanced stats, synergy,          │
│                                contracts, odds, injuries, refs    │
└──────────┬────────────────────────────┬─────────────────────────┘
           │                            │
           ▼                            ▼
┌──────────────────────┐   ┌────────────────────────────────────┐
│  CV TRACKING PIPELINE │   │  DATA COLLECTION PIPELINE          │
│                      │   │                                    │
│  1. Court detection  │   │  Smart TTL cache layer             │
│  2. Player detection │   │  25+ data sources                  │
│  3. Ball tracking    │   │  3 seasons of history              │
│  4. Re-identification│   │  Live feeds (injury/lines/refs)    │
│  5. Event detection  │   │                                    │
│  6. Possession class │   │  → data/nba/*.json                 │
│                      │   │  → data/external/*.json            │
│  → tracking_data.csv │   │                                    │
└──────────┬───────────┘   └──────────────┬─────────────────────┘
           │                              │
           ▼                              ▼
┌──────────────────────────────────────────────────────────────────┐
│  FEATURE ENGINEERING                                             │
│                                                                  │
│  CV features (spatial/temporal) + NBA API features (contextual)  │
│  60+ computed features, rolling windows [30/90/150 frames]       │
│                                                                  │
│  → features.csv                                                  │
└──────────────────────────────┬───────────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────────┐
│  ML MODEL ENSEMBLE (100 models, 7 tiers)                        │
│                                                                  │
│  Tier 1: Win prob, 7 props, 5 game models    ✅ 18 trained      │
│  Tier 2: xFG, shot zones, clutch             ✅ trained          │
│  Tier 3: CV behavioral models                🔲 Phase 7         │
│  Tier 4-7: Simulator, live LSTM              🔲 Phase 10-16     │
│                                                                  │
│  → predictions, probabilities, edges                             │
└──────────────────────────────┬───────────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────────┐
│  PRODUCTS                                                        │
│                                                                  │
│  Betting Dashboard    Analytics Dashboard    AI Chat             │
│  (Phase 11-13)        (Phase 14)             (Phase 15)          │
└──────────────────────────────────────────────────────────────────┘
```

---

## Module 1: Computer Vision Tracking Pipeline

**Location:** `src/tracking/`, `src/pipeline/unified_pipeline.py`

The CV pipeline processes broadcast video frame-by-frame, extracting the physical position and actions of every player and the ball in real-world court coordinates.

### Processing Chain

```
Video Frame (1280×720 or 1920×1080 broadcast)
    │
    ▼ src/tracking/rectify_court.py
Court Homography Estimation
  - SIFT feature matching against court panorama template
  - 3-tier acceptance: reject <8 inliers | EMA blend 8-39 | hard-reset ≥40
  - Drift check every 30 frames (white pixel alignment)
  - Output: 3×3 homography matrix M → pixel coords → court coords (feet)
    │
    ▼ src/tracking/player_detection.py
YOLOv8n Person Detection
  - Model: yolov8n.pt (Phase 2.5: yolov8x.pt for higher accuracy)
  - Classes: [0] (person only), conf=0.35
  - Input resolution: 640×640
  - Output: bounding boxes [x1, y1, x2, y2] per person
    │
    ▼ src/tracking/advanced_tracker.py — AdvancedFeetDetector
Player Tracking (Kalman + Hungarian + HSV Re-ID)
  - Kalman filter: 6D state [cx, cy, vx, vy, w, h] per tracked slot
  - Hungarian assignment: cost = 0.75 × (1-IoU) + 0.25 × appearance_distance
  - HSV appearance: 96-dim L1-normalized histogram (EMA α=0.7)
  - Similar-color mode: when team hue centroids within 20° → weight shifts +0.10
  - Gallery re-ID: TTL=300 frames, MAX_LOST=90 frames
  - Jersey OCR: EasyOCR dual-pass (normal + inverted) → JerseyVotingBuffer(maxlen=3)
  - Output: player_id, team_id, x_court, y_court, velocity per frame
    │
    ▼ src/tracking/ball_detect_track.py — BallDetectTrack
Ball Tracking (Hough + CSRT + Optical Flow)
  - Primary: Hough circle detection (param1=50, param2=25, radius 8-35px)
  - Fallback 1: CSRT tracker (when Hough loses ball)
  - Fallback 2: Lucas-Kanade optical flow (when CSRT fails)
  - Possession: IoU overlap between ball bbox and player foot bbox
    │
    ▼ src/tracking/event_detector.py — EventDetector
Event Detection
  - Monitors ball possession transitions: current_possessor ≠ prev_possessor
  - Shot: possessor releases ball → ball moves toward basket (velocity vector)
  - Pass: possessor releases → ball trajectory to teammate
  - Dribble: short possession release + recapture (<0.3s)
  - Fires: screen_set, cut, drive (start→end coord), closeout (mph), rebound_position
    │
    ▼ src/tracking/possession_classifier.py + play_type_classifier.py
Possession + Play Type Classification
  - PossessionClassifier: transition | drive | paint | post-up | double-team
  - PlayTypeClassifier: isolation | P&R ball handler | P&R roll man | spot-up |
                        cut | hand-off | post-up | off screen
  - ScoreboardOCR: extracts game clock, shot clock, score from broadcast overlay
    │
    ▼ Output
tracking_data.csv (36 columns, ~25,000 rows per game clip)
shot_log.csv, possessions.csv
```

### Key Classes

| Class | File | Responsibility |
|-------|------|----------------|
| `AdvancedFeetDetector` | `src/tracking/advanced_tracker.py` | Full player tracking orchestrator |
| `BallDetectTrack` | `src/tracking/ball_detect_track.py` | Ball position + possession |
| `TeamColorTracker` | `src/tracking/color_reid.py` | Team color separation (HSV KMeans) |
| `JerseyOCR` | `src/tracking/jersey_ocr.py` | Jersey number reading (EasyOCR) |
| `CourtRectifier` | `src/tracking/rectify_court.py` | Court homography estimation |
| `EventDetector` | `src/tracking/event_detector.py` | Shot / pass / dribble detection |
| `PossessionClassifier` | `src/tracking/possession_classifier.py` | Play type labeling |
| `ScoreboardOCR` | `src/tracking/scoreboard_ocr.py` | Clock and score extraction |
| `DeepReID` | `src/re_id/models/model.py` | CBAM attention-based deep re-ID |

---

## Module 2: Data Collection Pipeline

**Location:** `src/data/`

24 scrapers and enrichment modules cover every public data source relevant to NBA prediction.

### Data Sources

| Source | Module | Data | TTL |
|--------|--------|------|-----|
| NBA Stats API | `nba_stats.py` | Team stats, schedules, boxscores | 24h (active) / ∞ (complete) |
| NBA Tracking | `nba_tracking_stats.py` | Speed/distance, hustle, on/off, synergy, defender zones | 24h |
| NBA PBP | `pbp_scraper.py` | Play-by-play for all 3,685 games | 24h |
| NBA Shot Charts | `shot_chart_scraper.py` | 221,866 shots with zone + distance | 24h |
| Basketball Reference | `bbref_scraper.py` | BPM, VORP, WS/48, injury history | 48h |
| HoopsHype | `contracts_scraper.py` | Salary, years remaining, contract year flag | 7d |
| OddsPortal | `odds_scraper.py` | Historical spread + total lines | 7d |
| DraftKings / FanDuel | `props_scraper.py` | Current player prop lines | 15min |
| Rotowire RSS | `injury_monitor.py` | Injury + lineup news | 30min |
| NBA Official | `injury_monitor.py` | Official injury report | 6h |
| yt-dlp | `video_fetcher.py` | Game clip download | on-demand |

### Smart Caching Layer

`src/data/cache_utils.py` implements TTL-aware file caching:
- Completed seasons (2022-23, 2023-24): cached indefinitely — data never changes
- Active season (2024-25): 24h TTL for stats, 6h for injury, 15min for props
- External sources: 7d TTL for contracts/odds, 48h for BBRef
- Cache stored in `data/nba/` (NBA API) and `data/external/` (third-party)

### Enrichment

`src/data/nba_enricher.py` matches CV-tracked shots to NBA play-by-play:
- Matches on: game_id + period + approximate shot clock timestamp
- Labels each tracked shot with: made/missed, shot_type, defender, distance
- Required for xFG v2 training and possession outcome models

---

## Module 3: Feature Engineering

**Location:** `src/features/feature_engineering.py`

Transforms raw tracking data and NBA API data into ML-ready features.

### Feature Groups

| Group | Features | Source |
|-------|----------|--------|
| Rolling stats | velocity_mean, distance_30f/90f/150f, acceleration_mean | CV tracking |
| Spatial | team_spacing (convex hull), isolation_score, paint_density, defender_dist | CV tracking |
| Event counts | shots_per_90, passes_per_90, dribbles_per_90 | CV tracking |
| Momentum | scoring_run_length, momentum_shift_flag, pressure_trend | CV tracking |
| Court context | zone, distance_to_basket, shot_clock_pressure | CV + scoreboard |
| Game context | game_clock, score_diff, possession_number | CV scoreboard |
| Player context | season_pts_avg, last5_pts_avg, ts_pct, usg_rate | NBA Stats |
| Opponent context | def_rtg, opponent_clutch_pts_allowed | NBA Stats |
| Schedule context | rest_days, back_to_back, travel_miles | `schedule_context.py` |
| Ref context | ref_fta_tendency, ref_pace_tendency | `ref_tracker.py` |

### Rolling Windows

Three temporal windows computed for all velocity/distance metrics:
- **30 frames** (~1.0 seconds at 30fps) — immediate reaction
- **90 frames** (~3.0 seconds) — play-level context
- **150 frames** (~5.0 seconds) — possession-level trend

---

## Module 4: ML Model Ensemble

**Location:** `src/prediction/`

100 models across 7 tiers, designed to layer progressively as more CV game data accumulates.

### Model Architecture

```
Layer 1: Season context         (win/loss%, home/away, rest)
Layer 2: Player history         (gamelogs, rolling form, advanced)
Layer 3: Behavioral profile     (CV: drive freq, spacing, contests)  ← Phase 6+
Layer 4: Matchup context        (defender zone FG%, synergy vs matchup)
Layer 5: Game environment       (ref tendencies, injuries, travel)
Layer 6: Market signals         (line movement, public%, CLV)         ← Phase 11+
Layer 7: Live state             (current score, fatigue, momentum)    ← Phase 16+
                ↓
        Ensemble → Monte Carlo Simulator (10K sims/game)
                ↓
        Stat distributions → compare vs book lines → EV edges
```

### Tier Breakdown

| Tier | Phase | Count | Dependencies |
|------|-------|-------|-------------|
| 1 | Phase 4 ✅ | 13 | NBA API only |
| 2 | Phase 4 ✅ | 5 | Shot charts + clutch data |
| 3 (4.6) | Phase 4.6 🔲 | 7 retrains | 22 new features wired in |
| 4 | Phase 7 | 10 | 20 CV game clips |
| 5 | Phase 10 | 8 | 50 full games |
| 6 | Phase 10 | 7 | 100 games |
| 7 | Phase 12/16 | 7 | 200+ games + live feeds |

### The 7-Model Possession Simulator Chain

```
Possession Start
    │
    ▼ [Model 1] Play Type Predictor
    Isolation / P&R / Spot-up / Cut / Post-up
    │
    ▼ [Model 2] Shot Selection
    Who shoots? (spatial + usage + matchup)
    │
    ▼ [Model 3] xFG (Expected Field Goal %)
    Shot quality given zone + defender + spacing
    │
    ▼ [Model 4] Turnover / Foul Predictor
    Probability branch: TO, foul-to-shoot, dead ball
    │
    ▼ [Model 5] Rebound Position
    Crash angle, box-out, second-chance probability
    │
    ▼ [Model 6] Fatigue Adjustment
    Per-player fatigue curve → minutes-adjusted efficiency
    │
    ▼ [Model 7] Substitution Trigger
    Coach tendency model → lineup change probability
    │
× 10,000 Monte Carlo simulations per game
    │
    ▼ Full stat distribution per player
        → compare vs sportsbook lines → flag +EV edges
```

---

## Module 5: Analytics Signals

**Location:** `src/analytics/`

20 specialized analytics modules compute basketball intelligence signals from tracking data.

| Module | Signal | Use |
|--------|--------|-----|
| `shot_quality.py` | Shot quality 0-1 (defender dist, spacing, clock, fatigue) | xFG input, betting edge |
| `defense_pressure.py` | Defensive pressure index (team formation + closeout dist) | Possession value model |
| `momentum.py` | EMA-smoothed scoring run length, momentum shift flag | Live win prob feature |
| `spacing.py` | Convex hull team spacing metric | Shot quality feature |
| `betting_edge.py` | CLV backtest, EV computation, Kelly sizing | Betting dashboard |
| `drive_analysis.py` | Drive frequency, FTA conversion rate | Prop model feature |
| `rebound_positioning.py` | Crash angle, box-out detection, second-chance prob | Rebound prop model |
| `passing_network.py` | Touch map, pass completion, ball movement index | Ball stagnation model |
| `lineup_synergy.py` | 5-man unit net rating | Lineup optimizer |
| `pick_and_roll.py` | P&R frequency, coverage type, efficiency | Play type feature |
| `play_recognition.py` | Rule-based play type labeling | Play type classifier |
| `off_ball_events.py` | Cut frequency, screen usage, off-ball distance | Behavioral profile |
| `defensive_scheme.py` | Zone vs man detection, help rotation latency | Defensive model |
| `micro_timing.py` | Shot clock pressure score, fatigue penalty | Shot quality input |

---

## Module 6: Database Schema

**Location:** `database/schema.sql`

PostgreSQL schema with 9 tables and 2 materialized views. Currently populated by NBA API data only; CV tracking writes are wired in Phase 6.

### Tables

| Table | Key Columns | Purpose |
|-------|-------------|---------|
| `teams` | team_id, abbreviation, conference, arena_lat/lon | Team metadata |
| `players` | player_id, name, position, height, weight, team_id | Player registry |
| `games` | game_id, date, home/away, scores, model predictions | Game results + predictions |
| `tracking_frames` | game_id, frame, player_id, x, y, velocity, event | Per-frame CV output |
| `possessions` | game_id, possession_num, type, duration, spacing, pressure | Possession aggregates |
| `shots` | game_id, player_id, x, y, zone, defender_dist, made | Shot log |
| `player_identity_map` | jersey_num, player_id, game_id, confidence | OCR → player_id mapping |
| `game_lineups` | game_id, period, team_id, player_ids (5-man) | Lineup tracking |
| `model_predictions` | game_id, model_id, prediction, confidence, edge | Pre-game model output |

### Views

- `v_player_season_stats` — Joins players + games + shots for season-level aggregates
- `v_game_betting_summary` — Joins predictions + results for CLV backtest

---

## Module 7: API Backend

**Location:** `api/` (Phase 13)

FastAPI backend serving predictions, analytics, and data to the frontend.

### Planned Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/predictions/game/{game_id}` | GET | Win probability + spread + total predictions |
| `/predictions/props/{player_id}` | GET | All 7 prop projections + confidence |
| `/predictions/edges` | GET | All games with +EV edges today |
| `/analytics/shot-chart/{player_id}` | GET | Shot chart data (zone + frequency) |
| `/analytics/lineup/{team_id}` | GET | Lineup matrix + net ratings |
| `/analytics/win-prob/{game_id}` | GET | Win probability timeline |
| `/analytics/defense/{team_id}` | GET | Defensive pressure + spacing metrics |
| `/data/injuries` | GET | Current injury report (live) |
| `/data/props/{player_id}` | GET | Current DK/FD prop lines |
| `/data/lines/{game_id}` | GET | Opening + current spread/total |
| `/simulate/{game_id}` | POST | Run 10K Monte Carlo simulation |
| `/ws/live/{game_id}` | WebSocket | Real-time win probability stream |

---

## Module 8: AI Chat Interface

**Location:** `analytics/chat.py` (Phase 15)

Claude API integration with tool use, enabling natural language queries that produce inline charts.

### Architecture

```
User: "Show me Tatum's shot quality vs guards and his prop tonight"
    │
    ▼ Claude API (claude-opus-4-6) — tool_use mode
    Tools available:
    - get_game_prediction(home, away, date)
    - get_player_props(player, stats, date)
    - get_analytics(player, metric, filters)
    - get_lineup_data(team, period)
    - get_betting_edges(date, min_ev)
    - get_shot_chart(player, season, filters)
    - get_win_probability_timeline(game_id)
    - compare_players(player_a, player_b, metric)
    - get_injury_impact(player, team)
    - render_chart(type, data, title, axes)  ← frontend renders inline
    │
    ▼ Tool execution → API calls → data
    │
    ▼ Claude synthesizes response + calls render_chart
    │
    ▼ Frontend renders chart inline in chat conversation
```

### Chart Types

1. Shot chart (D3 hexbin — zone frequency + efficiency)
2. Bar comparison (player vs. league average)
3. Line trend (rolling stats over time)
4. Distribution curve (prop projections vs. book line)
5. Radar chart (multi-metric player profile)
6. Heatmap (court zone efficiency)
7. Scatter (shot quality vs. defender distance)
8. Win probability waterfall (quarter-by-quarter)
9. Box plot (prop distribution from 10K simulations)
10. Lineup matrix (5-man unit net ratings)

---

## Performance Characteristics

| Component | Performance | Hardware |
|-----------|-------------|----------|
| Player detection (YOLOv8n) | 5.7 fps | RTX 4060 |
| Player detection (YOLOv8x) | ~3.5 fps | RTX 4060 |
| Court homography (SIFT) | Every 15 frames | CPU |
| Full tracking pipeline | 5.7 fps | RTX 4060 |
| Full game (48 min) | ~6 hours | RTX 4060 |
| Win prob model inference | <10ms | CPU |
| Prop model inference (7 models) | <50ms | CPU |
| Monte Carlo simulation (10K) | ~2s | CPU |

---

## Environment

| Component | Version |
|-----------|---------|
| Python | 3.9 (conda env: `basketball_ai`) |
| PyTorch | 2.0.1 |
| CUDA | 11.8 |
| cuDNN | 8.9 |
| GPU | RTX 4060 (8.6GB VRAM) |
| YOLOv8 | ultralytics 8.x |
| XGBoost | 1.7.x |
| PostgreSQL | 14+ |

---

## Proposed Repository Restructure

The current repo has several legacy parallel directories that should be consolidated:

| Current (redundant) | Should Move To | Reason |
|--------------------|----------------|--------|
| `tracking/` (root) | Archive or merge into `src/tracking/` | Legacy code, superseded by `src/tracking/` |
| `models/` (root) | Merge `base.py` → `src/prediction/` | Overlaps with `src/prediction/` |
| `pipeline/` (root) | Archive or merge into `src/pipeline/` | Superseded by `src/pipeline/` |
| `pipelines/` (root) | Archive or merge into `src/pipeline/` | Detection pipeline wrapper only |
| `api/` (root) | Already at `src/api/` eventually | Keep as-is until Phase 13 |
| `_*.py` debug scripts (root) | `scripts/debug/` | Diagnostic scripts, not production |
| `run.py`, `process_game.py` | `scripts/` | Legacy entry points |
| `autonomous_loop.py`, `smart_loop.py` | `scripts/` | Development loops |

**Single source of truth for each module:**
- Production tracker → `src/tracking/`
- ML models → `src/prediction/`
- Data scraping → `src/data/`
- Pipeline orchestration → `src/pipeline/`
- Analytics signals → `src/analytics/`
