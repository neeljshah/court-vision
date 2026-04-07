<div align="center">

# CourtVision

**Possession-level spatial tracking from broadcast video · 90 ML models · Monte Carlo game simulation**

[![Python 3.9](https://img.shields.io/badge/Python-3.9-3776AB?logo=python&logoColor=white)](https://python.org)
[![PyTorch](https://img.shields.io/badge/PyTorch-2.0.1-EE4C2C?logo=pytorch&logoColor=white)](https://pytorch.org)
[![YOLOv8](https://img.shields.io/badge/YOLOv8-Ultralytics-FF6600)](https://ultralytics.com)
[![XGBoost](https://img.shields.io/badge/XGBoost-1.7-189AB4)](https://xgboost.readthedocs.io)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110-009688?logo=fastapi)](https://fastapi.tiangolo.com)
[![Tests](https://img.shields.io/badge/tests-passing-4CAF50)](https://github.com/neeljshah/nba-ai-system/actions)
[![License](https://img.shields.io/badge/license-MIT-blue)](LICENSE)

</div>

---

---

## What Is This

CourtVision extracts defender distance, spacing index, drive frequency, and fatigue proxies from NBA broadcast footage — spatial metrics that exist in no public dataset and that Second Spectrum provides to NBA teams at **$1M+/yr**. Those features feed a **90-model ML stack** that runs **10,000 Monte Carlo simulations** per game to produce full statistical distributions for every player, compares them against sportsbook lines, and surfaces positive-EV edges. The complete pipeline — from raw `.mp4` to bet recommendation — runs on a single consumer GPU.

---

## Key Results

| Model | Metric | Value |
|-------|--------|-------|
| Win Probability | Accuracy | **69.1%** |
| Win Probability | Brier Score | **0.203** |
| Expected Field Goal (xFG v1) | Brier Score | **0.226** |
| Player Props (pts) | MAE | **0.308** |
| Player Props (all 7) | R² | **>0.93** |
| DNP Predictor | AUC | **0.979** |
| Matchup Model | R² | **0.796** |
| CV Tracker throughput | FPS | **15 fps** (RTX 4060 8 GB) |
| Shot chart coverage | Shots | **221,866** across 3 seasons |
| Play-by-play coverage | Games | **3,627 / 3,685 (98.4%)** |

---

## Architecture

Broadcast video is ingested by a YOLOv8n + Kalman/Hungarian tracking pipeline that maps every player to real-world court coordinates via SIFT homography, assigns identities through OSNet deep re-ID and EasyOCR jersey reads, and fires an event detector for shots, passes, and dribbles. Per-frame spatial data is enriched with three seasons of NBA API context (shot charts, play-by-play, hustle stats, matchups) and transformed into 60+ features that train the ML stack. A 7-model possession chain then runs 10,000 Monte Carlo simulations to produce stat distributions, which are compared against sportsbook lines by a Kelly-sized betting portfolio engine.

---

## Tech Stack

**Vision**

![YOLOv8](https://img.shields.io/badge/YOLOv8-detection%20%2B%20pose-FF6600)
![OpenCV](https://img.shields.io/badge/OpenCV-SIFT%20%2B%20optical%20flow-5C3EE8)
![EasyOCR](https://img.shields.io/badge/EasyOCR-jersey%20numbers-2196F3)
![OSNet](https://img.shields.io/badge/OSNet-deep%20re--ID-9C27B0)

**ML**

![PyTorch](https://img.shields.io/badge/PyTorch-2.0.1-EE4C2C?logo=pytorch)
![XGBoost](https://img.shields.io/badge/XGBoost-90%20models-189AB4)
![scikit-learn](https://img.shields.io/badge/scikit--learn-Ridge%20%2F%20Logistic-F7931E)

**Data**

![nba_api](https://img.shields.io/badge/nba__api-stats%20%2B%20PBP-17408B)
![pandas](https://img.shields.io/badge/pandas-feature%20engineering-150458)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-14-336791?logo=postgresql)

**Infrastructure**

![FastAPI](https://img.shields.io/badge/FastAPI-REST%20API-009688?logo=fastapi)
![Redis](https://img.shields.io/badge/Redis-task%20queue-DC382D?logo=redis)
![Celery](https://img.shields.io/badge/Celery-async%20pipeline-37814A)
![Docker](https://img.shields.io/badge/Docker-containerized-2496ED?logo=docker)

---

## Features

### Tracking
- Tracks **10 players simultaneously** at 15 fps; Kalman-predicted positions survive occlusion for up to 90 frames
- **SIFT court homography** maps every player to real-world feet coordinates (ft_x, ft_y) with portrait-mode guard for vertically-cropped broadcasts
- **OSNet re-ID** (256-dim embeddings) + 99-dim HSV histogram embeddings recover identity after off-screen exits (gallery TTL = 300 frames)
- **YOLOv8-pose** ankle keypoints replace bbox-bottom heuristics for sub-foot court accuracy
- **EasyOCR dual-pass** jersey OCR with voting buffer resolves player names from NBA roster lookup

### Prediction
- **Win probability**: XGBoost on 27 features, **69.1%** accuracy, Brier **0.203**
- **7 player prop regressors**: pts / reb / ast / fg3m / stl / blk / tov — R² **>0.93**, MAE pts **0.308**
- **Ridge meta-model** stacks all 7 props into a confidence-gated ensemble
- **xFG v1**: trained on **221,866** shots; Brier **0.226** — enables shot quality vs. volume decomposition
- **DNP predictor**: AUC **0.979**; fires load-management and injury-return alerts

### Betting Edge
- **Kelly criterion** position sizing with CLV tracking and post-game settlement
- **Closing-line value** (CLV) audit across **1,225+** historical games
- Arbitrage detection across multiple books; sharp-money line-movement signal
- Paper trading mode for edge validation before live deployment

### Analytics
- **96 metrics** per player per game: spacing index, drive frequency, handler isolation, fatigue proxy, shot quality differential
- **10 chart types**: D3 shot charts, lineup net-rating matrix, zone tendency heatmaps, momentum curves
- Synergy play-type integration (300 offensive + 300 defensive archetypes)
- On/off splits, hustle stats, defender zone profiles across all three seasons

---

## Quick Start

```bash
# Clone
git clone https://github.com/neeljshah/nba-ai-system.git
cd nba-ai-system

# Environment
conda create -n basketball_ai python=3.9 -y
conda activate basketball_ai
pip install -r requirements.txt

# Configure
cp .env.example .env
# Set DATABASE_URL, ODDS_API_KEY in .env

# Verify
python -m pytest tests/ -q

# Predict a game
python src/prediction/game_prediction.py --predict GSW BOS

# Start API
uvicorn api.main:app --reload --port 8000
```

Full setup, environment variables, and GPU configuration: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)

---

## Project Roadmap

| Phase | Name | Status | Description |
|-------|------|--------|-------------|
| 1 | Data Infrastructure | ✅ | PostgreSQL schema, NBA API scraper, schedule |
| 2 | CV Tracker | ✅ | YOLOv8, Kalman/Hungarian, OSNet re-ID, 431 tests |
| 3 | NBA API Data | ✅ | 221K shots, 98.4% PBP, 3 seasons, all stat types |
| 4 | Tier 1 Models | ✅ | Win prob, props ×7, xFG v1, DNP, matchup |
| 5 | External Factors | ✅ | Injury risk, load management, public fade, line movement |
| 4.6 | Pre-Phase Enrichment | ✅ | Spatial gap-fill, team abbrev, player name backfill |
| F | Full Game Processing | 🔲 | 20+ full broadcast games, shot/possession enrichment |
| G | CV Data Collection | 🔲 | Season 2025-26 batch — 50 games, 2 per team |
| 7 | Tier 2–3 Models | 🔲 | xFG v2 with CV spatial features (needs 20 games) |
| 8 | Possession Simulator | 🔲 | 7-model chain, 10K Monte Carlo per game |
| 9 | Feedback Loop | 🔲 | Nightly retrain → self-improving pipeline |
| 10 | Tier 4–5 Models | 🔲 | Fatigue, lineup chemistry (needs 50–100 games) |
| 11 | Betting Infrastructure | 🔲 | Kelly sizing, CLV backtest, paper trading |
| 12 | Full Monte Carlo | 🔲 | All 90 models, full stat distributions |
| 13 | FastAPI Backend | 🔲 | 12 endpoints, Redis, WebSocket live updates |
| 14 | Analytics Dashboard | 🔲 | Next.js, D3 shot charts, 10 visualization types |
| 15 | AI Chat | 🔲 | Claude API + `render_chart` inline in conversation |
| 16 | Live Win Probability | 🔲 | 200+ games, LSTM, real-time WebSocket feed |
| 17 | Infrastructure | 🔲 | Docker, CI/CD, cloud GPU, monitoring |

Phase 17 target: win probability accuracy **76–78%** (vs. Second Spectrum ~80%), props MAE ~**0.12 pts**.

---

## Documentation

| Document | Contents |
|----------|----------|
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | System design, module dependencies, data flow |
| [docs/ML_MODELS.md](docs/ML_MODELS.md) | Model specs, feature sets, training procedures |
| [docs/CV_TRACKING.md](docs/CV_TRACKING.md) | Tracking pipeline, homography, re-ID, OCR |
| [docs/DATA_SCHEMA.md](docs/DATA_SCHEMA.md) | PostgreSQL schema, CSV formats, API cache structure |
| [docs/API.md](docs/API.md) | FastAPI endpoints, request/response schemas |

---

## License

MIT — see [LICENSE](LICENSE).
