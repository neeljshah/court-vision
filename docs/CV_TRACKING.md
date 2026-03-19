# Computer Vision Tracking — NBA AI System

The CV tracking pipeline processes NBA broadcast video frame-by-frame, extracting 2D court positions, player identities, ball location, and game events without any special camera hardware — just standard broadcast footage.

---

## Pipeline Overview

```
Broadcast Video (.mp4, 30fps)
    │
    ▼  STAGE 1
Court Homography (SIFT)
  pixel coords → court coords (feet)
    │
    ▼  STAGE 2
YOLOv8n Person Detection
  bounding boxes per frame
    │
    ▼  STAGE 3
AdvancedFeetDetector
  Kalman + Hungarian + HSV re-ID
  player_id, team, x_court, y_court, velocity
    │
    ▼  STAGE 4
BallDetectTrack
  Hough circles + CSRT + optical flow
  ball position + possession assignment
    │
    ▼  STAGE 5
EventDetector
  shot / pass / dribble events
    │
    ▼  STAGE 6
Feature Engineering
  60+ spatial/temporal features per frame
    │
    ▼
tracking_data.csv → NBA API enrichment → PostgreSQL
```

**Performance:** 5.7 fps on RTX 4060 (640px input resolution, YOLOv8n)

---

## Stage 1 — Court Homography

**Module:** `src/tracking/rectify_court.py`

Maps every pixel coordinate to a 2D position on a standardized 94×50 foot court diagram.

### How It Works

1. Template: `resources/pano_enhanced.png` — a top-down court panorama with known feature points
2. SIFT feature matching between current video frame and template
3. RANSAC to compute homography matrix M (3×3)
4. M transforms `[px, py]` → `[court_x, court_y]` in feet

### 3-Tier Acceptance Logic

| Inlier Count | Action |
|---|---|
| `< 8` | Reject — use previous homography |
| `8–39` | EMA blend: `M_new = 0.3 × M_detected + 0.7 × M_previous` |
| `≥ 40` | Hard reset to new homography |

### Drift Detection

Every 30 frames, the system checks if the current homography is still accurate:
- Projects court boundary lines using M
- Measures white pixel alignment (court lines should be white)
- If alignment score < 0.35 → force hard reset

**Constants:**
- `_H_RESET_INLIERS = 40`
- `_REANCHOR_INTERVAL = 30` (frames)
- `_REANCHOR_ALIGN_MIN = 0.35`
- `_SIFT_INTERVAL = 15` (run SIFT every 15 frames)
- `_SIFT_SCALE = 0.5` (downscale for speed — 44s → ~4s overhead)

### Phase 2.5 Upgrade (Per-Clip Homography)

Current issue (ISSUE-017): M1 was calibrated for `pano_enhanced` angle. Broadcast clips have different camera angles — 2D coordinates are systematically wrong.

Fix: `court_detector.py` auto-detects court lines per clip, builds M from intersections, then wires into `unified_pipeline.py`.

---

## Stage 2 — Person Detection

**Module:** `src/tracking/player_detection.py`

- **Model:** `resources/yolov8n.pt` (YOLOv8 nano, ~6MB)
- **Classes:** `[0]` — person only
- **Confidence threshold:** 0.35 (lowered from 0.5 for broadcast detection in Phase 2.5-01)
- **Input resolution:** 640×640
- **Output:** `[x1, y1, x2, y2, conf]` per detected person per frame

**Phase 2.5 upgrade:** `yolov8x.pt` for post-game processing (3× slower but 87% → 94% detection accuracy). Nano stays for real-time.

---

## Stage 3 — Player Tracking

**Module:** `src/tracking/advanced_tracker.py`
**Class:** `AdvancedFeetDetector`

### Kalman Filter (per tracked slot)

**State vector:** `[cx, cy, vx, vy, w, h]`
- `cx, cy` — center position on court (feet)
- `vx, vy` — velocity (feet/frame)
- `w, h` — bounding box dimensions

**Prediction step:** Linear constant-velocity model (`cx_next = cx + vx`, etc.)
**Update step:** Kalman gain applied when matched to new detection

### Hungarian Assignment

Solves the optimal assignment between tracked slots and new detections:

