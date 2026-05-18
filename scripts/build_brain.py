"""
build_brain.py — Generate a densely interlinked Obsidian knowledge graph
for the CourtVision NBA AI system.

Creates ~50 atomic topic notes in vault/ with heavy [[wikilinks]]
cross-referencing to produce a rich graph view.

Run: python scripts/build_brain.py
"""
from __future__ import annotations
import os
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parent.parent
VAULT = ROOT / "vault"
TODAY = datetime.now().strftime("%Y-%m-%d")

NOTES: dict[str, tuple[str, str]] = {}  # path -> (frontmatter_tags, content)


def note(path: str, tags: list[str], content: str):
    tag_str = ", ".join(tags)
    NOTES[path] = (tag_str, content)


# ═══════════════════════════════════════════════════════════════════
# CLUSTER 1: CV PIPELINE
# ═══════════════════════════════════════════════════════════════════

note("CV Pipeline/CV Pipeline", ["cv", "overview"], """
# CV Pipeline

The computer vision pipeline extracts spatial features from broadcast NBA video that no public dataset contains. This is the core moat.

## Flow

`Broadcast Video` → [[YOLOv8n Detection]] → [[Kalman-Hungarian Tracker]] → [[OSNet Re-ID]] → [[Court Mapping]] → [[Event Detection]] → [[Feature Engineering]]

## Components

| Stage | Module | Output |
|-------|--------|--------|
| Detection | [[YOLOv8n Detection]] | Player/ball bounding boxes |
| Tracking | [[Kalman-Hungarian Tracker]] | Persistent track IDs |
| Re-ID | [[OSNet Re-ID]] + [[Team Classification]] | Player identity across cuts |
| Court | [[SIFT Homography]] → [[Court Mapping]] | Real-world coordinates |
| Scoreboard | [[EasyOCR Scoreboard]] | Score, clock, quarter |
| Events | [[Event Detection]] | Possessions, shots, turnovers |
| Ball | [[Ball Tracking]] | Ball position, possession |

## Key Files

- `src/pipeline/unified_pipeline.py` — orchestrator
- `src/tracking/advanced_tracker.py` — [[YOLOv8n Detection]] + [[Kalman-Hungarian Tracker]]
- `src/tracking/osnet_reid.py` — [[OSNet Re-ID]]
- `src/tracking/color_reid.py` — [[Team Classification]]

## Performance

- FPS: ~12-15 on RTX 4060 (local), ~18-22 on RTX 3090 ([[RunPod Operations]])
- Ball valid: 40-80% depending on broadcast angle
- Re-ID accuracy: ~85% within-quarter, drops across commercial breaks

## Links

→ Feeds [[Feature Engineering]] with [[Spatial Features]]
→ Enables [[Defender Distance]], [[Spacing Score]], [[Fatigue Metrics]]
→ Output stored in `data/tracking/` per game
→ Quality tracked in [[CV Data Status]]
→ Improvements logged in [[Tracker Improvements]]
""")

note("CV Pipeline/YOLOv8n Detection", ["cv", "detection"], """
# YOLOv8n Detection

Ultralytics YOLOv8-nano runs player and ball detection on every frame.

## Architecture

- Model: `yolov8n.pt` (6.3M params) — fast enough for real-time on [[GPU Optimization|consumer GPUs]]
- Classes: person (0), sports_ball (32)
- Confidence: 0.25 (players), 0.15 (ball — lower due to small size)
- NMS IoU: 0.45

## Integration

Feeds into [[Kalman-Hungarian Tracker]] for temporal consistency.
Ball detections flow to [[Ball Tracking]] with Kalman smoothing.
Player boxes are cropped for [[OSNet Re-ID]] and [[Team Classification]].

## Key Issues

- Ball detection drops when occluded by players → [[Ball Tracking]] uses Kalman prediction
- Small players at broadcast distance → misses at court edges
- Trained on COCO, not NBA-specific → fine-tuning planned ([[Build Phases|Phase 7]])

## Files

- `src/tracking/advanced_tracker.py` — `AdvancedFeetDetector`
- `resources/yolov8n.pt` — pretrained weights
- YOLO prefetch batching wired but inactive (`_yolo_frame_buf`)

→ Part of [[CV Pipeline]]
→ Output consumed by [[Kalman-Hungarian Tracker]], [[Ball Tracking]]
""")

note("CV Pipeline/SIFT Homography", ["cv", "homography"], """
# SIFT Homography

SIFT feature matching computes the perspective transform from broadcast frame to court plane.

## Method

1. Extract SIFT keypoints from current frame
2. Match against [[Court Mapping|court template]] or [[Panorama Stitching|panorama]]
3. RANSAC to find homography matrix H
4. Apply H to player feet positions → real-world (x, y) in feet

## Parameters

- Ratio test: 0.7 (Lowe's ratio)
- RANSAC threshold: 5.0 pixels
- Min inliers: 10
- Panorama ratio: 3-10 (broadcast pano fix)
- Temporal window: 5 seconds for pano matching

## Known Issues

- Broadcast panoramas break standard SIFT — ratio 3-10 with 5s window is the fix
- Court markings provide best features; crowd/ads cause false matches
- Fallback to `pano_enhanced.png` when live pano fails
- Drift accumulates over long sequences → periodic re-anchor needed

## Files

- `unified_pipeline.py` → `_build_panorama()`, `_compute_homography()`

→ Core of [[Court Mapping]]
→ Enables [[Spatial Features]] like [[Defender Distance]] and [[Spacing Score]]
→ Part of [[CV Pipeline]]
""")

note("CV Pipeline/Kalman-Hungarian Tracker", ["cv", "tracking"], """
# Kalman-Hungarian Tracker

Multi-object tracking using Kalman filter for motion prediction and Hungarian algorithm for assignment.

## Design

1. **Kalman Filter**: Predicts next position using constant-velocity model
2. **Hungarian Algorithm**: Optimal assignment of detections to existing tracks
3. **Track lifecycle**: birth (3 consecutive detections) → active → death (30 frame gap)

## Integration

- Receives detections from [[YOLOv8n Detection]]
- Assigns persistent track IDs across frames
- Feeds [[OSNet Re-ID]] for cross-cut identity matching
- Provides trajectories for [[Spatial Features]] computation

## Performance

- Track fragmentation: ~5-8% per quarter
- ID switches: reduced by [[OSNet Re-ID]] re-identification
- Handles 10-12 simultaneous players reliably

## Files

- `src/tracking/advanced_tracker.py`

→ Part of [[CV Pipeline]]
→ Output used by [[Feature Engineering]], [[Event Detection]]
""")

note("CV Pipeline/OSNet Re-ID", ["cv", "reid"], """
# OSNet Re-ID

OSNet (Omni-Scale Network) generates 512-dimensional appearance embeddings for player re-identification.

## Architecture

- Model: `osnet_x0_25_imagenet.pth` (pre-trained, not NBA fine-tuned)
- Embedding: 512-dim L2-normalized vector per player crop
- Matching: cosine similarity with threshold 0.6

## Purpose

Re-identify players after:
- Camera cuts / commercial breaks
- Severe occlusion
- Track fragmentation in [[Kalman-Hungarian Tracker]]

## Integration

- Crops from [[YOLOv8n Detection]] → embedding extraction
- Combined with [[Team Classification]] (color) for joint identity
- Gallery maintained per-game with top-K embeddings per player

## Limitations

- Not fine-tuned on NBA data → jersey number discrimination is weak
- Similar team uniforms cause confusion (white vs light gray)
- Accuracy: ~85% within-quarter, ~70% across commercial breaks
- Fine-tuning on NBA crops planned for [[Build Phases|Phase 7]]

## Files

- `src/tracking/osnet_reid.py`
- `data/models/osnet_x0_25_imagenet.pth`

→ Part of [[CV Pipeline]]
→ Paired with [[Team Classification]]
→ Improves [[Kalman-Hungarian Tracker]] identity persistence
""")

