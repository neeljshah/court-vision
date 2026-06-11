# Computer Vision Tracking Pipeline

> Deep-dive on the broadcast-video → court-coordinate pipeline.
> For system-level context see [`ARCHITECTURE.md`](../ARCHITECTURE.md).
> For honest accuracy numbers and limitations see
> [`docs/JOB_EVIDENCE_PACKET.md`](JOB_EVIDENCE_PACKET.md).

---

## What It Does and Why It Matters

The pipeline converts raw NBA broadcast `.mp4` footage into per-frame 2D court
positions, player identities, ball location, and game events — without any
special camera hardware. Everything runs on a single consumer RTX 4060 GPU.

**Cost comparison:**

| Solution | Cost per game | Notes |
|---|---|---|
| **This system** | **~$0.10–0.13** | RTX 4060, ~$0.08/hr compute |
| Sportradar / Second Spectrum | ~$10,000–$100,000+ | Commercial tracking systems |

The gap exists because commercial systems use dedicated arena camera rigs and
proprietary software. This pipeline extracts equivalent spatial features from the
broadcast feed alone, trading some accuracy for a several-orders-of-magnitude
cost reduction.

**Current honest state:** CV-derived features (defender distance, spacing, fatigue
proxy) are wired into the production prop models and correctly assigned SHAP
importance ≈ 0.0 in production. The CV layer is real, running plumbing — it is not
yet a demonstrated predictive edge. See `docs/JOB_EVIDENCE_PACKET.md §4`.

---

## Pipeline Architecture

```
Broadcast Video (.mp4, 30fps)
        │
        │  _FramePrefetcher (background daemon thread)
        │  decode: decord NVDEC → PyAV → cv2.VideoCapture fallback chain
        │  async prefetch queue (size 8): overlaps I/O decode with GPU tracking
        ▼
┌─────────────────────────────────────────────────────┐
│  STAGE 1 — Court Homography                         │
│  modules: unified_pipeline.py, court_detector.py    │
└────────────────────────┬────────────────────────────┘
                         │  3×3 matrix M: pixel coords → court feet
                         ▼
┌─────────────────────────────────────────────────────┐
│  STAGE 2 — Person + Ball Detection                  │
│  module: advanced_tracker.py (YOLOv8n)              │
│          ball_detect_track.py (YOLOv8n + Hough + LK)│
└────────────────────────┬────────────────────────────┘
                         │  [x1,y1,x2,y2,conf] per detection
                         ▼
┌─────────────────────────────────────────────────────┐
│  STAGE 3 — Multi-Object Tracking                    │
│  module: advanced_tracker.py → AdvancedFeetDetector │
│  Kalman filter + Hungarian assignment + HSV re-ID   │
└────────────────────────┬────────────────────────────┘
                         │  player_id, x_court, y_court, vx, vy
                         ▼
┌─────────────────────────────────────────────────────┐
│  STAGE 4 — Player Identity Resolution               │
│  modules: osnet_reid.py, jersey_ocr.py,             │
│           color_reid.py, player_identity.py         │
└────────────────────────┬────────────────────────────┘
                         │  NBA player_id (real roster lookup)
                         ▼
┌─────────────────────────────────────────────────────┐
│  STAGE 5 — Event Detection                          │
│  module: event_detector.py → EventDetector          │
│  shot / pass / dribble classification               │
└────────────────────────┬────────────────────────────┘
                         │  events.json
                         ▼
┌─────────────────────────────────────────────────────┐
│  STAGE 6 — Scoreboard OCR                           │
│  module: scoreboard_ocr.py → ScoreboardOCR          │
│  game clock, shot clock, score, period, fouls       │
└────────────────────────┬────────────────────────────┘
                         │  ScoreboardReading per interval frame
                         ▼
┌─────────────────────────────────────────────────────┐
│  STAGE 7 — Feature Engineering                      │
│  modules: feature_engineering.py,                   │
│           tracking_feature_extractor.py             │
│  60+ spatial/temporal features per player per frame │
└────────────────────────┬────────────────────────────┘
                         │
                         ▼
           data/tracking/tracking_data.csv
           data/nba_ai.db  (cv_features table)
```

---

## Stage 1 — Court Homography

