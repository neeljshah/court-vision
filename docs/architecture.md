# System Architecture

## Full Pipeline

```
NBA Broadcast Video (.mp4)
    ↓
Court Rectification
    → SIFT panorama stitching → homography M saved to resources/Rectify1.npy
    → drift-corrected every 30 frames via court-line white-pixel alignment check
    ↓
AdvancedFeetDetector  [src/tracking/advanced_tracker.py]
    → YOLOv8n → person bboxes (classes=[0], conf=0.5)
    → HSV adaptive color classification → team_id (0=team A, 1=team B, 2=referee)
    → Kalman filter per player: 6D state [cx, cy, vx, vy, w, h]
    → Hungarian assignment: cost = (1-IoU)×0.75 + appearance_dist×0.25
    → Lost-track gallery: 96-dim HSV histogram, EMA updated, TTL=300 frames
    ↓
BallDetectTrack  [src/tracking/ball_detect_track.py]
    → Hough circles → CSRT tracker → Lucas-Kanade optical flow fallback
    → Possession = max IoU of ball bbox with player bboxes
    ↓
EventDetector  [src/tracking/event_detector.py]
    → Stateful: shot / pass / dribble / none per frame
    → Pass fires retroactively on passer's frame when receiver picks up
    ↓
UnifiedPipeline  [src/pipeline/unified_pipeline.py]
    → Spatial metrics per frame: team_spacing (convex hull), paint_count, isolation
    → Possessions segmented by ball possession changes
    → Outputs: tracking_data.csv, possessions.csv, shot_log.csv, player_clip_stats.csv
    ↓
NBA API Enrichment  [src/data/nba_enricher.py]
    → Joins shot_log → made/missed from play-by-play
    → Joins possessions → result + score_diff
    → Outputs: shot_log_enriched.csv, possessions_enriched.csv
    ↓
Feature Engineering  [src/features/feature_engineering.py]
    → Rolling window features (30/90/150 frame velocity, distance, possession%)
    → Event rate features (shots/passes/dribbles per 90 frames)
    → Momentum proxy, spacing advantage
    → Output: features.csv (60+ ML-ready columns)
    ↓
Analytics  [src/analytics/]
    → shot_quality.py  → shot quality score 0–1 per shot
    → momentum.py      → per-frame momentum score per team (EMA 30f)
    → defense_pressure.py → per-frame defensive pressure score (EMA 20f)
    ↓
ML Models  [src/prediction/]  ← IN PROGRESS
PostgreSQL Database            ← PLANNED (Phase 1)
FastAPI Backend                ← PLANNED (Phase 7)
React Frontend                 ← PLANNED (Phase 8)
```

---

## Module Map

| Module | Location | Purpose |
|---|---|---|
| `AdvancedFeetDetector` | `src/tracking/advanced_tracker.py` | Primary player tracker — Kalman + Hungarian + ReID |
| `FeetDetector` | `src/tracking/player_detection.py` | Baseline detector (deprecated, use Advanced) |
| `BallDetectTrack` | `src/tracking/ball_detect_track.py` | Ball tracking — Hough + CSRT + optical flow |
| `rectify_court` | `src/tracking/rectify_court.py` | SIFT homography, court panorama |
| `VideoHandler` | `src/tracking/video_handler.py` | Frame loop, CSV export |
| `EventDetector` | `src/tracking/event_detector.py` | Shot/pass/dribble event detection |
| `UnifiedPipeline` | `src/pipeline/unified_pipeline.py` | Full tracking → possession → CSV pipeline |
| `NBAEnricher` | `src/data/nba_enricher.py` | NBA API enrichment (shot outcomes, possession results) |
| `NBAStats` | `src/data/nba_stats.py` | NBA Stats API — team info, shot charts, game IDs |
| `VideoFetcher` | `src/data/video_fetcher.py` | yt-dlp downloader + auto court calibration |
| `FeatureEngineering` | `src/features/feature_engineering.py` | 60+ ML features from tracking data |
| `ShotQuality` | `src/analytics/shot_quality.py` | Shot quality score (zone, defender, spacing, clock) |
| `Momentum` | `src/analytics/momentum.py` | Team momentum per frame |
| `DefensePressure` | `src/analytics/defense_pressure.py` | Defensive pressure per frame |
| `ReID model` | `src/re_id/` | CBAM-based deep re-ID (alternative to HSV gallery) |

---

## Key Data Files

| File | Contents |
|---|---|
| `resources/Rectify1.npy` | Precomputed homography — generated on first run, reused thereafter |
| `resources/2d_map.png` | 2D court reference image |
| `data/tracking_data.csv` | Per-frame: player_id, team_id, x, y, speed, event, spacing, possession |
| `data/possessions.csv` | Per-possession: type, duration, spacing, pressure, outcome |
| `data/shot_log.csv` | Per-shot: player, location, zone, defender distance, made/missed |
| `data/features.csv` | 60+ ML-ready engineered features |
| `data/nba/` | Cached NBA API responses |

---

## Homography Architecture

Three-tier management to prevent drift:

| Tier | Condition | Action |
|---|---|---|
| Reject | SIFT inliers < 8 | Fall back to last accepted M |
| Blend | SIFT inliers 8–39 | EMA blend: `M = α×M_new + (1-α)×M_prev`, α=0.35 |
| Hard reset | SIFT inliers ≥ 40 | Discard EMA, use fresh M immediately |

Every 30 frames: `_check_court_drift()` projects 4 court boundary lines through `inv(M_ema)·inv(M1)` into frame space, checks white-pixel alignment. If alignment < 0.35 → force hard reset.
