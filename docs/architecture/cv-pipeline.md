# CV Pipeline — YOLO to Court-Coordinate Features

*Full CV layer — YOLO detection through court-coordinate feature extraction.*

---

> Deeper, code-grounded companion to [`docs/CV_TRACKING.md`](../CV_TRACKING.md)
> (stage-by-stage with constants + failure modes) and the honest-numbers source
> [`docs/JOB_EVIDENCE_PACKET.md`](../JOB_EVIDENCE_PACKET.md).

## Honest framing (read first)

The CV layer is **real, running plumbing** at **~$0.10-0.13 per full game on one
consumer GPU** (vs ~$10k-$100k+ for Sportradar / Second Spectrum). But the
CV-derived features carry **SHAP importance ~ 0.0** in the production prop models
today (`cv_lift_report.json: has_cv_data: false`). They are wired end-to-end; the
predictive lift is unproven. Treat the spatial features below as **lineage, not a
moat** — there is no CV predictive-edge claim. (The phrase "primary model moat"
elsewhere in this file is the original engineering intent, not a measured result.)

## Pipeline Overview

The CV pipeline transforms raw broadcast video into per-frame, per-player position data in court coordinates, with player identities resolved via re-identification. The output feeds the feature engineering layer which computes the spatial features (defender_distance, spacing_score, legs_fatigue) — wired into the prop models, SHAP ~ 0.0.

```
Broadcast video (H.264, ~30fps)
        │
        ▼
[1] Frame decode (decord → NVDEC; fallback: PyAV CPU)
        │
        ▼
[2] YOLOv8n detection
    Players (class 0) + ball (class 32) per frame
        │
        ▼
[3] SIFT homography
    Court line keypoints → perspective transform → court coordinates
        │
        ▼
[4] Kalman filter + Hungarian assignment
    Consistent track IDs across frames
        │
        ▼
[5] OSNet re-ID (512-dim embeddings)
    Track ID → Player identity (jersey + color + appearance)
        │
        ▼
[6] EasyOCR jersey number reading
    Corroborates re-ID assignment
        │
        ▼
[7] EventDetector
    Shot attempts, made shots, turnovers, fouls from trajectory + pose
        │
        ▼
[8] Feature extraction (feature_engineering.py)
    defender_distance, spacing_score, legs_fatigue, contest%, ...
        │
        ▼
data/tracking/*.json + data/events/*.json
```

---

## Stage Detail

### Stage 1: Frame Decode

Preferred: `decord` library using NVDEC GPU engine. Reduces CPU decode overhead by ~1.5 cores/worker versus PyAV CPU decode. Falls back silently to PyAV if decord is not installed.

Critical: stage videos to local disk (`/root/nba_videos` on pods, not the network filesystem). NFS reads are ~38× slower for video; this was the primary bottleneck before local staging was implemented.

AV1-encoded videos are quarantined — the decoder lacks AV1 hardware support. Only H.264 in the processing queue.

### Stage 2: YOLOv8n Detection

Model: `resources/yolov8n.pt` (standard pretrained). Runs at batch size 12 by default. Detects players, refs, and ball per frame.

Key implementation detail: `_VRAM_FLUSH_INTERVAL` must be 3000 (not 100). Setting flush to every 100 frames forces GPU sync barriers that stall CPU stages → 10× slowdown. See [`src/pipeline/unified_pipeline.py`](../../src/pipeline/unified_pipeline.py).

### Stage 3: SIFT Homography

SIFT keypoints on court lines → perspective transform to canonical 28m × 15m court coordinates. This is what converts pixel positions to physical distances for defender distance and spacing computations.

**Known issue:** Broadcast panoramas (wide-angle shots) break SIFT when the broadcast camera is too close or panned. Fix: ratio upper bound on acceptable homography + 5-second stability window + fallback to last valid homography. Implementation: `_compute_homography` in `unified_pipeline.py`.

The homography is the prerequisite for all spatial features. A failed or degraded homography silently corrupts the downstream spatial measurements.

### Stage 4: Kalman + Hungarian

Standard multi-object tracking. Kalman filter predicts next frame position for each track; Hungarian algorithm assigns detections to existing tracks by minimizing total distance cost. Handles brief occlusions by maintaining track state through missed frames (max gap: configurable).

Implementation: [`src/tracking/advanced_tracker.py`](../../src/tracking/advanced_tracker.py) — `AdvancedFeetDetector`

### Stage 5: OSNet Re-ID

