# System Architecture — NBA AI System

Full technical architecture — how data flows from raw inputs through the CV pipeline, feature engineering, ML stack, simulator, and out to the three end products.

---

## High-Level Data Flow

```
┌─────────────────────────────────────────────────────────────────────┐
│  INPUTS                                                             │
│                                                                     │
│  Broadcast Video (.mp4)          NBA API + External Sources         │
│  game clips (30s–full game)      gamelogs, shots, PBP, synergy,    │
│                                  contracts, odds, injuries, refs     │
└──────────┬───────────────────────────────┬──────────────────────────┘
           │                               │
           ▼                               ▼
┌──────────────────────┐      ┌────────────────────────────────────┐
│  CV TRACKING         │      │  DATA COLLECTION PIPELINE          │
│  src/tracking/       │      │  src/data/                         │
│                      │      │                                    │
│  Court homography    │      │  Smart TTL cache layer             │
│  YOLOv8n detection   │      │  25+ data sources, 3 seasons       │
│  Kalman tracking     │      │  Live feeds (injury/lines/refs)     │
│  HSV team re-ID      │      │  data/nba/*.json                   │
│  Jersey OCR          │      │  data/external/*.json              │
│  Ball detection      │      │                                    │
│  Event detection     │      │                                    │
│  → tracking_data.csv │      │                                    │
└──────────┬───────────┘      └──────────────┬─────────────────────┘
           └──────────────┬──────────────────┘
                          ▼
         ┌────────────────────────────────────────┐
         │  FEATURE ENGINEERING (57 features)    │
         │  src/features/feature_engineering.py  │
         │                                        │
         │  CV spatial + NBA API contextual       │
         │  Rolling windows [5 / 10 / 20 games]  │
         │  Bayesian shrinkage (K=15 games)       │
         └─────────────────────┬──────────────────┘
                               │
                               ▼
         ┌────────────────────────────────────────┐
         │  ML MODEL STACK (90 models, 7 tiers)  │
         │  src/prediction/                       │
         │                                        │
         │  Tier 1  Win prob, props, game    ✅   │
         │  Tier 2  xFG, shot zones, clutch  ✅   │
         │  Tier 3  CV behavioral            🔲   │
         │  Tier 4–7  Simulator + LSTM       🔲   │
         └─────────────────────┬──────────────────┘
                               │
                               ▼
         ┌────────────────────────────────────────┐
         │  POSSESSION SIMULATOR (Phase 8)        │
         │  7-model chain × 10,000 simulations   │
         │  = full stat distribution per player   │
         └─────────────────────┬──────────────────┘
                               │
                               ▼
         ┌────────────────────────────────────────┐
         │  BETTING ENGINE                        │
         │  src/analytics/betting_edge.py         │
         │  EV → Kelly sizing → CLV tracking      │
         └─────────────────────┬──────────────────┘
                               │
                               ▼
     ┌─────────────────────────────────────────────────┐
     │  FastAPI → Next.js Dashboard + Claude AI Chat   │
     └─────────────────────────────────────────────────┘
```

---

## CV Tracking Pipeline

**Location:** `src/tracking/` + `src/pipeline/unified_pipeline.py`

### Stage 1 — Court Homography (`rectify_court.py`)

Establishes the mapping from pixel coordinates to 2D court coordinates (feet):

- SIFT feature matching against `resources/pano_enhanced.png` (court panorama template)
- **3-tier acceptance logic:**
  - `<8 inliers` → reject, use previous homography
  - `8–39 inliers` → EMA blend (new:old = 0.3:0.7)
  - `≥40 inliers` → hard reset to new homography
- Drift check every 30 frames — checks white-pixel alignment of projected court lines
  - If alignment < 0.35 → force hard reset
- Constants: `_H_RESET_INLIERS=40`, `_REANCHOR_INTERVAL=30`, `_REANCHOR_ALIGN_MIN=0.35`
- SIFT runs every 15 frames at 0.5× scale → reduces 44s overhead to ~4s per clip

### Stage 2 — Person Detection (`player_detection.py`)

- YOLOv8n, `classes=[0]` (person only), `conf=0.35`
- Input resolution: 640×640 (upgraded to 1280 for post-game in Phase 2.5)
- Output: `[x1, y1, x2, y2, conf]` per detected person per frame

### Stage 3 — Player Tracking (`advanced_tracker.py`)

**AdvancedFeetDetector** — Kalman + Hungarian + HSV re-ID:

