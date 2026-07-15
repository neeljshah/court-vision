# Tracking Pipeline

> Operational runbook for the per-frame tracking loop. For the stage-by-stage
> deep dive with real algorithms + failure modes see
> [`docs/CV_TRACKING.md`](CV_TRACKING.md) and
> [`docs/architecture/cv-pipeline.md`](architecture/cv-pipeline.md). Honest numbers:
> [`docs/JOB_EVIDENCE_PACKET.md`](JOB_EVIDENCE_PACKET.md).

## Honest framing

This pipeline outputs court coordinates, identities, and events from broadcast
video at **~$0.10-0.13 per full game** on one consumer GPU. The downstream spatial
features it produces are wired into the prop models but carry **SHAP importance
~ 0.0** in production — real plumbing, not a demonstrated predictive edge. Position
accuracy is **not** benchmarked against ground truth (no MOTA/IDF1); the active
appearance model is the **HSV histogram**, not domain-adapted OSNet. Do not infer a
CV moat from the schema below — it is lineage.

## Entry Points

```bash
# Single clip — full pipeline (tracking → enrichment → features → analytics)
python run_clip.py --video game.mp4 --game-id 0022300001 --period 1 --start 0 --no-show

# Tracking quality metrics only
python run.py --eval
```

---

## Video Decode Path

The pipeline prefers GPU-accelerated video decode via **decord** (NVDEC engine):

```python
# src/pipeline/unified_pipeline.py::_decord_frame_iter
# 1st choice: decord (pip install decord) — NVDEC GPU decode, frees ~1.5 CPU cores/worker
# Fallback:   PyAV CPU decode — silent fallback if decord not installed
```

**Performance impact:**
- With decord: ~20 fps/worker on RTX 4090, ~80 fps aggregate (4 workers)
- Without decord (PyAV fallback): ~11 fps/worker, ~45 fps aggregate
- Install: `pip install decord` on pod before launch

---

## VRAM Flush Interval

```python
# src/pipeline/unified_pipeline.py
_VRAM_FLUSH_INTERVAL = 3000   # MUST be 3000, never 100
```

`torch.cuda.empty_cache()` is called every `_VRAM_FLUSH_INTERVAL` frames. Setting this to 100 forces GPU syncs every 100 frames → 10x slowdown. The value 3000 is enforced by the pod launch script preflight check.

---

## Performance Reference (RTX 4090, Phase G config)

| Config | fps/worker | Aggregate (4 workers) |
|--------|-----------|----------------------|
| decord + OMP_NUM_THREADS=6 | ~20 | ~80 |
| PyAV + no OMP cap | ~11 | ~45 |
| PyAV + OMP cap | ~11 | ~45 |

**fps interpretation:** The `PROFILE TOTAL=0.3s` log line is NOT the frame interval — decord batches decode. Real fps = `max_frame / wall_seconds_since_worker_start`.

---

## Per-Frame Processing Loop

```
Frame (BGR numpy array)
    ↓
1. Court rectification
   rectify_court.py → apply homography M to map frame pixels to 2D court coords

2. Player detection
   YOLOv8n(frame, classes=[0], conf=0.5) → list of (x1,y1,x2,y2) bboxes
   Head position: (x1+x2)//2, y1
   Foot position: (x1+x2)//2, y2  ← used for court coords

3. Team classification
   For each bbox: crop jersey region (center 40% of bbox height)
   HSV histogram → adaptive thresholds (brightness-adjusted) → team_id

4. Kalman prediction
   For each active track: predict next position from [cx,cy,vx,vy,w,h] state

5. Hungarian assignment
   Cost matrix (N_detections × N_tracks):
     cost[i,j] = (1 - IoU(det_i, track_j)) × 0.75
               + appearance_distance(det_i, track_j) × 0.25
   scipy.optimize.linear_sum_assignment → globally optimal matching

6. Track update
   Matched: update Kalman state, update HSV appearance embedding (EMA α=0.7)
   Unmatched detections: create new track
   Unmatched tracks: increment lost counter; if lost > MAX_LOST → move to gallery

7. Re-identification
   For new detections: compare HSV histogram to lost-track gallery
   If distance < 0.45 → reassign original track ID
   Gallery entries expire after GALLERY_TTL=300 frames

8. Ball tracking
   Hough circles on grayscale frame → if found, reinit CSRT
   If Hough fails: CSRT update → if CSRT fails: Lucas-Kanade optical flow
   If all fail: trajectory prediction from last 6-frame mean velocity
   Possession: argmax IoU(ball_bbox, player_bboxes)

9. Event detection
   EventDetector.update(players, ball) → event label per player per frame
   Shot: player had possession + ball leaves frame upward + speed spike
   Pass: possession transfer between players
   Dribble: ball near same player, low vertical velocity

10. Spatial metrics (per frame)
    team_spacing: convex hull area of 5 on-court players
    team_centroid_x/y: mean position
    paint_count_own/opp: players in lane
    handler_isolation: distance from ball-handler to nearest defender

11. CSV row written
    frame, timestamp, player_id, team_id, x, y, speed, acceleration,
    ball_possession, event, team_spacing, paint_count, possession_id, confidence
```

