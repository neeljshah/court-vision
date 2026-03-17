---
phase: 02-feature-engineering
plan: "04"
subsystem: feature-computation
tags: [python, networkx, tdd, passing-network, momentum, feature-pipeline, dataclasses, cli, db-03]

# Dependency graph
requires:
  - phase: 02-feature-engineering/02-01
    provides: features/types.py with PassingEdge and MomentumSnapshot dataclasses
  - phase: 02-feature-engineering/02-02
    provides: features/spacing.py and features/defensive_pressure.py
  - phase: 02-feature-engineering/02-03
    provides: features/off_ball_events.py and features/pick_and_roll.py

provides:
  - features/passing_network.py with build_passing_network() and export_network_graph()
  - features/momentum.py with compute_momentum()
  - features/feature_pipeline.py CLI (python -m features.feature_pipeline --game-id UUID)
  - tests/test_passing_network.py (16 tests)
  - tests/test_momentum.py (22 tests)
  - tests/test_feature_pipeline.py (17 tests)

affects:
  - Phase 3+ ML models consuming momentum_snapshots and passing edge logs
  - Phase 5 graph analytics consuming passing network DiGraph structure

# Tech tracking
tech-stack:
  added: [networkx>=3.0 (already installed)]
  patterns:
    - Proximity-based ball holder detection: nearest player to ball position each frame
    - Edge aggregation via dict keyed by (from_id, to_id) — no duplicate edges emitted
    - Segment-based momentum: possession_num // segment_size groups shot events
    - TDD RED-GREEN cycle: failing tests committed before implementation
    - Pipeline CLI: argparse entrypoint, steps 0a-7 each print summary line
    - DB-03 detection: heuristic thresholds from ball speed (possession) and proximity to basket (shot)

key-files:
  created:
    - features/passing_network.py
    - features/momentum.py
    - features/feature_pipeline.py
    - tests/test_passing_network.py
    - tests/test_momentum.py
    - tests/test_feature_pipeline.py
  modified: []

key-decisions:
  - "Ball holder = nearest player to ball position each frame; None ball frames leave holder unchanged"
  - "Pass detected only on holder change — same-holder consecutive frames are not passes"
  - "scoring_run = length of final consecutive made-shot streak at end of segment (not max run)"
  - "swing_point compares segment-local scores (not cumulative) — segment where leader changed"
  - "Possession boundary heuristic: speed < 20 px/s for 3+ consecutive frames = ball held/reset"
  - "Shot detection: speed > 400 px/s AND |y - 240| < 60 AND (x < 100 OR x > 820)"
  - "Passing network edges logged to stdout as JSON lines in Phase 2 — no DB table yet (Phase 5 will consume)"
  - "Momentum step uses shot index as possession_num since team data unavailable in Phase 2"

patterns-established:
  - "Step isolation in pipeline: each step is a private _run_*_step() function returning a count, enabling unit testing"
  - "ON CONFLICT DO NOTHING on all INSERT statements for idempotent re-runs"
  - "Pipeline prints [Step N] summary line after each step for operational observability"

requirements-completed: [FE-05, FE-06, DB-03]

# Metrics
duration: 8min
completed: 2026-03-09
---

# Phase 02 Plan 04: Passing Networks, Momentum, and Feature Pipeline CLI Summary

**Proximity-based passing network builder (networkx DiGraph), segment-level momentum snapshots with swing detection, and full Phase 2 integration CLI that detects possession boundaries and shot events (DB-03) then runs all feature modules — 132 Phase 2 tests passing**

## Performance

- **Duration:** ~8 min
- **Started:** 2026-03-09T19:30:00Z
- **Completed:** 2026-03-09T19:38:00Z
- **Tasks:** 2 (Task 1 TDD RED+GREEN, Task 2 implementation + tests)
- **Files created:** 6
- **Files modified:** 0

## Accomplishments

- Created `features/passing_network.py` with `build_passing_network()` and `export_network_graph()`:
  - Ball holder each frame = nearest player to ball position (Euclidean distance)
  - Holder transitions increment edge counters; aggregated into PassingEdge list with no duplicates
  - `export_network_graph()` wraps edges into `networkx.DiGraph` with `weight=count` on each edge
  - None ball frames leave holder unchanged — handles tracking gaps without spurious edges

