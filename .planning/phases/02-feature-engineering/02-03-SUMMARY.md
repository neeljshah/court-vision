---
phase: 02-feature-engineering
plan: "03"
subsystem: feature-engineering
tags: [python, tdd, off-ball-detection, pick-and-roll, dataclasses, pure-python]

# Dependency graph
requires:
  - phase: 02-feature-engineering
    plan: "01"
    provides: features/types.py with OffBallEvent and PickAndRollEvent dataclasses

provides:
  - features/off_ball_events.py with detect_off_ball_events(frame_sequence, game_id, ball_pos) -> list[OffBallEvent]
  - features/pick_and_roll.py with detect_pick_and_roll(frame_sequence, game_id) -> list[PickAndRollEvent]
  - tests/test_off_ball_events.py: 27 tests covering cut/screen/drift and degenerate cases
  - tests/test_pick_and_roll.py: 17 tests covering PnR detection, deduplication, multi-screener

affects:
  - downstream models consuming OffBallEvent and PickAndRollEvent detections

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Window-based temporal classifier: use frame_sequence[-1] for off-ball events; last PNR_WINDOW_FRAMES for PnR"
    - "Priority classification: cut > screen > drift within single function, at most one event per player per frame"
    - "O(n^2) proximity scan for screen detection — acceptable at NBA player counts (<=10)"
    - "Screener qualification: nearby player must exceed SCREEN_SPEED_THRESHOLD, not just be relatively faster"

key-files:
  created:
    - features/off_ball_events.py
    - features/pick_and_roll.py
    - tests/test_off_ball_events.py
    - tests/test_pick_and_roll.py
  modified: []

key-decisions:
  - "Screen detection requires nearby player to exceed SCREEN_SPEED_THRESHOLD (not merely be faster than screener candidate) — prevents mutual slow-player false positives"
  - "Drift uses cross-product lateral fraction (>30% of motion must be lateral) and excludes direct ball-approach — makes drift geometrically precise"
  - "PnR timestamps and frame_number taken from middle frame of window — represents the screen contact moment, not setup or separation"
  - "No numpy — pure math module only, consistent with plan's no-external-deps requirement"

# Metrics
duration: 3min
completed: 2026-03-09
---

# Phase 02 Plan 03: Off-Ball Event and Pick-and-Roll Detection Summary

**Cut/screen/drift classifier and 5-frame PnR detector using pure Python window-based temporal analysis — 44 tests passing, zero external dependencies**

## Performance

- **Duration:** 3 min
- **Started:** 2026-03-09T19:21:10Z
- **Completed:** 2026-03-09T19:24:21Z
- **Tasks:** 2 (TDD: RED + GREEN)
- **Files modified:** 4

## Accomplishments

- Created `features/off_ball_events.py` with `detect_off_ball_events()`:
  - Cut: speed > 200 px/s with positive x-velocity (toward basket at x=470)
  - Screen: speed < 30 px/s with a player exceeding SCREEN_SPEED_THRESHOLD within 60 px
  - Drift: speed 30-100 px/s, lateral fraction > 30% relative to ball-player axis
  - Priority: cut > screen > drift; at most one event per player per call
- Created `features/pick_and_roll.py` with `detect_pick_and_roll()`:
  - Requires >= 5 frames; analyzes middle frame for handler-screener proximity (<= 80 px)
  - Verifies separation (> 80 px) in final frame to confirm handler moved off screen
  - Deduplicates per (handler_id, screener_id) pair within window
  - Picks closest screener when multiple qualify
- Written TDD-style: 44 tests (27 off-ball + 17 PnR), all passing

## Task Commits

Each task was committed atomically:

1. **Task 1: Failing tests (RED)** - `53183d0` (test)
2. **Task 2: Implementation (GREEN)** - `34e6718` (feat)

_TDD: tests written first and confirmed failing (ModuleNotFoundError), then implementation driven to pass all 44 tests._

## Files Created/Modified

- `features/off_ball_events.py` - Cut/screen/drift detector using frame_sequence[-1]; pure math module
- `features/pick_and_roll.py` - 5-frame PnR window detector with deduplication and multi-screener resolution
- `tests/test_off_ball_events.py` - 27 tests: degenerate cases, return types, cut/screen/drift, priority enforcement
- `tests/test_pick_and_roll.py` - 17 tests: degenerate cases, return types, canonical PnR, deduplication, closest-screener

## Decisions Made

- Screen detection threshold: the nearby player must exceed `SCREEN_SPEED_THRESHOLD` (actively moving), not just be faster than the screener candidate — prevents false positives when two slow players are near each other (auto-fixed bug during GREEN phase)
- Drift geometry: cross-product lateral fraction > 30% + exclude direct ball approach (dot product check) — precise without numpy
- PnR frame metadata: taken from middle frame of window (screen contact moment), not first or last frame
- All constants exported at module level (importable by tests for parameterized thresholds)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed screen detection false positive for two slow players**
- **Found during:** Task 2 (GREEN) — test `test_slow_player_near_equally_slow_player_is_not_a_screen` failed
- **Issue:** Screen pre-pass used `q_speed > p_speed` (relative comparison) — slow2 (15 px/s) was considered "faster than" slow1 (10 px/s), triggering a false screen event
- **Fix:** Changed condition to `q_speed > SCREEN_SPEED_THRESHOLD` — the nearby player must be actively moving (above threshold), not just comparatively faster
- **Files modified:** `features/off_ball_events.py`
- **Commit:** `34e6718` (included in implementation commit)

## Issues Encountered

None beyond the auto-fixed screen detection bug above.

## User Setup Required

None — no database, no external service, no credentials required.

## Next Phase Readiness

- `detect_off_ball_events` and `detect_pick_and_roll` are ready for immediate integration into Phase 2 scoring/analytics pipelines
- Both return stdlib dataclass instances (OffBallEvent, PickAndRollEvent) importable from `features.types`
- No dependencies beyond the standard library — drop-in compatible with any existing Phase 1/2 environment

---
*Phase: 02-feature-engineering*
*Completed: 2026-03-09*
