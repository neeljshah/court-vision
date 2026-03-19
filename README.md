# Project CourtVision
> Broadcast-feed computer vision + 90 ML models + Monte Carlo simulation that extracts spatial tracking data from NBA games, prices player props, and surfaces sportsbook edges — the kind of data Second Spectrum charges $1M+/yr for.

![Python](https://img.shields.io/badge/Python-3.9-blue) ![PyTorch](https://img.shields.io/badge/PyTorch-2.0.1+CUDA11.8-orange) ![Phase](https://img.shields.io/badge/Phase-4%20of%2017-yellow) ![Models](https://img.shields.io/badge/Models-18%20trained-green)

## Overview

Project CourtVision ingests raw NBA broadcast footage and produces per-possession spatial metrics — defender distance, spacing index, drive frequency, fatigue proxy — that exist in no public dataset. These features feed a 90-model ML stack that runs 10,000 Monte Carlo simulations per game, producing full statistical distributions for every player, then compares those distributions against sportsbook lines to surface positive-EV edges.

The pipeline is end-to-end: YOLOv8 detection → Kalman + Hungarian tracking → HSV + OSNet re-ID → court homography → event detection → NBA API enrichment → 6-tier model stack → Monte Carlo simulator → prop pricing engine → FastAPI backend → Next.js dashboard + Claude AI chat. Phase 4 of 17 is active; 18 models are trained with validated accuracy; the remaining tiers unlock as full-game video data accumulates.

## System Performance

| Metric | Value | Benchmark | Status |
|--------|-------|-----------|--------|
| Win probability accuracy | 69.1% | Vegas closing line ~68% | ✅ Trained |
| Win probability Brier score | 0.203 | Perfect = 0.0 | ✅ Trained |
| xFG v1 Brier score | 0.226 | League-avg baseline ~0.25 | ✅ Trained (221K shots) |
| Props pts MAE (walk-forward) | 0.308 | PrizePicks model est. ~0.4+ | ✅ Trained |
| Props reb MAE | 0.113 | — | ✅ Trained |
| Props ast MAE | 0.093 | — | ✅ Trained |
| Props R² (all 7 models) | >0.93 | — | ✅ Trained |
| DNP predictor AUC | 0.979 | — | ✅ Trained |
| Matchup model R² | 0.796 | — | ✅ Trained |
| CV tracker speed | 15 fps | RTX 4060 8 GB | ✅ Active |
| Shot charts scraped | 221,866 | 3 seasons, 569 players | ✅ Complete |
| PBP game coverage | 3,627 / 3,685 (98.4%) | — | ✅ Complete |
| Phase 16 win accuracy target | 76–78% | Second Spectrum ~80% | 🔲 Phase 16 |
| Phase 16 props MAE target | ~0.12 pts | — | 🔲 Phase 16 |
| Monte Carlo simulations/game | 10,000 | — | 🔲 Phase 8 |

## Architecture

```
Broadcast Video (.mp4)
        │
        ▼
┌────────────────────────────────────────────────────────┐
│  CV Tracking Pipeline   (src/tracking/)                │
│                                                        │
│  YOLOv8n detection  (conf=0.35 broadcast mode)         │
│    → Court Rectification  (SIFT + 3-tier homography)   │
│    → AdvancedFeetDetector                              │
│        Kalman 6D state [cx, cy, vx, vy, w, h]         │
│        Hungarian assignment (IoU×0.75 + embed×0.25)   │
│        99-dim HSV histogram embeddings  (EMA α=0.7)   │
│        Optional: OSNet 256-dim deep re-ID              │
│        Gallery TTL=300 frames,  MAX_LOST=90            │
│        Pose estimation: YOLOv8-pose ankle keypoints    │
│        Optical flow gap-fill: Lucas-Kanade ≤8 frames   │
│    → BallDetectTrack  (Hough + CSRT + optical flow)    │
│    → EventDetector   (shot / pass / dribble)           │
│    → JerseyOCR       (EasyOCR dual-pass + voting buf)  │
└────────────────────────────────────────────────────────┘
        │  positions, speed, spacing, possession, events
        ▼
┌────────────────────────────────────────────────────────┐
│  Feature Engineering   (src/features/)                 │
│  60+ spatial + temporal features                       │
│  spacing index, defender distance, drive frequency     │
│  fatigue proxy, play type, possession value            │
└────────────────────────────────────────────────────────┘
        │                       NBA API (3 seasons)
        │                    ┌──────────────────────────┐
        │◄────────────────── │ gamelogs, shot charts    │
        │                    │ PBP, hustle, matchups    │
        │                    │ synergy, on/off, BBRef   │
        │                    └──────────────────────────┘
        ▼
┌────────────────────────────────────────────────────────┐
│  90-Model ML Stack   (src/prediction/, src/analytics/) │
│                                                        │
│  Tier 1 (trained): Win prob, props ×7, game models     │
│  Tier 2 (trained): xFG v1, zone tendency, clutch       │
│  Tier 3 (Phase 7):  xFG v2 + CV features (20 games)   │
│  Tier 4 (Phase 10): Fatigue, lineup chemistry          │
│  Tier 5 (Phase 10): Possession outcome model           │
│  Tier 6 (Phase 16): Live win prob LSTM (200+ games)    │
└────────────────────────────────────────────────────────┘
        │
        ▼
┌────────────────────────────────────────────────────────┐
│  Possession Simulator   (Phase 8)                      │
│  7-model chain per possession:                         │
│  Play Type → Shot Selector → xFG → TO/Foul             │
│  → Rebound → Fatigue → Substitution                    │
│  × 10,000 Monte Carlo → full stat distribution         │
└────────────────────────────────────────────────────────┘
        │
        ▼
┌──────────────────────┐  ┌──────────────────────────────┐
│  Betting Dashboard   │  │  Analytics Dashboard          │
│  FastAPI + Next.js   │  │  96 metrics, 10 chart types   │
│  Kelly sizing, CLV   │  │  D3 shot charts, lineup matrix│
└──────────────────────┘  └──────────────────────────────┘
        │
        ▼
┌────────────────────────────────────────────────────────┐
│  AI Chat   (Phase 15)                                  │
│  claude-sonnet-4-6 + 10 tools + render_chart           │
│  "Show Murray's shot quality vs guards tonight"        │
│  → chart renders inline in conversation                │
└────────────────────────────────────────────────────────┘
```

## What's Built

**CV Tracking**
- Tracks 10 players simultaneously at 15 fps on RTX 4060 (8 GB VRAM)
- Kalman-predicted positions survive occlusion for up to 90 frames (~3 s at 30 fps)
- Gallery-based re-ID recovers player identity after off-screen exits (TTL = 300 frames)
- Pose estimation via YOLOv8-pose: ankle keypoints replace bbox-bottom heuristic for sub-foot court-coordinate accuracy
- Similar-uniform detection: k-means warm-up clustering discovers team color centroids; raises appearance weight +0.10 and widens jersey-number tiebreaker when hue centroids are within 20 units
- Optical flow gap-fill (Lucas-Kanade) propagates position for up to 8 frames during YOLO misses

**Data — 3 Seasons, 3,685 Games**
- 221,866 shot chart coordinates (569 players)
- 3,627 play-by-play game logs (98.4% coverage)
- Hustle stats, on/off splits, defender zones, matchup data, synergy play types (all fetched)
- BBRef BPM, VORP, WS/48 wired into prop features
- Historical closing lines (1,225+ games), current props (DK/FD, 15 min TTL), contract data (523 players)

**ML Models — 18 Trained**
- Win probability: XGBoost, 27 features, 69.1% accuracy, Brier 0.203
- Player props: 7 XGBoost regressors (pts/reb/ast/fg3m/stl/blk/tov), 52 features, R² > 0.93 all
- DNP predictor: logistic regression, AUC 0.979, wired into prop predictions at ≥ 0.4 threshold
- xFG v1: Brier 0.226 on 221K shots
- Game models: total, spread, blowout, first-half, pace (5 models)
- Matchup model: XGBoost, R² = 0.796, MAE = 4.55

## Repository Structure

```
src/
├── tracking/        # CV pipeline — AdvancedFeetDetector, ball, events, OCR
├── prediction/      # ML models — win prob, props, xFG, matchup, DNP
├── analytics/       # 22 analytics modules — shot quality, spacing, momentum
├── data/            # NBA API + external scrapers (BBRef, odds, injury, PBP)
├── features/        # 60+ feature engineering functions
├── pipeline/        # End-to-end orchestration
├── re_id/           # OSNet deep re-ID training + inference
└── stats_tracker/   # In-game stat accumulation

data/
├── models/          # Trained model artifacts (.pkl, .json)
├── nba/             # NBA API cache (shot charts, gamelogs, PBP)
└── external/        # BBRef, contracts, historical lines

tests/               # pytest suite — 431 tests, phases 2–4
.planning/ROADMAP.md # Full 17-phase build plan
vault/               # Obsidian knowledge base — decisions, session logs
```

## The Competitive Moat

Second Spectrum provides spatial tracking data to NBA teams at $1M+/yr. No public API exposes defender distance, spacing index, fatigue proxy, or drive frequency at the possession level. Project CourtVision extracts these features from standard broadcast footage at zero marginal data cost.

At 200 full games processed (Phase 16), the model stack closes to within ~2% of Second Spectrum win prediction accuracy. The remaining gap is ball height and hand-contest angle — worth roughly 2% combined, not worth chasing for the prop market, where role-player and minutes props are priced with far less precision than star totals.

## Roadmap

| Phase | Status | Goal |
|-------|--------|------|
| 1 — Data Infrastructure | ✅ | PostgreSQL, schedule, lineup, NBA stats |
| 2 — Tracker Bug Fixes | ✅ | 431 tests, team color, EventDetector |
| 3 — NBA API Data | ✅ | 622 gamelogs, 221K shots, 98.4% PBP |
| **4 — Tier 1 Models** | **🟡 Active** | **18 models trained, props + win prob** |
| 5 — External Factors | 🔲 | Injury → props, refs, line movement |
| 6 — Full Game Processing | 🔲 | 20+ games, PostgreSQL, enriched shots |
| 7 — Tier 2–3 Models | 🔲 | xFG v2 with CV features |
| 8 — Possession Simulator v1 | 🔲 | 7-model chain, 10K Monte Carlo |
| 9 — Feedback Loop | 🔲 | Nightly retrain → better predictions |
| 10 — Tier 4–5 Models | 🔲 | Fatigue, lineup chemistry |
| 11 — Betting Infrastructure | 🔲 | Odds API, Kelly sizing, CLV backtest |
| 12 — Full Monte Carlo | 🔲 | All 50 models, stat distributions |
| 13 — FastAPI Backend | 🔲 | 12 endpoints, Redis, WebSocket |
| 14 — Analytics Dashboard | 🔲 | Next.js, D3 shot charts, 10 chart types |
| 15 — AI Chat | 🔲 | Claude API + render_chart inline |
| 16 — Live Win Probability | 🔲 | 200+ games, LSTM, real-time WebSocket |
| 17 — Infrastructure | 🔲 | Docker, CI/CD, cloud GPU |

## The Feedback Loop

```
Process game → CV features + NBA API enrichment
    → label possessions → retrain 7 simulator models
    → Monte Carlo 10K sims → stat distributions
    → compare vs book lines → flag edges
    → outcome → retrain → repeat
```

Every game processed improves every model. At 200 games the full 50-model stack is active.

## Quick Start

```bash
conda activate basketball_ai
cd C:/Users/neelj/nba-ai-system

# Run all tests (no video processing)
python -m pytest tests/ -q

# Predict tonight's game
python src/prediction/game_prediction.py --predict GSW BOS

# Get player prop projections
python -c "
from src.prediction.player_props import predict_props
result = predict_props('Jayson Tatum', 'MIA', '2024-25')
for stat, val in result['predictions'].items():
    print(f'{stat}: {val:.1f}')
"

# Train win probability model (no video required)
python src/prediction/win_probability.py --train
```

## Environment

- Python 3.9 · conda env `basketball_ai`
- PyTorch 2.0.1 + CUDA 11.8 + cuDNN 8.9 · RTX 4060 8 GB
- YOLOv8n (ultralytics) · OpenCV · EasyOCR · scipy · XGBoost · scikit-learn
- nba_api · PostgreSQL (schema ready at `database/schema.sql`, writes wired Phase 6)

---

*Full architecture decisions and phase-by-phase knowledge base: `vault/` | Roadmap: `.planning/ROADMAP.md`*
