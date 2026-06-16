# CourtVision — Start Here

> **STALE / ORIGIN DOC (2026-06).** This page describes the original NBA
> computer-vision + betting system, which is now the *Origin lineage*, not the
> headline product. The current product is the converged 4-sport calibrated
> predictor, and no $ edge is claimed. Start with the buyer docs instead:
> - [PREDICTOR_PLATFORM.md](PREDICTOR_PLATFORM.md) — the product
> - [PREDICTOR_QUICKSTART.md](PREDICTOR_QUICKSTART.md) — run a prediction in minutes
> - [JOB_EVIDENCE_PACKET.md](JOB_EVIDENCE_PACKET.md) — the honesty truth-source

New to this project? Read this first.

> **Canonical references:**
> - [README.md](../README.md) — github landing + headline results
> - [CLAUDE.md](../CLAUDE.md) — AI-agent runbook
> - [PROJECT_INDEX.md](PROJECT_INDEX.md) — navigation map

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

CourtVision is in **post-Gate-1 validation** — pre-game stack shipped with real-closing-line proof; in-play stack live and walk-forward-validated; first real CLV reading begins October 2026 preseason.

Where to skip the funnel:

- **Just want the numbers + how to verify?** → [PUBLIC_EVIDENCE.md](PUBLIC_EVIDENCE.md) (60-second scan, all reproducible)
- **Want to read the dense version?** → [README.md](../README.md)
- **Want the intelligence layer manifest (80 derived signals)?** → [INTELLIGENCE.md](INTELLIGENCE.md)

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
│   ├── prediction/        # 85 trained ML artifacts across ~120 modules (win prob, props, xFG, DNP, residual heads, period heads, live quantile bands)
│   ├── analytics/         # Betting edge, spacing, momentum, shot quality
│   ├── data/              # NBA API scrapers, enrichment, database helpers
│   └── simulation/        # Possession simulator (Monte Carlo)
├── api/                   # FastAPI REST backend (~49 endpoints across 7 routers)
├── scripts/               # Operational scripts (batch runs, training, backfills)
├── tests/                 # 2,661 pass on RunPod / 1040+ on core suite locally
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
# Expected on RunPod: ~2,661 pass, ~26 fail (tracking + pyarrow-missing transients)
# Expected locally: 1040 pass, 2 skip on the core prediction suite

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

## Key Numbers (honest / leak-free — see [JOB_EVIDENCE_PACKET.md](JOB_EVIDENCE_PACKET.md))

> The funnel: **DATA → SIGNALS → MODELS → ENGINES → PREDICTIONS → INTELLIGENCE.** Earlier
> headline ROI/Brier figures were retracted as measurement artifacts (listed at the bottom).

| Metric | Value | Source |
|--------|-------|--------|
| Prop MAE @ q50 (leak-free WF, ~51K held-out/stat) | PTS ~4.58 · REB ~1.90 · AST ~1.34 · FG3M ~0.88 | `data/models/quantile_pergame_metrics.json` |
| Win-prob accuracy / Brier (3-fold WF) | 0.709 / 0.193 | `data/models/win_prob_metrics.json` |
| In-play endQ3 MAE lift vs pregame | ~46% pooled (~26% over naive carry-forward, WF) | leak-clean residual heads |
| In-play endQ3 Brier (leak-free) | ~0.141 | after removing a Q4 feature leak (caught in self-audit) |
| Betting vs **real** closing lines | break-even-minus-vig; **AST ~+4–5%** the one durable edge | `scripts/run_gate1_full_analysis.py` → −2.00% unfiltered |
| CV pipeline | 17,254 cv_features rows / 241 games / 252 players · ~$0.10–0.13/game | `data/nba_ai.db` |
| DNP predictor AUC | 0.979 | committed metrics |
| In-play paper-ceiling ROI (L5 line proxy, n=55,073) | 78% hit / +54% — **ceiling, not edge**; real est. +15–25% | ⚠️ L5 proxy, first real CLV Oct 2026 |
| Shots in training data | 221,866 | |

**Retracted (artifacts the harness caught):** +18.38% ROI (market-follow grading bug → real break-even-minus-vig), endQ3 0.119 (Q4 leak → ~0.141), +54% in-play (L5 proxy). Full account: [JOB_EVIDENCE_PACKET.md](JOB_EVIDENCE_PACKET.md).

---

## Project Status (2026-05-28)

| Phase | Description | Status |
|-------|-------------|--------|
| 1–13.5 | Data infra, CV tracker, NBA data, 85 ML models, possession simulator, betting infra, FastAPI | ✅ Done |
| G | Full-game CV data collection (target 80 CLEAN) | 🟡 85 tracked / 7 full-feature — blocked behind ISSUE-022 `defender_distance=200.0` sentinel-vs-NULL |
| **Gate 1** | Real-Vegas re-grade vs DK/FD/MGM/BetRivers closes (8,360 bets) | ✅ **RUN** — market efficient: **break-even-minus-vig** (−2.00% unfiltered); the earlier "+18.38% filtered" was a market-follow grading artifact, retracted |
| In-play stack | endQ1/endQ2/endQ3 LGB + iter-68 v6_hp + iter-71 meta_blend | ✅ Shipped 2026-05-27 (CHANGELOG 0.17.0) |
| Intelligence layer | 80 derived artifacts (player/scheme/lineup/quality/calibration) | ✅ Shipped — manifest at [INTELLIGENCE.md](INTELLIGENCE.md) |
| Shadow-logged execution | Settlement engine + filter calibrator + decision-engine gates | ✅ Shipped 2026-05-27 |
| Pinnacle real-close CLV | First reading on real Pinnacle closes | ⏳ Oct 2026 preseason (daemon collecting) |
| Live trading desk UI | `/scan` + `/clv` + `/parlays` + `/live/{game_id}` + SSE arbs | ✅ Shipped 2026-05-27 |

For the full phase log see [ROADMAP.md](ROADMAP.md); for the forward strategic roadmap see [../ROADMAP.md](../ROADMAP.md).

---

## Documentation Index

| Doc | What's In It |
|-----|--------------|
| **[PUBLIC_EVIDENCE.md](PUBLIC_EVIDENCE.md)** | **60-second scan: headline numbers + 30-sec verification commands** |
| **[INTELLIGENCE.md](INTELLIGENCE.md)** | **80-artifact intelligence-layer manifest (signals between CV + models)** |
| [KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md) | Explicit validation gaps + caveats |
| [architecture.md](architecture.md) | System design, module dependencies, data flow |
| [CV_TRACKING.md](CV_TRACKING.md) | Tracking pipeline deep-dive: homography, re-ID, OCR |
| [ML_MODELS.md](ML_MODELS.md) | 85 trained signals: features, training, accuracy |
| [data_schema.md](data_schema.md) | PostgreSQL schema, CSV formats, API cache |
| [API.md](API.md) | FastAPI endpoints, request/response examples |
| [EXECUTION_GUIDE.md](EXECUTION_GUIDE.md) | Running batch jobs, training, deployment |
| [ROADMAP.md](ROADMAP.md) | Full phase-by-phase build plan |
| [PROJECT_INDEX.md](PROJECT_INDEX.md) | Canonical repository navigation map |
| [../MASTER_PLAN.md](../MASTER_PLAN.md) | Full strategic plan + canonical facts table |

---

## Contributing

See [CONTRIBUTING.md](../CONTRIBUTING.md) for code style, PR workflow, and no-touch zones.

---
*Last verified: 2026-05-28 against CHANGELOG.md [0.17.0] + iter61 sim-reconciliation.*