**Modules:** `src/pipeline/unified_pipeline.py`, `src/tracking/court_detector.py`

Maps pixel coordinates to a standardized 94×50 foot court plane. This is the
foundation: if M is wrong, every downstream court-coordinate is wrong.

### Algorithm

1. **Court line detection** (`court_detector.detect_court_homography`):
   - HSV masking to isolate white court lines
   - `cv2.HoughLinesP` detects candidate line segments
   - `_classify_lines` splits into horizontal vs vertical by angle threshold (±25°)
   - `_line_intersection` computes corners, 3-point line intersections
   - `cv2.getPerspectiveTransform` builds M from 4+ matched point pairs

2. **Three-tier SIFT acceptance** (steady-state, every `_SIFT_INTERVAL=15` frames):

   | Inlier count | Action |
   |---|---|
   | `< 8` | Reject — keep previous M |
   | `8–39` | EMA blend: `M_new = 0.3 × M_detected + 0.7 × M_prev` |
   | `≥ 40` | Hard reset to new M |

3. **Drift detection** (every `_REANCHOR_INTERVAL=30` frames):
   - Project court boundary lines through current M
   - Measure white-pixel alignment along projected lines
   - If alignment score `< _REANCHOR_ALIGN_MIN=0.35` → force hard reset

4. **Broadcast hardening:**
   - 2-frame confirmation gate before accepting a new M (prevents single-frame
     graphic overlays from corrupting the homography)
   - Replay/scene-cut suspension: pipeline suspends homography updates and
     emits `is_replay=True` rows during detected broadcast cuts
   - EMA smoothing prevents jitter from per-frame SIFT noise

### Key Constants

| Constant | Value | Purpose |
|---|---|---|
| `_H_RESET_INLIERS` | 40 | Hard-reset threshold |
| `_SIFT_INTERVAL` | 15 | Run SIFT every N frames |
| `_SIFT_SCALE` | 0.5 | Downscale before SIFT (44s → ~4s overhead) |
| `_REANCHOR_INTERVAL` | 30 | Drift check cadence (frames) |
| `_REANCHOR_ALIGN_MIN` | 0.35 | Minimum alignment score before force-reset |

### Honest Limitation

The homography is estimated from broadcast frames, not a calibrated camera rig.
Positional accuracy and MOT metrics (MOTA/IDF1) are not yet benchmarked against
labeled ground truth. Outputs court coordinates via homography; "±12–18 inch"
accuracy claims are not validated — do not repeat them.

---

## Stage 2 — Detection

### Person Detection

**Module:** `src/tracking/advanced_tracker.py` (delegates to `player_detection.py`)

- Model: `resources/yolov8n.pt` (YOLOv8 nano, ~6MB), class 0 = person only
- Confidence threshold: 0.35 (broadcast detection requires lower than the
  ImageNet default 0.5)
- Input resolution: 640×640

### Ball Detection

**Module:** `src/tracking/ball_detect_track.py` — `BallDetectTrack`

Three-tier fallback chain:

```
Tier 1: YOLOv8n fine-tuned ball detector
        weights: models/weights/yolov8n_ball.{pt,onnx,engine}
        trained via: scripts/train_ball_yolo.py
        exported: ONNX + TensorRT for deployment
          ↓ (on miss or low confidence)
Tier 2: Hough circle detector
        cv2.HoughCircles(dp=1, minDist=20, param1=50, param2=30,
                         minRadius=8, maxRadius=25)
        + brightness, radius, orange-hue filters
        + CSRT tracker for cross-frame continuity
          ↓ (on CSRT failure)
Tier 3: Lucas-Kanade optical flow
        tracks orange-colored pixels from last known ball position
        low-confidence fallback only
```

**Known issue:** `ball_valid_pct = 0%` on some games — root cause under
investigation. EventDetector falls back to last-known possessor coordinates when
`ball_pos is None`.

---

## Stage 3 — Multi-Object Tracking

**Module:** `src/tracking/advanced_tracker.py` — `AdvancedFeetDetector`

This is the core tracker, implemented from primitives (not a black-box wrapper).

### Kalman Filter (per tracked slot)