```
Cost matrix [N_tracks × N_detections]:
  cost[i,j] = 0.75 × (1 - IoU(track_i, det_j))
             + 0.25 × appearance_distance(track_i, det_j)
```

Solved via `scipy.optimize.linear_sum_assignment` for global optimality.

### Appearance Re-ID

Each track slot maintains a **96-dimensional HSV histogram** as its appearance signature:

```
Histogram: 32 bins Hue × 3 bins Saturation = 96 dims (L1-normalized)
Update:    emb_new = 0.7 × emb_prev + 0.3 × emb_detection
```

When a player leaves the frame (lost track), the appearance gallery maintains their embedding for 300 frames (TTL). If a detection in subsequent frames matches the gallery within threshold, the track is re-established with the original player ID.

### Similar-Color Team Handling

**Module:** `src/tracking/color_reid.py`
**Class:** `TeamColorTracker`

When two teams have similar uniform colors (e.g. OKC blue vs Memphis blue):
1. k-means k=2 on all detected player crops → team centroids
2. If hue centroids within 20° → similar-color mode activated
3. Appearance weight raised: `0.25 → 0.35` in cost matrix
4. Jersey number tiebreaker window widened +0.10

### Jersey OCR

**Module:** `src/tracking/jersey_ocr.py`

- **Model:** EasyOCR
- **Dual-pass:** normal crop + inverted binary (handles dark-on-light and light-on-dark)
- **Voting buffer:** `JerseyVotingBuffer(maxlen=3)` — majority vote over 3 frames before committing
- **Player identity:** jersey number → NBA API roster lookup → player name

### Key Constants

| Parameter | Value | Purpose |
|---|---|---|
| Gallery TTL | 300 frames | How long to remember lost players |
| MAX_LOST | 90 frames | Max frames before evicting a lost track |
| IoU weight | 0.75 | Position-based assignment weight |
| Appearance weight | 0.25 | HSV similarity weight |
| EMA alpha | 0.7 | Appearance update rate |
| Similar-color threshold | 20° hue | Trigger for similar-color mode |
| Freeze age | 20 frames | Evict slot stuck in same position |

---

## Stage 4 — Ball Tracking

**Module:** `src/tracking/ball_detect_track.py`
**Class:** `BallDetectTrack`

Three-tier fallback chain:

### Tier 1 — Hough Circle Detector

```python
circles = cv2.HoughCircles(
    gray_frame,
    cv2.HOUGH_GRADIENT,
    dp=1, minDist=20,
    param1=50, param2=30,
    minRadius=8, maxRadius=25
)
# Additional filters: brightness threshold, radius range, orange hue
```

### Tier 2 — CSRT Tracker

When Hough detection is unreliable (fast ball movement, partial occlusion):
- CSRT initialized from last confirmed Hough detection
- Tracks across frames where Hough fails
- Validated by comparing CSRT bbox to Hough detection when Hough fires again

### Tier 3 — Lucas-Kanade Optical Flow

When both Hough and CSRT fail:
- Tracks orange-colored pixels from previous ball position via LK flow
- Low-confidence fallback — only used for continuity

### Possession Assignment

Ball center within player bounding box → possession attributed to that player.
Ball fallback: if `ball_pos` is None, use possessor's 2D court coordinates for event detection.

---

## Stage 5 — Event Detection

**Module:** `src/tracking/event_detector.py`
**Class:** `EventDetector`

### Shot Detection

1. Ball tracked leaving possessor bbox (upward trajectory)
2. Parabola fit to recent ball positions → inflection point confirms shot arc
3. Event tagged: `{type: "shot", player_id, court_x, court_y, timestamp}`

### Pass Detection

1. Ball rapid displacement (> 200px/frame) from one possessor to another
2. New possessor assigned possession
3. Event tagged: `{type: "pass", from_player_id, to_player_id}`

### Dribble Detection

1. Ball bounces (y-coordinate local minimum) while same possessor maintains possession
2. Dribble count incremented per possessor
3. Event tagged: `{type: "dribble", player_id, dribble_count}`

### Ball Fallback (Fixed Phase 2)

When `ball_pos` is None, EventDetector uses the last known possessor's 2D court coordinates. This allows shot/pass events to fire even on frames where ball detection fails.

---

## Stage 6 — Feature Engineering

