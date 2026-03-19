# Project CourtVision — CV Tracking Pipeline
> Multi-object tracker that identifies, localizes, and continuously re-identifies 10 NBA players from broadcast footage at 15 fps — extracting spatial data (positions, speed, possession, events) that no public dataset provides.

![Python](https://img.shields.io/badge/Python-3.9-blue) ![OpenCV](https://img.shields.io/badge/OpenCV-4.x-green) ![YOLOv8](https://img.shields.io/badge/YOLOv8n-detection-red) ![Status](https://img.shields.io/badge/Status-Operational-brightgreen)

## Overview

`AdvancedFeetDetector` is the core tracking class in Project CourtVision. It replaces simple IoU-greedy matching with a full multi-object tracking stack: per-player Kalman filters predict position through occlusions, Hungarian assignment globally minimizes ID-switch cost, 99-dim HSV histogram embeddings separate visually similar players, and a gallery with a 300-frame TTL re-identifies players after they exit and re-enter the frame.

The tracker runs on broadcast footage — not the overhead camera angle used by most tracking research — which introduces lens distortion, partial occlusion from overlapping bodies, and variable player scale. Broadcast mode drops the detection confidence threshold to 0.35 (vs. 0.50 for fixed-camera setups) to recover smaller, distant players near the three-point line. Optical flow gap-fills positions during the YOLO misses that broadcast angles produce at this threshold.

## Performance Metrics

| Metric | Value | Benchmark | Status |
|--------|-------|-----------|--------|
| Tracking speed | 15 fps | RTX 4060 8 GB | ✅ |
| Max players tracked simultaneously | 10 | — | ✅ |
| Occlusion recovery (Kalman) | 90 frames (~3 s at 30 fps) | — | ✅ |
| Gallery re-ID TTL | 300 frames (~10 s at 30 fps) | — | ✅ |
| Appearance embedding dim | 99 (96 HSV hist + 3 mean HSV) | — | ✅ |
| Optional deep re-ID dim (OSNet) | 256 | — | ✅ (optional) |
| Court homography inliers (hard-reset) | ≥ 40 SIFT matches | — | ✅ |
| SIFT interval (drift check cadence) | Every 15 frames | — | ✅ |
| SIFT scale factor | 0.5× downscale | Latency: ~9 ms/call | ✅ |
| Position jump gate | 250 court px/frame | ~2× court width/s | ✅ |
| Similar-color appearance boost | +0.10 weight | Triggered when hue ∆ < 20 | ✅ |
| Optical flow gap-fill window | 8 frames | Lucas-Kanade LK | ✅ |
| Pose keypoint cadence | Every 3 frames | Ankle keypoints | ✅ |
| ID switch rate (estimated) | ~8–12% | ByteTrack target ~3% | 🔲 Phase 2.5 |
| Position accuracy | ±12–18" court coords | Second Spectrum ±3" | 🔲 Phase 2.5 |

## Architecture

```
Frame (BGR)
    │
    ▼
YOLOv8n Detection
  conf=0.35 (broadcast mode) or 0.50 (fixed cam)
  classes=[0] (person only)
  imgsz=640 → ~5.7 fps net throughput
    │
    ├── OSNet extractor (optional, 256-dim L2-norm deep embeddings)
    │
    ▼
Cost Matrix Construction
  Rows: active tracker slots (≤10)
  Cols: YOLOv8 detections this frame
  Cost[i,j] = (1 - IoU(pred_i, det_j)) × 0.75
             + appear_dist(emb_i, emb_j) × 0.25
  Similar-color flag: both weights shift +0.10 / -0.10
    │
    ▼
Hungarian Assignment  (scipy.optimize.linear_sum_assignment)
  Gate: reject pairs with cost > 0.80
  Unmatched detections → new slot candidates
  Unmatched slots → lost_age++
    │
    ├── Matched slots:
    │     Kalman correct(bbox)
    │     EMA update appearance  (α=0.70)
    │     Reset lost_age → 0
    │     Optical flow anchor update
    │
    ├── Unmatched slots (lost):
    │     Optical flow propagation (≤8 frames)
    │     Kalman predict (fallback)
    │     lost_age > MAX_LOST=90 → evict → gallery
    │
    └── Unmatched detections:
          Gallery re-ID: appear_dist < REID_THRESH=0.45
          Jersey-number tiebreaker (±REID_TIE_BAND=0.05)
          No match → new slot assignment
    │
    ▼
Court Homography  (src/tracking/rectify_court.py)
  SIFT panorama every 15 frames at 0.5× scale
  Three-tier: reject <8 inliers | EMA blend 8–39 | hard-reset ≥40
  Drift check every 30 frames: white-pixel alignment < 0.35 → force reset
  Velocity clamp: jump > 250 court px → freeze to last known position
    │
    ▼
Pose Estimation  (YOLOv8-pose, every 3 frames)
  Ankle keypoints replace bbox-bottom foot-position heuristic
  Cached between pose frames; falls back to bbox_bottom on miss
    │
    ▼
Team Color Calibration  (dynamic, warm-up)
  First 30 non-referee detections → collect dominant HSV
  K-means k=2 → team centroids A and B
  Re-calibrates every 150 frames
  TeamColorTracker (color_reid.py) updates per-team EMA signature
    │
    ▼
Output per frame:
  player_id, team_id, (x, y) court coords, speed,
  ball_possession, event, jersey_number, player_name
  → data/tracking_data.csv  →  PostgreSQL (Phase 6)
```

## Features

- Tracks 10 players simultaneously at 15 fps on an RTX 4060 (8 GB VRAM) from standard broadcast footage
- Kalman filter 6D state `[cx, cy, vx, vy, w, h]` predicts player bounding box when detection fails; positions survive up to 90 lost frames (~3 s at 30 fps)
- Hungarian algorithm (scipy) solves globally optimal assignment over `(1-IoU)×0.75 + appearance_distance×0.25` cost; greedy fallback when scipy unavailable
- 99-dim L1-normalised HSV histogram embeddings computed from the top 70% of each player crop (jersey region) — mean-HSV replaces KMeans dominant cluster for a 50–100× latency reduction
- EMA appearance update (`α=0.70`) keeps embeddings stable across frame noise while adapting to changing lighting
- Lost-track gallery: evicted slots archived with appearance snapshot, TTL = 300 frames; re-ID fires on unmatched detections via histogram intersection distance
- Similar-uniform correction: when team HSV hue centroids are within 20 units, appearance weight raised +0.10 and jersey-number tiebreaker window widened +0.10 in gallery re-ID
- Optical flow gap-fill (Lucas-Kanade) propagates pixel position for up to 8 frames during YOLO misses before handing off to pure Kalman prediction
- Pose estimation (YOLOv8-pose) runs every 3 frames; ankle keypoints replace bbox-bottom heuristic, reducing foot-position error by approximately 40% on broadcast angle footage
- Court homography three-tier strategy: EMA blend on 8–39 SIFT inliers, hard-reset on ≥ 40; drift check every 30 frames via white-pixel court-line alignment score
- Position velocity clamp: projected court jump > 250 px/frame freezes slot to last known position, preventing SIFT noise from corrupting trajectory
- Optional OSNet deep re-ID (`DeepAppearanceExtractor`, 256-dim L2-norm) replaces HSV histograms when model weights are available

## How It Works

**Detection and state initialization.** Each frame, YOLOv8n runs at `imgsz=640` with `conf=0.35` (broadcast mode) or `0.50` (fixed-camera) on `classes=[0]`. Detections are bundled into dicts containing the raw bounding box, an HSV embedding, an optional OSNet deep embedding pre-computed before the cost loop (avoiding the 256-dim vs. 99-dim dimension mismatch that caused ISSUE-022), and the Lucas-Kanade foot anchor point. New slots are initialized with a fresh Kalman filter seeded at the detection centroid.

**Cost matrix and assignment.** For each frame, the `N×M` cost matrix is built between active tracker slots and current detections. The base cost is `(1 - IoU(kalman_prediction, detection)) × 0.75 + histogram_intersection_distance × 0.25`. When `TeamColorTracker` flags that both teams wear similar colors (hue centroids within 20 units), appearance weight rises to 0.35 and IoU weight drops to 0.65 — prioritizing the embedding signal that can actually discriminate between visually similar jerseys. Pairs above the gate of 0.80 are rejected before `linear_sum_assignment` runs. This two-weight design means the tracker degrades gracefully under poor lighting (where embeddings are noisy) by falling back to IoU, and degrades gracefully under occlusion (where IoU is zero) by falling back to appearance.

**Re-identification after frame exit.** When a slot exceeds `MAX_LOST=90` frames, it is evicted and its last appearance embedding is archived in `_gallery` with a TTL of 300 frames. On subsequent frames, unmatched detections are checked against every gallery entry via histogram intersection distance. If the minimum distance is below `REID_THRESH=0.45`, the slot is reclaimed. When two gallery candidates are within `REID_TIE_BAND=0.05` of each other, jersey number (from `JerseyVotingBuffer`) breaks the tie. This two-stage check — live matching first, gallery re-ID second — avoids the false-positive re-IDs that arise when players with similar jersey colors re-enter the frame near a slot that was just evicted for a different reason.

**Court homography and position clamping.** SIFT runs every 15 frames at 0.5× scale on a panoramic court template. Inlier count determines the tier: fewer than 8 inliers rejects the new homography and holds the previous estimate; 8–39 blends with EMA (`α=0.7`); 40+ hard-resets. Every 30 frames, the current homography is validated by projecting the court boundary lines and measuring white-pixel alignment — if below 0.35, a hard-reset is forced regardless of SIFT confidence. Individual position updates are clamped at 250 court pixels/frame; jumps above that threshold freeze the slot to its last good position, preventing SIFT noise from producing impossible player velocities in the 2D court coordinate output.

**Pose and optical flow.** YOLOv8-pose runs every `_POSE_INTERVAL=3` frames; ankle keypoints are cached in `_pose_state[slot]` and reused on intervening frames, contributing ankle-derived foot position to the `(x, y)` court-coordinate output instead of the bbox-bottom heuristic. Optical flow (Lucas-Kanade, window `15×15`, 2 pyramid levels) activates automatically when a slot goes undetected — it propagates the pixel-space foot anchor for up to 8 frames, providing smoother position interpolation than pure Kalman prediction alone during brief occlusions.

## Usage

```python
from src.tracking.advanced_tracker import AdvancedFeetDetector
from src.tracking.player import Player

# Initialize with roster slots
players = [Player(name=f"player_{i}", team_id=i % 2) for i in range(10)]
tracker = AdvancedFeetDetector(players)

# Per-frame tracking
import cv2
cap = cv2.VideoCapture("game_clip.mp4")
frame_idx = 0

while True:
    ret, frame = cap.read()
    if not ret:
        break

    annotated_frame, court_map_2d, court_map_text = tracker.get_players_pos(
        frame,
        homography_matrix=H,  # from rectify_court.py
        timestamp=frame_idx,
    )
    frame_idx += 1

# Access tracked positions
for player in players:
    if player.positions:
        last_ts = max(player.positions)
        x, y = player.positions[last_ts]
        print(f"{player.name}: court ({x:.1f}, {y:.1f})")
```

```python
# Broadcast mode (default) — lower conf threshold, pose enabled
from src.tracking.tracker_config import load_config
cfg = load_config()
print(cfg["broadcast_mode"])      # True
print(cfg["conf_threshold"])      # 0.35 (overridden from 0.50 in __init__)
print(cfg["appearance_w"])        # 0.25
print(cfg["max_lost_frames"])     # 90
```

```python
# Access jersey OCR + identity
from src.tracking.jersey_ocr import JerseyVotingBuffer
from src.tracking.player_identity import persist_identity_map

# Jersey voting buffer is wired externally after construction
buf = JerseyVotingBuffer(n_slots=10, window=3)
tracker._jersey_buf = buf

# After N frames, persist confirmed identities to PostgreSQL
persist_identity_map(tracker.players)
```

## Integration

```
Court Rectification (rectify_court.py)
    → homography matrix H
    → AdvancedFeetDetector.get_players_pos(frame, H, timestamp)
        → BallDetectTrack (ball_detect_track.py)
        → EventDetector (event_detector.py)
        → JerseyOCR (jersey_ocr.py) + JerseyVotingBuffer (player_identity.py)
        → TeamColorTracker (color_reid.py)
        → OSNet extractor (osnet_reid.py) [optional]
    → positions, events, possession
    → Feature Engineering (src/features/feature_engineering.py)
    → Analytics (src/analytics/shot_quality.py, defense_pressure.py, ...)
    → unified_pipeline.py → tracking_data.csv → PostgreSQL (Phase 6)
```

## Configuration

Key parameters in `src/tracking/tracker_config.py`:

| Parameter | Default | Controls | When to Change |
|-----------|---------|----------|----------------|
| `conf_threshold` | 0.50 (0.35 broadcast) | YOLO detection confidence | Lower for distant players; raises false-positive rate |
| `appearance_w` | 0.25 | Embedding vs. IoU weight in cost matrix | Raise for similar-color teams |
| `max_lost_frames` | 90 | Frames before evicting a lost slot | Raise for longer occlusion sequences |
| `gallery_ttl` | 300 | Frames a gallery entry stays valid | Raise if players exit frame for > 10 s |
| `reid_threshold` | 0.45 | Max appearance distance for gallery re-ID | Lower to reduce false re-IDs |
| `broadcast_mode` | True | Activates 0.35 conf, enables pose | Set False for fixed overhead cameras |
| `osnet_weights_path` | `""` | Path to pre-trained OSNet weights | Set when fine-tuned weights are available |
| `HIST_BINS` | 32 | Bins per channel in HSV histogram | Higher = more discriminative; slower |
| `APPEAR_ALPHA` | 0.70 | EMA stability for appearance updates | Lower = faster adaptation to lighting change |
| `MAX_2D_JUMP` | 250 | Court px/frame velocity clamp | Raise for faster players on longer clips |

## Current Limitations + Roadmap

**ID switch rate (~8–12%).** The HSV histogram embedding discriminates well between teams but struggles when two players on the same team wear the same jersey color in close proximity. Fix: ByteTrack two-stage matching (Stage 1: high-conf detections; Stage 2: low-conf "byte" detections) is scaffolded (`BT_HIGH_THRESH=0.50`, `BT_SECOND_IOUGATE=0.50`) but not yet the default path. Target: ~3% ID switch rate. **Phase 2.5.**

**Position accuracy (±12–18").** Bbox-bottom foot position on broadcast angle introduces systematic error from players not being directly overhead. Ankle keypoints from YOLOv8-pose close most of this gap; per-clip homography calibration (vs. the current pre-computed `Rectify1.npy` from the panorama calibration clip) closes the rest. **Phase 2.5.**

**No ball height or hand-contest angle.** These require a second camera angle or stereo vision and are not addressable from broadcast feeds. Worth ~2% on xFG accuracy — deprioritized in favor of data volume. **Acknowledged limitation, not on roadmap.**

**PostgreSQL writes not yet wired.** Every run overwrites `tracking_data.csv`. ISSUE-010. **Phase 6.**