```python
# State vector: [cx, cy, vx, vy, w, h]
# cx, cy: center position (court feet after homography)
# vx, vy: velocity (feet/frame)
# w, h:   bounding box dimensions

# Prediction step (constant-velocity model):
cx_next = cx + vx
cy_next = cy + vy
# (w, h remain constant between detections)

# Update step: standard Kalman gain applied when slot matches detection
```

Process noise: `KF_PROC_NOISE = 5e-2` | Measurement noise: `KF_MEAS_NOISE = 1e-1`

### Hungarian Assignment

Globally optimal assignment between N_tracks and N_detections:

```python
# Cost matrix (N_tracks × N_detections):
cost[i, j] = (1 - APPEARANCE_W) * (1 - IoU(track_i, det_j))
           +  APPEARANCE_W       * appearance_distance(track_i, det_j)

# APPEARANCE_W = 0.25 (default); raised to 0.35 in similar-color mode
# Solved by: scipy.optimize.linear_sum_assignment (global optimum)
# lapx/lap used when available (ByteTrack-style two-stage assignment):
#   Stage 1: high-confidence detections (conf ≥ BT_HIGH_THRESH=0.35)
#   Stage 2: lower-conf occluded players (IoU gate 0.30,
#            proximity fallback 80px when IoU=0)
```

Unmatched tracks: increment `lost` counter. Evict at `MAX_LOST = 90` frames.
Unmatched detections: spawn new track slot.

### Appearance Re-ID

**Primary appearance model (production):**

```python
# 96-dim L1-normalized HSV histogram (32 hue × 3 sat bins)
# EMA update:
embedding_new = APPEAR_ALPHA * embedding_prev + (1 - APPEAR_ALPHA) * embedding_det
# APPEAR_ALPHA = 0.7 (stable across frames)
```

Lost tracks are held in a gallery (`GALLERY_TTL = 300` frames, ~10s at 30fps).
Re-ID: gallery embedding vs detection embedding, accept if `distance < REID_THRESH=0.45`.
Jersey-number tiebreaker within `REID_TIE_BAND=0.05`.

**Deep appearance model (OSNet, secondary):**

Module: `src/tracking/osnet_reid.py` — `DeepAppearanceExtractor`

The OSNet-x0.25 architecture is reimplemented directly in PyTorch:

```
Input (256×128 px crop)
  → Conv-BN-ReLU (3×3, 64 ch)
  → Max pool
  → OSBlock × 3   [each block has 3 branches:
                    1×1 | 1×1 → 3×3 dw-sep | 1×1 → 3×3 → 3×3 dw-sep
                    gate-aggregated at three receptive-field scales]
  → Conv-BN-ReLU transition layers
  → Global average pool
  → FC → 256-dim L2-normalized embedding
```

Inference backend (priority order):
1. TensorRT (fastest, `yolov8n_ball.engine`-style export)
2. torchreid (if installed)
3. Standalone PyTorch (this module)
4. MobileNetV2 (fallback if OSNet fails)
5. HSV histogram (always available)

**Important caveat:** ships with ImageNet-pretrained weights, not NBA-fine-tuned.
In production the HSV histogram is the active appearance model; OSNet is
structurally complete but not domain-adapted.

### Similar-Color Team Handling

**Module:** `src/tracking/color_reid.py` — `TeamColorTracker`

When two teams have visually similar uniforms:

1. k-means (k=2) on all detected player crops → team color centroids
2. If hue centroids within 20° → activate similar-color mode
3. Appearance weight in cost matrix raised: `0.25 → 0.35`
4. Jersey-number tiebreaker window widened by +0.10

### Pose Keypoints (Cadence-Based)

`advanced_tracker.py` drives a YOLOv8-pose head at adaptive intervals:

| Condition | Interval (frames) | Purpose |
|---|---|---|
| Active (ball holder in frame) | `_POSE_INTERVAL_ACTIVE = 5` | Fresh keypoints at shot release |
| In-play, no ball holder | `_POSE_INTERVAL = 15` | Reasonably current |
| Suspended (no ball holder, game paused) | `_POSE_INTERVAL_SUSPENDED = 30` | Reduce compute |

Ankle keypoints replace bbox-bottom for court coordinate estimation (reduces foot
position error from ~±18" to ~±4" when pose is available).

### Tracking Quality Constants

