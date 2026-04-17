# CourtVision

**Possession-by-possession NBA simulator. CV tracking + NBA API + ML models → 10K Monte Carlo → +EV edges vs sportsbooks.**

![Status](https://img.shields.io/badge/Status-Phase_G_Active-22c55e)
![Models](https://img.shields.io/badge/Models-75_trained-2563eb)
![Tests](https://img.shields.io/badge/Tests-960%2B_passing-brightgreen)
![API](https://img.shields.io/badge/API-FastAPI-0ea5e9)
![License](https://img.shields.io/badge/License-All_Rights_Reserved-red)

---

## Quick Start (one command on a fresh machine)

```bash
git clone https://github.com/neeljshah/court-vision.git && cd court-vision
git checkout main-sync

# macOS / Linux / Windows Git-Bash:
bash scripts/setup_dev.sh

# Windows PowerShell:
powershell -ExecutionPolicy Bypass -File scripts/setup_dev.ps1
```

The setup script creates the `basketball_ai` conda env, installs deps, verifies models, and bootstraps `.env` from the template. Everything except `.env` secrets and large video/tracking outputs is in git — no external file copy needed. After setup, fill `.env` with your API keys.

### Manual steps (if you prefer)

```bash
conda create -n basketball_ai python=3.9 -y
conda activate basketball_ai
pip install -r requirements.txt
cp .env.example .env  # fill in NBA_API_KEY, THE_ODDS_API_KEY, etc.
python -m pytest tests/ -q  # 960+ pass, ~93 skip
uvicorn api.main:app --reload
# → http://localhost:8000
# → http://localhost:8000/docs  (Swagger UI)
```

**Dependencies:** Python 3.9, CUDA 11.8 (optional for GPU tracking), conda

---

## What It Does

CourtVision builds differentiated NBA prediction signal from broadcast video.

**Moat:** Spatial CV telemetry (defender distance, spacing, fatigue proxies, movement context) extracted from broadcast video — impossible to replicate from public box scores.

**Pipeline:** `YOLOv8n → SIFT homography → Kalman+Hungarian → OSNet re-ID → EasyOCR → EventDetector → 73 prediction modules → 10K Monte Carlo → FastAPI`

```
Broadcast Video ──► CV Tracking ──► Feature Engineering (60+ features)
NBA/Market Data ──►                              │
                                                 ▼
                              ML Stack (75 models, 7 tiers)
                                                 │
                                                 ▼
                            Monte Carlo Simulation (10K runs)
                                                 │
                                                 ▼
                          Edge Scoring vs Sportsbooks → API
```

---

## Directory Structure

```
src/
  tracking/        # YOLOv8, homography, Kalman, OSNet re-ID, event detection
  features/        # feature_engineering.py — 60+ features, rolling windows
  prediction/      # 73 modules: props, win-prob, portfolio, simulator, tier4/5
  pipeline/        # unified_pipeline.py — orchestrator; batch_season.py
  data/            # NBA API collectors, enrichment, storage
api/               # FastAPI — 9 endpoints across 5 routers
database/          # PostgreSQL schema.sql
scripts/           # RunPod launchers, batch runners, sync scripts
data/models/       # 75 trained .pkl/.json files (gitignored)
docs/              # Architecture, API reference, model docs
.planning/         # Roadmap and phase plans
vault/             # Obsidian knowledge base (gitignored — local only)
```

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for the full system diagram.

---

## Current State (Session 36, 2026-04-15)

| Area | Status |
|------|--------|
| CV games tracked | 41 / 94 videos (16 A/B-grade) |
| CV player records | 24 in registry |
| Models trained | 75 .pkl/.json files |
| Prop R² | pts=0.47, reb=0.40, ast=0.46, fg3m=0.28 |
| API | 9 endpoints live |
| Tests | 960+ pass, 93 skip |
| Phase | 13.5 done — ready for 100-game RunPod run |

---

## API

```bash
GET  /health                          # system status
POST /simulate                        # game simulation (Monte Carlo)
GET  /props/{player_id}               # 7-stat prop projections
GET  /edge/{game_id}                  # betting edge vs market
GET  /win-prob/{game_id}              # win probability
GET  /lineup/{team}                   # lineup optimizer
POST /backtest/{stat}                 # backtest gate (fails closed on empty data)
POST /simulate_game                   # full game simulation
POST /over_prob                       # over probability for a stat line
```

Full schema: [`docs/API.md`](docs/API.md)

---

## RunPod (100-game batch)

```bash
# Launch single 4090 pod
bash scripts/launch_single_gpu_pod.sh

# Watch and sync results back
bash scripts/watch_and_sync.sh
```

See `CLAUDE.md` → RunPod section for full runbook (CFS quota, decord, OMP caps).

---

## Key Files

| Task | File |
|------|------|
| Tracking bug | `src/pipeline/unified_pipeline.py` |
| Prop model | `src/prediction/player_props.py` + `prop_model_stack.py` |
| Betting logic | `src/prediction/betting_portfolio.py` |
| API endpoint | `api/main.py` |
| Feature engineering | `src/features/feature_engineering.py` |
| Re-ID | `src/tracking/osnet_reid.py` |
| Batch runner | `scripts/batch_season.py` |

---

## Documentation

| Doc | Description |
|-----|-------------|
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | Full system diagram, data flow, component map |
| [`docs/API.md`](docs/API.md) | All endpoints, request/response schemas, curl examples |
| [`docs/ML_MODELS.md`](docs/ML_MODELS.md) | 75 trained models — tiers, R² scores, file locations |
| [`docs/tracking_pipeline.md`](docs/tracking_pipeline.md) | CV pipeline — per-frame loop, decord GPU path, perf |
| [`docs/PRODUCTION_RUNBOOK.md`](docs/PRODUCTION_RUNBOOK.md) | RunPod deployment, health checks, data sync |

---

## Tests

```bash
python -m pytest tests/ -q
# expect: 960+ passed, ~93 skipped (GPU/RunPod tests skip without CUDA)
# 0 failures allowed
```

---

## License

All rights reserved. No reuse, redistribution, or commercial use without explicit written permission.
