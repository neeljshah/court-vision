# CourtVision

**A full-stack NBA intelligence engine: computer vision + market data + ML + simulation.**

![Status](https://img.shields.io/badge/Status-Phase_G_Active-22c55e)
![Core](https://img.shields.io/badge/Core-CV_%2B_ML_%2B_Monte_Carlo-7c3aed)
![Models](https://img.shields.io/badge/Target-90_Models-2563eb)
![Serving](https://img.shields.io/badge/API-FastAPI-0ea5e9)
![License](https://img.shields.io/badge/License-All_Rights_Reserved-red)

---

## Why This Project Matters

Most NBA prediction systems are built on public box score and play-by-play abstractions.  
CourtVision is designed to go deeper by reconstructing court-space behavior from broadcast video and turning it into predictive signals.

The long-term goal is not just better picks. The goal is a **defensible intelligence platform** that can:

- model games and props as probability distributions (not single-point guesses),
- exploit structural inefficiencies in line pricing,
- and continuously improve as more games are processed.

---

## The Core Moat

CourtVision extracts proprietary spatial features that are difficult to replicate cheaply:

- defender distance and closeout pressure,
- team spacing and off-ball geometry,
- movement-derived fatigue and pace decay proxies,
- lineup-level behavior patterns from tracking continuity.

These CV-derived signals are fused with NBA/API/context/market data to power the prediction pipeline.

---

## End-to-End System

```mermaid
graph LR
    A[Broadcast Video + NBA/Market Data] --> B[CV Tracking Pipeline]
    B --> C[Spatial Feature Engineering]
    A --> D[Data Enrichment + Storage]
    C --> E[Model Stack]
    D --> E
    E --> F[Backtesting + Calibration + Drift Checks]
    F --> G[Monte Carlo Simulation]
    G --> H[Edge + Portfolio Construction]
    H --> I[FastAPI + Dashboard + AI Interface]
```

### 1) CV Tracking Pipeline

Key components include `YOLOv8`, homography rectification, Kalman/Hungarian tracking, OCR-assisted identity recovery, and `OSNet` re-identification.

Output:
- court-mapped player and ball trajectories,
- event primitives (shots, possessions, transitions),
- quality metadata for downstream gating.

### 2) Data Layer

CourtVision combines video-derived telemetry with structured context:

- NBA box, shot, lineup, and schedule context,
- injuries, referee context, and market lines,
- PostgreSQL-backed schema for reproducible model training.

### 3) Prediction Pipeline

The target architecture is a multi-layer ensemble (up to 90 models) spanning:

- game outcomes and win probability,
- player props across core stat markets,
- matchup/context/risk adjustment models,
- meta-model and calibration stack for reliability.

### 4) Simulation + Execution

CourtVision is built for distributional decision-making:

- possession/game simulation with Monte Carlo sampling,
- edge scoring against market prices,
- risk-aware sizing and portfolio controls (fractional Kelly + correlation discipline).

---

## Current Status

CourtVision is an advanced in-progress system, not a finished product.

Built today:
- working CV pipeline and tracking artifacts,
- broad feature engineering and model orchestration framework,
- API + batch infrastructure,
- active roadmap and failure-gate planning for world-class rigor.

In progress:
- scaling high-quality CV game coverage,
- strict leakage-proof backtesting and calibration gating,
- stronger correlation/risk controls for production-grade portfolio deployment.

See `PLAN.md` and `.planning/ROADMAP.md` for governance gates and execution details.

---

## What Makes The Prediction Pipeline Strong

The prediction pipeline is designed to compound edge through structure:

1. **Better raw signal** from CV-derived spatial context.
2. **Better model architecture** through layered specialization and meta-adjustment.
3. **Better validation discipline** through leakage controls, drift checks, and calibration gates.
4. **Better decision layer** through distribution-aware simulation and risk-constrained execution.

This combination is what can turn a good model stack into a durable intelligence system.

---

## Repository Map

- `src/tracking/` - tracking, homography, re-ID, event detection
- `src/features/` - feature construction and transformations
- `src/prediction/` - model modules, props stack, portfolio logic
- `src/pipeline/` - orchestration, registries, retrain/validation flow
- `src/simulation/` - possession and game simulation
- `api/` - FastAPI serving layer
- `database/` - PostgreSQL schema and migrations
- `.planning/` - phased execution roadmap
- `PLAN.md` - canonical world-class operating plan

---

## Tech Stack

| Layer | Primary Tools |
|---|---|
| Vision | YOLOv8, OpenCV, EasyOCR, OSNet |
| ML | PyTorch, XGBoost, LightGBM, scikit-learn |
| Data | pandas, nba_api, PostgreSQL, Redis |
| API | FastAPI, Uvicorn |
| Runtime | Python 3.9, CUDA 11.8 |

---

## Collaboration

CourtVision is a proprietary quantitative R&D platform.  
Collaboration and investor conversations are welcome for:

- model quality and validation hardening,
- system architecture and production reliability,
- strategic commercialization of NBA intelligence products.

---

## License

All rights reserved.  
No reuse, redistribution, or commercial use without explicit written permission.