note("CV Pipeline/Ball Tracking", ["cv", "ball"], """
# Ball Tracking

Dedicated ball tracking pipeline with Kalman smoothing for the small, fast-moving basketball.

## Challenges

- Ball is ~15-20 pixels in broadcast view
- Frequent occlusion by players' hands/bodies
- Fast motion blur during passes and shots
- `ball_valid_pct` = 0% on some games (known issue)

## Method

1. [[YOLOv8n Detection]] at confidence 0.15
2. Kalman filter with higher process noise (ball is less predictable than players)
3. `ball_track_suspended` flag when no detection for N frames
4. Possession assignment based on proximity to nearest player

## Metrics

- `ball_valid_pct`: percentage of frames with valid ball position
- Target: >60% for A-grade games
- Current: 40-80% depending on broadcast angle

## Open Issues

- `ball_track_suspended` stays True entire video on some games
- Investigate after 80-game [[RunPod Operations|RunPod run]]

→ Part of [[CV Pipeline]]
→ Feeds [[Event Detection]] (shot detection, possession changes)
→ Affects [[Possession Simulator]] accuracy
""")

note("CV Pipeline/Event Detection", ["cv", "events"], """
# Event Detection

Detects basketball events from tracking data: possessions, shots, turnovers, rebounds.

## Events Detected

| Event | Signal | Confidence |
|-------|--------|------------|
| Shot attempt | [[Ball Tracking]] trajectory + rim proximity | Medium |
| Possession change | Ball carrier switch + court side | High |
| Fast break | Ball speed + player positions | Medium |
| Timeout/dead ball | [[EasyOCR Scoreboard]] clock stop | High |

## Method

- `EventDetector` class in `unified_pipeline.py`
- Combines [[Ball Tracking]] position, player positions from [[Court Mapping]], and [[EasyOCR Scoreboard]] state
- Rule-based with learned thresholds

## Output

- Per-possession records with timestamps
- Feeds [[Possession Simulator]] transition matrices
- Used by [[Feature Engineering]] for temporal features

→ Part of [[CV Pipeline]]
→ Dependent on [[Ball Tracking]], [[Court Mapping]]
→ Output used by [[Feature Engineering]], [[Possession Simulator]]
""")

note("CV Pipeline/Team Classification", ["cv", "color"], """
# Team Classification

HSV color-based team assignment for detected players.

## Method

- Extract jersey region from player bounding box (top 40%)
- Convert to HSV color space
- Dynamic clustering (K=2) per game to learn team colors
- Assignment based on cluster distance

## Integration

- Paired with [[OSNet Re-ID]] for joint player identity
- Team label used by [[Spatial Features]] (offensive vs defensive)
- [[Defender Distance]] requires knowing which team is on offense

## Performance Hotspot

- `color_reid.py::classify_dyn` is second-largest CPU hotspot
- HSV vectorization would improve throughput significantly

## Files

- `src/tracking/color_reid.py` — `TeamColorTracker`

→ Part of [[CV Pipeline]]
→ Paired with [[OSNet Re-ID]]
→ Required for [[Defender Distance]], [[Spacing Score]]
""")

note("CV Pipeline/Court Mapping", ["cv", "court"], """
# Court Mapping

Transforms pixel coordinates to real-world court coordinates (in feet).

## Pipeline

1. [[SIFT Homography]] computes perspective transform H
2. Player feet positions (bottom-center of bbox) are transformed
3. Output: (x, y) in feet on standard NBA court (94 × 50 ft)

## Court Template

- Standard NBA half-court template with key markings
- Three-point line, free throw line, paint used as anchor features
- [[Panorama Stitching]] builds game-specific reference

## Output Used By

- [[Defender Distance]] — nearest defender in feet
- [[Spacing Score]] — convex hull area of offensive players
- [[Fatigue Metrics]] — distance traveled per minute
- [[Possession Simulator]] — spatial context

→ Core component of [[CV Pipeline]]
→ Depends on [[SIFT Homography]]
→ Enables all [[Spatial Features]]
""")

note("CV Pipeline/EasyOCR Scoreboard", ["cv", "ocr"], """
# EasyOCR Scoreboard

Reads score, game clock, shot clock, and quarter from broadcast scoreboard overlay.

## Method

- EasyOCR with custom ROI for scoreboard region
- Validated against [[NBA Stats API]] game data
- Temporal smoothing to handle OCR flicker

## Output

- Score differential (used by [[Win Probability]])
- Game clock (used by [[Event Detection]], [[Clutch Models]])
- Quarter (used by [[Feature Engineering]])

## Reliability

- Works well on ESPN/TNT standard overlays
- Struggles with custom regional broadcast graphics
- Fallback: NBA API play-by-play timestamps

→ Part of [[CV Pipeline]]
→ Feeds [[Win Probability]], [[Event Detection]]
""")

note("CV Pipeline/Panorama Stitching", ["cv", "panorama"], """
# Panorama Stitching

Builds a full-court panorama from broadcast camera pans for [[SIFT Homography]] matching.

## Method

- Accumulate frames as camera pans across court
- SIFT feature matching + blending
- Stored as `pano_enhanced.png` per game

## Known Fix

- Broadcast panoramas break standard SIFT parameters
- Fix: ratio 3-10, 5-second temporal window
- Fallback to pre-built `pano_enhanced.png` when live stitching fails

→ Supports [[SIFT Homography]] → [[Court Mapping]]
→ Part of [[CV Pipeline]]
""")


# ═══════════════════════════════════════════════════════════════════
# CLUSTER 2: FEATURES & SIGNALS
# ═══════════════════════════════════════════════════════════════════

note("Features/Feature Engineering", ["features", "ml"], """
# Feature Engineering

60+ features across 7 classes power all [[Model Registry|prediction models]].

## Feature Classes

| Class | Count | Source | Key Features |
|-------|-------|--------|-------------|
| API Box-Score | ~20 | [[NBA Stats API]] | pts, reb, ast, fg_pct, usage_rate |
| API Derived | ~12 | [[NBA Stats API]] | rolling averages, matchup history |
| CV Spatial | ~8 | [[CV Pipeline]] | [[Defender Distance]], [[Spacing Score]] |
| CV Temporal | ~12 | [[CV Pipeline]] | speed, acceleration, court coverage |
| CV Biomechanical | ~6 | [[CV Pipeline]] | [[Fatigue Metrics]], gait patterns |
| Market | ~6 | [[Market Microstructure]] | line velocity, steam, public% |
| Sentiment | ~5 | External | injury reports, lineup news |

## The Moat

Three CV spatial features contribute **31% of SHAP mass** on the pts model:
- [[Defender Distance]] — nearest defender in feet
- [[Spacing Score]] — offensive spacing area
- [[Fatigue Metrics]] — legs fatigue from distance traveled

These add **ΔR² = +0.08** over API-only baseline. No public dataset has them.

## Files

- `src/features/feature_engineering.py` — 60+ feature transforms

→ Feeds [[Player Props]], [[Win Probability]], [[xFG Model]]
→ Sources: [[CV Pipeline]], [[NBA Stats API]], [[Market Microstructure]]
→ Catalog: [[Signal Inventory]]
""")

note("Features/Spatial Features", ["features", "cv"], """
# Spatial Features

Court-position-derived features extracted from [[Court Mapping]] output.

## Features

| Feature | Description | SHAP Rank |
|---------|-------------|-----------|
| [[Defender Distance]] | Nearest defender distance (ft) | #1 CV feature |
| [[Spacing Score]] | Offensive convex hull area | #2 CV feature |
| paint_density | Players in paint count | Medium |
| three_pt_spacing | Players beyond arc | Medium |
| ball_handler_pressure | Defender angle + distance to ball | High |

## Source

All derived from [[Court Mapping]] real-world coordinates via [[SIFT Homography]].

→ Part of [[Feature Engineering]]
→ Key input to [[Player Props]], [[xFG Model]]
→ The [[Edge Taxonomy|competitive moat]] — not in any public dataset
""")

note("Features/Defender Distance", ["features", "cv", "spatial"], """
# Defender Distance

Nearest defender distance in feet — the single most impactful CV feature.

## Computation

1. [[Court Mapping]] gives (x, y) for all players
2. [[Team Classification]] identifies offensive vs defensive
3. For each offensive player: min Euclidean distance to any defender
4. Smoothed over 3-frame window

## Impact

- **#1 CV feature** by SHAP importance across [[Player Props]] models
- Directly predicts shot quality for [[xFG Model]]
- Used by [[Possession Simulator]] for transition probability adjustment

## Validation

- Correlates with NBA.com tracking "closest defender" at r=0.82 on matched possessions
- Higher distance → higher eFG% (expected)

→ Part of [[Spatial Features]] → [[Feature Engineering]]
→ Key input to [[Player Props]], [[xFG Model]], [[Possession Simulator]]
→ Requires [[Court Mapping]] + [[Team Classification]]
""")

