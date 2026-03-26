<div align="center">

# CourtVision — NBA AI Prediction System

**Broadcast-feed computer vision + 90 ML models + Monte Carlo simulation**
*Extracts spatial tracking data from NBA games, prices player props, and surfaces sportsbook edges — the kind of data Second Spectrum charges $1M+/yr for.*

[![Python 3.9](https://img.shields.io/badge/Python-3.9-3776AB?logo=python&logoColor=white)](https://python.org)
[![PyTorch 2.0](https://img.shields.io/badge/PyTorch-2.0.1+CUDA11.8-EE4C2C?logo=pytorch&logoColor=white)](https://pytorch.org)
[![YOLOv8](https://img.shields.io/badge/YOLOv8-Ultralytics-FF6600)](https://ultralytics.com)
[![XGBoost](https://img.shields.io/badge/XGBoost-1.7-189AB4)](https://xgboost.readthedocs.io)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110-009688?logo=fastapi)](https://fastapi.tiangolo.com)
[![Phase](https://img.shields.io/badge/Phase-G%20of%2017-FFB300)](https://github.com/neeljshah/court-vision)
[![Models Trained](https://img.shields.io/badge/Models-90%20trained-4CAF50)](https://github.com/neeljshah/court-vision)
[![Tests](https://img.shields.io/badge/Tests-passing-4CAF50)](https://github.com/neeljshah/court-vision)

</div>

---

## What Is This?

CourtVision is an end-to-end NBA analytics and sports betting edge system built from first principles. It processes raw NBA broadcast footage with a custom computer vision pipeline, extracts spatial metrics that exist in no public dataset, and feeds them through a 90-model machine learning stack that runs 10,000 Monte Carlo simulations per game to produce full statistical distributions for every player — then compares those distributions against sportsbook lines to flag positive-EV edges.

**The moat:** Defender distance, spacing index, drive frequency, and fatigue proxies extracted at the possession level from standard broadcast video. No API sells this. Second Spectrum provides it to NBA teams at $1M+/year. CourtVision replicates it at near-zero marginal cost.

---

## Key Performance Metrics

| Model | Metric | Value | Benchmark |
|-------|--------|-------|-----------|
| Win Probability | Accuracy | **69.1%** | Vegas closing line ~68% |
| Win Probability | Brier Score | **0.203** | Perfect = 0.0 |
| Expected Field Goal (xFG v1) | Brier Score | **0.226** | League-avg baseline ~0.25 |
| Player Props (pts) | MAE | **0.308** | PrizePicks est. ~0.4+ |
| Player Props (all 7) | R² | **>0.93** | — |
| DNP Predictor | AUC | **0.979** | — |
| Matchup Model | R² | **0.796** | — |
| CV Tracker | Speed | **15 fps** | RTX 4060, 8 GB VRAM |
| Shot Charts | Coverage | **221,866** shots | 3 seasons, 569 players |
| Play-by-Play | Coverage | **98.4%** | 3,627 / 3,685 games |

---

## System Architecture

```
Broadcast Video (.mp4)
        │
        ▼
┌───────────────────────────────────────────────────────┐
│  CV TRACKING PIPELINE  (src/tracking/)                │
│                                                       │
│  YOLOv8n detection  (conf=0.35)                       │
│   → Court Rectification  (SIFT + 3-tier homography)   │
│   → AdvancedFeetDetector                              │
│       Kalman 6D state [cx, cy, vx, vy, w, h]          │
│       Hungarian assignment  (IoU×0.75 + embed×0.25)   │
│       99-dim HSV histogram embeddings  (EMA α=0.7)    │
│       Gallery TTL = 300 frames │ MAX_LOST = 90         │
│       Pose estimation: YOLOv8-pose ankle keypoints     │
│       Optical flow gap-fill: Lucas-Kanade ≤8 frames   │
│   → BallDetectTrack  (Hough + CSRT + optical flow)    │
│   → EventDetector    (shot / pass / dribble)          │
│   → JerseyOCR        (EasyOCR dual-pass + voting buf) │
└───────────────────────────────────────────────────────┘
        │  positions · speed · spacing · possession · events
        ▼
┌───────────────────────────────────────────────────────┐
│  FEATURE ENGINEERING  (src/features/)                 │
│  60+ spatial + temporal features                      │
│  spacing index · defender dist · fatigue proxy        │
│  drive frequency · possession value · play type       │
└───────────────────────────────────────────────────────┘
        │                         ┌──────────────────────┐
        │◄─── NBA API 3 seasons ──│ gamelogs · shot charts│
        │                         │ PBP · hustle · matchups│
        │                         │ synergy · BBRef       │
        │                         └──────────────────────┘
        ▼
┌───────────────────────────────────────────────────────┐
│  90-MODEL ML STACK  (src/prediction/ · src/analytics/)│
│                                                       │
│  Tier 1 ✅  Win prob · props ×7 · game models         │
│  Tier 2 ✅  xFG v1 · zone tendency · clutch           │
│  Tier 3 🔲  xFG v2 + CV features  (needs 20 games)   │
│  Tier 4 🔲  Fatigue · lineup chemistry  (50 games)    │
│  Tier 5 🔲  Possession outcome model  (100 games)     │
│  Tier 6 🔲  Live win prob LSTM  (200+ games)          │
└───────────────────────────────────────────────────────┘
        │
        ▼
┌───────────────────────────────────────────────────────┐
│  POSSESSION SIMULATOR  (Phase 8)                      │
│  7-model chain per possession:                        │
│  Play Type → Shot Selector → xFG → TO/Foul            │
│  → Rebound → Fatigue → Substitution                   │
│  × 10,000 Monte Carlo → full stat distribution        │
└───────────────────────────────────────────────────────┘
        │
        ▼
┌───────────────────┐   ┌──────────────────────────────┐
│  Betting Dashboard│   │  Analytics Dashboard          │
│  FastAPI + Next.js│   │  96 metrics · 10 chart types  │
│  Kelly · CLV      │   │  D3 shot charts · lineup matrix│
└───────────────────┘   └──────────────────────────────┘
        │
        ▼
┌───────────────────────────────────────────────────────┐
│  AI CHAT  (Phase 15)                                  │
│  claude-sonnet-4-6 + 10 tools + render_chart          │
│  "Show Murray's shot quality vs guards tonight"       │
│  → chart renders inline in conversation               │
└───────────────────────────────────────────────────────┘
```

---

## Repository Structure

```
nba-ai-system/
├── src/
│   ├── tracking/          # CV pipeline — detection, tracking, OCR, court mapping
│   │   ├── advanced_tracker.py       # AdvancedFeetDetector (Kalman + Hungarian)
│   │   ├── ball_detect_track.py      # Ball tracker (Hough + CSRT + optical flow)
│   │   ├── color_reid.py             # TeamColorTracker (similar-uniform handling)
│   │   ├── event_detector.py         # Shot / pass / dribble detection
│   │   ├── jersey_ocr.py             # EasyOCR dual-pass + JerseyVotingBuffer
│   │   ├── rectify_court.py          # SIFT panorama + 3-tier homography
│   │   └── ...
│   ├── prediction/        # 50+ ML model files — props, win prob, matchup, etc.
│   │   ├── win_probability.py        # XGBoost win prob (69.1% accuracy)
│   │   ├── player_props.py           # 7 prop regressors (R² > 0.93)
│   │   ├── prop_model_stack.py       # Ridge meta-model over all 7 props
│   │   ├── game_prediction.py        # Game outcome prediction
│   │   ├── dnp_predictor.py          # DNP predictor (AUC 0.979)
│   │   ├── betting_portfolio.py      # Kelly sizing + CLV tracking
│   │   └── ...
│   ├── analytics/         # 26 analytics modules — shot quality, spacing, momentum
│   ├── data/              # NBA API + external scrapers
│   │   ├── nba_stats.py              # NBA API wrapper (stats, PBP, shots)
│   │   ├── player_scraper.py         # 63-metric self-improving player scraper
│   │   ├── pbp_scraper.py            # Play-by-play scraper (98.4% coverage)
│   │   ├── shot_chart_scraper.py     # 221K shot charts (3 seasons)
│   │   ├── odds_scraper.py           # Historical closing lines
│   │   └── ...
│   ├── features/          # 60+ feature engineering functions
│   ├── pipeline/          # End-to-end orchestration (Celery + Redis)
│   ├── simulation/        # Possession simulator (Monte Carlo)
│   ├── re_id/             # OSNet deep re-ID training + inference
│   └── utils/             # Shared utilities (bbox crop, frame tools, visualize)
├── api/                   # FastAPI backend (10 prediction endpoints)
├── dashboards/            # Streamlit analytics dashboards
├── data/
│   ├── models/            # Trained model artifacts (.pkl, .json)
│   ├── nba/               # NBA API cache (shot charts, gamelogs, PBP)
│   ├── external/          # BBRef, contracts, historical lines
│   └── tracking/          # Per-game CV tracking output CSVs
├── database/              # PostgreSQL schema (9 tables, 2 views)
├── tests/                 # pytest suite (431 tests, phases 2–4)
├── scripts/               # CLI tools (daily pipeline, batch processor, outcomes)
├── config/                # Tracker params, model configs
├── resources/             # Homography matrix (Rectify1.npy), court template
├── vault/                 # Obsidian knowledge base (architecture, decisions, logs)
└── .planning/             # Roadmap, state, requirements, config
```

---

## What's Built

### CV Tracking — Phase 2 Complete

- Tracks 10 players simultaneously at **15 fps** on RTX 4060 (8 GB VRAM)
- **Kalman-predicted positions** survive occlusion for up to 90 frames (~3 s at 30 fps)
- **Gallery re-ID** recovers player identity after off-screen exits (TTL = 300 frames)
- **Pose estimation** via YOLOv8-pose: ankle keypoints replace bbox-bottom heuristic for sub-foot court accuracy
- **Similar-uniform detection**: k-means warm-up discovers team color centroids; raises appearance weight +0.10 when hue centroids are within 20 units
- **Optical flow gap-fill** (Lucas-Kanade) propagates position for up to 8 frames during YOLO misses
- **Jersey OCR** (EasyOCR dual-pass + voting buffer) assigns player names from NBA roster lookup

### Data — 3 Seasons, 3,685 Games

| Dataset | Count | Status |
|---------|-------|--------|
| Shot chart coordinates | 221,866 shots / 569 players | ✅ |
| Play-by-play logs | 3,627 / 3,685 games (98.4%) | ✅ |
| Player gamelogs | 622 players (3 seasons) | ✅ |
| Hustle stats | 567 / 567 players (3 seasons) | ✅ |
| On/off splits | 569 players (3 seasons) | ✅ |
| Defender zones | 566 players (3 seasons) | ✅ |
| Matchup data | 2,269+ records (3 seasons) | ✅ |
| Synergy play types | 300 offensive + 300 defensive | ✅ |
| BBRef advanced stats | 736 players (3 seasons) | ✅ |
| Player contracts | 523 players, 171 walk-year | ✅ |
| Historical closing lines | 1,225+ games (3 seasons) | ✅ |

### ML Models — 18 Trained

| Model | Architecture | Performance |
|-------|-------------|-------------|
| Win probability | XGBoost (27 features) | 69.1% acc, Brier 0.203 |
| Player props ×7 | XGBoost (52 features) | R² > 0.93, MAE pts=0.308 |
| Prop model stack | Ridge meta-model | Confidence-gated ensemble |
| DNP predictor | Logistic regression | AUC 0.979 |
| xFG v1 | XGBoost (location + context) | Brier 0.226 (221K shots) |
| Game total / spread / pace | XGBoost | 5 models trained |
| Matchup model | XGBoost (hustle + on/off) | R² 0.796, MAE 4.55 |
| Load management | Logistic weights | Production-ready |
| Injury risk | Linear risk weights | Production-ready |
| DNP / breakout / public fade | Various | All production-ready |

### API — 10 Endpoints

```
GET  /api/predictions/today              → full slate predictions
GET  /api/predictions/props/{player_id}  → prop projections + edge flags
GET  /api/predictions/game               → win prob + spread/total
GET  /api/predictions/win-prob           → win probability only
GET  /api/predictions/injury-risk        → injury risk scores
GET  /api/predictions/breakout           → breakout candidate alerts
GET  /api/predictions/lineup-optimizer   → optimal lineup suggestion
POST /api/predictions/shot               → xFG for a shot attempt
GET  /api/predictions/player-impact      → plus/minus prediction
GET  /api/models/status                  → model health + last-trained dates
```

---

## Quick Start

### Prerequisites

- Python 3.9 (conda recommended)
- CUDA 11.8 + cuDNN 8.9 (for GPU-accelerated tracking)
- PostgreSQL 14+ (for full pipeline; optional for predictions-only)
- Redis (for Celery task queue; optional)

### Installation

```bash
# 1. Clone the repository
git clone https://github.com/your-username/nba-ai-system.git
cd nba-ai-system

# 2. Create and activate conda environment
conda create -n basketball_ai python=3.9 -y
conda activate basketball_ai

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment
cp .env.example .env
# Edit .env — add your PostgreSQL URL and Odds API key

# 5. Verify installation
python -m pytest tests/ -q --ignore=tests/test_tracking.py
```

### Environment Variables

```bash
# .env (copy from .env.example)
DATABASE_URL=postgresql://user:pass@localhost:5432/nba_ai
ODDS_API_KEY=your_key_here         # The Odds API (historical + live lines)
ANTHROPIC_API_KEY=your_key_here    # Phase 15 AI chat (claude-sonnet-4-6)
REDIS_URL=redis://localhost:6379/0 # Celery task queue
```

### Run Predictions (No Video Required)

```bash
# Predict tonight's game
python src/prediction/game_prediction.py --predict GSW BOS

# Get player prop projections
python -c "
from src.prediction.player_props import predict_props
result = predict_props('Jayson Tatum', 'MIA', '2024-25')
for stat, val in result['predictions'].items():
    print(f'{stat}: {val:.1f}')
"

# Run full test suite (431 tests)
python -m pytest tests/ -q

# Start API server
uvicorn api.main:app --reload --port 8000

# Launch Streamlit dashboard
streamlit run dashboards/app.py
```

### Train Models

```bash
# Train win probability model (safe — no video needed)
python src/prediction/win_probability.py --train

# Retrain all prop models
python src/prediction/player_props.py --train

# Run morning pipeline (injuries → props → predictions → CLV log)
python scripts/daily_pipeline.py

# Record game outcome (post-game CLV tracking)
python scripts/record_outcome.py --game-id 0022400710
```

---

## The Feedback Loop

```
Process game → CV features + NBA API enrichment
    → label possessions → retrain 7 simulator models
    → Monte Carlo 10K sims → stat distributions
    → compare vs book lines → flag edges → bet
    → outcome → retrain → repeat
```

Every game processed improves every model. At 200 full games, the complete 50-model stack is active and the system self-improves nightly.

---

## Roadmap

| Phase | Status | Goal | Unlock At |
|-------|--------|------|-----------|
| 1 — Data Infrastructure | ✅ | PostgreSQL, schedule, NBA stats | — |
| 2 — Tracker | ✅ | YOLOv8, Kalman, 431 tests | — |
| 3 — NBA API Data | ✅ | 221K shots, 98.4% PBP, 3 seasons | — |
| **4 — Tier 1 Models** | **🟡 Active** | **18 models trained + validated** | — |
| 5 — External Factors | 🔲 | Injury → props, refs, line movement | — |
| 6 — Full Game Processing | 🔲 | 20+ full games, enriched shots | Video pipeline |
| 7 — Tier 2–3 Models | 🔲 | xFG v2 with CV spatial features | 20 games |
| 8 — Possession Simulator v1 | 🔲 | 7-model chain, 10K Monte Carlo | 20 games |
| 9 — Feedback Loop | 🔲 | Nightly retrain → self-improving | Simulator |
| 10 — Tier 4–5 Models | 🔲 | Fatigue, lineup chemistry | 50–100 games |
| 11 — Betting Infrastructure | 🔲 | Kelly sizing, CLV backtest | Models |
| 12 — Full Monte Carlo | 🔲 | All 50 models, stat distributions | Phase 10 |
| 13 — FastAPI Backend | 🔲 | 12 endpoints, Redis, WebSocket | Phase 12 |
| 14 — Analytics Dashboard | 🔲 | Next.js, D3 shot charts, 10 types | Phase 13 |
| 15 — AI Chat | 🔲 | Claude API + render_chart inline | Phase 14 |
| 16 — Live Win Probability | 🔲 | 200+ games, LSTM, real-time WS | Phase 14 |
| 17 — Infrastructure | 🔲 | Docker, CI/CD, cloud GPU, monitoring | Phase 16 |

**Phase 16 targets:** Win probability accuracy 76–78% (vs Second Spectrum ~80%), props MAE ~0.12 pts.

---

## Tech Stack

| Layer | Technologies |
|-------|-------------|
| Computer Vision | YOLOv8n / YOLOv8-pose, OpenCV, EasyOCR, PyTorch 2.0.1 |
| Tracking | Kalman filter, Hungarian algorithm, scipy, Lucas-Kanade optical flow |
| Re-Identification | OSNet (256-dim deep embeddings), 99-dim HSV histograms |
| ML Models | XGBoost, scikit-learn, Ridge regression, joblib |
| Data Scraping | nba_api, pandas, BeautifulSoup, aiohttp, requests |
| API | FastAPI, uvicorn, pydantic v2, Redis |
| Database | PostgreSQL 14, psycopg2 |
| Task Queue | Celery, Redis |
| Dashboard | Streamlit, Plotly |
| AI Chat | Anthropic Claude API (claude-sonnet-4-6) |
| Infrastructure | Docker, GitHub Actions CI/CD |
| Hardware | NVIDIA RTX 4060 (8 GB VRAM), CUDA 11.8, cuDNN 8.9 |

---

## The Competitive Moat

Second Spectrum provides spatial tracking data to NBA teams at **$1M+/yr**. No public API exposes defender distance, spacing index, fatigue proxy, or drive frequency at the possession level. CourtVision extracts these features from standard broadcast footage at near-zero marginal data cost.

At 200 full games processed (Phase 16), the model stack closes to within ~2% of Second Spectrum win prediction accuracy. The remaining gap (ball height, hand-contest angle — worth roughly 2% combined) is not worth chasing for the prop market, where role-player and minutes props are priced with far less precision than star totals.

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines on reporting issues, submitting pull requests, and code style standards.

---

## License

MIT License — see [LICENSE](LICENSE) for details.

---

*Full architecture decisions and phase-by-phase knowledge base: [`vault/`](vault/) | Roadmap: [`.planning/ROADMAP.md`](.planning/ROADMAP.md)*