| Component | Detail |
|---|---|
| Kalman state | 6D: [cx, cy, vx, vy, w, h] |
| Prediction | Linear constant-velocity model |
| Hungarian cost | `0.75 × (1-IoU) + 0.25 × appearance_distance` |
| Appearance | 96-dim L1-normalized HSV histogram, EMA α=0.7 |
| Similar-color mode | When team hue centroids within 20° → cost weight shifts +0.10 |
| Gallery TTL | 300 frames |
| MAX_LOST | 90 frames before eviction |
| Jersey OCR | EasyOCR dual-pass (normal + inverted binary) |
| OCR buffer | `JerseyVotingBuffer(maxlen=3)` — majority vote over 3 frames |

**Similar-color handling** (`color_reid.py`):
- `TeamColorTracker` runs k-means k=2 per detection
- Tracks per-team mean HSV signature via EMA
- When hue centroids within 20°: appearance weight raised +0.10, jersey number tiebreaker widened

### Stage 4 — Ball Tracking (`ball_detect_track.py`)

Three-tier fallback chain:
1. **Hough circles** — primary detector (brightness threshold + radius filter)
2. **CSRT tracker** — initialized from last confirmed Hough detection
3. **Lucas-Kanade optical flow** — fallback between detection frames

Possession assignment: ball center within player bounding box → possession attributed.

### Stage 5 — Event Detection (`event_detector.py`)

- **Shot:** ball trajectory inflection upward + release from possessor bbox
- **Pass:** rapid ball displacement (>200px) to new possessor
- **Dribble:** ball returns to same possessor after bounce detection
- **Ball fallback:** if `ball_pos` is None, use possessor 2D court coords

### Stage 6 — Feature Engineering (`feature_engineering.py`)

Computes 60+ spatial/temporal features per frame:

```
Spacing index:     convex hull area of 5-man offensive unit
Paint density:     number of players within paint boundaries
Defensive pressure: distance from nearest defender to ball handler
Speed:             feet/second per player (derived from position delta)
Acceleration:      Δspeed per frame
Shot quality inputs: defender_dist, shot_clock (Phase 2.5), fatigue flag
```

---

## Data Collection Pipeline

**Location:** `src/data/`

### Cache Strategy

All external fetches are cached with TTL:

| Source | Module | TTL | Cache path |
|---|---|---|---|
| Player gamelogs | `nba_stats.py` | 6h | `data/nba/gamelogs_{season}.json` |
| Season averages | `nba_stats.py` | 24h | `data/nba/player_avgs_{season}.json` |
| Shot charts | `shot_chart_scraper.py` | 24h | `data/nba/shots_{season}.json` |
| Play-by-play | `pbp_scraper.py` | 48h | `data/nba/pbp_{game_id}.json` |
| Hustle stats | `nba_tracking_stats.py` | 24h | `data/nba/hustle_stats_{season}.json` |
| On/off splits | `nba_tracking_stats.py` | 24h | `data/nba/on_off_{season}.json` |
| Matchup data | `nba_tracking_stats.py` | 24h | `data/nba/matchups_{season}.json` |
| Synergy play types | `nba_tracking_stats.py` | 24h | `data/nba/synergy_{season}.json` |
| BBRef advanced | `bbref_scraper.py` | 48h | `data/external/bbref_advanced_{season}.json` |
| Historical lines | `odds_scraper.py` | 7d | `data/external/historical_lines_{season}.json` |
| Contracts | `contracts_scraper.py` | 7d | `data/external/contracts_{season}.json` |
| Live props | `props_scraper.py` | 15min | `data/external/props_live.json` |
| Injury report | `injury_monitor.py` | 30min | `data/nba/injury_report.json` |

---

## Feature Engineering Details

**Location:** `src/features/feature_engineering.py`

### Bayesian Rolling Averages

```python
# Bayesian shrinkage toward season average
# Prevents small-sample noise in rolling stats
smoothed = (K * season_avg + N * rolling_avg) / (K + N)
# K = 15 games (prior weight), N = games in rolling window
```

### 57 Feature Categories

| Category | Features | Count |
|---|---|---|
| Rolling form | L5/L10/L20 pts/reb/ast/3pm/stl/blk/tov | 21 |
| Context | opp_def_rtg, home/away, rest days, B2B, travel | 6 |
| Advanced | VORP, WS/48, BPM, on/off diff | 4 |
| Shot profile | contested%, pull-up%, C&S%, defender dist | 4 |
| Synergy | ISO PPP, P&R PPP, spot-up PPP | 3 |
| Hustle | deflections/g, screen assists/g, contested shots/g | 3 |
| Shot zones | paint rate, corner 3 rate, above-break 3, mid | 4 |
| Availability | DNP risk score, injury flag, contract year | 3 |
| Momentum | Q4 shot rate, Q4 pts share, comeback pts/g | 3 |
| Matchup | matchup_fg_allowed, ref_pace, ref_fta | 3 |
| BBRef | clutch score, vs-opp history | 3 |