note("Features/Spacing Score", ["features", "cv", "spatial"], """
# Spacing Score

Convex hull area of the five offensive players — measures floor spacing.

## Computation

1. [[Court Mapping]] gives (x, y) for all 10 players
2. [[Team Classification]] identifies offense
3. Convex hull of 5 offensive players → area in sq ft
4. Normalized to [0, 1] scale

## Impact

- Higher spacing → better shot quality, more driving lanes
- Used by [[Possession Simulator]] for play type prediction
- Strong predictor in [[Player Props]] assists model

→ Part of [[Spatial Features]] → [[Feature Engineering]]
→ Linked to [[Defender Distance]], [[Fatigue Metrics]]
""")

note("Features/Fatigue Metrics", ["features", "cv", "biomechanical"], """
# Fatigue Metrics

Distance traveled and acceleration patterns indicating player fatigue.

## Features

| Feature | Method |
|---------|--------|
| legs_fatigue | Cumulative distance / minutes played |
| sprint_count | Acceleration spikes > threshold |
| distance_last_5min | Recent movement intensity |
| deceleration_rate | Change in avg speed over quarter |

## Source

- Player trajectories from [[Kalman-Hungarian Tracker]] via [[Court Mapping]]
- Minutes context from [[EasyOCR Scoreboard]] + [[NBA Stats API]]

## Impact

- 3rd most important CV feature cluster
- Predicts 4th quarter performance dropoff in [[Player Props]]
- Not yet wired into [[Possession Simulator]] (uses defaults — known gap)

→ Part of [[Feature Engineering]]
→ Derived from [[CV Pipeline]] tracking data
→ Feeds [[Player Props]], planned for [[Possession Simulator]]
""")

note("Features/Signal Inventory", ["features", "catalog"], """
# Signal Inventory

Master catalog of all ~69 features with wiring status.

## Status Summary

| Class | Wired | Unwired | Gap |
|-------|-------|---------|-----|
| API box-score | 20/20 | 0 | — |
| API derived | 12/12 | 0 | — |
| CV spatial | 6/8 | 2 | ball_handler_pressure, help_side_distance |
| CV temporal | 10/12 | 2 | transition_speed, halfcourt_set_time |
| CV biomechanical | 4/6 | 2 | gait_asymmetry, vertical_load |
| Market | 0/6 | 6 | All collected but not in model feature set |
| Sentiment | 0/5 | 5 | Planned for Phase 9 |

## Key Gaps

- [[Market Microstructure]] features (line velocity, steam flag, public%) — collected but not wired
- CV biomechanical features — wired but not in [[Portfolio Manager|betting stack]]

## Reference

- Full catalog: `docs/signal-inventory.md`

→ Tracks all [[Feature Engineering]] inputs
→ Links to [[Edge Taxonomy]] for competitive analysis
""")


# ═══════════════════════════════════════════════════════════════════
# CLUSTER 3: ML MODELS
# ═══════════════════════════════════════════════════════════════════

note("Models/Model Registry", ["models", "overview"], """
# Model Registry

75 trained artifacts in `data/models/`. Central manifest: `model_registry.json`.

## Model Categories

| Category | Count | Notes |
|----------|-------|-------|
| [[Win Probability]] | 2 | XGBoost + calibration layer |
| [[Player Props]] | 14 | 7 stats × v1/v2 |
| [[xFG Model]] | 2 | Spatial + CV-augmented |
| [[DNP Predictor]] | 2 | Model + meta |
| [[Matchup Model]] | 2 | JSON + meta |
| [[Game Models]] | 6 | Total, spread, blowout, half, pace + meta |
| [[Injury Models]] | 5 | Risk, return, severity, breakout, age curve |
| [[Context Models]] | 6 | Altitude, B2B, home/away, rest, travel, referee |
| [[Tier 4-5 CV Models]] | 11 | Closeout, help def, screen, etc. |
| Support models | 25 | Clutch, foul trouble, garbage time, etc. |

## Governance

- v2 prop files are active; v1 retained as fallback
- Drift checks planned for [[Build Phases|Phase 8+]]
- [[OSNet Re-ID]] backbone is pre-trained, not NBA fine-tuned

→ All models consumed by [[Prediction Pipeline]]
→ Performance tracked in [[Model Performance]]
→ Features from [[Feature Engineering]]
""")

note("Models/Win Probability", ["models", "prediction"], """
# Win Probability

XGBoost classifier predicting game outcome probability.

## Performance

| Metric | Value |
|--------|-------|
| Accuracy | 69.1% |
| Brier Score | 0.203 |

## Features

- Score differential, time remaining from [[EasyOCR Scoreboard]]
- Team strength ratings from [[NBA Stats API]]
- Home/away, back-to-back from [[Context Models]]
- Lineup quality when available

## Calibration

- `CalibrationLayer.win_prob()` added
- [[Calibration]] via isotonic regression
- ECE target: < 0.05

## Files

- `src/prediction/win_probability.py`
- `data/models/win_probability.pkl`

→ Feeds [[Line Evaluator]] for moneyline edges
→ Uses features from [[Feature Engineering]]
→ Part of [[Model Registry]]
""")

note("Models/Player Props", ["models", "prediction", "props"], """
# Player Props

7 stat-specific regression models — the core betting product.

## Performance (v2, current)

| Stat | R² | Status |
|------|-----|--------|
| PTS | 0.47 | ✅ Solid |
| REB | 0.40 | ✅ Solid |
| AST | 0.46 | ✅ Solid |
| FG3M | 0.28 | 🟡 Adequate |
| BLK | 0.18 | 🟡 Weak |
| TOV | 0.25 | 🟡 Adequate |
| STL | 0.07 | 🔴 Needs work |

## Architecture

- LightGBM regressors with [[Walk-Forward Validation]]
- Stacked via `prop_model_stack.py` with [[Calibration|isotonic calibration]]
- Features: [[Feature Engineering]] (60+ features including CV spatial)

## Key Improvement Levers

- STL: add `opp_to_rate` + `opp_pace` features
- All: more [[CV Data Status|CV game data]] (17 → 80 games)
- All: [[Market Microstructure]] features (unwired)

## Files

- `src/prediction/player_props.py`
- `src/prediction/prop_model_stack.py`
- `data/models/props_*.json`

→ Output consumed by [[Line Evaluator]] → [[Portfolio Manager]]
→ [[Calibration]] layer in prop stack
→ Key product for [[Edge Taxonomy|+EV betting]]
""")

note("Models/xFG Model", ["models", "prediction", "spatial"], """
# xFG Model (Expected Field Goal)

Predicts shot make probability using spatial context from [[CV Pipeline]].

## Performance

| Metric | Value |
|--------|-------|
| Brier Score | 0.226 |

## Features

- [[Defender Distance]] — primary spatial feature
- Shot distance, angle (from [[Court Mapping]])
- Shot type (from [[NBA Stats API]])
- [[Spacing Score]] context

## Variants

| File | Description |
|------|-------------|
| `xfg_v1.pkl` | Spatial features only |
| `xfg_cv_stack.pkl` | CV-augmented (includes tracking data) |

→ Part of [[Model Registry]]
→ Unique to CourtVision — requires [[CV Pipeline]] data
→ Can feed [[Player Props]] as meta-feature
""")

note("Models/DNP Predictor", ["models", "availability"], """
# DNP Predictor

Predicts whether a player will be a Did Not Play.

## Performance

| Metric | Value |
|--------|-------|
| AUC | 0.979 |

## Purpose

- Filter out DNP players before [[Player Props]] prediction
- Avoid sizing bets on players who won't play
- Critical for [[Portfolio Manager]] reliability

## Features

- Injury report status, game-time decisions
- Back-to-back, travel from [[Context Models]]
- Historical DNP patterns from [[NBA Stats API]]

→ Part of [[Model Registry]]
→ Guards [[Player Props]] and [[Portfolio Manager]]
→ Paired with [[Injury Models]]
""")

