# NBA AI System

An end-to-end NBA analytics and prediction platform: computer vision player tracking → NBA API enrichment → machine learning models → betting edge detection → analytics dashboards → AI chat.

---

## What This System Does

```
NBA Broadcast Video (.mp4)
    ↓
Computer Vision Tracking Pipeline
    → player positions (2D court), ball location, spacing, possession, events, shot context
    ↓
NBA API Enrichment
    → shot outcomes, possession results, lineups, box scores, schedule, rest, travel
    ↓
PostgreSQL Database
    → all tracking + stats stored, versioned, queryable
    ↓
Machine Learning Models
    → win probability, shot quality, possession outcome, player props, lineup impact
    ↓
Betting Edge Detection
    → model probability vs sportsbook implied probability → flag value bets
    ↓
FastAPI Backend
    → /predictions, /props, /analytics, /betting-edges, /chat
    ↓
Web App (React + Next.js)
    → Betting Dashboard | Analytics Dashboard | AI Chat (Claude API)
```

---

## Three Final Products

### 1. Betting Dashboard
- Live sportsbook lines (spread, total, moneyline, props) via The Odds API
- Model prediction vs implied probability for every market
- Edge score and star rating (1–3★) per bet
- Best bets panel — highest-edge opportunities ranked automatically
- Historical model accuracy vs closing line

### 2. Analytics Dashboard
- Court heatmaps — shot locations, player movement density
- Win probability chart over all possessions in a game
- Team spacing over time (convex hull area)
- Shot quality by zone — xFG vs actual eFG%
- Lineup performance — any 5-man unit, net rating, spacing score
- Ball movement network — pass map, touch distribution
- Defensive pressure timeline
- Momentum chart — EMA-smoothed scoring run detection

### 3. AI Chat Interface
- Powered by Claude API with tool use calling the backend
- Tools: `get_game_prediction()`, `get_player_props()`, `get_analytics()`, `get_lineup_data()`, `get_betting_edges()`
- Answers questions with real data, not general knowledge
- Examples: *"What lineup should the Celtics use vs zone defense?"* / *"Which props have the most edge tonight?"*

---

## Current Build Status

### Tracking (✅ Complete)
| Module | Status | File |
|---|---|---|
| Player detection (YOLOv8n) | ✅ | `src/tracking/player_detection.py` |
| Advanced tracker (Kalman + Hungarian) | ✅ | `src/tracking/advanced_tracker.py` |
| Appearance re-identification (HSV gallery) | ✅ | `src/tracking/advanced_tracker.py` |
| Ball tracking (Hough + CSRT + optical flow) | ✅ | `src/tracking/ball_detect_track.py` |
| Court rectification (SIFT + homography) | ✅ | `src/tracking/rectify_court.py` |
| Event detection (shot/pass/dribble) | ✅ | `src/tracking/event_detector.py` |
| Spatial metrics (spacing, paint, isolation) | ✅ | `src/pipeline/unified_pipeline.py` |

### Analytics (✅ Complete)
| Module | Status | File |
|---|---|---|
| Shot quality scoring | ✅ | `src/analytics/shot_quality.py` |
| Defensive pressure scoring | ✅ | `src/analytics/defense_pressure.py` |
| Momentum tracking | ✅ | `src/analytics/momentum.py` |
| Feature engineering (60+ ML features) | ✅ | `src/features/feature_engineering.py` |

### Data Pipeline (✅ Complete)
| Module | Status | File |
|---|---|---|
| Unified tracking → CSV pipeline | ✅ | `src/pipeline/unified_pipeline.py` |
| NBA API enrichment (shot labels, possession outcomes) | ✅ | `src/data/nba_enricher.py` |
| NBA stats fetcher | ✅ | `src/data/nba_stats.py` |
| Video downloader (yt-dlp) | ✅ | `src/data/video_fetcher.py` |
| Single-command clip processor | ✅ | `run_clip.py` |

### ML Models (🔲 In Progress)
| Module | Status | File |
|---|---|---|
| Pre-game win probability | 🔲 Next | `src/prediction/win_probability.py` |
| Game prediction | 🔲 Next | `src/prediction/game_prediction.py` |
| Shot quality model | 🔲 Needs 20 games | `src/analytics/shot_quality.py` |
| Possession outcome model | 🔲 Needs 50 games | — |
| Player prop models (pts/reb/ast) | 🔲 Planned | — |
| Live win probability (LSTM) | 🔲 Needs 200 games | — |
| Lineup chemistry | 🔲 Needs 100 games | — |

### Not Built Yet
| Component | Status |
|---|---|
| Jersey number OCR (named player tracking) | 🔲 Planned |
| PostgreSQL schema + migrations | 🔲 Planned |
| NBA API schedule context (rest, travel) | 🔲 Planned |
| NBA API lineup data (on/off splits) | 🔲 Planned |
| Automated game processing pipeline | 🔲 Planned |
| The Odds API integration | 🔲 Planned |
| Historical odds + backtesting framework | 🔲 Planned |
| FastAPI backend | 🔲 Planned |
| React frontend | 🔲 Planned |
| AI Chat (Claude API + tool use) | 🔲 Planned |
| Docker + deployment | 🔲 Planned |