---

## ML Model Stack

**Location:** `src/prediction/`

### Architecture per Model

All prediction models follow the same training pattern:

```
Input: feature vector (57 dims for props, 27 dims for win prob)
    ↓
XGBoost regressor (or LogisticRegression for DNP)
  - n_estimators: 300
  - max_depth: 5
  - learning_rate: 0.05
  - subsample: 0.8
  - colsample_bytree: 0.8
    ↓
Walk-forward cross-validation (no look-ahead bias)
    ↓
Output: point prediction + confidence interval
```

### Model Storage Format

```python
# props_pts.json structure
{
  "model_type": "xgboost",
  "feature_names": ["pts_l5", "pts_season", "opp_def_rtg", ...],  # 57 features
  "booster": "<base64 encoded XGBoost model>",
  "train_mae": 0.308,
  "train_r2": 0.934,
  "trained_on": "2024-25",
  "trained_date": "2026-03-18"
}
```

---

## Possession Simulator Architecture (Phase 8)

```
For each simulation (× 10,000):
    game_state = initialize(lineup, score=0, time=2880)

    while game_state.time > 0:

        [1] play_type = PlayTypeClassifier.predict(
                possession_context, lineup, game_state)

        [2] shot_attempt = ShotSelector.predict(
                play_type, spacing, matchup)

        [3] xfg = XFGModel.predict(
                shot_attempt.zone, defender_dist,
                shot_clock, fatigue, closeout_speed)

        [4] outcome = TOFoulModel.predict(
                play_type, pressure, ball_handler_skill)

        if outcome == "shot":
            made = random() < xfg
            [5] rebound = ReboundModel.predict(
                    shot_attempt.zone, crash_speed)

        [6] fatigue_mult = FatigueModel.predict(
                player_minutes, recent_speed)

        [7] sub = SubstitutionModel.predict(
                foul_count, fatigue, score_diff, time)

        game_state.update(outcome, time_elapsed)

    simulation_results.append(game_state.box_score)

# Aggregate across 10,000 simulations
distributions = compute_percentiles(simulation_results)
# → P10, P25, mean, P75, P90 per player per stat
```

---

## PostgreSQL Schema

**Location:** `database/schema.sql`

```sql
-- Core tables
games             -- game_id, date, home_team, away_team, final_score, arena
tracking_data     -- game_id, frame, player_id, team_id, x, y, speed, event
ball_tracking     -- game_id, frame, x, y, possession_player_id
possessions       -- game_id, possession_id, team, play_type, outcome, duration
shots             -- game_id, possession_id, player_id, zone, made, xfg, defender_dist

-- Statistical tables
player_stats      -- game_id, player_id, pts, reb, ast, stl, blk, tov, min
lineup_data       -- game_id, team_id, player_ids[5], time_together, net_rtg

-- Output tables
model_predictions -- game_id, player_id, model, prediction, confidence
betting_edges     -- game_id, player_id, stat, direction, ev, kelly_size, outcome
```

**Views:**
- `v_game_summary` — aggregated game metrics (pace, eFG%, net rating)
- `v_player_performance` — rolling player stats with all 57 features joined

---

## Tracking Data Schema (CSV)

```python
{
    "game_id":         str,     # NBA game ID (e.g. "0022401234")
    "timestamp":       float,   # seconds from video start
    "frame":           int,
    "player_id":       int,     # 0–9 tracked players, 10 referee
    "team_id":         int,     # 0=home, 1=away, 2=referee
    "x_position":      float,   # court feet from left baseline (0–94)
    "y_position":      float,   # court feet from bottom sideline (0–50)
    "speed":           float,   # feet/second
    "acceleration":    float,   # feet/second²
    "ball_possession": bool,
    "event":           str,     # "shot" | "pass" | "dribble" | "none"
    "jersey_number":   int,     # from OCR, -1 if unknown
    "player_name":     str,     # from NBA API roster lookup
    # Phase 2.5 additions:
    "ankle_x":         float,   # YOLOv8-pose ankle keypoint
    "ankle_y":         float,
}
```
