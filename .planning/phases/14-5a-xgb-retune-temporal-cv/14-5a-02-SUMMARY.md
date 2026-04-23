---
phase: 14-5a-xgb-retune-temporal-cv
plan: "02"
subsystem: prediction
tags: [temporal-cv, player-exclusion, xgboost, prop-models]
depends_on: [14-5a-01]
provides: [prop_cv_split, temporal-train-split, player-exclusion]

dependency_graph:
  requires: [14-5a-01]
  provides: [prop_cv_split.py, make_temporal_split, filter_excluded_players, _objective_for_stat]
  affects: [player_props.train_props, Plan-03-grid-search]

tech_stack:
  added: [sklearn.model_selection.TimeSeriesSplit]
  patterns: [temporal-fold-holdout, player-id-exclusion, poisson-objective-dispatch]

key_files:
  created:
    - src/prediction/prop_cv_split.py
  modified:
    - src/prediction/player_props.py

key_decisions:
  - "make_temporal_split returns TimeSeriesSplit object only (not tuple) to match test contract from Plan 01"
  - "sort_chronologically added as separate helper to decouple sorting from tscv creation"
  - "Last fold of TimeSeriesSplit used as holdout (most recent data) — replaces fixed season boundary split"

metrics:
  duration_seconds: 1628
  tasks_completed: 2
  tasks_total: 2
  files_created: 1
  files_modified: 1
  completed_date: "2026-04-23"
---

# Phase 14-5a Plan 02: Temporal CV Wiring Summary

Temporal CV helpers created in `prop_cv_split.py` and wired into `train_props()`. TimeSeriesSplit replaces the fixed season-boundary train/test split, eliminating future data leakage from training folds. Player exclusion list now supported as first-class param.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Create prop_cv_split.py with temporal split helpers | 335abd8b | src/prediction/prop_cv_split.py |
| 2 | Wire make_temporal_split and exclusion into train_props() | 7c9eb3f9 | src/prediction/player_props.py |

## Verification

```
tests/test_prop_temporal_cv.py — 4 XPASS (temporal_split, no_leakage, rolling_features, poisson_objective)
tests/test_player_exclusion.py — 2 XPASS (excluded_players, empty_list_noop)
python -c "from src.prediction.prop_cv_split import make_temporal_split, filter_excluded_players, _objective_for_stat; print('import OK')" → OK
train_props() source contains 'make_temporal_split' and 'exclude_player_ids' → verified
```

## Artifacts

- `src/prediction/prop_cv_split.py` — 123 LOC. Exports: `make_temporal_split`, `sort_chronologically`, `assert_no_future_leakage`, `filter_excluded_players`, `_objective_for_stat`
- `src/prediction/player_props.py` — `train_props(seasons, force, exclude_player_ids)`. Uses `sort_chronologically` + `make_temporal_split` + last-fold holdout internally.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Signature mismatch] make_temporal_split returns TimeSeriesSplit only (not tuple)**
- **Found during:** Task 1 — reading the xfail tests from Plan 01
- **Issue:** Plan spec said return `(TimeSeriesSplit, pd.DataFrame)` tuple, but test stubs assigned result to `tscv` and called `tscv.n_splits` and `tscv.split()` directly — meaning the return value must be a TimeSeriesSplit, not a tuple.
- **Fix:** `make_temporal_split` returns only the `TimeSeriesSplit`. Added `sort_chronologically` as a separate helper. `train_props()` calls both in sequence.
- **Files modified:** src/prediction/prop_cv_split.py, src/prediction/player_props.py
- **Commits:** 335abd8b, 7c9eb3f9

## Self-Check: PASSED

- src/prediction/prop_cv_split.py: FOUND
- src/prediction/player_props.py: modified (contains make_temporal_split and exclude_player_ids)
- Commit 335abd8b: FOUND
- Commit 7c9eb3f9: FOUND
- All 6 plan-related tests: XPASS