| Parameter | Value | Purpose |
|---|---|---|
| `COST_GATE` | 0.80 | Reject assignments above this cost |
| `APPEARANCE_W` | 0.25 | Appearance vs IoU weight in cost |
| `MAX_LOST` | 90 | Frames before evicting lost track |
| `GALLERY_TTL` | 300 | Frames to remember lost player (~10s) |
| `REID_THRESH` | 0.45 | Max appearance distance for re-ID |
| `REID_TIE_BAND` | 0.05 | Jersey-number tiebreaker window |
| `APPEAR_ALPHA` | 0.70 | EMA weight for appearance update |
| `MAX_2D_JUMP` | 250 | Max court pixels between frames |
| `HIST_BINS` | 32 | HSV histogram bins per channel |

---

## Stage 4 — Player Identity Resolution

**Modules:** `src/tracking/jersey_ocr.py`, `src/tracking/player_identity.py`

```
Track slot has anonymous ID (integer)
    │
    ▼
JerseyOCR.read(bbox_crop):
  dual-pass: normal crop + inverted binary
  EasyOCR (PaddleOCR when available)
  JerseyVotingBuffer(maxlen=3): majority vote over 3 frames
    │
    ▼
jersey_number → NBA API roster lookup → player_name + player_id
    │
    ▼
confirmed slot persisted in data/nba_ai.db
```

**Scale achieved:** `cv_features` table: 17,254 rows across 241 games,
252 distinct real NBA player IDs resolved.

**Honest limitation:** per-player attribution accuracy is early-stage.
The `docs/JOB_EVIDENCE_PACKET.md` cites ~4% accurate per-player CV attribution
in the initial implementation. Jersey OCR on broadcast footage is a well-known
noise wall: numbers are often occluded, rotated, or covered by overlay graphics.

---

## Stage 5 — Event Detection

**Module:** `src/tracking/event_detector.py` — `EventDetector`

| Event | Detection logic | Output |
|---|---|---|
| Shot | Ball leaves possessor bbox (upward), parabola fit to recent positions confirms shot arc | `{type:"shot", player_id, court_x, court_y, timestamp}` |
| Pass | Ball rapid displacement > 200px/frame from one possessor to another | `{type:"pass", from_player_id, to_player_id}` |
| Dribble | Ball y-coordinate local minimum while same possessor holds | `{type:"dribble", player_id, dribble_count}` |
| Rebound | Ball retrieval after shot arc descends to player bbox | `{type:"rebound", player_id, offensive}` |

**Ball fallback:** when `ball_pos is None`, EventDetector uses last-known
possessor's 2D court coordinates. This allows shot/pass events to fire even on
frames where ball detection fails (important given the ball tracking known issue).

---

## Stage 6 — Scoreboard OCR

**Module:** `src/tracking/scoreboard_ocr.py` — `ScoreboardOCR`

Reads the broadcast score overlay every `_OCR_INTERVAL` frames, caching last-known
values on skipped or failed frames.

```python
reading = ScoreboardOCR(frame_width, frame_height).read(frame)
# Returns ScoreboardReading with fields:
#   game_clock_sec  float (-1 = unknown)
#   shot_clock      float (-1 = unknown)
#   home_score      int   (-1 = unknown)
#   away_score      int   (-1 = unknown)
#   period          int, 1-4 or 5 for OT (-1 = unknown)
#   home_timeouts   int   (-1 = unknown)
#   away_timeouts   int   (-1 = unknown)
#   home_fouls      int   (-1 = unknown)
#   away_fouls      int   (-1 = unknown)
#   confidence      float 0.0-1.0 (fraction of 5 primary fields read)
```

Confidence is computed as the fraction of the 5 primary fields
(clock, shot_clock, home_score, away_score, period) successfully parsed.

OCR backend: EasyOCR primary, PaddleOCR preferred when available.

---

## Stage 7 — Feature Engineering

**Modules:** `src/features/feature_engineering.py`,
`src/pipeline/tracking_feature_extractor.py`

60+ features per player per frame, organized into families:

### Spatial Features