**Module:** `src/features/feature_engineering.py`

Computes 60+ spatial and temporal features per frame, aggregated per possession and per game:

### Spatial Features

```python
# Spacing index — how spread out is the offense?
spacing_index = convex_hull_area(offensive_player_positions)  # ft²
# 200 ft² = tight, 280 ft² = well-spaced

# Paint density — how crowded is the paint?
paint_density = count_players_in_paint(all_player_positions)

# Defensive pressure — how much space does the ball handler have?
defensive_pressure = distance_to_nearest_defender(ball_handler)

# Shot quality inputs
defender_distance = min_distance(shooter, defensive_players)
```

### Temporal Features

```python
# Speed and acceleration per player
speed[i] = euclidean_distance(pos[i][t], pos[i][t-1]) / time_delta
acceleration[i] = (speed[i][t] - speed[i][t-1]) / time_delta

# Fatigue proxy — speed vs player's baseline
fatigue_score = 1 - (current_speed / baseline_speed[player_id])
```

---

## Phase 2.5 — CV Quality Upgrades

### 2.5-07 — YOLOv8-Pose Ankle Keypoints (Highest ROI)

**Problem:** Current foot position = bbox bottom edge → ±18 inch error
**Solution:** YOLOv8-pose predicts ankle keypoints directly → ±4 inch error

```python
# Current
foot_y = bbox.y2  # bottom of bounding box — up to 18" off

# Phase 2.5
results = pose_model(frame)
ankle_x = results.keypoints[15].x  # left ankle
ankle_y = results.keypoints[15].y
# → transform with homography → court coords (±4 inches)
```

Impact:
- Court coordinate accuracy: ±18" → ±4" (closes 60% of Second Spectrum gap)
- Unlocks: contest arm angle (xFG v2), movement asymmetry (injury risk)
- Full homography accuracy requires this fix first

### 2.5-04/05 — Per-Clip Court Homography

**Problem:** M1 calibrated for `pano_enhanced` angle. Broadcast clips have different camera angles → 2D coordinates systematically wrong.

**Solution:** `court_detector.py` — detect court lines automatically per clip:
1. Detect court lines via Hough line transform
2. Find intersections (corner, 3pt line, paint corners)
3. Build M from intersections vs known court geometry
4. Wire into `unified_pipeline.py`

---

## Known Issues

| ID | Issue | Status |
|---|---|---|
| ISSUE-017 | Per-clip homography wrong — M1 for pano angle | 🔲 Phase 2.5 (025-04/05) |
| ISSUE-008 | No shot clock from video | 🔲 Phase 2.5 (scoreboard OCR) |
| ISSUE-010 | PostgreSQL not wired — overwrites CSV | 🔲 Phase 6 |
| ISSUE-009 | 0 shots enriched (no --game-id runs) | 🔲 Phase 6 |

---

## How to Run

```bash
conda activate basketball_ai
cd C:/Users/neelj/nba-ai-system

# Process a single clip (NEVER run without --game-id for enrichment)
python run_clip.py --video data/videos/cavs_celtics_2025.mp4 --game-id 0022400710

# Run full game (~6 hours, RTX 4060)
python run_full_game.py --video data/videos/cavs_gsw_2016_finals_g7.mp4 --game-id 0041500407

# Run tests (no video processing)
python -m pytest tests/test_phase2.py -v

# Validate tracking on a clip (no model inference)
python scripts/validate/check_tracking.py --video data/videos/clip.mp4
```

**Never run** `autonomous_loop.py` or `scripts/loop_processor.py` unattended — they fill disk.

---

## Competitive Comparison

| Metric | This System | Second Spectrum | After Phase 2.5 |
|---|---|---|---|
| Position accuracy | ±18 inches | ±3 inches | ±4–6 inches |
| xFG accuracy | Brier 0.226 | ~Brier 0.18 | Brier ~0.200 |
| ID switch rate | ~15% | <1% | ~3–5% |
| Detection accuracy | 87% | >95% | 94% (yolov8x) |
| Ball tracking | 57% frames | >95% | Target 95%+ |

The gap is closeable through Phase 2.5 upgrades. The remaining gap (ball height, hand contest) is worth ~2% total — not worth the hardware investment.
