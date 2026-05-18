# Repository Structure Guide

> Note: this file includes historical target structure notes from prior phases. For current public-facing canonical navigation, use `docs/PROJECT_INDEX.md`.

This document describes the intended clean structure of the repository, current redundancies to resolve, and the single source of truth for each module.

---

## Target Structure

```
nba-ai-system/
│
├── src/                              # ALL production source code lives here
│   ├── tracking/                     # Computer vision tracking (20 modules)
│   │   ├── advanced_tracker.py       # AdvancedFeetDetector — main tracking orchestrator
│   │   ├── ball_detect_track.py      # Ball tracking (Hough + CSRT + optical flow)
│   │   ├── color_reid.py             # Team color separation (KMeans + EMA)
│   │   ├── court_detector.py         # Per-clip court detection (Phase 2.5)
│   │   ├── event_detector.py         # Shot / pass / dribble detection
│   │   ├── jersey_ocr.py             # Jersey number reading (EasyOCR)
│   │   ├── osnet_reid.py             # OSNet appearance model
│   │   ├── play_type_classifier.py   # Play type labeling
│   │   ├── player.py                 # Player data class
│   │   ├── player_detection.py       # YOLOv8 wrapper
│   │   ├── player_identity.py        # Jersey OCR → player name resolution
│   │   ├── possession_classifier.py  # Possession type labeling
│   │   ├── rectify_court.py          # SIFT homography estimation
│   │   ├── scoreboard_ocr.py         # Game clock + score extraction
│   │   ├── tracker_config.py         # Tracking hyperparameters
│   │   ├── evaluate.py               # Tracking quality metrics
│   │   ├── video_handler.py          # Video I/O
│   │   └── utils/
│   │       └── plot_tools.py
│   │
│   ├── data/                         # Data collection (24 modules)
│   │   ├── bbref_scraper.py          # Basketball Reference (BPM, VORP, WS)
│   │   ├── cache_utils.py            # TTL-aware file caching
│   │   ├── contracts_scraper.py      # HoopsHype salary data
│   │   ├── db.py                     # PostgreSQL connection helper
│   │   ├── game_matcher.py           # Match tracking game to NBA game_id
│   │   ├── injury_monitor.py         # NBA official + Rotowire injury feed
│   │   ├── line_monitor.py           # Opening/closing line tracking
│   │   ├── lineup_data.py            # 5-man unit on/off data
│   │   ├── nba_enricher.py           # CV shot → NBA PBP outcome matching
│   │   ├── nba_stats.py              # Core NBA Stats API wrapper
│   │   ├── nba_tracking_stats.py     # Hustle / on-off / synergy / defender zones
│   │   ├── news_scraper.py           # ESPN headline feed
│   │   ├── odds_scraper.py           # Historical betting lines (OddsPortal)
│   │   ├── pbp_scraper.py            # Play-by-play (3,685 games)
│   │   ├── player_identity.py        # Player identity resolution
│   │   ├── player_scraper.py         # 63-metric self-improving player loop
│   │   ├── prop_validator.py         # Prop data quality validation
│   │   ├── props_scraper.py          # DraftKings / FanDuel live props
│   │   ├── ref_tracker.py            # Referee tendencies + assignments
│   │   ├── schedule_context.py       # Rest days, travel, back-to-back
│   │   ├── shot_chart_scraper.py     # Shot chart data (221K shots)
│   │   └── video_fetcher.py          # yt-dlp game clip downloader
│   │
│   ├── prediction/                   # ML model training + inference (8 modules)
│   │   ├── clutch_efficiency.py      # Clutch efficiency composite
│   │   ├── game_models.py            # 5 game-level models
│   │   ├── game_prediction.py        # Pre-game prediction orchestrator
│   │   ├── matchup_model.py          # M22 matchup model
│   │   ├── player_props.py           # 7 player prop models
│   │   ├── shot_zone_tendency.py     # Zone tendency model
│   │   ├── win_probability.py        # Pre-game win probability (XGBoost)
│   │   └── xfg_model.py              # Expected field goal (xFG v1)
│   │
│   ├── analytics/                    # Basketball analytics signals (20 modules)
│   │   ├── betting_edge.py           # CLV backtest + EV computation
│   │   ├── defense_pressure.py       # Defensive pressure index
│   │   ├── defensive_scheme.py       # Zone vs man detection
│   │   ├── drive_analysis.py         # Drive frequency + FTA conversion
│   │   ├── game_flow.py              # Score flow + momentum
│   │   ├── lineup_synergy.py         # 5-man unit net rating
│   │   ├── micro_timing.py           # Shot clock pressure + fatigue
│   │   ├── momentum.py               # EMA-smoothed momentum
│   │   ├── momentum_events.py        # Momentum event detection
│   │   ├── off_ball_events.py        # Cut / screen / off-ball distance
│   │   ├── passing_network.py        # Touch map + ball movement
│   │   ├── pick_and_roll.py          # P&R frequency + coverage type
│   │   ├── play_recognition.py       # Rule-based play type labeling
│   │   ├── player_defensive_pressure.py # Per-player defensive impact
│   │   ├── rebound_positioning.py    # Crash angle + box-out detection
│   │   ├── shot_creation.py          # Shot creation type classification
│   │   ├── shot_quality.py           # Shot quality score (0-1)
│   │   ├── space_control.py          # Spatial control metrics
│   │   ├── spacing.py                # Convex hull team spacing
│   │   └── spatial_types.py          # Shared spatial type definitions
│   │
│   ├── features/                     # Feature engineering
│   │   └── feature_engineering.py   # 60+ ML features, rolling windows
│   │
│   ├── pipeline/                     # Pipeline orchestration (6 modules)
│   │   ├── unified_pipeline.py       # Main pipeline: video → CSV
│   │   ├── model_pipeline.py         # Train / eval / save orchestration
│   │   ├── tracking_pipeline.py      # CV-only pipeline
│   │   ├── feature_pipeline.py       # Feature computation pipeline
│   │   ├── data_loader.py            # Data loading utilities
│   │   └── run_pipeline.py           # Pipeline CLI
│   │
│   ├── re_id/                        # Deep appearance re-identification
│   │   ├── models/model.py           # CBAM attention architecture
│   │   ├── module/
│   │   │   ├── cbam.py               # Convolutional Block Attention Module
│   │   │   ├── reid.py
│   │   │   ├── loss.py
│   │   │   └── transform.py
│   │   └── tools/
│   │       ├── inference.py
│   │       └── train.py
│   │
│   ├── detection/                    # YOLOv8 detection wrapper
│   │   └── detection/
│   │       ├── models/detection_model.py
│   │       └── tools/
│   │           ├── inference.py
│   │           └── train.py
│   │
│   ├── api/                          # FastAPI backend (Phase 13)
│   │   ├── main.py
│   │   ├── analytics_router.py
│   │   └── models_router.py
│   │
│   ├── apps/dashboards/              # Dashboard UI (Phase 14)
│   │   ├── app.py
│   │   └── charts.py
│   │
│   └── utils/                        # Shared utilities
│       ├── bbox_crop.py
│       ├── frame.py
│       └── visualize.py
│
├── data/                             # All data artifacts
│   ├── models/                       # Trained model files (18 JSON/PKL)
│   ├── nba/                          # NBA API cache (gamelogs, shots, PBP, etc.)
│   ├── external/                     # BBRef, odds history, contracts
│   └── games/                        # Per-game: video + tracking CSV outputs
│       └── {game_id}/
│           ├── clip.mp4
│           ├── tracking_data.csv
│           ├── shot_log.csv
│           ├── possessions.csv
│           └── features.csv
│
├── database/                         # PostgreSQL schema
│   └── schema.sql
│
├── tests/                            # Test suite (pytest)
│   ├── test_phase2.py                # 431 tracking tests
│   └── test_phase3.py                # 21 ML model tests
│
├── docs/                             # Technical documentation
│   ├── decisions.md                  # Architecture decisions
│   ├── experiments.md                # Model experiments + results
│   ├── improvements.md               # Continuous improvement log
│   └── repository_structure.md       # This file
│
├── resources/                        # Model weights + court panoramas
│   ├── yolov8n.pt                    # Primary detector (47MB)
│   ├── yolov8x.pt                    # High-accuracy detector (137MB)
│   ├── yolov8n-pose.pt               # Pose estimation
│   └── Rectify1.npy                  # Precomputed homography
│
├── scripts/                          # Utility scripts (non-production)
│   ├── debug/                        # Diagnostic scripts
│   │   ├── _bench_run.py
│   │   ├── _check_ball.py
│   │   ├── _check_track.py
│   │   └── ...
│   └── loops/                        # Development loops
│       ├── autonomous_loop.py
│       └── smart_loop.py
│
├── vault/                            # Obsidian knowledge vault
├── notebooks/                        # Jupyter notebooks
│
├── run_clip.py                       # MAIN ENTRY: process a game clip
├── run_full_game.py                  # Full game processing
├── README.md
├── SYSTEM_OVERVIEW.md
├── DATA_SCHEMA.md
├── ROADMAP.md
├── MACHINE_LEARNING.md
├── requirements.txt
└── .env.example
```