note("Models/Matchup Model", ["models", "prediction"], """
# Matchup Model

Predicts player performance adjustments based on opponent matchup.

## Performance

| Metric | Value |
|--------|-------|
| R² | 0.796 |

## Purpose

- Adjusts [[Player Props]] predictions for defensive matchup quality
- Elite defender → suppress scoring projection
- Weak defender → boost projection

## Features

- Opponent defensive rating, position matchup
- Historical player-vs-team performance
- Defensive scheme indicators from [[NBA Stats API]]

→ Part of [[Model Registry]]
→ Adjusts [[Player Props]] predictions
→ Feeds [[Possession Simulator]] matchup context
""")

note("Models/Game Models", ["models", "prediction", "game"], """
# Game Models

Suite of game-level prediction models.

## Models

| Model | File | Purpose |
|-------|------|---------|
| Game Total | `game_game_total.json` | Over/under prediction |
| Spread | `game_spread.json` | Point spread |
| Blowout | `game_blowout.json` | P(margin > 20) |
| First Half | `game_first_half.json` | 1H total |
| Pace | `game_pace.json` | Possessions per 48 min |

## Integration

- All feed [[Line Evaluator]] for game-level markets
- Pace prediction used by [[Possession Simulator]]
- [[Win Probability]] is the primary game outcome model

→ Part of [[Model Registry]]
→ Complement [[Player Props]] for [[Portfolio Manager]] diversification
""")

note("Models/Injury Models", ["models", "lifecycle"], """
# Injury Models

Player health and availability prediction suite.

## Models

| Model | Purpose |
|-------|---------|
| `injury_risk.pkl` | Probability of injury occurrence |
| `injury_return.pkl` | Expected return timeline |
| `injury_severity_clf.pkl` | Severity classification |
| `breakout_predictor.pkl` | Young player breakout detection |
| `age_curve_model.pkl` | Age-related decline modeling |
| `load_management.pkl` | Rest day prediction |

## Integration

- Feeds [[DNP Predictor]] as input features
- Informs [[Portfolio Manager]] position sizing (higher injury risk → smaller positions)
- [[Context Models]] interact with fatigue and rest patterns

→ Part of [[Model Registry]]
→ Critical for [[Player Props]] availability filtering
""")

note("Models/Context Models", ["models", "context"], """
# Context Models

Situational adjustment models for game context.

## Models

| Model | Feature | Impact |
|-------|---------|--------|
| `altitude_model.pkl` | Denver/Utah elevation | Pace, fatigue |
| `back_to_back_model.pkl` | B2B schedule | Performance drop |
| `home_away_model.pkl` | Home court advantage | ~3 pts |
| `rest_day_model.pkl` | Days since last game | Recovery |
| `travel_impact_model.pkl` | Travel distance/timezone | Fatigue |
| `referee_model.pkl` | Referee tendencies | Pace, FTA |

## Integration

- Adjust [[Player Props]] and [[Win Probability]] predictions
- Feed into [[Possession Simulator]] as context parameters
- Referee model is unique — most systems ignore ref effects

→ Part of [[Model Registry]]
→ Adjustments applied in [[Prediction Pipeline]]
""")

note("Models/Tier 4-5 CV Models", ["models", "cv", "advanced"], """
# Tier 4-5 CV Models

Advanced models that require [[CV Pipeline]] spatial data — the unique edge.

## Tier 4 (Tactical)

| Model | Purpose |
|-------|---------|
| `tier4_closeout.pkl` | Closeout speed → three-point defense |
| `tier4_help_def.pkl` | Help defense rotation patterns |
| `tier4_late_game.pkl` | Clutch spatial behavior |
| `tier4_rebound.pkl` | Rebound positioning |
| `tier4_screen.pkl` | Screen effectiveness |
| `tier4_stagnation.pkl` | Offensive stall detection |
| `tier4_tov.pkl` | Turnover-prone formations |

## Tier 5 (Behavioral)

| Model | Purpose |
|-------|---------|
| `tier5_foul_drawing.pkl` | Foul-drawing play patterns |
| `tier5_momentum.pkl` | Run/momentum spatial signatures |
| `tier5_second_chance.pkl` | Offensive rebound probability |
| `tier5_sub_timing.pkl` | Substitution pattern prediction |

## Status

- Trained on limited [[CV Data Status|CV game data]] (29 usable: 9 CLEAN + 20 PARTIAL of 75 attempted)
- Need 80+ CLEAN games to be reliable ([[Build Phases|Phase 7]])
- Currently informational, not in [[Portfolio Manager|betting stack]]

→ Part of [[Model Registry]]
→ Depend on [[CV Pipeline]] → [[Spatial Features]]
→ Future integration into [[Player Props]] as meta-features
""")

note("Models/Model Performance", ["models", "metrics"], """
# Model Performance

Tracking dashboard for all model metrics.

## Primary Models

| Model | Metric | Value | Target |
|-------|--------|-------|--------|
| [[Win Probability]] | Accuracy | 69.1% | 72% |
| [[Win Probability]] | Brier | 0.203 | <0.19 |
| [[Player Props]] PTS | R² | 0.47 | 0.55 |
| [[Player Props]] REB | R² | 0.40 | 0.50 |
| [[Player Props]] AST | R² | 0.46 | 0.55 |
| [[Player Props]] FG3M | R² | 0.28 | 0.35 |
| [[Player Props]] BLK | R² | 0.18 | 0.25 |
| [[Player Props]] TOV | R² | 0.25 | 0.30 |
| [[Player Props]] STL | R² | 0.07 | 0.20 |
| [[xFG Model]] | Brier | 0.226 | <0.20 |
| [[DNP Predictor]] | AUC | 0.979 | >0.97 |
| [[Matchup Model]] | R² | 0.796 | >0.80 |

## Improvement Path

1. More [[CV Data Status|CV games]] (17 → 80) — biggest single lever
2. Wire [[Market Microstructure]] features
3. [[Calibration]] tuning across all models
4. [[Tier 4-5 CV Models]] as meta-features

→ All models in [[Model Registry]]
→ Tracked per session in [[Tracker Improvements]]
""")


# ═══════════════════════════════════════════════════════════════════
# CLUSTER 4: BETTING & QUANT
# ═══════════════════════════════════════════════════════════════════

note("Quant/Kelly Criterion", ["quant", "sizing"], """
# Kelly Criterion

Optimal bet sizing: f* = k(bp − q) / b

## Implementation

- Fractional Kelly (k = 0.25) to reduce variance
- [[Correlation Engine|Ledoit-Wolf shrinkage]] on correlated legs
- Position limits from [[Risk Framework]]
- [[Circuit Breakers]] override Kelly when triggered

## Integration

- Receives edge estimates from [[Line Evaluator]]
- Correlation matrix from [[Correlation Engine]]
- Output: bet size as fraction of bankroll

## Files

- `src/prediction/betting_portfolio.py` — `kelly_corr`

## Known Issue

- Correlation matrix assumes zero correlation (not populated)
- Need `--build-residuals` then `--compute-corr`

→ Core of [[Portfolio Manager]]
→ Depends on [[Line Evaluator]], [[Correlation Engine]]
→ Constrained by [[Risk Framework]], [[Circuit Breakers]]
""")

note("Quant/Shin Devig", ["quant", "probability"], """
# Shin Devig

Removes bookmaker vig to extract true implied probabilities.

## Method

Shin's model accounts for the favorite-longshot bias that simple multiplicative devig misses. Uses Pinnacle closing lines as the "truth" benchmark.

## Formula

Iteratively solves for the overround parameter z, then extracts fair probabilities.

## Why It Matters

- Raw bookmaker odds include 4-8% vig
- Naive devig (divide by sum) systematically overestimates longshot probability
- Shin handles the bias correctly → more accurate [[CLV Validation|CLV]] measurement

## Integration

- Applied in [[Line Evaluator]] before edge computation
- Used in [[CLV Validation]] — Pinnacle closing (Shin-devigged) vs placement price
- Part of [[Walk-Forward Validation]] pipeline

→ Core methodology for [[Line Evaluator]]
→ Essential for accurate [[CLV Validation]]
→ Part of [[Quant Framework]]
""")

