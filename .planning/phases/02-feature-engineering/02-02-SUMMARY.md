---
phase: 02-feature-engineering
plan: "02"
subsystem: feature-computation
tags: [python, scipy, dataclasses, tdd, spatial-features, feature-engineering]

# Dependency graph
requires:
  - phase: 02-feature-engineering/02-01
    provides: features/types.py with SpacingMetrics and DefensivePressure dataclasses

provides:
  - features/spacing.py with compute_spacing() returning SpacingMetrics
  - features/defensive_pressure.py with compute_defensive_pressure() returning list[DefensivePressure]
  - tests/test_spacing.py (9 tests)
  - tests/test_defensive_pressure.py (11 tests)

affects:
  - 02-feature-engineering/02-03 (off-ball detection uses same pattern)
  - 02-feature-engineering/02-04 (passing/momentum modules)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - Pure computation modules — no DB imports, no numpy; stdlib math + scipy only
    - TDD RED-GREEN-REFACTOR cycle for spatial feature modules
    - scipy ConvexHull.volume used as 2D area (QhullError caught for collinear/degenerate cases)
    - itertools.combinations for O(n^2) pairwise distances
    - prev_distances dict mutated in place to track frame-over-frame closing speed

key-files:
  created:
    - features/spacing.py
    - features/defensive_pressure.py
    - tests/test_spacing.py
    - tests/test_defensive_pressure.py
  modified: []

key-decisions:
  - "scipy ConvexHull.volume is the correct 2D area (not .area, which is perimeter in 2D) — avoids silent wrong-value bug"
  - "QhullError imported from scipy.spatial (not deprecated scipy.spatial.qhull) — future-proof for scipy 2.0"
  - "closing_speed = current - prev using prev_distances.get(tid, current) would give 0 algebraically; explicit None check is clearer"
  - "team=None fallback treats all players as both targets and defenders — handles untagged tracking data without crashing"

# Metrics
duration: 2min
completed: 2026-03-09
---

# Phase 02 Plan 02: Player Spacing and Defensive Pressure Metrics Summary

**Pure scipy + stdlib spatial feature modules computing convex hull area, average pairwise distance, nearest defender distance, and closing speed — 20 tests covering all geometric and degenerate cases via full TDD cycle**

## Performance

- **Duration:** ~2 min
- **Started:** 2026-03-09T19:21:19Z
- **Completed:** 2026-03-09T19:23:31Z
- **Tasks:** 2 (TDD RED + GREEN/REFACTOR)
- **Files created:** 4
- **Files modified:** 0

## Accomplishments

- Created `features/spacing.py` with `compute_spacing()`:
  - Uses `scipy.spatial.ConvexHull.volume` for 2D hull area (catches `QhullError` for collinear/degenerate inputs)
  - Uses `itertools.combinations` + `math.hypot` for average pairwise distance
  - Returns `SpacingMetrics` dataclass; all degenerate cases (0/1/2 players, collinear) handled cleanly

- Created `features/defensive_pressure.py` with `compute_defensive_pressure()`:
  - Splits players by `team` field (`offense` = target, `defense` = defender); `team=None` treats all others as defenders
  - `closing_speed = current_dist - prev_distances.get(tid)` — first frame yields `0.0`
  - Mutates `prev_distances` dict in place for stateful frame-over-frame computation
  - Returns one `DefensivePressure` per offensive player (or all players when team is unset)

- 9 tests for spacing (4 squares/multi-player + 4 degenerate + 1 metadata/type check)
- 11 tests for defensive pressure (distance, closing/opening speed, first-frame, empty inputs, mutation, team=None fallback, metadata)
- All 20 tests pass with 0 warnings

## Task Commits

Each task committed atomically:

1. **Task 1 (TDD RED): Failing tests for spacing and defensive pressure** — `93d5e3e`
2. **Task 2 (TDD GREEN + REFACTOR): Implement both modules, fix QhullError import** — `5e1e311`

## Files Created/Modified

- `features/spacing.py` — `compute_spacing()` using scipy ConvexHull + itertools pairwise distances
- `features/defensive_pressure.py` — `compute_defensive_pressure()` using math.hypot; stateful via prev_distances
- `tests/test_spacing.py` — 9 tests: geometric fixtures and all degenerate edge cases
- `tests/test_defensive_pressure.py` — 11 tests: distance, speed, mutation, team=None, metadata

## Decisions Made

- `ConvexHull.volume` is the 2D area in scipy (not `.area`, which returns perimeter) — used per plan spec; prevents silent wrong-value bug
- `QhullError` imported from `scipy.spatial` directly (deprecated `scipy.spatial.qhull` path removed during refactor) — forward-compatible with scipy 2.0
- `closing_speed` uses explicit `None` check on `prev_distances.get(tid)` rather than algebraic `get(tid, current)` — semantically clearer
- `team=None` fallback computes pressure of every player against all others — enables use with untagged tracking coordinate rows

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed deprecated QhullError import path**
- **Found during:** Task 2 (GREEN) via pytest deprecation warning
- **Issue:** `from scipy.spatial.qhull import QhullError` triggers `DeprecationWarning: removed in scipy 2.0`
- **Fix:** Changed to `from scipy.spatial import ConvexHull, QhullError`
- **Files modified:** `features/spacing.py`
- **Commit:** `5e1e311`

## Issues Encountered

None beyond the deprecation fix above.

## User Setup Required

None — scipy is already in requirements.txt from Plan 02-01.

## Next Phase Readiness

- `features/spacing.py` and `features/defensive_pressure.py` are ready for import by downstream modules
- Both modules are pure functions with no DB/network dependencies — safe to use in any context
- Established pattern: pure math module + known-geometry fixture tests can be reused for 02-03 (off-ball detection) and 02-04 (passing/momentum)

---

*Phase: 02-feature-engineering*
*Completed: 2026-03-09*

## Self-Check: PASSED

- `features/spacing.py` — FOUND
- `features/defensive_pressure.py` — FOUND
- `tests/test_spacing.py` — FOUND
- `tests/test_defensive_pressure.py` — FOUND
- Commit `93d5e3e` (RED tests) — FOUND
- Commit `5e1e311` (GREEN implementation) — FOUND
- All 20 tests pass: CONFIRMED