---

## Current Redundancies to Resolve

The repository has grown organically, resulting in several parallel implementations that should be consolidated.

### 1. Three Pipeline Directories

| Directory | Status | Action |
|-----------|--------|--------|
| `src/pipeline/` | ✅ Active | Keep — this is the production pipeline |
| `pipeline/` (root) | Legacy | Archive → `scripts/legacy/pipeline/` |
| `pipelines/` (root) | Legacy | Archive → `scripts/legacy/pipelines/` |

**Single source of truth:** `src/pipeline/unified_pipeline.py`

The root `pipeline/` contains `run_all.py`, `ingest_game.py`, `export_data.py`, `render_video.py`, `generate_graphs.py` — all superseded by `src/pipeline/` modules.

---

### 2. Two Model Directories

| Directory | Status | Action |
|-----------|--------|--------|
| `src/prediction/` | ✅ Active | Keep — production models |
| `models/` (root) | Legacy | Move `base.py` to `src/prediction/base.py`; archive rest |

The root `models/` contains `win_probability.py`, `shot_probability.py`, `momentum_detector.py`, `player_impact.py`, `lineup_optimizer.py` — early prototypes, superseded by `src/prediction/`.

The `models/artifacts/` directory contains 5 older `.joblib` files — these are NOT the current trained models. Current models are in `data/models/`.