note("Quant/CLV Validation", ["quant", "validation"], """
# CLV Validation (Closing Line Value)

The primary metric for evaluating prediction quality — did our line beat the closing line?

## Definition

CLV = (our implied probability) − (Pinnacle closing implied probability, [[Shin Devig|Shin-devigged]])

## Why CLV > ROI

- ROI has high variance (need 1000+ bets to converge)
- CLV converges in ~100 bets
- Positive CLV is necessary and sufficient for long-term profitability

## Gate Criteria

- CLV beat rate ≥ 55% required for [[Paper Trading Gate]]
- This is the **#1 open validation question** for the project

## Integration

- Computed in [[Walk-Forward Validation]] pipeline
- Uses [[Shin Devig]] for fair probability extraction
- Feeds [[Learning Loop]] for model improvement signal

## Files

- `src/prediction/prop_backtester.py`

→ Primary quality metric
→ Gate for [[Paper Trading Gate]] → live trading
→ Part of [[Quant Framework]]
""")

note("Quant/Correlation Engine", ["quant", "portfolio"], """
# Correlation Engine

Joint probability distributions for SGP (Same Game Parlay) pricing and portfolio correlation.

## Components

1. **SGP Joint Distributions**: Correlated player outcomes within same game
2. **Portfolio Correlation**: Cross-bet correlation for [[Kelly Criterion]] sizing
3. **Ledoit-Wolf Shrinkage**: Σ̂ = (1−α)Σ_sample + α·(tr(Σ)/n)·I

## Why Ledoit-Wolf

- Small sample → noisy sample covariance matrix
- Shrinkage toward identity stabilizes eigenvalues
- Prevents Kelly from over-concentrating on spuriously uncorrelated positions

## Status

- Correlation matrix in `betting_portfolio.kelly_corr` **not yet populated**
- Need to run `--build-residuals` then `--compute-corr`

→ Feeds [[Kelly Criterion]] for position sizing
→ Critical for [[Portfolio Manager]] risk management
→ Part of [[Quant Framework]]
""")

note("Quant/Circuit Breakers", ["quant", "risk"], """
# Circuit Breakers

Automated risk controls that override [[Kelly Criterion]] sizing.

## Triggers (Phase 16)

| Trigger | Action |
|---------|--------|
| Daily loss > 5% bankroll | Halt all new bets |
| Drawdown > 10% from HWM | Kill switch — paper only |
| 3 consecutive losses | Reduce to 50% stakes |
| 5 consecutive losses | Paper only mode |
| Model disagreement | Halt affected market |

## Integration

- Override [[Kelly Criterion]] output in [[Portfolio Manager]]
- Must be clear for [[Paper Trading Gate]] activation
- Part of [[Risk Framework]]

→ Safety layer for [[Portfolio Manager]]
→ Gate condition for [[Paper Trading Gate]]
→ Part of [[Risk Framework]]
""")

note("Quant/Calibration", ["quant", "ml"], """
# Calibration

Ensuring predicted probabilities match actual frequencies.

## Method

- Isotonic regression calibration layer
- Added in `prop_model_stack.py`
- Needs `prop_residuals.json` to train

## Metrics

- ECE (Expected Calibration Error) target: < 0.05
- Reliability diagram: should follow diagonal
- Cohort-segmented: checked per market type

## Status

- `CalibrationLayer.win_prob()` added for [[Win Probability]]
- Isotonic layer added in `prop_model_stack.py` for [[Player Props]]
- Needs end-to-end verification before sizing bets

→ Applied to [[Win Probability]], [[Player Props]]
→ Critical for [[Kelly Criterion]] accuracy
→ Part of [[Quant Framework]]
""")

note("Quant/Walk-Forward Validation", ["quant", "methodology"], """
# Walk-Forward Validation

Temporal train/test split that prevents data leakage.

## Method

1. Train on games 1..N
2. Predict game N+1
3. Slide window forward
4. Never use future data in features or labels

## Why Not K-Fold

- Basketball has strong temporal patterns (injuries, trades, hot streaks)
- K-fold would leak future information into training
- Walk-forward respects the temporal structure

## Integration

- All [[Model Registry|models]] trained with walk-forward
- [[Player Props]] backtester uses this methodology
- [[CLV Validation]] computed on walk-forward test sets

## Files

- `src/prediction/prop_backtester.py`

→ Methodology for [[Model Registry]] training
→ Prevents leakage in [[Player Props]], [[Win Probability]]
→ Part of [[Quant Framework]]
""")

note("Quant/Paper Trading Gate", ["quant", "operations"], """
# Paper Trading Gate

Six conditions that must pass simultaneously before LIVE_BETTING=1.

## Conditions

1. ≥ 50 paper bets placed
2. [[CLV Validation]] beat rate ≥ 55%
3. Paper ROI ≥ 3%
4. Zero [[Circuit Breakers]] events in last 7 days
5. [[Calibration]] ECE < 0.05
6. All models passing drift checks

## Status

- Not yet activated — blocked on [[CV Data Status|CV data volume]] and [[CLV Validation]]
- This is the final gate before real money

→ Gate for live trading
→ Depends on [[CLV Validation]], [[Circuit Breakers]], [[Calibration]]
→ Part of [[Risk Framework]]
""")

note("Quant/Risk Framework", ["quant", "risk"], """
# Risk Framework

Position limits, tail risk, and factor hedging.

## Position Limits

| Limit | Value |
|-------|-------|
| Total per slate | ≤ 20% bankroll |
| Per game | ≤ 5% |
| Per player | ≤ 8% |
| Correlated cluster | ≤ 15% |

## Tail Risk

- Daily VaR / CVaR / ES monitoring
- Monthly risk packet generation
- Three stress scenarios tested

## Future (Phase 30)

- PCA on prop residuals → latent factor identification
- Risk parity reweighting targeting 25% variance reduction

→ Constrains [[Kelly Criterion]] and [[Portfolio Manager]]
→ [[Circuit Breakers]] are the automated enforcement layer
→ Full doc: `docs/risk-framework.md`
""")

note("Quant/Quant Framework", ["quant", "overview"], """
# Quant Framework

The four methodology documents that describe how CourtVision prices, sizes, and validates.

## Components

1. **[[Walk-Forward Validation]]** — temporal integrity
2. **[[Shin Devig]]** — true probability extraction
3. **[[Kelly Criterion]]** — optimal sizing with [[Correlation Engine|Ledoit-Wolf]]
4. **[[Calibration]]** — probability accuracy (ECE < 0.05)

## Key Equations

- Shin devig: iterative overround parameter z
- Fractional Kelly: f* = k(bp − q) / b
- Ledoit-Wolf: Σ̂ = (1−α)Σ_sample + α·(tr(Σ)/n)·I
- Conformal prediction intervals for uncertainty bands

## Validation Chain

[[Walk-Forward Validation]] → [[Calibration]] → [[CLV Validation]] → [[Paper Trading Gate]] → Live

→ Foundation for all [[Five Systems]]
→ Reference docs: `docs/quant-methodology.md`, `docs/risk-framework.md`, `docs/backtest-methodology.md`
""")


# ═══════════════════════════════════════════════════════════════════
# CLUSTER 5: FIVE SYSTEMS
# ═══════════════════════════════════════════════════════════════════

note("Systems/Five Systems", ["systems", "overview"], """
# The Five Systems

Everything flows through five systems. The 75 models are components — these systems are the architecture.

## Flow

```
[[CV Pipeline]] + [[NBA Stats API]]
        ↓
[[Possession Simulator]] — 10K Monte Carlo → full distributions
        ↓
[[Line Evaluator]] — model prob vs book implied → edge
        ↓
[[Correlation Engine]] — joint distributions for SGP + portfolio
        ↓
[[Portfolio Manager]] — [[Kelly Criterion]] sizing → bet slip
        ↓
[[Execution Engine]] — timing, routing, stealth
        ↓
[[Learning Loop]] — [[CLV Validation]] → retrain signal
```

→ Architecture described in `docs/architecture/system-overview.md`
→ All systems depend on [[Feature Engineering]] and [[Model Registry]]
""")

note("Systems/Possession Simulator", ["systems", "simulation"], """
# Possession Simulator

Lineup-dependent transition matrices + 10K Monte Carlo paths.

## Output

P(stat > X) for every player, every stat, any threshold X.
Full probability distributions, not just point estimates.

## Method

1. Build lineup-specific transition matrices from [[NBA Stats API]] + [[CV Pipeline]] spatial data
2. Run 10,000 Monte Carlo game simulations
3. Track per-player stat accumulation across all paths
4. Output: empirical CDFs for each player-stat combination

## Integration

- Receives: lineup data, pace from [[Game Models]], spatial context from [[CV Pipeline]]
- Produces: full distributions consumed by [[Line Evaluator]]
- [[Fatigue Metrics]] planned but not yet wired (uses defaults)

## Status

- Core framework built
- Blocked on [[CV Data Status|CV data volume]] for spatial calibration
- Planned activation: [[Build Phases|Phase 8]]

→ One of [[Five Systems]]
→ Feeds [[Line Evaluator]]
→ Uses [[Feature Engineering]], [[Context Models]], [[Matchup Model]]
""")

