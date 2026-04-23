---
phase: 14-5a-xgb-retune-temporal-cv
plan: 01
subsystem: testing
tags: [xgboost, temporal-cv, grid-search, pytest, xfail, prop-models]

requires: []
provides:
  - "5 wave-0 test stubs defining contracts for Plans 02-05"
  - "validate_holdout_gap.py CLI exits 1 when R² gap > threshold"
  - "xfail markers for temporal split, grid search, registry, retrain, player exclusion"
affects: [14-5a-02, 14-5a-03, 14-5a-04, 14-5a-05]

tech-stack:
  added: []
  patterns:
    - "Wave-0 test stubs with xfail(strict=False) for contract-first TDD across plans"
    - "pytest.importorskip for modules not yet created (zero collection errors)"
    - "CLI validate_holdout_gap.py as plan-level acceptance gate"

key-files:
  created:
    - tests/test_prop_temporal_cv.py
    - tests/test_player_exclusion.py
    - tests/test_prop_grid_search.py
    - tests/test_model_registry.py
    - tests/test_prop_retrain.py
    - scripts/validate_holdout_gap.py
  modified: []

key-decisions:
  - "Used pytest.importorskip for pending modules so collection never raises ImportError"
  - "test_holdout_gap_under_threshold is self-contained (uses xgboost directly) to define threshold contract without Plan 03 dependency"
  - "test_needs_retrain_flag_logic is fully standalone (no registry file needed) to verify flag logic immediately"
  - "validate_holdout_gap.py defaults to data/models/model_registry.json — registry already exists with real gaps (6/7 stats fail 0.08 threshold)"

patterns-established:
  - "Wave-0 stub pattern: xfail tests define contract before implementation exists"
  - "CLI gate pattern: validate_holdout_gap.py called in plan verification to enforce gap threshold"

requirements-completed: [temporal-cv, grid-search, holdout-gap, player-exclusion, registry-update]

duration: 2min
completed: 2026-04-23
---

# Phase 14-5a Plan 01: Wave-0 Test Stubs Summary

**5 pytest xfail stub files + validate_holdout_gap.py CLI defining contracts for XGBoost temporal CV retune (Plans 02-05)**

## Performance

- **Duration:** 2 min
- **Started:** 2026-04-23T20:40:33Z
- **Completed:** 2026-04-23T20:42:47Z
- **Tasks:** 2
- **Files modified:** 6 created

## Accomplishments
- Created 14 total tests across 5 files (zero collection errors, all xfail/skip/pass as expected)
- validate_holdout_gap.py correctly exits 1 — real registry already has 6/7 stats with gaps > 0.08 (confirms the overfitting the phase targets)
- Self-contained test_needs_retrain_flag_logic passes immediately (no file dependency)
- test_holdout_gap_under_threshold passes immediately using xgboost directly on toy data

## Task Commits

1. **Task 1: temporal CV + player exclusion stubs** - `ea0edfd4` (test)
2. **Task 2: grid search, registry, retrain stubs + CLI** - `cf873d3a` (test)

**Plan metadata:** pending

## Files Created/Modified
- `tests/test_prop_temporal_cv.py` - 4 xfail tests: temporal split, no future leakage, rolling features, Poisson objective selector
- `tests/test_player_exclusion.py` - 2 xfail tests: excluded players not in train set, empty list noop
- `tests/test_prop_grid_search.py` - 3 tests: best_params dict, holdout gap <0.08 (passes now), Poisson grid tighter LR
- `tests/test_model_registry.py` - 3 tests: holdout fields present, all 7 stats, needs_retrain flag logic (passes now)
- `tests/test_prop_retrain.py` - 2 xfail tests: produces model files, updates registry
- `scripts/validate_holdout_gap.py` - CLI: exits 1 if any stat gap > threshold or registry missing

## Decisions Made
- Used `pytest.importorskip` for modules pending Plans 02-03 so collection never raises ImportError regardless of which plan runs first
- Made `test_holdout_gap_under_threshold` self-contained (xgboost directly on toy data) — this test passes now and guards against regression
- Made `test_needs_retrain_flag_logic` fully standalone — verifies flag logic immediately without waiting for registry file
- `validate_holdout_gap.py` already shows value: real registry has 6/7 stats failing 0.08 threshold (pts gap=0.131, reb=0.132, ast=0.142, fg3m=0.138, blk=0.148, tov=0.158), confirming the overfitting problem Plans 02-05 address

## Deviations from Plan

None - plan executed exactly as written. The CLI exiting 1 due to gap failures (not "registry not found") is correct behavior since the registry already exists with real data.

## Issues Encountered
- Registry file already exists at `data/models/model_registry.json` with real R² values — validate_holdout_gap.py exits 1 with gap failures rather than the "registry not found" error the plan anticipated. This is correct and more informative behavior.

## Next Phase Readiness
- All 5 test contracts defined — Plans 02-05 have clear acceptance criteria
- validate_holdout_gap.py is the CI gate: run after Plan 05 to confirm retrain closes gaps
- `test_needs_retrain_flag_logic` and `test_holdout_gap_under_threshold` already passing (2 of 14 tests green now)

---
*Phase: 14-5a-xgb-retune-temporal-cv*
*Completed: 2026-04-23*