---

### 3. Two Tracking Directories

| Directory | Status | Action |
|-----------|--------|--------|
| `src/tracking/` | ✅ Active | Keep — production tracker |
| `tracking/` (root) | Legacy | Archive → `scripts/legacy/tracking/` |

The root `tracking/` contains 8 files: `tracker.py`, `ball_kalman.py`, `homography.py`, `coordinate_writer.py`, `database.py`, `seed_historical.py`, `schema.sql`. These predate the current `src/tracking/` architecture.

The `tracking/schema.sql` is distinct from `database/schema.sql` — the latter is authoritative.

---

### 4. Debug Scripts in Root Directory

14 `_*.py` diagnostic scripts currently live in the repository root. These should move to `scripts/debug/`:

```
_bench_run.py       → scripts/debug/
_check_ball.py      → scripts/debug/
_check_ball2.py     → scripts/debug/
_check_map.py       → scripts/debug/
_check_pano.py      → scripts/debug/
_check_track.py     → scripts/debug/
_check_video.py     → scripts/debug/
_check_video2.py    → scripts/debug/
_diag_atl.py        → scripts/debug/
_diag_det.py        → scripts/debug/
_diag_det2.py       → scripts/debug/
_diag_fps.py        → scripts/debug/
_diag_poss.py       → scripts/debug/
_fetch_gsw_pbp.py   → scripts/debug/
```

---

### 5. Multiple Entry Points

| Script | Status | Action |
|--------|--------|--------|
| `run_clip.py` | ✅ Production | Keep in root |
| `run_full_game.py` | ✅ Production | Keep in root |
| `run.py` | Legacy | Archive → `scripts/legacy/` |
| `process_game.py` | Legacy | Archive → `scripts/legacy/` |
| `autonomous_loop.py` | Dev tool | Move → `scripts/loops/` |
| `smart_loop.py` | Dev tool | Move → `scripts/loops/` |
| `improve_loop.py` | Dev tool | Move → `scripts/loops/` |
| `monitor_loop.py` | Dev tool | Move → `scripts/loops/` |
| `continuous_runner.py` | Dev tool | Move → `scripts/loops/` |
| `quality_report.py` | Utility | Move → `scripts/` |
| `check_video.py` | Diagnostic | Move → `scripts/debug/` |

---

## Single Source of Truth

| Component | Canonical Location |
|-----------|-------------------|
| Player tracking | `src/tracking/advanced_tracker.py` |
| Ball tracking | `src/tracking/ball_detect_track.py` |
| Team color re-ID | `src/tracking/color_reid.py` |
| Court homography | `src/tracking/rectify_court.py` |
| Event detection | `src/tracking/event_detector.py` |
| Feature engineering | `src/features/feature_engineering.py` |
| Pipeline orchestration | `src/pipeline/unified_pipeline.py` |
| Win probability model | `src/prediction/win_probability.py` |
| Player props model | `src/prediction/player_props.py` |
| xFG model | `src/prediction/xfg_model.py` |
| NBA API data | `src/data/nba_stats.py` + `nba_tracking_stats.py` |
| Shot chart data | `src/data/shot_chart_scraper.py` |
| Caching layer | `src/data/cache_utils.py` |
| Database schema | `database/schema.sql` |
| Trained model artifacts | `data/models/` |
| NBA API cache | `data/nba/` |
| External data | `data/external/` |
