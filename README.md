# NBA AI System

> **A self-improving NBA analytics and prediction engine — combining computer vision player tracking, 25+ data sources, and 90 ML models to simulate every game 10,000 times, surface betting edges, and deliver professional-grade analytics through a conversational AI interface.**

---

## What This Is

This system extracts spatial data from NBA broadcast video that no public tool provides, combines it with exhaustive statistical data from the NBA API and external sources, and feeds everything into a layered machine learning stack.

The end product is a **possession-by-possession Monte Carlo game simulator** that produces full stat distributions for every player — not just point estimates, but the entire probability curve. Those distributions get compared against sportsbook lines to flag edges automatically.

The closest comparable system is Second Spectrum, which NBA teams pay $1M+/year for. This is the self-built version.

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

## Three End Products

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
| CLV Backtest Baseline | Correct winner | 70.7% / MAE 10.2 pts |

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│  INPUTS                                                             │
│                                                                     │
│  Broadcast Video (.mp4)          NBA API + External Sources         │
│  broadcast footage,              gamelogs, shot charts, PBP,        │
│  game clips (30s–full game)      advanced stats, synergy,           │
│                                  contracts, odds, injuries, refs     │
└──────────┬───────────────────────────────┬──────────────────────────┘
           │                               │
           ▼                               ▼
