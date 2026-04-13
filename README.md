# CourtVision

CourtVision is an end-to-end NBA computer vision and ML intelligence system that transforms broadcast video into spatial telemetry, fuses it with traditional basketball data, and produces prediction and betting analytics.

## What It Does Today

- Extracts player/ball tracking from broadcast footage using a GPU CV pipeline.
- Engineers CV + context features for downstream modeling.
- Runs a large prediction stack for game, player, and props intelligence.
- Exposes prediction and analytics surfaces through FastAPI endpoints.
- Supports batch processing workflows for season-scale game pipelines.

## Why It Matters

Most public NBA systems rely on box score or play-by-play data only. CourtVision adds spatial signals that are otherwise expensive or unavailable:

- Defender distance and contest quality
- Floor spacing and shape dynamics
- Possession-level movement and fatigue context
- Event-level context from multi-stage CV tracking

## Architecture

High-level flow:

1. Video ingest and frame decode
2. Detection, tracking, court homography, OCR/re-ID
3. Event extraction and per-game tracking artifacts
4. Feature engineering and context enrichment
5. Model orchestration and predictions
6. API serving and analytics output

Core directories:

- `src/tracking`: detection, tracking, homography, OCR, re-ID
- `src/pipeline`: orchestration, registries, drift/retrain utilities
- `src/features`: feature engineering and advanced derived features
- `src/prediction`: model logic, game/props predictors, portfolio logic
- `src/data` and `src/ingest`: external data collection and enrichment
- `api`: FastAPI app and routers
- `scripts`: operational runners for batch, validation, retraining
- `tests`: unit/integration coverage

## Tech Stack

- Python 3.9
- PyTorch + CUDA, YOLOv8, OpenCV, EasyOCR
- scikit-learn, XGBoost, LightGBM
- FastAPI + Uvicorn
- PostgreSQL + Redis
- Docker / docker-compose

## Quick Start

```bash
conda create -n basketball_ai python=3.9 -y
conda activate basketball_ai
pip install -r requirements.txt
python -m pytest tests/ -q
```

Run a clip pipeline:

```bash
python scripts/run_clip.py --game 0022400430 --no-show
```

Run Phase G batch queue:

```bash
python scripts/run_phase_g.py --parallel 4
```

Start API locally:

```bash
uvicorn api.main:app --host 0.0.0.0 --port 8000
```

## Current Priorities

- Increase high-quality processed CV games and registry density
- Improve model governance and contract safety between API and models
- Harden production security and runtime settings
- Strengthen fallback observability and data quality gates

## Vision & Future

CourtVision is evolving from a research-grade pipeline into a public, production-grade basketball intelligence platform.

Near-term direction:

- Reliable live and pregame prediction APIs with strict contracts
- Better confidence scoring tied to CV data quality and drift health
- Streamlined frontend experiences backed by real auth and real-time endpoints
- Stronger model lifecycle controls: promotion, rollback, drift-triggered retrain

Long-term direction:

- Possession-level simulation as a first-class product surface
- Institutional-grade analytics delivery for media, teams, and quants
- Subscription-ready prediction services with transparent model governance

## Project Health and Planning

- Strategic roadmap and gap audit live in `PLAN.md`.
- Additional architecture notes are in `docs/`.
- Contribution workflow and quality standards are in `CONTRIBUTING.md`.

## Disclaimer

For research and educational use. Not financial advice.
