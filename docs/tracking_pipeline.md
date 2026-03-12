# Tracking Pipeline

## Entry Points

```bash
# Single clip — full pipeline (tracking → enrichment → features → analytics)
python run_clip.py --video game.mp4 --game-id 0022300001 --period 1 --start 0

# Full video with debug overlay
python run.py --frames 100 --debug

# Tracking quality metrics only
python run.py --eval
```

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

1. Fetch play-by-play for the game (`nba_api.stats.endpoints.PlayByPlayV2`)
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
| `_H_MIN_INLIERS` | 8 | Minimum SIFT inliers to accept new homography |
| `_H_RESET_INLIERS` | 40 | SIFT inliers threshold for hard EMA reset |
| `_REANCHOR_INTERVAL` | 30 | Frames between court-line drift checks |
| `_REANCHOR_ALIGN_MIN` | 0.35 | Minimum white-pixel alignment before forcing reset |
| `EMA_ALPHA` | 0.35 | Homography smoothing factor |
| Kalman Q | 1e-2 | Process noise (position uncertainty) |
| Kalman R | 0.1 | Measurement noise |