note("Systems/Line Evaluator", ["systems", "betting"], """
# Line Evaluator

Compares model probability vs bookmaker implied probability to find edges.

## Method

1. Get model P(over) from [[Possession Simulator]] or [[Player Props]]
2. Get book implied P from sportsbook odds via [[Shin Devig]]
3. Edge = model_prob − implied_prob
4. Filter: only edges > minimum threshold (typically 3%)

## Integration

- Input: [[Possession Simulator]] distributions or [[Player Props]] point estimates
- Output: edge opportunities sent to [[Portfolio Manager]]
- Uses [[Calibration]] to ensure probability accuracy

→ One of [[Five Systems]]
→ Receives from [[Possession Simulator]], [[Player Props]]
→ Feeds [[Portfolio Manager]] via [[Kelly Criterion]]
""")

note("Systems/Portfolio Manager", ["systems", "portfolio"], """
# Portfolio Manager

Aggregates edges, sizes positions, enforces risk limits.

## Components

1. [[Kelly Criterion]] — optimal sizing per bet
2. [[Correlation Engine]] — adjust for correlated positions
3. [[Risk Framework]] — position limits and concentration caps
4. [[Circuit Breakers]] — automated halts

## Flow

```
[[Line Evaluator]] → edges
    ↓
[[Kelly Criterion]] → raw sizes
    ↓
[[Correlation Engine]] → correlation adjustment
    ↓
[[Risk Framework]] → cap enforcement
    ↓
[[Circuit Breakers]] → safety check
    ↓
Final bet slip → [[Execution Engine]]
```

## Files

- `src/prediction/betting_portfolio.py`

→ One of [[Five Systems]]
→ Outputs to [[Execution Engine]]
→ Constrained by [[Risk Framework]]
""")

note("Systems/Execution Engine", ["systems", "execution"], """
# Execution Engine

Routes bets to sportsbooks with timing and stealth considerations.

## Components

1. **Timing Layer** — when to place (pre-game vs live, early vs late)
2. **Book Routing** — which sportsbook has best price
3. **[[Account Longevity]]** — stealth patterns to avoid limiting

## Status

- Architecture designed
- Not yet implemented — requires [[Paper Trading Gate]] clearance first
- Planned for [[Build Phases|Phase 15+]]

→ One of [[Five Systems]]
→ Receives from [[Portfolio Manager]]
→ Governed by [[Account Longevity]] strategy
""")

note("Systems/Learning Loop", ["systems", "feedback"], """
# Learning Loop

CLV-driven feedback cycle for continuous model improvement.

## Cycle

1. Place bet (paper or live)
2. Record placement price + [[Shin Devig|Shin-devigged]] closing price
3. Compute [[CLV Validation|CLV]]
4. Segment CLV by: market, sport, time-of-day, model version
5. Identify systematic under/over-performance
6. Retrain models with new data + insight
7. Repeat

## Integration

- [[CLV Validation]] is the primary signal
- [[Walk-Forward Validation]] ensures retraining doesn't leak
- Model versioning in [[Model Registry]]

→ One of [[Five Systems]]
→ Closes the feedback loop
→ Drives [[Model Performance]] improvement
""")


# ═══════════════════════════════════════════════════════════════════
# CLUSTER 6: DATA SOURCES
# ═══════════════════════════════════════════════════════════════════

note("Data/NBA Stats API", ["data", "api"], """
# NBA Stats API

Primary structured data source — box scores, play-by-play, lineups, shooting.

## Endpoints Used

| Endpoint | Data | TTL |
|----------|------|-----|
| leaguegamefinder | Schedule, scores | Daily |
| boxscoretraditionalv2 | Box score stats | Per game |
| playbyplayv2 | Play-by-play | Per game |
| commonplayerinfo | Player metadata | Weekly |
| leaguedashlineups | Lineup stats | Daily |

## Coverage

- 20+ features from raw box score
- 12+ derived features (rolling averages, matchup history)
- Full season coverage, real-time during games

## Integration

- Enrichment in `src/data/enrichment/`
- Feeds [[Feature Engineering]] alongside [[CV Pipeline]]
- Ground truth for [[Event Detection]] validation

→ Primary data source for all [[Model Registry|models]]
→ Combined with [[CV Pipeline]] for [[Feature Engineering]]
→ Reference: `docs/research/data-sources.md`
""")

note("Data/CV Data Status", ["data", "tracking"], """
# CV Data Status

Tracking the volume and quality of computer vision processed games.

## Current State

| Metric | Value | Target |
|--------|-------|--------|
| Games processed | 17 | 80 |
| High quality (A/B) | ~10 | 60 |
| Season 2025-26 | 0 | 50 |

## Why Volume Matters

- [[Tier 4-5 CV Models]] need 80+ games to be reliable
- [[Spatial Features]] SHAP importance validated on small sample
- [[Player Props]] R² expected to improve +0.05-0.10 with more spatial data

## Pipeline

`Download` → [[Ingest System]] → [[CV Pipeline]] → Quality score → `data/tracking/`

## Next Step

80-game batch on [[RunPod Operations]] (RTX 3090, ~$3-5)

→ Bottleneck for [[Model Performance]] improvement
→ [[Build Phases|Phase G]] target
→ Quality logged in [[Tracker Improvements]]
""")

note("Data/Market Microstructure", ["data", "market"], """
# Market Microstructure

Sportsbook odds data — line movements, steam moves, public betting percentages.

## Features (Collected but Unwired)

| Feature | Description | Status |
|---------|-------------|--------|
| line_velocity | Speed of line movement | Collected |
| steam_flag | Sharp money indicator | Collected |
| public_pct | Public betting percentage | Collected |
| opening_line | Opening line value | Collected |
| reverse_line_movement | Line moves against public | Collected |
| book_hold_pct | Implied vig percentage | Collected |

## Gap

All 6 features collected but **not in the model feature set**. Wiring them is a known improvement lever.

## Related Models

- `line_movement_predictor.pkl` — predicts line movement direction
- `soft_book_lag.pkl` — identifies slow-to-move books
- `public_fade.pkl` — contrarian signal

→ Part of [[Signal Inventory]]
→ Feeds [[Line Evaluator]], [[Execution Engine]]
→ Wiring planned for [[Build Phases|Phase 9]]
""")


# ═══════════════════════════════════════════════════════════════════
# CLUSTER 7: OPERATIONS
# ═══════════════════════════════════════════════════════════════════

note("Operations/RunPod Operations", ["ops", "gpu"], """
# RunPod Operations

Cloud GPU processing for batch [[CV Pipeline]] execution.

## Current Setup

| Setting | Value |
|---------|-------|
| GPU | RTX 3090 |
| Parallel workers | 4 |
| OMP threads | 4 |
| Batch size | 12 |
| Est. cost | $0.35-0.50/hr |
| Est. total | $2.50-4.50 for 80 games |

## Commands

```bash
bash scripts/ingest_preflight.sh
bash scripts/launch_single_3090_pod.sh
bash scripts/watch_and_sync.sh
```

## Key Files

- `scripts/run_phase_g.py` — batch runner with dedup-by-hash
- `scripts/launch_single_3090_pod.sh` — pod launcher

## Known Issues

- Dedup-by-hash + per-game crash isolation needed (fixed in d265ece)
- CPU quota throttling (nr_throttled < 30/60s target)

→ Executes [[CV Pipeline]] at scale
→ Produces data for [[CV Data Status]]
→ Runbook: `docs/operations/runpod-runbook.md`
""")

note("Operations/Ingest System", ["ops", "pipeline"], """
# Ingest System

SQLite-backed pipeline for downloading, processing, and quality-scoring NBA games.

## Commands

```bash
python -m src.ingest.manifest migrate          # import legacy
python scripts/ingest_fetch.py --count N       # download
python scripts/ingest_process.py --max-games N # process
python scripts/ingest_backfill_quality.py      # score
python scripts/ingest_status.py                # dashboard
python scripts/sync_remote.py --push           # push to B2
```

## Flow

1. Fetch game videos (YouTube, archive.org fallback)
2. Queue in SQLite manifest
3. Process through [[CV Pipeline]]
4. Quality score output
5. Sync to Backblaze B2

## Data

- `data/ingest/queue.db` — SQLite manifest
- `data/videos/full_games/` — raw video files
- `data/tracking/` — CV output

→ Feeds [[CV Pipeline]] → [[CV Data Status]]
→ Operated via [[RunPod Operations]]
""")