---

## Possession Segmentation

A new possession starts when:
- Ball possession changes from team A to team B
- A shot is detected
- The ball goes out of frame for > N frames

Each possession row in `possessions.csv`:
- `possession_id`, `team_id`, `start_frame`, `end_frame`, `duration_s`
- `avg_spacing`, `avg_pressure`, `shot_attempted`, `fast_break`, `result` (filled by enricher)

---

## NBA API Enrichment

`src/data/nba_enricher.py` runs after tracking:

1. Fetch play-by-play for the game (`nba_api.stats.endpoints.playbyplayv3.PlayByPlayV3`)
2. Time-align tracking timestamps to game clock
3. For each shot in `shot_log.csv`: find matching play-by-play event → label `made` (True/False)
4. For each possession in `possessions.csv`: find result (scored/turnover/foul) + score_diff at end

Outputs: `shot_log_enriched.csv`, `possessions_enriched.csv`
Cache: raw API responses saved to `data/nba/` — not re-fetched on subsequent runs

---

## Output Schema

### tracking_data.csv
| Column | Type | Description |
|---|---|---|
| `game_id` | str | NBA game identifier |
| `frame` | int | Video frame number |
| `timestamp` | float | Seconds from video start |
| `player_id` | int | 0–9 players, 10=referee |
| `team_id` | int | 0=team A, 1=team B, 2=referee |
| `x_position` | float | 2D court X coordinate |
| `y_position` | float | 2D court Y coordinate |
| `speed` | float | px/frame in court coords |
| `acceleration` | float | Speed delta from last frame |
| `ball_possession` | bool | Player holds ball this frame |
| `event` | str | shot / pass / dribble / none |
| `team_spacing` | float | Convex hull area of 5-man unit |
| `possession_id` | int | Which possession this frame belongs to |
| `confidence` | float | Track confidence (1.0 → 0.0 as track ages) |

### shot_log_enriched.csv
| Column | Description |
|---|---|
| `player_id` | Shooter |
| `x`, `y` | Court coordinates |
| `court_zone` | restricted / paint / mid-range / corner3 / above-break3 |
| `defender_distance` | Nearest defender (court units) |
| `team_spacing` | Convex hull area at shot time |
| `possession_id` | Parent possession |
| `shot_clock` | Estimated from play-by-play |
| `made` | True/False (from NBA API) |
| `shot_quality` | 0–1 score from shot_quality.py |

---

## Tracker Parameters

| Parameter | Value | Effect |
|---|---|---|
| `MAX_LOST` | 90 frames | Frames before track moved to gallery |
| `GALLERY_TTL` | 300 frames | Frames before gallery entry expires |
| `REID_THRESHOLD` | 0.45 | HSV histogram distance for re-ID match |
| `_H_MIN_INLIERS` | 5 | Minimum SIFT inliers to accept new homography |
| `_H_RESET_INLIERS` | 40 | SIFT inliers threshold for hard EMA reset |
| `_REANCHOR_INTERVAL` | 60 | Frames between court-line drift checks |
| `_REANCHOR_ALIGN_MIN` | 0.35 | Minimum white-pixel alignment before forcing reset |
| `_H_EMA_ALPHA` | 0.15 | Homography smoothing factor |
| Kalman Q | 5e-2 | Process noise (position uncertainty) |
| Kalman R | 0.1 | Measurement noise |

---

## Known Failure Modes

| Stage | Failure | Effect / mitigation |
|---|---|---|
| Homography | replay/graphic overlay or close panorama corrupts M | every court coord wrong; 2-frame confirm gate + EMA blend + drift re-anchor + last-valid fallback |
| Ball | `ball_valid_pct = 0%` (`ball_track_suspended` stuck True, ~8% of games) | events fall back to last-known possessor coords; below 80% valid -> API-only features |
| Tracking | ghost slots near stars; 10-slot ceiling | only ~5-6 stable slots; phantom eviction via `MAX_LOST=90`, speed/jump caps |
| Identity | jersey-OCR noise wall (occlusion/rotation/overlay) | ~4% per-player attribution; aggregate team/position features ship-ready, per-player not |
| Scoreboard | per-quarter `scoreboard_period` NaN / percentile-filled | per-quarter signals defeated; last-known caching on skipped frames |

## Data Quality Gates

| Gate | Threshold | Failure behavior |
|---|---|---|
| `ball_valid_pct` | >= 80% | fall back to API-only features |
| Player re-ID coverage | >= 8 of 10 | excluded from spatial feature training set |
| Homography error | below keypoint RMS threshold | fall back to last valid M; flag game |

---

*Related: [`docs/CV_TRACKING.md`](CV_TRACKING.md) - [`docs/architecture/cv-pipeline.md`](architecture/cv-pipeline.md) - [`docs/JOB_EVIDENCE_PACKET.md`](JOB_EVIDENCE_PACKET.md) - [`docs/INDEX.md`](INDEX.md)*


---
<!-- nav-footer -->
**Navigate:** [Up: full doc map](INDEX.md) - [Home](../README.md) - [Glossary](GLOSSARY.md)