┌──────────────────────┐      ┌────────────────────────────────────┐
│  CV TRACKING         │      │  DATA COLLECTION PIPELINE          │
│                      │      │                                    │
│  Court homography    │      │  Smart TTL cache layer             │
│  YOLOv8n detection   │      │  25+ data sources, 3 seasons       │
│  Kalman tracking     │      │  Live feeds (injury/lines/refs)     │
│  HSV team re-ID      │      │                                    │
│  Jersey OCR          │      │  data/nba/*.json                   │
│  Ball detection      │      │  data/external/*.json              │
│  Event detection     │      │                                    │
│  → tracking_data.csv │      │                                    │
└──────────┬───────────┘      └──────────────┬─────────────────────┘
           └──────────────┬──────────────────┘
                          ▼
         ┌────────────────────────────────────────┐
         │  FEATURE ENGINEERING (60+ features)   │
         │  CV spatial + NBA API contextual       │
         │  Rolling windows [5 / 10 / 20 games]  │
         │  Bayesian shrinkage toward season avg  │
         └─────────────────────┬──────────────────┘
                               │
                               ▼
         ┌────────────────────────────────────────┐
         │  ML MODEL STACK (90 models, 7 tiers)  │
         │                                        │
         │  Tier 1  Win prob, props, game models ✅│
         │  Tier 2  xFG, shot zones, clutch      ✅│
         │  Tier 3  CV behavioral (Phase 7)      🔲│
         │  Tier 4–7  Simulator + live LSTM      🔲│
         └─────────────────────┬──────────────────┘
                               │
                               ▼
         ┌────────────────────────────────────────┐
         │  POSSESSION SIMULATOR (Phase 8)        │
         │                                        │
         │  [1] Play Type → [2] Shot Selector     │
         │  → [3] xFG → [4] TO/Foul              │
         │  → [5] Rebound → [6] Fatigue           │
         │  → [7] Substitution                    │
         │  × 10,000 simulations per game         │
         │  = Full stat distribution per player   │
         └─────────────────────┬──────────────────┘
                               │
                               ▼
         ┌────────────────────────────────────────┐
         │  Compare vs sportsbook lines           │
         │  → Flag +EV edges                      │
         │  → Kelly-size positions                │
         │  → Track CLV (closing line value)      │
         └─────────────────────┬──────────────────┘
                               │
                               ▼
     ┌─────────────────────────────────────────────────┐
     │  FastAPI → Next.js Dashboard + Claude AI Chat   │
     │  render_chart tool → inline chart rendering     │
     └─────────────────────────────────────────────────┘
```

---

## Dataset

| Source | Volume | Status |
|---|---|---|
| Player gamelogs (NBA API) | 622 players, 3 seasons | ✅ |
| Shot charts with court coordinates | 221,866 shots | ✅ |
| Play-by-play | 3,627 / 3,685 games (98.4%) | ✅ |
| Player advanced stats | 569 / 569 players | ✅ |
| Hustle stats | 567 players × 3 seasons | ✅ |
| On/off splits | 569 players × 3 seasons | ✅ |
| Defender zone FG% allowed | 566 players × 3 seasons | ✅ |
| Matchup data (who guards whom) | 2,200+ records × 3 seasons | ✅ |
| Synergy play types | 600 records (offense + defense) | ✅ |
| BBRef advanced (VORP / WS48 / BPM) | 736 players × 3 seasons | ✅ |
| Historical closing lines | 1,225+ games × 3 seasons | ✅ |
| Player contracts | 523 players (171 walk-year) | ✅ |
| CV tracking rows | 29,220 rows (17 short clips) | 🟡 Full games next |

---

## Technology Stack

| Layer | Technology |
|---|---|
| Computer Vision | YOLOv8n (detection), OpenCV (ball tracking), EasyOCR (jersey OCR) |
| Player Tracking | Kalman filter (6D state), Hungarian algorithm, HSV appearance re-ID |
| Court Mapping | SIFT feature matching, 3-tier homography, drift detection every 30 frames |
| ML Models | XGBoost (game/props/matchup), scikit-learn (DNP), 57-feature vectors |
| Data Collection | nba_api, BeautifulSoup (BBRef), feedparser (RotoWire) |
| Backend API | FastAPI + Redis caching + WebSocket |
| Database | PostgreSQL (9 tables, 2 views — schema ready) |
| Frontend | Next.js + TypeScript + D3.js + Recharts + TailwindCSS (Phase 14) |
| AI Chat | Claude API (claude-sonnet-4-6) + 10 tools + render_chart (Phase 15) |
| Environment | Python 3.9, conda `basketball_ai`, PyTorch 2.0.1 + CUDA 11.8 |

---

## Repository Structure

```
nba-ai-system/
│
├── src/                        # All production source code
│   ├── tracking/               # Computer vision tracking (20 modules)
│   │   ├── advanced_tracker.py     # AdvancedFeetDetector (Kalman + Hungarian + HSV)
│   │   ├── ball_detect_track.py    # BallDetectTrack (Hough + CSRT + optical flow)
│   │   ├── rectify_court.py        # SIFT panorama + 3-tier homography
│   │   ├── event_detector.py       # Shot / pass / dribble detection
│   │   ├── jersey_ocr.py           # EasyOCR dual-pass jersey number reader
│   │   └── color_reid.py           # TeamColorTracker (similar-color aware)
│   │
│   ├── prediction/             # ML model training and inference (8 modules)
│   │   ├── win_probability.py      # XGBoost, 27 features, 69.1% accuracy
│   │   ├── player_props.py         # 7 prop models (pts/reb/ast/3pm/stl/blk/tov)
│   │   ├── game_models.py          # Total / spread / blowout / first-half / pace
│   │   ├── xfg_model.py            # Expected field goal % (221K shots)
│   │   ├── dnp_predictor.py        # DNP probability (ROC-AUC 0.979)
│   │   └── matchup_model.py        # Player matchup efficiency (R² 0.808)
│   │
│   ├── analytics/              # Analytics computation (20 modules)
│   │   ├── betting_edge.py         # EV, Kelly sizing, CLV, edge detection
│   │   ├── shot_quality.py         # Shot quality score (0–1)
│   │   ├── defense_pressure.py     # Defensive pressure metrics
│   │   ├── momentum.py             # Scoring run / momentum detection
│   │   └── prop_correlation.py     # Cross-player prop correlation matrix
│   │
│   ├── data/                   # Data collection and enrichment (24 modules)
│   │   ├── nba_stats.py            # NBA API wrapper
│   │   ├── nba_enricher.py         # Shot outcome enrichment via PBP matching
│   │   ├── player_scraper.py       # 63-metric self-improving scraper
│   │   ├── injury_monitor.py       # RotoWire RSS + NBA official injury PDF
│   │   ├── bbref_scraper.py        # Basketball Reference VORP/WS48/BPM
│   │   ├── odds_scraper.py         # Historical closing lines (OddsPortal)
│   │   └── props_scraper.py        # Live DraftKings/FanDuel props (15min TTL)
│   │
│   ├── pipeline/               # Pipeline orchestration (6 modules)
│   │   ├── unified_pipeline.py     # CV → possession → spatial metrics → CSV
│   │   └── model_pipeline.py       # Train / evaluate / save all models
│   │
│   ├── features/               # Feature engineering
│   │   └── feature_engineering.py  # 60+ spatial and temporal ML features
│   │
│   └── re_id/                  # Deep player re-identification model
│
├── api/                        # FastAPI backend
│   ├── main.py
│   └── routers/
│       ├── predictions.py
│       └── analytics.py
│
├── dashboards/                 # Streamlit prototype dashboard
│
├── database/                   # PostgreSQL schema
│   └── schema.sql                  # 9 tables, 2 views
│
├── tests/                      # Test suite (431+ tests)
│   ├── test_phase2.py
│   └── test_phase3.py
│
├── scripts/                    # Utility and diagnostic scripts
│   ├── benchmark/
│   ├── diagnostics/
│   └── validate/
│
├── resources/                  # Model weights and court templates
│
├── data/                       # Data artifacts (gitignored — large files)
│   ├── models/                     # 18 trained model files
│   ├── nba/                        # NBA API cache (3 seasons)
│   ├── external/                   # BBRef, historical lines, contracts
│   └── games/                      # Per-game tracking outputs
│
├── docs/                       # Full documentation suite
│   ├── ROADMAP.md
│   ├── ARCHITECTURE.md
│   ├── ML_MODELS.md
│   ├── DATA.md
│   ├── CV_TRACKING.md
│   ├── BETTING.md
│   └── API.md
│
└── vault/                      # Obsidian knowledge vault
    └── Project Vision.md
```

---

## Quick Start

```bash
# Clone and set up environment
git clone https://github.com/neeljshah/nba-ai-system.git
cd nba-ai-system
conda create -n basketball_ai python=3.9
conda activate basketball_ai
pip install -r requirements.txt

# Train win probability model (NBA API only — no video needed)
python src/prediction/win_probability.py --train

# Predict a game
python src/prediction/game_prediction.py --predict GSW BOS

# Predict player props
python -c "
from src.prediction.player_props import predict_props
print(predict_props('Jayson Tatum', 'MIL', '2024-25'))
"

# Run the full test suite
python -m pytest tests/ -q

# Start the API
uvicorn api.main:app --reload
```

---

## The Self-Improving Loop

```
New game (video + game-id)
    ↓
CV tracker → positions + spacing + events + play types
    ↓
NBA API enrichment → shot outcomes + possession results
    ↓
PostgreSQL → all data stored, versioned by tracker_version + date
    ↓
Auto-retrain → triggered at 20 / 50 / 100 / 200 game milestones
    ↓
Simulator improves → predictions more accurate
    ↓
CLV tracking → did your bet beat the closing line?
    ↓
Feedback into confidence calibration → better bet sizing
    ↓
Loop → next game → repeat
```

Every game processed makes every model better. At 200 games the full 90-model stack is running.

---

## Competitive Position

| Feature | This System | Second Spectrum | Public Tools |
|---|---|---|---|
| CV tracking from broadcast video | ✅ | ✅ (proprietary) | ❌ |
| Spatial features (defender dist, spacing) | ✅ | ✅ | ❌ |
| ML player prop prediction | ✅ 18 models | ❌ | Partial |
| Monte Carlo game simulator | 🔲 Phase 8 | ❌ | ❌ |
| Betting edge detection + Kelly sizing | 🔲 Phase 11 | ❌ | Partial |
| AI chat with inline chart rendering | 🔲 Phase 15 | ❌ | ❌ |
| Cost | Free (self-built) | $1M+/year | Free–$50/mo |

---

## Accuracy Targets by Phase

| Phase | Win Probability | Props MAE (pts) | xFG Brier |
|---|---|---|---|
| 4 — current | 69.1% | 0.308 | 0.226 |
| 4.6 — feature wiring | ~70–71% | ~0.22 | — |
| 7 — CV behavioral models | ~72–73% | ~0.18 | ~0.200 |
| 10 — 50–100 games | ~74–76% | ~0.15 | ~0.185 |
| 16 — full stack, 200+ games | ~76–78% | ~0.12 | ~0.175 |

---

## Documentation

| Document | Contents |
|---|---|
| [docs/ROADMAP.md](docs/ROADMAP.md) | Full 18-phase development plan with deliverables and success criteria |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Complete system architecture and module-level data flow |
| [docs/ML_MODELS.md](docs/ML_MODELS.md) | All 90 models — inputs, outputs, tier, status, build order |
| [docs/DATA.md](docs/DATA.md) | Every data source, collection method, cache TTL, and schema |
| [docs/CV_TRACKING.md](docs/CV_TRACKING.md) | Computer vision pipeline — detection, tracking, homography, events |
| [docs/BETTING.md](docs/BETTING.md) | Betting system — EV calculation, Kelly sizing, CLV workflow |
| [docs/API.md](docs/API.md) | FastAPI backend — all endpoints with request/response schemas |

---

*Private repository — all rights reserved.*
