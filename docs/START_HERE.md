# CourtVision — Start Here

New to this project? Read this first.

---

## What This Is

CourtVision is an end-to-end NBA analytics pipeline that:

1. **Watches broadcast video** and tracks every player's position on the court in real time
2. **Extracts spatial metrics** (defender distance, spacing, drive frequency) that don't exist in any public dataset
3. **Feeds those metrics into 85 trained models** that predict game outcomes and player stats
4. **Runs 10,000 Monte Carlo simulations** per game to find positive-EV edges against sportsbook lines

The key moat: Second Spectrum sells spatial tracking to NBA teams at $1M+/yr. This pipeline replicates that on a single consumer GPU.

---

## Current Stage (Important)

CourtVision is in late build / validation stage.

Current focus is intentionally narrow:

- maximize NBA prediction quality (games + props),
- prove reliability with leakage/calibration/drift gates,
- prove execution quality with CLV and risk controls.

Not the focus yet:

- multi-sport expansion,
- heavy frontend polish,
- broad commercialization beyond validation milestones.

If you are contributing, prioritize tasks that improve prediction quality or evidence quality first.

---

## How It Works (Plain English)

```
NBA broadcast video (.mp4)
    │
    ▼
CV Tracker (YOLOv8 + Kalman filter + SIFT homography)
    │   Detects and tracks all 10 players frame-by-frame
    │   Maps pixel positions → real court coordinates (feet)
    │   Identifies players via jersey OCR + deep re-ID
    ▼
Spatial Features (defender_distance, spacing_index, drive_freq, fatigue_proxy)
    │
    ▼
NBA API Enrichment (shot charts, play-by-play, hustle stats, 3 seasons)
    │
    ▼
60+ ML Features → 85 Trained Signals (XGBoost, Ridge, PyTorch)
    │   Win probability, 7 player props, xFG, DNP predictor, matchups
    ▼
10,000 Monte Carlo Simulations per game
    │
    ▼
Kelly-sized bet recommendations + CLV tracking
```

---

## Repository Structure

```
nba-ai-system/
├── src/
│   ├── tracking/          # CV pipeline: player detection, tracking, re-ID, OCR
│   ├── pipeline/          # Orchestrator: runs full game end-to-end
│   ├── features/          # 60+ feature engineering functions
│   ├── prediction/        # 75 ML models (win prob, props, xFG, DNP, etc.)
│   ├── analytics/         # Betting edge, spacing, momentum, shot quality
│   ├── data/              # NBA API scrapers, enrichment, database helpers
│   └── simulation/        # Possession simulator (Monte Carlo)
├── api/                   # FastAPI REST backend (10 endpoints)
├── scripts/               # Operational scripts (batch runs, training, backfills)
├── tests/                 # 1040+ tests
├── database/              # PostgreSQL schema + migrations
├── docs/                  # Documentation (you are here)
└── .github/workflows/     # CI/CD (GitHub Actions)
```

---

## Setup

**Requirements:** Python 3.9, CUDA 11.8, GPU with 8GB+ VRAM (CPU works, but slowly)

```bash
# 1. Clone
git clone https://github.com/neeljshah/nba-ai-system.git
cd nba-ai-system

# 2. Create environment
conda create -n basketball_ai python=3.9 -y
conda activate basketball_ai
pip install -r requirements.txt

# 3. Configure secrets
cp .env.example .env
# Edit .env — set DATABASE_URL, ODDS_API_KEY

# 4. Run tests
python -m pytest tests/ -q
# Expected: 1040 pass, 2 skip

# 5. Start the API
uvicorn api.main:app --reload --port 8000
# Visit http://localhost:8000/docs
```

---

## Run a Prediction

```bash
# Predict a matchup
python src/prediction/game_prediction.py --predict GSW BOS

# Process a game clip (needs video file + GPU)
python scripts/run_clip.py --video data/videos/game.mp4 --no-show

# Run batch season processing
python scripts/batch_season.py --season 2025-26
```

---

## Key Numbers

| Metric | Value |
|--------|-------|
| Win probability accuracy | 68.5% |
| Player props MAE (pts) | 4.12 (holdout) |
| DNP predictor AUC | 0.979 |
| xFG Brier score | 0.226 |
| Shots in training data | 221,866 |
| Play-by-play coverage | 98.4% (3,627 / 3,685 games) |
| Tracking throughput | 15 fps on RTX 4060 8GB |

---

## Project Status

| Phase | Description | Status |
|-------|-------------|--------|
| 1–13.5 | Data infra, CV tracker, NBA data, 75 ML models, possession simulator, betting infra, FastAPI | ✅ Done |
| G | Full-game CV data collection (target 80 CLEAN games) | 🟡 Active — 29 usable / 75 attempted |
| Gate 1 | CLV validation vs Pinnacle close (≥50 bets, beat rate ≥55%, ROI ≥3%) | 🔴 Not yet run — top priority |
| 14 | 80-game RunPod run + retrain with CV spatial features | ⏳ Next |
| 15–18 | Analytics dashboard, AI chat, live win-prob LSTM, infrastructure | 🔲 Future |

For the full phase log see [ROADMAP.md](ROADMAP.md); for the forward strategic roadmap see [../ROADMAP.md](../ROADMAP.md).

---

## Documentation Index

| Doc | What's In It |
|-----|--------------|
| [architecture.md](architecture.md) | System design, module dependencies, data flow |
| [CV_TRACKING.md](CV_TRACKING.md) | Tracking pipeline deep-dive: homography, re-ID, OCR |
| [ML_MODELS.md](ML_MODELS.md) | 75 trained signals: features, training, accuracy |
| [data_schema.md](data_schema.md) | PostgreSQL schema, CSV formats, API cache |
| [API.md](API.md) | FastAPI endpoints, request/response examples |
| [EXECUTION_GUIDE.md](EXECUTION_GUIDE.md) | Running batch jobs, training, deployment |
| [ROADMAP.md](ROADMAP.md) | Full phase-by-phase build plan |
| [PROJECT_INDEX.md](PROJECT_INDEX.md) | Canonical repository navigation map |
| [../MASTER_PLAN.md](../MASTER_PLAN.md) | Full strategic plan + canonical facts table |

---

## Contributing

See [CONTRIBUTING.md](../CONTRIBUTING.md) for code style, PR workflow, and no-touch zones.
