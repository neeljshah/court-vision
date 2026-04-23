---
phase: 14-5a-xgb-retune-temporal-cv
plan: "03"
subsystem: prediction
tags: [xgboost, gridsearchcv, timeseriessplit, temporal-cv, prop-models, hyperparameter-tuning]

requires:
  - phase: 14-5a-01
    provides: test stubs for grid search, holdout gap, Poisson grid tighter
  - phase: 14-5a-02
    provides: prop_cv_split.py — make_temporal_split, sort_chronologically, filter_excluded_players, _objective_for_stat

provides:
  - GridSearchCV orchestrator (run_grid_search) with REGRESSION/POISSON param grids
  - CLI retrain script (retrain_props_temporal.py) with --stats/--dry-run/--threshold/--seasons/--exclude flags
  - Best hyperparams persisted to data/models/hyperparams_{stat}.json after each stat

affects: [14-5a-04, model-registry, prop-backtesting]

tech-stack:
  added: []
  patterns:
    - "GridSearchCV n_jobs=4, XGBRegressor n_jobs=1 — GridSearchCV owns parallelism to avoid oversubscription"
    - "Poisson stats (stl, blk) get tighter LR grid (max 0.05 vs 0.10) per research constraint"
    - "sort_chronologically called before make_temporal_split (split returns TimeSeriesSplit only, not tuple)"

key-files:
  created:
    - src/prediction/prop_grid_search.py
    - scripts/retrain_props_temporal.py
  modified: []

key-decisions:
  - "GridSearchCV refit=True so best_estimator_ is refitted on full X,y — returned directly to caller"
  - "Holdout uses last TimeSeriesSplit fold's test indices (splits[-1]) — most conservative out-of-time eval"
  - "sort_chronologically separate from make_temporal_split (Plan 02 decision: split returns only TimeSeriesSplit)"

patterns-established:
  - "Param grid dispatch: _COUNT_STATS frozenset drives POISSON vs REGRESSION grid selection"
  - "Hyperparams persisted to data/models/hyperparams_{stat}.json after each stat completes"

requirements-completed: [grid-search, holdout-gap]

duration: 12min
completed: 2026-04-23
---

# Phase 14-5a Plan 03: GridSearchCV Orchestrator + CLI Retrain Script Summary

**Per-stat GridSearchCV over TimeSeriesSplit folds: REGRESSION (3×4×3×3×3=324 combos) and POISSON (3×3×3×2×2=108 combos) grids, best params persisted to data/models/hyperparams_{stat}.json, CLI retrain script with --dry-run/--threshold gates**

## Performance

- **Duration:** 12 min
- **Started:** 2026-04-23T08:13:36Z
- **Completed:** 2026-04-23T08:25:22Z
- **Tasks:** 2
- **Files created:** 2

## Accomplishments
- `prop_grid_search.py` — run_grid_search() orchestrates GridSearchCV with REGRESSION/POISSON param grids; best estimator returned after JSON persist
- `retrain_props_temporal.py` — full CLI (--stats, --dry-run, --threshold, --seasons, --exclude); calls sort_chronologically + make_temporal_split + run_grid_search per stat; holdout gap warning at configurable threshold
- All 5 tests across test_prop_grid_search.py and test_prop_retrain.py XPASS (3 + 2)

## Task Commits

1. **Task 1: Create prop_grid_search.py** - `7bac495f` (feat)
2. **Task 2: Create scripts/retrain_props_temporal.py CLI** - `16d67500` (feat)

**Plan metadata:** (final commit below)

## Files Created/Modified
- `src/prediction/prop_grid_search.py` — GridSearchCV orchestrator; REGRESSION_PARAM_GRID, POISSON_PARAM_GRID constants; run_grid_search() → XGBRegressor; hyperparams_{stat}.json persist
- `scripts/retrain_props_temporal.py` — CLI entry point; loads seasons, sorts chronologically, grid-searches per stat, reports holdout metrics with gap threshold check

## Decisions Made
- `sort_chronologically` called explicitly before `make_temporal_split` because Plan 02 decided the split function returns only `TimeSeriesSplit` (not a tuple) to match Plan 01 test contract
- `GridSearchCV(refit=True)` — best estimator refitted on full training set before return; avoids second manual fit call
- Holdout defined as `splits[-1][1]` (last fold test set) — most out-of-time evaluation against most recent season data

## Deviations from Plan

**1. [Rule 1 - Bug] Corrected make_temporal_split call signature in retrain script**
- **Found during:** Task 2 implementation
- **Issue:** Plan 03's sample code called `make_temporal_split(df, date_col, n_splits=5)` and unpacked `tscv, df_sorted` — but Plan 02 made `make_temporal_split` return only `TimeSeriesSplit` (df sort is done by `sort_chronologically`)
- **Fix:** Called `sort_chronologically(df, date_col="game_date")` first to get `df_sorted`, then `make_temporal_split(df_sorted, ...)` for `tscv`
- **Files modified:** `scripts/retrain_props_temporal.py`
- **Verification:** Both test_prop_retrain.py tests XPASS (9-min run); --help works
- **Committed in:** 16d67500 (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (Rule 1 — bug in plan's sample code vs Plan 02 actual API)
**Impact on plan:** Fix required for correctness; no scope creep.

## Issues Encountered
- PerformanceWarning from Pandas when filling 100+ missing feature columns via loop (`frame.insert` fragmentation) — cosmetic warning, does not affect correctness. Out-of-scope for this plan.

## User Setup Required
None — no external service configuration required.

## Next Phase Readiness
- `run_grid_search` and `retrain_props_temporal_cv` ready for Plan 04 (model registry formalization)
- `data/models/hyperparams_{stat}.json` will be populated on first live run
- `--dry-run` flag enables safe end-to-end testing without writing model files

---
*Phase: 14-5a-xgb-retune-temporal-cv*
*Completed: 2026-04-23*