512-dimensional appearance embeddings computed per player crop. Gallery built from clean first-half frames; re-identification by cosine similarity against gallery. Assignment to player roster via jersey number OCR correlation.

Implementation: [`src/tracking/osnet_reid.py`](../../src/tracking/osnet_reid.py)

Team color tracking for primary assignment: [`src/tracking/color_reid.py`](../../src/tracking/color_reid.py) — `TeamColorTracker`

### Stage 6: EasyOCR Jersey Number

Reads jersey numbers from player crops, used to corroborate OSNet assignments. Handles partial occlusion, rotated numbers, and compressed video quality. Secondary check only; OSNet is primary.

### Stage 7: EventDetector

Detects game events from tracking data:
- **Shot attempts:** ball trajectory exceeds height threshold + player in shooting pose
- **Made shots:** trajectory terminates at basket + scoreboard update (where visible)
- **Turnovers:** possession changes without shot attempt
- **Fouls:** flagged from referee gestures (partial implementation)

Output: `data/events/*.json` with possession-level event records keyed by `game_id`.

### Stage 8: Feature Extraction

Joins tracking data with event records on `(game_id, event_id, player_id)`. Computes:

| Feature | Computation | Notes |
|---------|-------------|-------|
| `defender_distance` | Distance (meters) from shooter to nearest defender in court coords at shot release frame | Primary moat feature |
| `spacing_score` | Convex hull area of 4 off-ball offensive players, normalized to half-court | Ball-handler excluded from hull |
| `legs_fatigue` | Cumulative running distance over last 6 minutes, exponentially decayed (λ=0.02/min) | Uses full track history |
| `nearest_opponent` | Distance to nearest opponent across all frames of possession | Different from shot-release distance |
| `handler_isolation` | Euclidean distance from ball-handler to nearest teammate | Isolation play detection |
| `contest_pct` | Fraction of possession frames where defender within 2m | Sustained pressure metric |

Implementation: [`src/features/feature_engineering.py`](../../src/features/feature_engineering.py) — `compute_spatial_features`

---

## Real Algorithms + Constants (per stage)

The stages above are not black-box wrappers — the tracker is built from primitives.
Verified constants from `src/tracking/advanced_tracker.py` and the pipeline:

| Stage | Algorithm (real) | Key constants |
|---|---|---|
| 1 Decode | decord/NVDEC → PyAV CPU fallback; background prefetch queue | prefetch queue size 8; `_VRAM_FLUSH_INTERVAL=3000` (never 100) |
| 2 Detect | YOLOv8n (`yolov8n.pt`), class 0 = person; ball: YOLOv8n-ball → Hough circles → Lucas-Kanade | conf 0.35; 640×640 input; Hough `param1=50, param2=8, r=8..25` |
| 3 Homography | HSV line mask → `HoughLinesP` → `getPerspectiveTransform`; 3-tier SIFT acceptance + drift re-anchor | `_SIFT_INTERVAL=300` (RunPod GPU saturation), `_H_RESET_INLIERS=40`, `_REANCHOR_INTERVAL=60` (court stable), `_REANCHOR_ALIGN_MIN=0.35` |
| 4 Track | Kalman (state `[cx,cy,vx,vy,w,h]`, constant-velocity) + Hungarian (`scipy.linear_sum_assignment`); ByteTrack-style 2-stage when lap available | `COST_GATE=0.80`, `APPEARANCE_W=0.25` (0.35 similar-color), `MAX_LOST=90`, `MAX_2D_JUMP=250` |
| 5 Re-ID | **Production: 96-dim L1 HSV histogram** + EMA; OSNet-x0.25 (256-dim L2) structurally complete but **ImageNet weights, not domain-adapted** | `REID_THRESH=0.45`, `REID_TIE_BAND=0.05`, `APPEAR_ALPHA=0.70`, `GALLERY_TTL=300`, `HIST_BINS=32` |
| 6 OCR | EasyOCR (PaddleOCR when available); dual-pass crop + `JerseyVotingBuffer(maxlen=3)` majority vote | confidence = fraction of 5 primary scoreboard fields read |
| 7 Events | EventDetector: parabola-fit shot arc, displacement-threshold pass, y-minimum dribble | pass displacement > 200px/frame |
| 8 Features | convex-hull spacing, min-distance defender, season-baseline fatigue proxy | ~10 sentinel-leak guards (pixel/feet auto-rescale, speed > 30 ft/frame reject) |

**Re-ID caveat (load-bearing):** despite the "512-dim OSNet embeddings" framing in
the stage detail above, the **active appearance model in production is the HSV
histogram**. OSNet is reimplemented and runnable but ships with ImageNet-pretrained
weights (no NBA fine-tune) and is the secondary backend. Do not cite an OSNet re-ID
accuracy number — none is reproduced.