note("Operations/Batch Processing", ["ops", "pipeline"], """
# Batch Processing

Season-scale CV processing orchestration.

## Scripts

| Script | Purpose |
|--------|---------|
| `scripts/batch_season.py` | Full season batch runner |
| `scripts/run_phase_g.py` | Phase G batch (80-game target) |
| `scripts/ingest_process.py` | Ingest-based processing |

## Configuration

- `_VRAM_FLUSH_INTERVAL` = 3000 (MUST be 3000, not 100)
- Max frames per game: stride-adjusted
- Per-game crash isolation

## Integration

- Uses [[Ingest System]] for job management
- Runs [[CV Pipeline]] per game
- Output feeds [[CV Data Status]]
- Executed on [[RunPod Operations]]

→ Orchestrates [[CV Pipeline]] at scale
→ Part of [[Build Phases|Phase F/G]]
""")

note("Operations/GPU Optimization", ["ops", "performance"], """
# GPU Optimization

VRAM management and throughput optimization for [[CV Pipeline]].

## Local (RTX 4060, 8GB)

- VRAM flush interval: 3000 frames
- FPS: ~12-15
- Single game at a time

## Cloud (RTX 3090, 24GB, [[RunPod Operations]])

- VRAM flush interval: 3000 frames
- FPS: ~18-22
- 4 parallel workers

## Performance Wins on Table

1. **YOLO prefetch batching** — `_yolo_frame_buf` wired but inactive. +50% FPS expected. ~30 LOC.
2. **HSV vectorization** — `color_reid.py::classify_dyn` is CPU hotspot
3. **Mixed precision** — FP16 inference for YOLO

→ Affects [[RunPod Operations]] cost and [[Batch Processing]] throughput
→ [[CV Pipeline]] FPS directly impacts data volume timeline
""")


# ═══════════════════════════════════════════════════════════════════
# CLUSTER 8: ARCHITECTURE
# ═══════════════════════════════════════════════════════════════════

note("Architecture/Tech Stack", ["architecture", "overview"], """
# Tech Stack

## Core

| Layer | Technology |
|-------|------------|
| Detection | [[YOLOv8n Detection]] (Ultralytics) |
| Tracking | [[Kalman-Hungarian Tracker]] + [[OSNet Re-ID]] |
| Homography | [[SIFT Homography]] (OpenCV) |
| OCR | [[EasyOCR Scoreboard]] |
| ML | XGBoost, LightGBM, PyTorch |
| API | FastAPI (9 endpoints, 5 routers) |
| Frontend | Next.js + React ([[Dashboard]]) |
| Database | PostgreSQL |
| Storage | Backblaze B2 |
| GPU Cloud | [[RunPod Operations]] |

## Environment

- Python 3.9 | conda: `basketball_ai` | CUDA 11.8
- Local: RTX 4060 8GB | Cloud: RTX 3090 24GB
- Tests: pytest (960+ pass, 93 skip)

→ Foundation for [[CV Pipeline]], [[Model Registry]], [[API Server]]
""")

note("Architecture/API Server", ["architecture", "api"], """
# API Server

FastAPI serving predictions and analytics.

## Endpoints

9 endpoints across 5 routers:

| Router | Purpose |
|--------|---------|
| predictions | [[Win Probability]], [[Player Props]] |
| analytics | Historical analysis, trends |
| cv | [[CV Pipeline]] status and data |
| health | System health checks |
| models | [[Model Registry]] status |

## Files

- `api/main.py` — main app
- `api/execution_router.py` — execution routing

## Integration

- Serves [[Player Props]] and [[Win Probability]] predictions
- Connects to [[Dashboard]] frontend
- Reads from [[Model Registry]] for model serving

→ Part of [[Tech Stack]]
→ Serves [[Five Systems]] output
→ Frontend: [[Dashboard]]
""")

note("Architecture/Dashboard", ["architecture", "frontend"], """
# Dashboard

Next.js + React frontend for visualization and monitoring.

## Planned Views

1. **Prediction Dashboard** — live [[Player Props]] + [[Win Probability]]
2. **CV Monitor** — [[CV Pipeline]] processing status
3. **Model Performance** — [[Model Performance]] metrics over time
4. **Betting Tracker** — [[Portfolio Manager]] positions and P&L
5. **Pipeline Status** — [[Ingest System]] queue and progress

## Tech

- Next.js with TypeScript
- Consumes [[API Server]] endpoints
- Real-time updates via WebSocket (planned)

## Status

- Spec: `docs/architecture/dashboard-spec.md`
- Implementation: [[Build Phases|Phase 9+]]
- Directory: `apps/quant-dashboard/`

→ Visualizes [[Five Systems]] state
→ Consumes [[API Server]]
""")

note("Architecture/Prediction Pipeline", ["architecture", "orchestration"], """
# Prediction Pipeline

Orchestrates model inference from features to predictions.

## Flow

```
[[Feature Engineering]] → feature vectors
    ↓
[[DNP Predictor]] → filter unavailable players
    ↓
[[Context Models]] → situational adjustments
    ↓
[[Matchup Model]] → opponent adjustments
    ↓
[[Player Props]] / [[Win Probability]] / [[Game Models]] → predictions
    ↓
[[Calibration]] → calibrated probabilities
    ↓
[[Line Evaluator]] → edge identification
```

## Files

- `src/pipeline/prediction_orchestrator.py`

## Design

- 73 modules in `src/prediction/`
- Stack fully functional on [[NBA Stats API]] data
- [[CV Pipeline]] features optional (graceful degradation)

→ Orchestrates [[Model Registry]] inference
→ Output feeds [[Five Systems]]
""")


# ═══════════════════════════════════════════════════════════════════
# CLUSTER 9: STRATEGY & RESEARCH
# ═══════════════════════════════════════════════════════════════════

note("Strategy/Edge Taxonomy", ["strategy", "research"], """
# Edge Taxonomy

164 enumerated edges across 5 categories — the competitive analysis.

## Categories

| Category | Count | Example |
|----------|-------|---------|
| CV Spatial | 42 | [[Defender Distance]] impact on eFG% |
| Statistical | 38 | [[Walk-Forward Validation]] vs naive backtesting |
| Market | 31 | [[Shin Devig]] vs multiplicative devig |
| Behavioral | 28 | [[Fatigue Metrics]] late-game impact |
| Structural | 25 | [[Correlation Engine]] for SGP pricing |

## Moat Argument

No competitor has all three: broadcast CV spatial features + proper quant methodology + full pipeline automation. Each alone is table stakes; the combination at 164 edges is the moat.

## Reference

- Full taxonomy: `docs/research/edge-taxonomy.md`
- README thesis: "the gap is 164 edges wide"

→ Strategic foundation for [[Five Systems]]
→ CV edges require [[CV Pipeline]]
→ Quant edges from [[Quant Framework]]
""")

note("Strategy/Account Longevity", ["strategy", "stealth"], """
# Account Longevity

Strategy for avoiding sportsbook account limiting.

## Principles

1. **Size management** — never max-bet; fractional [[Kelly Criterion]]
2. **Timing variation** — don't always bet at the same time
3. **Market mixing** — bet some -EV markets to look recreational
4. **Book rotation** — spread action across multiple books
5. **Withdrawal pacing** — don't withdraw immediately after wins

## Integration

- Constrains [[Execution Engine]] behavior
- [[Risk Framework]] position limits serve dual purpose (risk + stealth)
- Timing layer in [[Execution Engine]] implements variation

→ Part of [[Execution Engine]] strategy
→ Detailed in `docs/strategy/account-longevity.md`
""")

