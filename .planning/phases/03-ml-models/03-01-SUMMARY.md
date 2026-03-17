---
phase: 03-ml-models
plan: "01"
subsystem: models
tags: [sklearn, joblib, pandas, psycopg2, abstract-base-class, training-data]

# Dependency graph
requires:
  - phase: 02-feature-engineering
    provides: "shot_logs, feature_vectors, possessions, momentum_snapshots, detected_events DB tables"
  - phase: 01-cv-pipeline-storage
    provides: "tracking_coordinates DB table, get_connection() factory"
provides:
  - "Abstract BaseModel ABC with fit(), predict(), save(), load() interface"
  - "models/artifacts/ git-tracked directory for serialized model artifacts"
  - "Training data loaders for all 5 Phase 3 models: load_shot_data, load_possession_data, load_momentum_data, load_player_event_data, load_lineup_data"
affects:
  - "03-02-shot-probability"
  - "03-03-win-probability"
  - "03-04-momentum-detection"
  - "04-api"

# Tech tracking
tech-stack:
  added:
    - "scikit-learn>=1.4 (sklearn estimator wrapper target)"
    - "joblib>=1.3 (model serialization)"
    - "pandas>=2.1 (DataFrame-based training data contract)"
  patterns:
    - "Abstract BaseModel ABC — all models implement fit(df) and predict(features_dict)"
    - "Joblib artifact persistence — models/artifacts/{model_name}.joblib"
    - "Loader functions scope by optional game_id — None = full training set"
    - "Empty DataFrame with correct columns returned on no rows (graceful)"

key-files:
  created:
    - "models/base.py — AbstractBaseModel with fit/predict/save/load"
    - "models/training_data.py — 5 training data loader functions"
    - "models/artifacts/.gitkeep — git-tracks artifact directory"
  modified:
    - "requirements.txt — added scikit-learn, joblib, pandas"

key-decisions:
  - "BaseModel uses ABC abstractmethod enforcement — compile-time guarantee subclasses implement fit/predict"
  - "ARTIFACTS_DIR resolved relative to base.py via pathlib.Path(__file__).parent — portable across environments"
  - "load_possession_data uses frame_number // 150 to match 5-second momentum segments (30 fps)"
  - "load_momentum_data computes lag features (scoring_run_prev, streak_delta) via pandas groupby/shift — no DB-side window functions needed"
  - "load_lineup_data aggregates track_id sets per frame then deduplicates to unique lineup keys — roster-frame join for lineup scoring model"
  - "won=0 placeholder in load_possession_data — real win labels require play-by-play data, deferred to v2"

patterns-established:
  - "Pattern: All loaders close their own connection — no leaked connections, connection-per-call pattern"
  - "Pattern: SQL game_id filter appended as WHERE clause with %(game_id)s param — injection-safe"
  - "Pattern: Derived columns computed in Python after SQL query — keeps SQL simple, logic testable"

requirements-completed: []

# Metrics
duration: 12min
completed: "2026-03-09"
---

# Phase 3 Plan 01: ML Model Infrastructure Summary

**Abstract BaseModel ABC + 5 DB-backed training data loaders using pandas/psycopg2, establishing the shared contract all Phase 3 models build against.**

## Performance

- **Duration:** ~12 min
- **Started:** 2026-03-09T19:48:07Z
- **Completed:** 2026-03-09T19:60:00Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments

- Abstract BaseModel with fit(), predict(), save(), load() — enforces contract via ABC, serializes to joblib artifacts
- models/artifacts/ directory git-tracked via .gitkeep, ready to receive trained model files
- Five loader functions covering every model type in Phase 3: shot probability, possession/win, momentum, player impact, lineup optimization
- All loaders scope by optional game_id, gracefully return empty DataFrame on no rows, close connections in finally blocks

## Task Commits

1. **Task 1: Model infrastructure — base class, artifacts dir, requirements** - `ca8c475` (feat)
2. **Task 2: Training data loaders for all five models** - `1954ab9` (feat)

## Files Created/Modified

- `models/base.py` - Abstract BaseModel ABC with fit/predict/save/load and ARTIFACTS_DIR constant
- `models/training_data.py` - Five loader functions backed by PostgreSQL via psycopg2 + pandas read_sql
- `models/artifacts/.gitkeep` - Tracks artifact output directory in git
- `requirements.txt` - Added scikit-learn>=1.4, joblib>=1.3, pandas>=2.1

## Decisions Made

- BaseModel uses ABC + abstractmethod so Python raises TypeError at instantiation if subclass forgets to implement fit/predict — catches contract violations early
- ARTIFACTS_DIR resolves via pathlib relative to base.py so the path is correct regardless of where the process runs from
- Momentum loader computes lag features with pandas groupby/shift rather than SQL window functions — keeps the DB query simple and the lag logic easily unit-testable
- load_possession_data carries `won=0` placeholder; comment documents that real win labels require play-by-play data (deferred to v2) so no downstream model silently trains on wrong labels

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- models/base.py and models/training_data.py are the shared foundation — Plans 02, 03, and 04 can now import BaseModel and the appropriate loader function
- All imports verified clean on the local Python environment
- models/artifacts/ is git-tracked and ready to hold serialized .joblib files after training runs

---
*Phase: 03-ml-models*
*Completed: 2026-03-09*
