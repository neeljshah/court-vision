---
phase: 03-ml-models
plan: "02"
subsystem: models
tags: [sklearn, logistic-regression, gradient-boosting, joblib, synthetic-data, tdd]

# Dependency graph
requires:
  - phase: 03-ml-models
    plan: "01"
    provides: "BaseModel ABC, ARTIFACTS_DIR, load_shot_data, load_momentum_data"
provides:
  - "ShotProbabilityModel — LogisticRegression pipeline, predict() returns float [0,1]"
  - "MomentumDetector — GradientBoostingClassifier, predict() returns int 0/1"
  - "models/artifacts/shot_probability.joblib — serialized shot model"
  - "models/artifacts/momentum_detector.joblib — serialized momentum model"
affects:
  - "04-api: both models are consumed by Phase 4 prediction endpoints"

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "TDD RED/GREEN: failing tests committed before implementation"
    - "Synthetic seed data encodes domain knowledge (NBA shot rates, momentum rules)"
    - "DB-unavailable fallback in --train CLI: catches Exception, falls back to pd.DataFrame()"
    - "GradientBoostingClassifier for tree-based momentum model (no scaler needed)"
    - "LogisticRegression + StandardScaler pipeline for shot probability"

key-files:
  created:
    - "models/shot_probability.py — ShotProbabilityModel with LogisticRegression pipeline"
    - "models/momentum_detector.py — MomentumDetector with GradientBoostingClassifier"
    - "models/tests/test_shot_probability.py — 6 TDD tests for ML-01"
    - "models/tests/test_momentum_detector.py — 7 TDD tests for ML-03"
  modified: []

key-decisions:
  - "Synthetic data for ShotProbabilityModel encodes lower defender_dist → higher made rate per plan spec, achieved by splitting rows into close/far halves with different made rates"
  - "MomentumDetector synthetic data uses deterministic rule (|scoring_run|>=6 AND streak_delta>=3) with 10% label noise to prevent perfect memorization"
  - "CLI --train block catches all Exceptions from DB loaders and falls back to empty DataFrame, enabling CLI use in dev environments without PostgreSQL"

# Metrics
duration: 6min
completed: "2026-03-09"
---

# Phase 3 Plan 02: Shot Probability + Momentum Detection Summary

**Two sklearn models implementing ML-01 and ML-03: LogisticRegression shot probability and GradientBoosting momentum shift detector, both with synthetic fallbacks and joblib serialization.**

## Performance

- **Duration:** ~6 min
- **Started:** 2026-03-09T20:35:55Z
- **Completed:** 2026-03-09T20:41:37Z
- **Tasks:** 2 (+ TDD RED commits)
- **Tests added:** 13 (6 shot, 7 momentum)
- **Files created:** 4

## Accomplishments

- ShotProbabilityModel (ML-01): LogisticRegression + StandardScaler pipeline, ordinal zone encoding (paint=0, midrange=1, three=2), 50-row synthetic fallback reflecting NBA made rates, float predict() and joblib save/load
- MomentumDetector (ML-03): GradientBoostingClassifier, 100-row synthetic fallback with deterministic swing rule + 10% noise, int predict() and float predict_proba() for Phase 4 API
- Both models have --train CLI entry points that gracefully fall back to synthetic data when PostgreSQL is unavailable
- 13 TDD tests covering all plan behavior specs, all passing

## Task Commits

1. **test(03-02): add failing tests for ShotProbabilityModel (ML-01)** - `2ba19d3` (test - RED)
2. **feat(03-02): implement ShotProbabilityModel (ML-01)** - `b0cdc5e` (feat - GREEN)
3. **test(03-02): add failing tests for MomentumDetector (ML-03)** - `d6fca1c` (test - RED)
4. **feat(03-02): implement MomentumDetector (ML-03) + CLI DB fallback** - `72761ab` (feat - GREEN)

## Files Created/Modified

- `models/shot_probability.py` — ShotProbabilityModel with LogisticRegression, synthetic data, CLI
- `models/momentum_detector.py` — MomentumDetector with GradientBoostingClassifier, predict_proba, CLI
- `models/tests/test_shot_probability.py` — 6 tests: float range, zone ordering, defender distance, save/load
- `models/tests/test_momentum_detector.py` — 7 tests: 0/1 return, high-momentum=1, proba range, save/load

## Decisions Made

- Synthetic data for ShotProbabilityModel splits each zone into contested/open halves to teach the model the correct defender_dist direction per plan spec (lower dist → higher probability)
- MomentumDetector uses a deterministic rule-based label with noise rather than purely random labels — ensures the model learns a meaningful decision boundary from synthetic data
- Both --train CLIs wrap `load_*()` in try/except to prevent environment-specific DB errors from blocking training pipeline runs (falls back to synthetic data, logs warning)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Synthetic data direction for defender_dist feature**
- **Found during:** Task 1 (GREEN phase, test failure)
- **Issue:** Initial synthetic data used uniform random defender distances, causing the model to learn no meaningful correlation. Test `test_predict_closer_defender_higher_probability` failed with close=0.31 < far=0.40.
- **Fix:** Split each zone's rows into contested (low dist, lower made rate) and open (high dist, higher made rate) halves, encoding the plan-specified correlation.
- **Files modified:** `models/shot_probability.py` (`_synthetic_df()` method)
- **Commit:** `b0cdc5e`

**2. [Rule 2 - Missing error handling] CLI crashes when DB unavailable**
- **Found during:** Final verification (`python -m models.shot_probability --train`)
- **Issue:** `load_shot_data()` raises `OSError` when `DATABASE_URL` is unset. The fit() method handles empty DataFrames gracefully, but the error propagated before reaching fit().
- **Fix:** Wrapped `load_*()` call in try/except in both `__main__` blocks; prints warning and passes `pd.DataFrame()` to `fit()` which triggers synthetic fallback.
- **Files modified:** `models/shot_probability.py`, `models/momentum_detector.py`
- **Commit:** `72761ab`

## Issues Encountered

None beyond the two auto-fixed deviations above.

## User Setup Required

None — both models train on synthetic data when no DB is available.

## Next Phase Readiness

- models/shot_probability.py and models/momentum_detector.py are importable and tested
- Phase 4 API can import `ShotProbabilityModel` and `MomentumDetector`, call `load()` to get trained instances
- models/artifacts/ contains both .joblib artifacts after training runs
- Plan 03-03 (win probability + player impact) can proceed immediately

---
*Phase: 03-ml-models*
*Completed: 2026-03-09*
