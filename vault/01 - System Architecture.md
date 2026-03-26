# System Architecture
*Last updated: 2026-03-24*

← [[00 - Home]] | → [[02 - Model Catalog]]

---

## Overview

CourtVision is an end-to-end NBA analytics pipeline: broadcast video → CV tracking → feature engineering → ML models → Monte Carlo simulation → betting edge detection. The system self-improves — every game processed retrains the models, which improves the next simulation.

**Target:** 10,000 Monte Carlo simulations per game → full stat distributions → +EV prop edges.
**Competitive benchmark:** Second Spectrum (~$1M+/yr, teams only). Gap at Phase 16: ~2%.

---

## End-to-End Data Flow

```
Broadcast Video (.mp4)
    ↓
Court Rectification (SIFT + 3-tier homography → resources/Rectify1.npy)
    ↓
AdvancedFeetDetector (src/tracking/advanced_tracker.py)
    - YOLOv8n person detection (imgsz=640, conf=0.35)
    - HSV + k-means warm-up → team classification
    - Kalman 6D state [cx, cy, vx, vy, w, h]
    - Hungarian assignment (IoU×0.75 + embed×0.25)
    - 99-dim L1-normalised HSV histogram (EMA α=0.7)
    - Gallery TTL=300 frames | MAX_LOST=90
    - YOLOv8-pose ankle keypoints (sub-foot accuracy)
    - Optical flow gap-fill (Lucas-Kanade, ≤8 frames)
    ↓
BallDetectTrack (YOLO TRT FP16 → Hough + CSRT fallback + possession IoU)
    ↓
EventDetector (shot / pass / dribble)
    ↓
JerseyOCR (EasyOCR dual-pass + JerseyVotingBuffer deque[3])
    ↓
Feature Engineering (60+ spatial + temporal features)
    ↓
NBA API Enrichment (shot outcomes, score context, lineup)
    ↓
data/tracking/{game_id}_{date}.csv → PostgreSQL
    ↓
90-Model ML Stack → Possession Simulator → Betting Edge
```

---

## Core Components

### CV Tracking — `src/tracking/`

| Component | File | Description |
|-----------|------|-------------|
| AdvancedFeetDetector | `advanced_tracker.py` | Main tracker: Kalman + Hungarian + HSV re-ID |
| TeamColorTracker | `color_reid.py` | Similar-uniform detection via k-means |
| BallDetectTrack | `ball_detect_track.py` | YOLO TRT → Hough + CSRT fallback |
| EventDetector | `event_detector.py` | Shot / pass / dribble from ball + player state |
| JerseyOCR | `jersey_ocr.py` | EasyOCR dual-pass + voting buffer |
| CourtRectifier | `rectify_court.py` | SIFT panorama + 3-tier homography EMA |
| PlayerResolver | `player_resolver.py` | Maps jersey → NBA roster name |
| PossessionClassifier | `possession_classifier.py` | Which team controls the ball |
| PlayTypeClassifier | `play_type_classifier.py` | Isolate / P&R / post / transition / spot-up |

**Tracking speed:** 15 fps on RTX 4060 (8 GB VRAM) — imgsz=640, YOLOv8n

### Feature Engineering — `src/features/`

60+ features including:
- **Spatial:** spacing index (convex hull), paint density, defender distance, court zone
- **Temporal:** speed, acceleration, 5-frame rolling velocity, possession duration
- **Context:** quarter, game time, score differential, lineup ID, play type
- **CV-only (moat):** spacing at shot, nearest defender at shot, drive frequency, fatigue proxy (speed vs baseline)

### ML Stack — `src/prediction/`, `src/analytics/`

90 models in 6 tiers. See [[02 - Model Catalog]] for full detail.

**The 7-model possession chain (Phase 8 simulator core):**
```
[1] Play Type → [2] Shot Selector → [3] xFG
→ [4] TO/Foul → [5] Rebound → [6] Fatigue → [7] Substitution
× 10,000 per game = full stat distribution per player
```

### API — `api/`

FastAPI app with 10 prediction endpoints. See README for full list. Redis for caching. Celery for async batch processing.

### Database — `database/schema.sql`

PostgreSQL, 9 tables, 2 views:
- `tracking_data` — per-frame CV output
- `possessions` — labeled possessions with outcome
- `shots` — shots with CV context + NBA API enrichment
- `games`, `players`, `teams`, `lineups`, `predictions`, `outcomes`
- Views: `player_performance_view`, `game_summary_view`

---

## Homography — 3-Tier Logic

```
SIFT match count → routing:
  < 8 inliers    → REJECT (use prev)
  8–39 inliers   → EMA blend (α=0.3, soft update)
  ≥ 40 inliers   → HARD RESET (high-confidence re-anchor)

Court drift check every 30 frames:
  white-pixel alignment < 0.35 → force hard reset
```

Constants: `_H_RESET_INLIERS=40`, `_REANCHOR_INTERVAL=30`, `_REANCHOR_ALIGN_MIN=0.35`

---

## Similar-Uniform Handling

When team hue centroids are within **20 hue units** (HSV):
- Hungarian cost: appearance weight raised +0.10 (IoU×0.65 + embed×0.35)
- Gallery re-ID: jersey-number tiebreaker window widened +0.10

Implemented in [[color_reid.py]] via `TeamColorTracker.similar_team_colors()`.

---

## Tracking Data Schema

```python
{
    "game_id": str,
    "timestamp": float,      # seconds from video start
    "frame": int,
    "player_id": int,        # 0–9 players, 10 referee
    "team_id": int,          # 0=team_a, 1=team_b, 2=referee
    "x_position": float,     # 2D court coordinates (post-homography)
    "y_position": float,
    "speed": float,          # court px/frame
    "acceleration": float,
    "ball_possession": bool,
    "event": str,            # "dribble" | "pass" | "shot" | "none"
    "jersey_number": int,    # -1 if OCR failed
    "player_name": str,      # from NBA API roster lookup
}
```

---

## Infrastructure

- **Video processing:** RTX 4060 (8.6 GB VRAM), YOLOv8n imgsz=640, ~15 fps
- **Batch processing:** Celery + Redis (`scripts/batch_process.py`)
- **Cloud GPU (Phase G):** RunPod A100, 50–100 games, $50–100 budget
- **Monitoring:** Feature drift detector (`src/pipeline/feature_drift_detector.py`)
- **Auto-retrain:** `src/pipeline/auto_retrain.py` — triggered nightly after outcome recording

---

## Related Notes

- [[02 - Model Catalog]] — all 90 models
- [[03 - Data Sources]] — NBA API + external scrapers
- [[04 - Pipeline Flow]] — step-by-step run guide
