# CourtVision — System Architecture

> Technical shape of the platform. For strategy: [VISION.md](VISION.md). For build sequence: [ROADMAP.md](ROADMAP.md).

---

## The Four Clusters

```
┌─────────────────────────────────────────────────────────────────────┐
│  CLUSTER 1: CV TRACKING                                             │
│  src/tracking/ + src/pipeline/                                      │
│                                                                     │
│  Broadcast video → court-coordinate spatial features                │
│  YOLOv8n → SIFT homography → Kalman+Hungarian → OSNet → EasyOCR   │
│                                                                     │
│  Output: defender_distance, spacing_score, fatigue_index,           │
│          play_type, event_stream, jersey_ids                        │
└─────────────────────┬───────────────────────────────────────────────┘
                      │
┌─────────────────────▼───────────────────────────────────────────────┐
│  CLUSTER 2: DATA INGEST + FEATURE STORE                             │
│  src/ingest/ + src/features/ + src/data/                            │
│                                                                     │
│  NBA API (3 seasons, 221K shots, 3.6K PBP) + CV features +         │
│  betting odds + injury feeds + referee tendencies → unified store   │
│                                                                     │
│  Keyed on (player, game, possession, timestamp)                     │
│  Database: PostgreSQL (target) / SQLite (current ingest queue)      │
└─────────────────────┬───────────────────────────────────────────────┘
                      │
┌─────────────────────▼───────────────────────────────────────────────┐
│  CLUSTER 3: ML PREDICTION + SIMULATION                              │
│  src/prediction/                                                    │
│                                                                     │
│  75 trained models → 10K-path Monte Carlo possession simulator      │
│  7 prop models + win prob + xFG + game total + spread + more        │
│  Calibration layer, meta-model, quantile regression                 │
│                                                                     │
│  Output: full joint distribution over every observable outcome      │
└─────────────────────┬───────────────────────────────────────────────┘
                      │
┌─────────────────────▼───────────────────────────────────────────────┐
│  CLUSTER 4: SERVING + EXECUTION                                     │
│  api/ + src/prediction/betting_portfolio.py                         │
│                                                                     │
│  FastAPI (6 endpoints) + fractional Kelly + Shin devig +            │
│  CLV tracker + multi-book execution router                          │
│                                                                     │
│  Output: bet recommendations, paper/live fills, CLV attribution     │
└─────────────────────────────────────────────────────────────────────┘
```

---

## The Agentic Research Layer (Planned)

The above four clusters are the substrate. The agentic layer is the research machine that runs on top of them.

```
┌─────────────────────────────────────────────────────────────────────┐
│  CLUSTER 5: AGENTIC RESEARCH SYSTEM (not yet built)                │
│                                                                     │
│  Orchestrator Agent                                                 │
│    ├── Researcher Agent: hypothesis generation + literature search  │
│    ├── Engineer Agent: signal implementation + feature wiring       │
│    ├── Validator Agent: holdout testing + IR calculation            │
│    ├── Risk Manager Agent: correlation + Kelly impact               │
│    └── Retirement Monitor: signal decay detection + deprecation     │
│                                                                     │
│  Memory: signal registry + IR history + P&L attribution            │
│  Output: autonomous signal discovery, validation, deployment        │
└─────────────────────────────────────────────────────────────────────┘
```

This is the difference between "a prediction system" and "the Renaissance of sports." See [vault/Plans/Agentic Research System.md](vault/Plans/Agentic%20Research%20System.md).

---

## Component Status

| Component | File(s) | Status |
|-----------|---------|--------|
| YOLOv8n detection | `src/tracking/advanced_tracker.py` | ✅ Running |
| SIFT homography | `src/pipeline/unified_pipeline.py` | ✅ Running |
| Kalman+Hungarian tracking | `src/tracking/advanced_tracker.py` | ✅ Running |
| OSNet re-ID (512-dim) | `src/tracking/osnet_reid.py` | ✅ Running |
| HSV team classification | `src/tracking/color_reid.py` | ✅ Running |
| EasyOCR jersey reading | `src/pipeline/unified_pipeline.py` | ✅ Running |
| EventDetector | `src/pipeline/unified_pipeline.py` | ✅ Running |
| Ball detection/tracking | `src/tracking/ball_detect_track.py` | 🟡 bug: ball_valid_pct=0% on some games |
| Feature engineering (60+ features) | `src/features/feature_engineering.py` | ✅ Done |
| 7 prop models (pts/reb/ast/fg3m/blk/tov/stl) | `src/prediction/player_props.py` | ✅ Holdout validated |
| Win probability (XGBoost) | `src/prediction/win_probability.py` | ✅ 69.1% acc, Brier 0.203 |
| xFG model | `src/prediction/` | ✅ Brier 0.226 on 221K shots |
| Fractional Kelly + shrinkage | `src/prediction/betting_portfolio.py` | ✅ Built |
| Shin devig | `src/prediction/devig.py` | ✅ Built |
| CLV tracker | `src/prediction/betting_portfolio.py` | ✅ Scaffolded (Gate 1 not run) |
| Temporal CV harness | `src/prediction/prop_backtester.py` | ✅ Walk-forward, 48-hr purge |
| Model registry | `data/models/model_registry.json` | ✅ 75 models registered |
| Regression test suite | `tests/` | ✅ 1040 passing |
| FastAPI serving | `api/main.py` | ✅ 6 endpoints |
| PostgreSQL schema | `database/schema.sql` | 🟡 Schema exists, not yet in production |
| Ingest queue (SQLite) | `src/ingest/` | ✅ Running |
| Possession simulator (Monte Carlo) | — | 🔲 Not started |
| Agentic research system | — | 🔲 Not started |
| News ingestion | — | 🔲 Not started |
| Real-time / live betting | — | 🔲 Phase 5+ |

