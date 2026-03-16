# Project State: NBA AI System

## Current Status

**Active Phase**: Phase 2 — Tracking Improvements
**Current Plan**: 02-03 complete → next: 02-04
**Last Updated**: 2026-03-16
**Milestone**: MVP tracking pipeline with named players

## Completed Work

### Phase 1 — Data Infrastructure ✅ (2026-03-12)
- PostgreSQL schema (9 tables, 2 views): `database/schema.sql`
- `src/data/schedule_context.py` — rest days, back-to-back, travel distance
- `src/data/lineup_data.py` — 5-man lineup splits, on/off, game rotation
- `src/data/nba_stats.py` — opponent features: `fetch_matchup_features(home, away, season)`

### Tracking Core ✅
- YOLOv8n + Kalman + Hungarian + HSV re-ID (AdvancedFeetDetector)
- Ball tracking: Hough circles + CSRT + optical flow
- Court rectification: SIFT homography + EMA drift correction
- Event detection: shot/pass/dribble via stateful EventDetector
- 60+ ML-ready features per frame
- NBA API enrichment (shot labels, possession outcomes)

## Key Decisions

- **Detector**: YOLOv8n (migrated from Detectron2 on 2026-03-12) — faster, no install issues
- **Tracker**: AdvancedFeetDetector (Kalman + Hungarian) — globally optimal assignment
- **Court rectification**: SIFT panorama + three-tier homography with EMA drift correction
- **Re-ID**: 96-dim HSV histogram (EMA), gallery TTL=300 frames
- **Database**: PostgreSQL for all persistent outputs
- **02-03 Referee filtering**: NaN sentinel (not row removal) for referee spatial columns; string label "referee" not team_id==2; compute_spatial_features() is a post-load guard not a recompute

## Dataset Status

- 16 games fully processed (first complete pass 2026-03-15)
- 29,220 tracking rows total
- 124 possessions labeled
- 0 shots enriched (need --game-id for enrichment)
- Player IDs are anonymous — no jersey OCR yet

## Open Issues

- ISSUE-005: HSV re-ID on similar-colored uniforms (🟡 In Progress)
- ISSUE-006: Anonymous player IDs — no jersey OCR (Phase 2)
- ISSUE-007: Referees included in analytics calculations — ✅ fixed in 02-03 (feature_engineering + shot_quality)
- ISSUE-008: No shot clock from video (Phase 2)

## Technology Stack

- Python 3.9, PyTorch 2.0.1 + CUDA 11.8
- YOLOv8n (ultralytics), OpenCV, NumPy, Pandas
- nba_api, XGBoost, scipy
- PostgreSQL (schema ready, needs connection wiring)
- Conda env: basketball_ai
