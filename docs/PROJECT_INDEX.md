# Project Index — Navigation Hub

This is the canonical navigation map for the CourtVision repository. For the full strategic vision, start with [MASTER_PLAN.md](../MASTER_PLAN.md). For system design, start with [docs/architecture/system-overview.md](architecture/system-overview.md).

---

## Research

| Document | Description |
|----------|-------------|
| [edge-taxonomy.md](research/edge-taxonomy.md) | All 164 enumerated edges — CV-spatial, context, model, execution, structural — with academic backing and build estimates |
| [competitive-landscape.md](research/competitive-landscape.md) | Why SIG, Jump, Citadel, and IMC cannot enter player prop markets; the structural argument |
| [market-microstructure.md](research/market-microstructure.md) | How books price props, where they're systematically wrong, venue comparison |
| [precedent-analysis.md](research/precedent-analysis.md) | Voulgaris, Benter, Thorp — solo operators who proved the template |
| [data-sources.md](research/data-sources.md) | Complete data architecture — free tier, paid tier, proprietary CV pipeline |
| [validation-methodology.md](research/validation-methodology.md) | CLV framework — how to prove edge exists before deploying capital |

---

## Architecture

| Document | Description |
|----------|-------------|
| [system-overview.md](architecture/system-overview.md) | The 5 core systems and how they interconnect |
| [cv-pipeline.md](architecture/cv-pipeline.md) | YOLO → homography → Kalman → OSNet → features — full CV layer |
| [possession-simulator.md](architecture/possession-simulator.md) | Monte Carlo engine design — why distributions beat point estimates |
| [execution-engine.md](architecture/execution-engine.md) | Multi-book routing, account health, P2P adapters, circuit breakers |
| [dashboard-spec.md](architecture/dashboard-spec.md) | Bloomberg-terminal-grade panel specifications (10 panels) |

---

## Strategy

| Document | Description |
|----------|-------------|
| [timing-layer.md](strategy/timing-layer.md) | When to bet throughout the day — event timeline from 6am to post-game |
| [account-longevity.md](strategy/account-longevity.md) | Anti-limiting tactics — heat score model, rotation strategy, P2P migration |
| [learning-loop.md](strategy/learning-loop.md) | Nightly improvement cycle — residuals → calibration → drift detection |
| [multi-sport-expansion.md](strategy/multi-sport-expansion.md) | NFL/MLB/Soccer expansion plan — infrastructure reuse by component |
| [revenue-streams.md](strategy/revenue-streams.md) | Beyond bankroll — picks service, API licensing, dashboard SaaS |

---

## Models

| Document | Description |
|----------|-------------|
| [feature-inventory.md](models/feature-inventory.md) | All ~70 features across 7 classes — API, CV spatial, temporal, market microstructure |
| [model-registry.md](models/model-registry.md) | 75 models, tiers, algorithms, current R² / ECE, production gates |
| [calibration.md](models/calibration.md) | Probability calibration — Platt scaling, isotonic regression, ECE, Shin devig |

---

## Operations

| Document | Description |
|----------|-------------|
| [runpod-runbook.md](operations/runpod-runbook.md) | GPU cloud operations — CFS quota, OMP cap, VRAM flush, data sync |
| [data-pipeline.md](operations/data-pipeline.md) | Ingest system — download, queue, processing, quality scoring, sync |
| [deployment.md](operations/deployment.md) | API serving, execution router, VPS deployment plan, environment config |

---

## Canonical Source Documents

| Document | Purpose |
|----------|---------|
| [MASTER_PLAN.md](../MASTER_PLAN.md) | Full strategic vision — load at session start |
| [README.md](../README.md) | System overview, results, methodology, limitations |
| [CLAUDE.md](../CLAUDE.md) | Operational runbook and session state |
| [.planning/ROADMAP.md](../.planning/ROADMAP.md) | Full phase roadmap (125K; load only if needed) |

---

## Source Code Map

| Path | Contents |
|------|----------|
| `src/tracking/` | YOLOv8 detection, re-ID (OSNet, color), homography, Kalman/Hungarian |
| `src/features/` | Feature engineering — CV spatial + API derived features |
| `src/prediction/` | 75 models, calibration, Kelly sizer, CLV, backtester |
| `src/pipeline/` | unified_pipeline.py — the orchestrator |
| `src/ingest/` | SQLite queue, yt-dlp wrapper, B2 sync |
| `src/data/` | NBA API connectors, line monitor, injury scraper |
| `src/execution/` | Book adapters, exchange connectors |
| `api/` | FastAPI — 9 endpoints, 5 routers |
| `scripts/` | Operational scripts — ingest, batch, setup, validation |
| `tests/` | 960+ tests; 93 skip (PG/GPU excluded) |

---

## Historical Documentation (Legacy — Still Accurate)

| Document | Notes |
|----------|-------|
| [docs/CV_TRACKING.md](CV_TRACKING.md) | Original CV pipeline writeup |
| [docs/ML_MODELS.md](ML_MODELS.md) | Pre-restructure model documentation |
| [docs/BETTING.md](BETTING.md) | Betting methodology (predates MASTER_PLAN) |
| [docs/API.md](API.md) | API reference (kept current) |
| [docs/PRODUCTION_RUNBOOK.md](PRODUCTION_RUNBOOK.md) | Operational runbook (superseded by operations/ below) |
| [docs/operations/runpod_video_sync_notes.md](operations/runpod_video_sync_notes.md) | Raw session notes from RunPod runs |