---

## Data Flow (Detailed)

```
Broadcast Video (.mp4)
    │
    ▼
unified_pipeline.py
    ├─ advanced_tracker.py → player detections (bbox, class, conf)
    ├─ SIFT homography → court coordinates (feet, 94×50 plane)
    ├─ osnet_reid.py → player identity (512-dim embedding)
    ├─ color_reid.py → team classification (HSV clusters)
    ├─ ball_detect_track.py → ball position + possession
    ├─ EasyOCR → jersey numbers + game clock
    └─ EventDetector → shot/pass/dribble/screen/rebound/foul events
    │
    ▼
tracking_data.csv + events.json
    │
    ▼
feature_engineering.py
    ├─ CV spatial features: defender_distance, spacing_score, fatigue_index
    ├─ CV temporal: rolling shots/passes/dribbles over 5/10/20-frame windows
    ├─ NBA API features: pace, team total, lineup on/off, ref, altitude, travel
    └─ Market features: Pinnacle no-vig, line velocity, steam flag
    │
    ▼
Model Stack (75 models)
    ├─ Tier 1: Win prob, 7 prop models, game total, spread, pace, blowout
    ├─ Tier 2: xFG (Brier 0.226), shot zones, xPTS
    ├─ Tier 2B: DNP predictor (AUC 0.979), load management, injury return
    ├─ Tier 3-4: gated on 80+ CV games (retrain pending)
    └─ Meta-model: Ridge on stacked outputs
    │
    ▼
betting_portfolio.py
    ├─ Shin devig → implied probabilities
    ├─ Kelly fraction (0.25-0.5) × model confidence tier
    ├─ Ledoit-Wolf shrinkage on 7×7 residual covariance
    └─ CLV tracker → vs Pinnacle close
    │
    ▼
FastAPI (api/main.py)
    └─ 6 endpoints: predictions, props, win_prob, kelly, clv, health
```

---

## Integration Points

| System | Where it connects | Current state |
|--------|------------------|---------------|
| NBA API | `src/data/nba_api_collector.py` | ✅ 569 gamelogs, 221K shots, 3.6K PBP |
| The Odds API | `src/data/odds_collector.py` | ✅ Live lines 6 books |
| Pinnacle (CLV) | `src/prediction/betting_portfolio.py` | 🟡 Scaffolded, Gate 1 pending |
| Injury feeds | `src/data/injury_collector.py` | ✅ ESPN + NBA official |
| RunPod (CV compute) | `scripts/launch_multigpu.sh` | ✅ Operational |
| B2 storage | `scripts/sync_remote.py` | ✅ Syncing |
| PostgreSQL | `database/schema.sql` | 🟡 Schema ready, migration pending |

---

## Module Ownership Map

| Concern | Owner file |
|---------|-----------|
| Pipeline orchestration | `src/pipeline/unified_pipeline.py` |
| Player tracking | `src/tracking/advanced_tracker.py` |
| Ball tracking | `src/tracking/ball_detect_track.py` |
| Team color re-ID | `src/tracking/color_reid.py` |
| Identity re-ID (deep) | `src/tracking/osnet_reid.py` |
| Feature engineering | `src/features/feature_engineering.py` |
| Prop models | `src/prediction/player_props.py` |
| Win probability | `src/prediction/win_probability.py` |
| Kelly + CLV | `src/prediction/betting_portfolio.py` |
| Devig | `src/prediction/devig.py` |
| Backtesting | `src/prediction/prop_backtester.py` |
| Risk guards | `src/prediction/risk_guards.py` |
| API serving | `api/main.py` |
| Ingest queue | `src/ingest/` |
| Batch runner | `scripts/batch_season.py` |

---

## Key Invariants

- `_VRAM_FLUSH_INTERVAL` in `unified_pipeline.py` must be **3000** (not 100 — causes OOM crashes)
- Panorama SIFT ratio: 3-10 (not default 2.0 — broadcast frames break at default)
- OMP thread cap: set before any YOLO call (`OMP_NUM_THREADS=4`)
- Never run: `run.py`, `loop_processor.py`
- Video: always headless (`--no-show`), never `cv2.imshow`
- PostgreSQL and CV clusters are isolated — never mix in same process

---

*Related: [VISION.md](VISION.md) · [ROADMAP.md](ROADMAP.md) · [vault/Pipeline/System Architecture.md](vault/Pipeline/System%20Architecture.md)*
