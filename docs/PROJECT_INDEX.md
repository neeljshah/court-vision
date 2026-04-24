# Project Index

This is the canonical navigation map for the public showcase repository.

## Core Application

- `src/tracking`: CV detection, tracking, homography, OCR, re-ID
- `src/features`: feature engineering and derived basketball features
- `src/prediction`: model training and inference logic
- `src/pipeline`: orchestration, model registry, retraining/drift helpers
- `src/data` and `src/ingest`: data connectors and enrichment
- `src/analytics`: basketball and betting analytics signals
- `src/simulation`: simulation engines and scenario logic

## API Surface

- `api/main.py`: FastAPI app bootstrap and router wiring
- `api/models_router.py`: model-backed prediction endpoints
- `api/predictions_router.py`: extended prediction endpoints
- `api/analytics_router.py`: analytics endpoints
- `api/dashboard_router.py`: dashboard/chat support routes
- `api/stitch_router.py`: stitch-facing and realtime routes

## Operations and Tooling

- `scripts/`: operational scripts (batch runs, validation, retraining, setup)
- `database/`: schema and migration assets
- `docs/`: architecture, data, model, and execution documentation
- `tests/`: automated unit/integration validation

## Public-Facing Source of Truth

- Product overview and future direction: `README.md`
- Gap analysis and execution roadmap: `PLAN.md`
- Contributor workflow and quality standards: `CONTRIBUTING.md`

## Notes on Legacy and Internal Paths

- Some directories are intentionally excluded from public workflow and git hygiene (`vault`, `.planning`, archived/legacy folders).
- Root scratch notes were consolidated into `docs/operations/runpod_video_sync_notes.md`.
