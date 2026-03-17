# System Architecture

*Last updated: 2026-03-12*

> All code lives in `C:\Users\neelj\nba-ai-system\`. The old `BasketTracking\` folder is obsolete — do not use it.

---

## Full Pipeline

```
NBA Broadcast Video (.mp4)
    ↓
Court Rectification  [src/tracking/rectify_court.py]
    → SIFT panorama → homography M → resources/Rectify1.npy
    → Drift-corrected every 30 frames via court-line pixel alignment
    ↓
AdvancedFeetDetector  [src/tracking/advanced_tracker.py]
    → YOLOv8n person detection (classes=[0], conf=0.5)
    → Adaptive HSV team classification
    → Kalman filter per player (6D state)
    → Hungarian assignment (cost = IoU×0.75 + appearance×0.25)
    → HSV appearance gallery (MAX_LOST=90, TTL=300 frames)
    ↓
BallDetectTrack  [src/tracking/ball_detect_track.py]
    → Hough → CSRT → Lucas-Kanade optical flow fallback
    → Possession = argmax IoU(ball, player bboxes)
    ↓
EventDetector  [src/tracking/event_detector.py]
    → shot / pass / dribble / none per frame (stateful)
    ↓
UnifiedPipeline  [src/pipeline/unified_pipeline.py]
    → Spatial metrics per frame (spacing, paint count, isolation)
    → Possession segmentation
    → Outputs: tracking_data.csv, possessions.csv, shot_log.csv, player_clip_stats.csv
    ↓
NBA API Enrichment  [src/data/nba_enricher.py]
    → shot_log + play-by-play → made/missed labels
    → possessions + play-by-play → result + score_diff
    → Outputs: shot_log_enriched.csv, possessions_enriched.csv
    ↓
Feature Engineering  [src/features/feature_engineering.py]
    → 60+ ML-ready features per frame
    → Output: features.csv
    ↓
Analytics  [src/analytics/]
    → shot_quality.py  → shot quality score 0–1
    → momentum.py      → momentum per team per frame
    → defense_pressure.py → pressure per frame
    ↓
ML Models  [src/prediction/]    ← Phase 3
PostgreSQL                      ← Phase 1
FastAPI + Frontend + AI Chat    ← Phases 7–9
```

---

## Module Owners

| Module | Primary File |
|---|---|
| Player detection | `src/tracking/player_detection.py` |
| Player tracking + ReID | `src/tracking/advanced_tracker.py` |
| Ball tracking | `src/tracking/ball_detect_track.py` |
| Court mapping | `src/tracking/rectify_court.py` |
| Event detection | `src/tracking/event_detector.py` |
| Full pipeline | `src/pipeline/unified_pipeline.py` |
| NBA API enrichment | `src/data/nba_enricher.py` |
| Feature engineering | `src/features/feature_engineering.py` |
| Shot quality | `src/analytics/shot_quality.py` |
| Momentum | `src/analytics/momentum.py` |
| Defensive pressure | `src/analytics/defense_pressure.py` |
| Win probability | `src/prediction/win_probability.py` (Phase 3) |
| Deep ReID model | `src/re_id/` |

---

## Key Resources

| File | Description |
|---|---|
| `resources/2d_map.png` | 2D court reference image |
| `resources/Rectify1.npy` | Precomputed homography (generated on first run) |
| `data/tracking_data.csv` | Per-frame tracking output |
| `data/shot_log_enriched.csv` | Shots with made/missed labels |
| `data/possessions_enriched.csv` | Possessions with outcomes |
| `data/features.csv` | 60+ ML features |
| `data/nba/` | Cached NBA API responses |

---

## Related Notes

- [[CLAUDE.md]] — always read first
- [[Project Vision]] — full product vision
- [[Roadmap]] — 11-phase build plan
- [[Tracker Improvements Log]] — all issues and fixes
