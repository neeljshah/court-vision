# CourtVision

> **A self-improving NBA analytics and prediction engine — combining computer vision player tracking, 25+ data sources, and 90 ML models to simulate every game 10,000 times, surface betting edges, and deliver professional-grade analytics through a conversational AI interface.**

---

## What This Is

CourtVision extracts spatial data from NBA broadcast video that no public tool provides, combines it with exhaustive statistical data from the NBA API and external sources, and feeds everything into a layered machine learning stack.

The end product is a **possession-by-possession Monte Carlo game simulator** that produces full stat distributions for every player — not just point estimates, but the entire probability curve. Those distributions get compared against sportsbook lines to flag edges automatically.

The closest comparable system is Second Spectrum, which NBA teams pay $1M+/year for. This is the self-built version.

---

## Three Products

### 1. Betting Dashboard
Live sportsbook lines vs model predictions — sorted by expected value. Kelly-sized bet recommendations, CLV tracking, same-game parlay optimizer, and injury reaction alerts for the 15–60 minute window when books haven't adjusted.

### 2. Analytics Dashboard
96 metrics across player, team, lineup, game, and predictive categories. D3 hexbin shot charts, win probability waterfalls, team spacing timelines, defensive pressure heatmaps, lineup matrices, and 10 chart types total.

### 3. AI Chat Interface
Claude API with 10 tools and a `render_chart` tool that renders charts inline in the conversation. Ask natural language questions — the model calls tools, fetches analytics, runs simulations, and renders everything visually in the chat window.

```
User: "How does Tatum perform vs zone defense and what's his best prop tonight?"

Claude calls:
  1. get_analytics("Tatum", "shot_quality", {"defense_type": "zone"})
  2. get_player_props("Tatum", ["pts", "ast", "3pm"], today)
  3. render_chart("scatter", tatum_zone_data)
  4. render_chart("distribution", tatum_pts_simulation)

→ Both charts render inline in the chat conversation.
```

---

## Current Status

| Layer | Status | Details |
|---|---|---|
| CV Tracking Pipeline | ✅ Operational | 5.7 fps, YOLOv8n + Kalman + Hungarian |
| Data Collection | ✅ Complete | 25+ sources, 3 seasons, 221K shots |
| Tier 1 ML Models | ✅ 18 trained | Win prob 69.1%, 7 props R²>0.93 |
| External Data Feeds | ✅ Live | Injury / refs / lines wired |
| CV Quality Upgrades | 🟡 Active | Phase 2.5 — pose estimation, per-clip homography |
| Full Game Processing | 🔲 Next | Phase 6 — 20 games → PostgreSQL → shots enriched |
| Possession Simulator | 🔲 Phase 8 | 7-model chain, 10K Monte Carlo |
| Products (Dashboard / Chat) | 🔲 Phase 13–15 | FastAPI → Next.js → Claude AI Chat |

---

## Model Performance

| Model | Metric | Value |
|---|---|---|
| Win Probability (pre-game) | Accuracy | **69.1%** |
| Win Probability | Brier Score | 0.203 |
| xFG v1 (shot quality) | Brier Score | 0.226 (221K shots) |
| Player Props — Points | Walk-forward MAE | 0.308 / R² 0.93 |
| Player Props — Rebounds | Walk-forward MAE | 0.113 / R² 0.94 |
| Player Props — Assists | Walk-forward MAE | 0.093 / R² 0.95 |
| DNP Predictor | ROC-AUC | **0.979** |
| Matchup Model | R² | **0.808** / MAE 4.55 |

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│  INPUTS                                                             │
│                                                                     │
│  Broadcast Video (.mp4)          NBA API + External Sources         │
│  broadcast footage               gamelogs, shot charts, PBP,       │
│  any game, any camera angle      injuries, refs, betting lines      │
└───────────────────┬─────────────────────────┬───────────────────────┘
                    ↓                         ↓
     ┌──────────────────────┐    ┌────────────────────────┐
     │  CV Tracking Layer   │    │  Data Pipeline (src/)  │
     │  src/tracking/       │    │  src/data/             │
     │  YOLOv8 + Kalman +   │    │  25+ sources, 3 seasons│
     │  Hungarian matching  │    │  221K shots, full PBP  │
     └──────────┬───────────┘    └────────────┬───────────┘
                └──────────┬─────────┘
                           ↓
             ┌─────────────────────────┐
             │   Feature Engineering   │
             │   src/features/ + src/  │
             │   analytics/ — 96 metrics│
             └────────────┬────────────┘
                          ↓
          ┌───────────────────────────────┐
          │  90 ML Models (6 tiers)       │
          │  src/prediction/              │
          │  Win prob, props, xFG, matchup│
          └────────────┬──────────────────┘
                       ↓
       ┌───────────────────────────────────┐
       │  Possession Simulator (Phase 8)   │
       │  7-model chain × 10K Monte Carlo  │
       │  → stat distributions per player  │
       └────────────┬──────────────────────┘
                    ↓
   ┌────────────────────────────────────────────┐
   │  Products (Phases 13–15)                   │
   │  FastAPI  →  Betting Dashboard             │
   │           →  Analytics Dashboard (D3)      │
   │           →  AI Chat (Claude API)          │
   └────────────────────────────────────────────┘
```

---

## Repository Structure

```
courtvision/
├── src/
│   ├── tracking/       # CV tracking — YOLOv8, Kalman, re-ID, homography
│   ├── analytics/      # 22 analytics modules — shot quality, betting edge, spacing
│   ├── data/           # Data scrapers — NBA API, BBRef, odds, injuries
│   ├── prediction/     # ML models — win prob, player props, xFG, matchup
│   ├── pipeline/       # Unified processing pipeline
│   ├── features/       # Feature engineering
│   ├── re_id/          # Re-identification neural net
│   ├── detection/      # YOLO detection tools
│   └── utils/          # Shared utilities
├── api/                # FastAPI backend (Phase 13)
├── dashboards/         # Streamlit analytics dashboard
├── frontend/           # Flask game dashboard
├── features/           # CV-computed spatial features (legacy layer)
├── tracking/           # Database + homography layer (legacy)
├── models/             # Phase 1–2 model definitions
├── pipeline/           # Export + render pipeline
├── pipelines/          # CV detection pipeline
├── tests/              # 850+ tests
├── scripts/            # Benchmarks, debug tools, validators
├── data/               # Cached NBA data, trained model artifacts
├── database/           # PostgreSQL schema + migrations
├── config/             # Tracker configuration
├── resources/          # Court panoramas, calibration snapshots
├── docs/               # Architecture docs, API spec
└── vault/              # Obsidian knowledge base — session notes, improvement log
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

Every game processed improves every model. At 200 games the full 50-model stack is running.

---

## The 7-Model Possession Chain (Simulator Core)

```
[1] Play Type → [2] Shot Selector → [3] xFG → [4] TO/Foul
→ [5] Rebound → [6] Fatigue → [7] Substitution
× 10,000 per game = full stat distribution per player
```

---

## Setup

```bash
conda activate basketball_ai   # Python 3.9, PyTorch 2.0.1 + CUDA 11.8
cd courtvision

# Run tests
python -m pytest tests/ -q

# Train win probability model
python src/prediction/win_probability.py --train

# Predict a game
python src/prediction/game_prediction.py --predict GSW BOS
```

---

## Environment

- Python 3.9, conda env: `basketball_ai`
- PyTorch 2.0.1 + CUDA 11.8
- YOLOv8n (ultralytics), OpenCV, XGBoost, scikit-learn
- PostgreSQL (schema at `database/schema.sql`)