## Known Failure Modes

| Stage | Failure | Mitigation |
|---|---|---|
| Homography | Replay/graphic overlay or close panorama corrupts M | 2-frame confirm gate, EMA blend, replay suspension, drift re-anchor |
| Ball | `ball_valid_pct = 0%` / `ball_track_suspended` stuck True (~8% of games) | last-known-possessor fallback; below-80% games fall back to API-only features |
| Tracking | ghost slots near stars; 10-slot ceiling; ~5-6 stable slots | phantom eviction (`FREEZE_AGE=20`), validity caps |
| Identity | jersey-OCR noise wall → ~4% per-player attribution | aggregate team/position features ship-ready; per-player not |
| Features | unit confusion / silent corruption when M wrong | `Bug 30/31/34/...` sentinel guards |

## Performance Characteristics

| Config | Aggregate fps | Bottleneck |
|--------|--------------|-----------|
| CPU only | ~4 fps | YOLO inference |
| Single 3090, 1 worker | ~20 fps | CPU stages (re-ID, feature extraction) |
| Single 3090, 4 workers, OMP cap | ~80 fps | CPU CFS quota (~17.85 cores) |
| Single 4090, 4 workers, OMP cap | ~100 fps | Similar CPU bound |

**OMP cap is required:** `OMP_NUM_THREADS=6 MKL_NUM_THREADS=6 OPENBLAS_NUM_THREADS=6`. Without it, parallel-4 workers oversubscribe thread pools → 45% of CFS periods throttled → ~3× slowdown.

See [runpod-runbook.md](../operations/runpod-runbook.md) for full pod configuration.

---

## Data Quality Gates

| Gate | Threshold | Failure behavior |
|------|-----------|-----------------|
| `ball_valid_pct` | ≥ 80% | Games below threshold fall back to API-only features |
| Player re-ID coverage | ≥ 8 of 10 players | Low-coverage games excluded from spatial feature training set |
| Homography error | Below keypoint RMS threshold | Fall back to last valid homography; flag game |

**Open issue:** `ball_track_suspended` stays True on ~8% of games for the entire video, silently degrading to imputed means. Root cause not yet identified; scheduled for triage at N=80 games.

---

## Output Format

`data/tracking/GAME_ID.json`:
```json
{
  "game_id": "0022401234",
  "frames": [...],
  "players": {
    "player_id": "203076",
    "tracks": [
      {"frame": 0, "x": 14.2, "y": 7.1, "confidence": 0.92},
      ...
    ]
  },
  "events": [
    {
      "event_type": "shot_attempt",
      "frame": 842,
      "player_id": "203076",
      "defender_distance": 1.4,
      "spacing_score": 187.3
    }
  ]
}
```

`data/events/GAME_ID.json`: possession-level event records with feature snapshots at event time.

---

## Planned Extensions

| Extension | Edge # | Status | Estimated build |
|-----------|--------|--------|----------------|
| Closeout speed on shooters | 3 | Planned | 1–2 days |
| Paint density per possession | 4 | Planned | hours |
| Transition/half-court classification | 5 | Planned | hours |
| Catch-and-shoot detection | 6 | Planned | 1 day |
| Off-ball movement quality | 7 | Planned | 1–2 days |
| Shot trajectory / release angle | 8 | Planned | 2 weeks |
| PnR detection (rule-based) | 9 | Planned | 1–2 weeks |
| YOLO prefetch batching | — | Planned | ~30 LOC; est. +50% fps |

---

The Edge # column above tracks engineering intent for richer spatial features.
None of these is a demonstrated betting edge; they are extraction targets. The
honest status of any CV predictive lift remains SHAP ~ 0.0 until the 80-clean-game
retrain clears (see [`docs/KNOWN_LIMITATIONS.md`](../KNOWN_LIMITATIONS.md)).

---

*See [system-overview.md](system-overview.md) for where CV features fit in the full pipeline. See [feature-inventory.md](../models/feature-inventory.md) for all features including non-CV signals. Companion: [`docs/CV_TRACKING.md`](../CV_TRACKING.md) · honest numbers: [`docs/JOB_EVIDENCE_PACKET.md`](../JOB_EVIDENCE_PACKET.md).*


---
<!-- nav-footer -->
**Navigate:** [Up: full doc map](../INDEX.md) - [Home](../../README.md) - [Glossary](../GLOSSARY.md)
