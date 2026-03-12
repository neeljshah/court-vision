# NBA AI System

An end-to-end NBA analytics and prediction platform combining computer vision player tracking, official NBA statistics, and machine learning.

---

## What This System Does

The system processes NBA broadcast video to extract player and ball movement data, enriches it with official statistics, and feeds machine learning models to generate predictions and analytics. The final product is a web application with three interfaces: a **Betting Dashboard**, an **Analytics Dashboard**, and an **AI Chat assistant**.

```
NBA Video (broadcast .mp4)
    ↓
Computer Vision Tracking Pipeline
    → player positions, ball location, spacing, possession, shot context
    ↓
NBA API Enrichment
    → shot outcomes, possession results, lineups, box scores, schedule
    ↓
Machine Learning Models
    → shot quality, possession outcome, player props, win probability
    ↓
Web App + AI Chat (Claude API with tool use)
    → Betting Dashboard | Analytics Dashboard | AI Chat
```

---

## Current Status

| Module | Status |
|---|---|
| Player detection (YOLOv8n) | ✅ Working |
| Advanced tracker (Kalman + Hungarian + Re-ID) | ✅ Working |
| Ball tracking (Hough + CSRT + optical flow) | ✅ Working |
| Court rectification (SIFT + homography) | ✅ Working |
| Analytics engine (shot quality, pressure, momentum) | ✅ Working |
| NBA API data enrichment | ✅ Working |
| Feature engineering pipeline | ✅ Working |
| ML models (shot, possession, win probability) | 🔲 In progress |
| Betting edge detection | 🔲 Planned |
| Web app + AI chat | 🔲 Planned |

---

## Capabilities

### Tracking
- Detects and tracks up to 10 players + ball per frame from broadcast video
- Assigns persistent player IDs across the full game using appearance re-identification
- Maps all positions onto a 2D court coordinate system via homography
- Detects events: dribbles, passes, shots, ball possession changes

### Analytics
- **Shot quality** — defender proximity, shooter positioning, court zone, shot type
- **Defensive pressure** — nearest defender distance, help defense coverage, rotation timing
- **Team spacing** — convex hull area, floor balance, drive-and-kick opportunities
- **Momentum** — scoring run detection, pace shifts, pressure windows
- **Possession classification** — half-court vs transition, set play vs freelance

### Machine Learning (planned)
- Pre-game win probability from team stats and context
- Shot make/miss probability from tracking features
- Possession outcome (scored / turnover / foul)
- Player performance projections (points, rebounds, assists)
- Live in-game win probability (LSTM over possession sequence)
- Lineup impact and chemistry ratings

---

## Data Generated

The system generates structured data at multiple levels. See [DATA_OUTPUTS.md](DATA_OUTPUTS.md) for the full schema.

- Per-frame player and ball positions (2D court coordinates)
- Per-possession: outcome, shot location, spacing, defensive setup
- Per-game: team and player aggregates, lineup splits, shot charts
- Contextual: schedule, rest days, travel load, home/away

---

## Predictions

See [MACHINE_LEARNING.md](MACHINE_LEARNING.md) for model details.

- **Win probability** — pre-game and live in-game
- **Expected score margin** — team offensive/defensive rating projections
- **Shot success probability** — tracking-based shot quality score
- **Expected points per possession** — possession value model
- **Player prop projections** — points, rebounds, assists over/under
- **Lineup performance** — projected net rating for any 5-man unit

---

## Front-End Dashboards

See [FRONTEND_OVERVIEW.md](FRONTEND_OVERVIEW.md) for full interface description.

- **Betting Dashboard** — model predictions vs live sportsbook lines, edge scores, best bets
- **Analytics Dashboard** — court heatmaps, shot charts, spacing timelines, lineup splits
- **AI Chat** — Claude-powered assistant with tool access to all predictions and live data

---

## Quick Start

```bash
conda activate basketball_ai
cd nba-ai-system

python run.py                        # process full video
python run.py --frames 100 --debug   # 100 frames with debug overlays
python run.py --eval                 # print tracking quality metrics
```

Output is written to `data/tracking_data.csv`.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Detection | YOLOv8n (ultralytics) |
| Tracking | Kalman filter + Hungarian algorithm |
| Court mapping | SIFT + homography (OpenCV) |
| Re-identification | HSV appearance gallery + CBAM re-ID model |
| Analytics | Python, NumPy, custom modules |
| ML models | XGBoost, PyTorch |
| Backend (planned) | FastAPI |
| Frontend (planned) | React + Next.js, D3 / Recharts |
| AI Chat (planned) | Claude API with tool use |
| Database (planned) | PostgreSQL |

---

## Documentation

| File | Contents |
|---|---|
| [DATA_OUTPUTS.md](DATA_OUTPUTS.md) | All data categories and fields produced by the system |
| [MACHINE_LEARNING.md](MACHINE_LEARNING.md) | Model objectives, training data, and prediction outputs |
| [ANALYTICS_AND_BETTING.md](ANALYTICS_AND_BETTING.md) | Analytics and sports betting use cases |
| [FRONTEND_OVERVIEW.md](FRONTEND_OVERVIEW.md) | Dashboard and interface descriptions |
| [docs/architecture.md](docs/architecture.md) | Technical architecture detail |
| [docs/tracking_pipeline.md](docs/tracking_pipeline.md) | Tracking pipeline internals |