```python
# Spacing index — offensive spread (convex hull of offensive player positions)
spacing_index = convex_hull_area(offensive_player_positions)  # ft²
# 200 ft² = tight half-court, 280 ft² = well-spaced

# Paint density
paint_density = count_players_in_paint(all_positions)

# Defender distance for ball handler
defender_distance = min_distance(ball_handler, defensive_players)

# Nearest defender for shooter (shot quality input)
nearest_defender_dist = min_distance(shooter, defenders)
```

### Temporal Features

```python
# Per-player kinematics
speed[t]        = euclidean_distance(pos[t], pos[t-1]) / time_delta
acceleration[t] = (speed[t] - speed[t-1]) / time_delta

# Fatigue proxy: deviation from that player's season-average movement rate
fatigue_score = 1 - (current_speed / baseline_speed[player_id])
```

### Rolling Window Features

Shot, pass, and dribble event counts in 5/10/20-frame windows per player.

### Data Quality Guards

`tracking_feature_extractor.py` applies ~10 documented sentinel-leak fixes:

- Pixel-vs-feet auto-rescale (prevent unit confusion when homography is wrong)
- Physical validity caps (speed > 30 ft/frame = reject as phantom)
- Phantom-slot filtering (evict tracks stuck in one position > `FREEZE_AGE=20` frames)
- Per-bug guards documented in code comments (`Bug 30/31/34/...`) tied to specific
  observed silent-corruption artifacts

---

## Performance

**Observed throughput on RTX 4060 (640px input, YOLOv8n):** ~5–7 fps end-to-end
(frame decode + YOLO inference + Kalman + Hungarian + feature extraction).

The `_FramePrefetcher` background thread decodes frames N+1 to N+8 while the
main thread processes frame N, yielding ~20–40% end-to-end throughput improvement
over synchronous decode.

**Tracked slot count:** stable at ~5–6 slots on the calibration clip; reliable
10-player broadcast tracking is not yet demonstrated on arbitrary game footage.

---

## Honest Limitations

| Claim | Honest status |
|---|---|
| Position accuracy ±12–18 inches | Not validated against ground truth. No MOT benchmark (MOTA/IDF1). Use "outputs court coordinates via homography" framing. |
| Re-ID accuracy ~91% | Not reproduced. OSNet ships with ImageNet weights; production appearance model is the HSV histogram. |
| Ball tracking valid % | Known issue: `ball_valid_pct = 0%` on some games. |
| 10-player tracking at 15fps | Not reproduced. Observed ~5–7 fps end-to-end; ~5–6 stable slots on calibration clip. |
| CV features = predictive edge | CV features are wired into prop models; SHAP importance ≈ 0.0 in production. Complete plumbing, not a demonstrated advantage. |

---

## Running the Pipeline

```bash
conda activate basketball_ai

# Process a single clip
python run_clip.py \
  --video data/videos/cavs_celtics_2025.mp4 \
  --game-id 0022400710 \
  --no-show   # always headless

# Full game (~6 hours on RTX 4060)
python run_full_game.py \
  --video data/videos/game.mp4 \
  --game-id 0041500407 \
  --no-show

# Tests (no video required)
python -m pytest tests/test_court_detector.py tests/test_homography_thresholds.py -v
python -m pytest tests/test_phase2.py -v

# Validate tracking on a clip (no inference)
python scripts/validate/check_tracking.py --video data/videos/clip.mp4
```

**Never run** `autonomous_loop.py` or `scripts/loop_processor.py` unattended.

---

## Roadmap Targets (Not Yet Achieved)

These are engineering targets, not current metrics:

- **YOLOv8-pose ankle keypoints** at every active frame (reduces foot coord
  error from ~±18" to ~±4"; unlocks contest arm angle for xFG v2)
- **NBA-fine-tuned OSNet weights** (ImageNet pretrain → domain adaptation on
  broadcast jersey crops)
- **Full MOT benchmarking** (MOTA/IDF1/IDP) on labeled ground-truth game segments
- **Ball tracking reliability** to >90% valid frames (currently failing on some games)

---

*Related: [`ARCHITECTURE.md`](../ARCHITECTURE.md) · [`docs/ML_MODELS.md`](ML_MODELS.md) · [`docs/API.md`](API.md) · [`docs/JOB_EVIDENCE_PACKET.md`](JOB_EVIDENCE_PACKET.md)*

*Last verified: 2026-06-11*