note("Strategy/Build Phases", ["strategy", "roadmap"], """
# Build Phases

Phase-by-phase construction plan for CourtVision.

## Completed

| Phase | Description | Status |
|-------|-------------|--------|
| 1 | Data Infrastructure | ✅ |
| 2 | [[CV Pipeline|CV Tracker]] | ✅ |
| 2.5 | CV Tracker Upgrades | ✅ |
| 3 | [[NBA Stats API]] Data | ✅ |
| 4 | Tier 1 [[Model Registry|ML Models]] | ✅ |
| 5 | External Factors | ✅ |
| 4.6 | Pre-Phase Enrichment | ✅ |
| 13.5 | Full model training | ✅ |

## Active

| Phase | Description | Status |
|-------|-------------|--------|
| F | Full Game Processing | 🟡 5 clean / 20 target |
| G | Season Batch (80 games) | 🔲 Next up |

## Future

| Phase | Description |
|-------|-------------|
| 7 | [[Tier 4-5 CV Models]] (needs CV data) |
| 8 | [[Possession Simulator]] |
| 9-14 | [[Market Microstructure]], [[Dashboard]], feedback |
| 15-17 | [[Execution Engine]], [[Paper Trading Gate]], live |
| 18+ | [[Learning Loop]], optimization, expansion |

→ Full roadmap: `.planning/ROADMAP.md`
→ Current focus: [[CV Data Status]] expansion
""")

note("Strategy/Revenue Model", ["strategy", "business"], """
# Revenue Model

Multiple revenue streams beyond direct betting.

## Streams

1. **Direct Betting** — [[Portfolio Manager]] → [[Execution Engine]] → sportsbooks
2. **Data Products** — [[CV Pipeline]] spatial data licensing
3. **API Access** — [[API Server]] subscription for other bettors
4. **Consulting** — Methodology consulting for funds
5. **Multi-Sport** — Expand [[CV Pipeline]] to other sports

## Validation Path

[[Paper Trading Gate]] → Paper P&L → Live P&L → Scale

## Reference

- `docs/strategy/revenue-streams.md`
- `docs/strategy/multi-sport-expansion.md`

→ Business layer on top of [[Five Systems]]
→ Requires [[CLV Validation]] proof first
""")

note("Strategy/Project Vision", ["strategy", "overview"], """
# Project Vision

Possession-by-possession NBA simulator that finds +EV edges vs sportsbooks using spatial CV features no one else has.

## Thesis

The gap between what sportsbooks price and what's knowable is 164 edges wide ([[Edge Taxonomy]]). The technology cost to close that gap has collapsed. One person with the right stack can do what required a team of 20 five years ago.

## Architecture

[[Five Systems]] — Possession Simulator → Line Evaluator → Correlation Engine → Kelly Sizer → Execution Engine, all fed by [[CV Pipeline]] + [[NBA Stats API]] through [[Feature Engineering]].

## Current State

- 75 [[Model Registry|trained models]]
- [[CV Pipeline]] operational (29 usable: 9 CLEAN + 20 PARTIAL of 75, targeting 80 CLEAN)
- [[Player Props]] R² 0.16-0.41 holdout (walk-forward temporal CV)
- [[Paper Trading Gate]] not yet cleared
- [[CLV Validation]] is the #1 open question

## What's Left

More [[CV Data Status|CV data]] → better models → [[CLV Validation]] proof → [[Paper Trading Gate]] → live

→ The north star for everything in this vault
→ Technical depth: [[Quant Framework]]
→ Build sequence: [[Build Phases]]
""")


# ═══════════════════════════════════════════════════════════════════
# CLUSTER 10: IMPROVEMENT TRACKING
# ═══════════════════════════════════════════════════════════════════

note("Tracking/Tracker Improvements", ["tracking", "improvements"], """
# Tracker Improvements

Log of [[CV Pipeline]] fixes and improvements over time.

## Recent Fixes

- `unified_pipeline.py`: max_frames stride bug — gameplay vs source units mismatch at 60fps
- `fetch_games.py`: archive.org fallback, Android player client for YouTube bot bypass
- Highlights min_dur=1800s
- PREFLIGHT retry loop reads `phase_g_processed.txt` at startup
- Broadcast panorama SIFT fix: ratio 3-10, 5s window

## Performance Wins Still Available

1. YOLO prefetch batching (+50% FPS, ~30 LOC)
2. HSV vectorization in [[Team Classification]]
3. Mixed precision inference

→ History: `vault/Improvements/Tracker Improvements Log.md`
→ Improvements to [[CV Pipeline]]
→ Metrics tracked in [[Model Performance]]
""")

note("Tracking/Open Issues", ["tracking", "issues"], """
# Open Issues

## Critical

1. [[Correlation Engine]] — `kelly_corr` correlation matrix not populated
2. [[CV Data Status]] — 29 usable (9 CLEAN + 20 PARTIAL), need 80 CLEAN for reliable models

## High

3. [[Player Props]] STL R²=0.18 (weakest prop) — add `opp_to_rate` + `opp_pace`
4. [[Fatigue Metrics]] not wired into [[Possession Simulator]]

## Medium

5. `ball_valid_pct` = 0% on some games — [[Ball Tracking]] `ball_track_suspended` stays True
6. [[Calibration]] isotonic layer needs end-to-end verification

→ Tracked in `docs/CLAUDE-state.md`
→ Priority aligned with [[Build Phases]]
""")


# ═══════════════════════════════════════════════════════════════════
# MAP OF CONTENT (updated Home.md)
# ═══════════════════════════════════════════════════════════════════

note("Brain MOC", ["moc", "index"], """
# CourtVision — Brain Map

*The complete knowledge graph. Every node links to 5+ others. Open Graph View to explore.*

---

## Core Systems
→ [[Five Systems]] — the architecture
→ [[Possession Simulator]] · [[Line Evaluator]] · [[Correlation Engine]] · [[Portfolio Manager]] · [[Execution Engine]] · [[Learning Loop]]

## CV Pipeline
→ [[CV Pipeline]] — the moat
→ [[YOLOv8n Detection]] · [[SIFT Homography]] · [[Kalman-Hungarian Tracker]] · [[OSNet Re-ID]] · [[Ball Tracking]] · [[Event Detection]] · [[Team Classification]] · [[Court Mapping]] · [[EasyOCR Scoreboard]] · [[Panorama Stitching]]

## Features & Signals
→ [[Feature Engineering]] · [[Spatial Features]] · [[Defender Distance]] · [[Spacing Score]] · [[Fatigue Metrics]] · [[Signal Inventory]]

## Models
→ [[Model Registry]] · [[Model Performance]]
→ [[Win Probability]] · [[Player Props]] · [[xFG Model]] · [[DNP Predictor]] · [[Matchup Model]] · [[Game Models]] · [[Injury Models]] · [[Context Models]] · [[Tier 4-5 CV Models]]

## Quant Methodology
→ [[Quant Framework]]
→ [[Kelly Criterion]] · [[Shin Devig]] · [[CLV Validation]] · [[Correlation Engine]] · [[Circuit Breakers]] · [[Calibration]] · [[Walk-Forward Validation]] · [[Paper Trading Gate]] · [[Risk Framework]]

## Data
→ [[NBA Stats API]] · [[CV Data Status]] · [[Market Microstructure]]

## Operations
→ [[RunPod Operations]] · [[Ingest System]] · [[Batch Processing]] · [[GPU Optimization]]

## Architecture
→ [[Tech Stack]] · [[API Server]] · [[Dashboard]] · [[Prediction Pipeline]]

## Strategy
→ [[Project Vision]] · [[Edge Taxonomy]] · [[Build Phases]] · [[Account Longevity]] · [[Revenue Model]]

## Tracking
→ [[Tracker Improvements]] · [[Open Issues]]

---

*50+ notes · 300+ cross-links · Updated {today}*
""")


# ═══════════════════════════════════════════════════════════════════
# WRITE ALL NOTES
# ═══════════════════════════════════════════════════════════════════

def main():
    created = 0
    for path, (tags, content) in NOTES.items():
        full_path = VAULT / f"{path}.md"
        full_path.parent.mkdir(parents=True, exist_ok=True)

        name = path.split("/")[-1]
        frontmatter = f"""---
tags: [{tags}]
updated: {TODAY}
aliases: ["{name}"]
---
"""
        full_path.write_text(frontmatter + content.strip() + "\n", encoding="utf-8")
        created += 1
        print(f"  + {path}")

    print(f"\n{created} brain notes created in vault/")
    print(f"Cross-links: ~{created * 7} [[wikilinks]]")
    print("Open Obsidian -> Graph View to see your brain!")


if __name__ == "__main__":
    main()