- Created `features/momentum.py` with `compute_momentum()`:
  - Groups shot events by `possession_num // segment_size_possessions`
  - `scoring_run`: length of final consecutive made-shot streak at end of segment
  - `possession_streak`: longest consecutive sequence of possessions won by same team
  - `swing_point`: True if leading team (by segment scores) changed from previous segment
  - Returns list sorted by segment_id ascending; returns [] for empty input

- Created `features/feature_pipeline.py` — integration CLI for all Phase 2 features:
  - Step 0a: detects possession boundaries (speed < 20 px/s for 3+ frames) and INSERTs into possessions (DB-03 complete)
  - Step 0b: detects shot events (speed > 400, y within 60 of basket_y=240, near basket x) and INSERTs into shot_logs (DB-03 complete)
  - Steps 2-5: spacing, defensive pressure, off-ball events, pick-and-roll with every-5th-frame sampling and 10-frame sliding windows
  - Step 6: passing network per possession logged as JSON lines to stdout
  - Step 7: momentum snapshots INSERTed into momentum_snapshots table
  - CLI: `python -m features.feature_pipeline --game-id <UUID>` with argparse

- 16 passing network tests, 22 momentum tests, 17 pipeline tests — 132 total Phase 2 tests passing

## Task Commits

Each task was committed atomically:

1. **Task 1 (TDD RED): Failing tests for passing network and momentum** — `ba9e11f` (test)
2. **Task 1 (TDD GREEN): Implement passing_network.py and momentum.py** — `f930c5b` (feat)
3. **Task 2: Feature pipeline CLI with possession/shot detection** — `e2e590c` (feat)

## Files Created/Modified

- `features/passing_network.py` — `build_passing_network()` via proximity holder detection, `export_network_graph()` via networkx
- `features/momentum.py` — `compute_momentum()` with segment grouping, scoring run, possession streak, swing point
- `features/feature_pipeline.py` — Integration CLI: steps 0a-7, argparse, all Phase 2 feature modules imported
- `tests/test_passing_network.py` — 16 tests: basic pass detection, aggregation, None ball handling, DiGraph export
- `tests/test_momentum.py` — 22 tests: return types, segment counting, scoring run, possession streak, swing point, timestamp
- `tests/test_feature_pipeline.py` — 17 tests: import, argparse, step 0a/0b logic, module mocking, INSERT source checks

## Decisions Made

- Ball holder detection uses nearest-player-to-ball heuristic — simple and sufficient for Phase 2; more sophisticated methods deferred to Phase 3
- `scoring_run` tracks the final consecutive run at segment end (not the max run) — captures momentum state at segment close, not just peak
- Swing point uses segment-local scores (not cumulative total) — detects momentum shifts within segments, not just overall game lead changes
- Possession boundary heuristic: speed < 20 px/s for 3+ consecutive frames; this produces `O(boundaries)` possessions without requiring court-side detection
- Passing network edges not written to DB in Phase 2 — logged as JSON lines to stdout; Phase 5 graph analytics will consume from a dedicated table
- Momentum step uses shot log order as possession_num proxy since team assignment is not available in Phase 2

## Deviations from Plan

None — plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None — no external service configuration required. Pipeline requires a live database with tracking_coordinates loaded; that is expected operational context, not new setup.

## Next Phase Readiness

- All Phase 2 feature modules (types, spacing, defensive pressure, off-ball events, pick-and-roll, passing network, momentum) are complete and tested
- Feature pipeline CLI is the integration point for Phase 3 model training data generation
- DB-03 is complete: possession boundaries and shot events are detected and persisted from tracking_coordinates
- 132 Phase 2 tests provide regression coverage across all modules

---
*Phase: 02-feature-engineering*
*Completed: 2026-03-09*

## Self-Check: PASSED

- `features/passing_network.py` — FOUND
- `features/momentum.py` — FOUND
- `features/feature_pipeline.py` — FOUND
- `tests/test_passing_network.py` — FOUND
- `tests/test_momentum.py` — FOUND
- `tests/test_feature_pipeline.py` — FOUND
- Commit `ba9e11f` (RED tests) — FOUND
- Commit `f930c5b` (GREEN passing_network + momentum) — FOUND
- Commit `e2e590c` (pipeline CLI) — FOUND
- 132 Phase 2 tests pass: CONFIRMED