---

## Full Build Roadmap

See [ROADMAP.md](ROADMAP.md) for detailed task breakdown per phase.

### Phase 1 — Data Infrastructure
- PostgreSQL schema, NBA API schedule context, lineup data, opponent features, caching layer

### Phase 2 — Tracking Improvements
- Jersey number OCR (named player identity), HSV re-ID improvements, referee filtering

### Phase 3 — First ML Models (NBA API only, no tracking required)
- Pre-game win probability, player prop models (pts/reb/ast), backtesting framework

### Phase 4 — Tracking-Enhanced ML Models
- Shot quality model, possession outcome model, betting edge detection logic

### Phase 5 — Automated Game Processing
- Nightly pipeline, job queue, historical odds collection, dataset compounding

### Phase 6 — Betting Infrastructure
- The Odds API integration, historical odds storage, edge scoring, CLV backtesting, star rating

### Phase 7 — Backend API
- FastAPI: `/predictions`, `/props`, `/analytics`, `/betting-edges`, `/chat`, caching, rate limiting

### Phase 8 — Frontend
- React + Next.js, analytics dashboard, betting dashboard, court visualizations (D3)

### Phase 9 — AI Chat
- Claude API with tool use, backend tool endpoints, context management

### Phase 10 — Live Win Probability
- LSTM on possession sequences, real-time WebSocket updates, 200+ game dataset

### Phase 11 — Infrastructure
- Docker, CI/CD, cloud deployment, model monitoring, automated retraining

---

## Data Generated

Each game clip processed produces:

| File | Contents |
|---|---|
| `tracking_data.csv` | Per-frame: player ID, team, 2D position, speed, possession, event, spacing |
| `possessions.csv` | Per-possession: type, duration, spacing, pressure, shot attempted, outcome |
| `shot_log.csv` | Per-shot: who, where, zone, defender distance, spacing, made/missed |
| `features.csv` | 60+ ML-ready engineered features per frame |
| `player_clip_stats.csv` | Per-player aggregates: distance, velocity, possession%, shots, drive rate |
| `shot_quality.csv` | Per-shot quality score (0–1) |
| `momentum.csv` | Per-frame momentum score per team |
| `defense_pressure.csv` | Per-frame defensive pressure score |

**Volume needed for ML:**
- 20 games → shot quality model
- 50 games → possession outcome model
- 100 games → lineup chemistry model
- 200+ games → live win probability LSTM

See [DATA_OUTPUTS.md](DATA_OUTPUTS.md) for full field-level schema.

---

## ML Models

See [MACHINE_LEARNING.md](MACHINE_LEARNING.md) for full model specs.

| Model | Type | Needs | Output |
|---|---|---|---|
| Pre-game win probability | XGBoost | NBA API only | Win%, spread |
| Player prop (pts/reb/ast) | XGBoost | NBA API only | Projected stats |
| Shot quality | XGBoost | 20+ games tracked | xFG per shot |
| Possession outcome | XGBoost | 50+ games tracked | Score/TO/foul % |
| Lineup chemistry | Regression | 100+ games tracked | Net rating |
| Live win probability | LSTM | 200+ games tracked | Win% per possession |

---

## Tech Stack

| Layer | Technology |
|---|---|
| Detection | YOLOv8n (ultralytics) |
| Tracking | Kalman filter + Hungarian algorithm (scipy) |
| Court mapping | SIFT + homography (OpenCV) |
| Re-identification | 96-dim HSV histogram gallery + CBAM re-ID model |
| Analytics | Python, NumPy, Pandas |
| ML models | XGBoost, LightGBM, PyTorch (LSTM) |
| Database | PostgreSQL |
| Backend API | FastAPI (Python) |
| Frontend | React + Next.js, D3.js, Recharts, Tailwind |
| AI Chat | Claude API with tool use |
| Odds data | The Odds API |
| Environment | conda `basketball_ai`, Python 3.9, CUDA 11.8 |

---

## Quick Start

```bash
conda activate basketball_ai
cd nba-ai-system

# Process a game clip end-to-end
python run_clip.py --video game.mp4 --game-id 0022300001 --period 1 --start 0

# Full video with debug overlays
python run.py --frames 100 --debug

# Print tracking quality metrics
python run.py --eval
```

Output is written to `data/`.

---

## Documentation

| File | Contents |
|---|---|
| [ROADMAP.md](ROADMAP.md) | Full phase-by-phase build plan with task breakdown |
| [DATA_OUTPUTS.md](DATA_OUTPUTS.md) | All data categories and fields produced by the system |
| [MACHINE_LEARNING.md](MACHINE_LEARNING.md) | Model objectives, training data, build order |
| [ANALYTICS_AND_BETTING.md](ANALYTICS_AND_BETTING.md) | Analytics and sports betting use cases |
| [FRONTEND_OVERVIEW.md](FRONTEND_OVERVIEW.md) | Dashboard and interface descriptions |
| [docs/architecture.md](docs/architecture.md) | Technical architecture detail |
| [docs/tracking_pipeline.md](docs/tracking_pipeline.md) | Tracking pipeline internals |
