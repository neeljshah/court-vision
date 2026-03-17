---
phase: 02-tracking-improvements
plan: 07
subsystem: testing
tags: [event-detector, clip-validation, pytest, opencv, basketball-tracking]

# Dependency graph
requires:
  - phase: 02-tracking-improvements
    provides: EventDetector (shot/pass/dribble classifier) and run_clip.py entry point
provides:
  - MIN_CLIP_SECONDS=60 constant and cv2-based duration guard in run_clip.py
  - Five unit tests validating EventDetector shot/dribble/pass/none events and clip duration constant
affects: [02-tracking-improvements, run_clip, event_detector]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "cv2.VideoCapture for pre-flight duration check before UnifiedPipeline construction"
    - "Synthetic frame_tracks dicts for EventDetector unit tests (no video required)"
    - "Retroactive pass confirmation: _pending dict stores frame_idx -> 'pass', consumed on later pop"

key-files:
  created: []
  modified:
    - run_clip.py
    - tests/test_phase2.py

key-decisions:
  - "Exit code sys.exit(2) chosen for short clips (distinct from sys.exit(1) for missing file)"
  - "MIN_CLIP_SECONDS=60 placed at module level (not inside main) for testability via import"
  - "test_event_detector_shot uses ball moving left toward basket_left (x=32) — nearest basket determines dot-product direction, so test is designed with ball at (200,140) moving to (100,140)"

patterns-established:
  - "EventDetector tests: establish possession first, then trigger event on next frame"
  - "Pass test: assert _pending[loss_frame] == 'pass' after receiver pickup (not return value)"

requirements-completed: [REQ-02B, REQ-02C, REQ-02D, REQ-02E]

# Metrics
duration: 15min
completed: 2026-03-16
---

# Phase 2 Plan 7: Clip Duration Validator + EventDetector Unit Tests Summary

**Clip duration guard in run_clip.py (MIN_CLIP_SECONDS=60, sys.exit(2)) and five synthetic EventDetector unit tests validating shot, dribble, pass, none, and duration constant without video processing.**

## Performance

- **Duration:** ~15 min
- **Started:** 2026-03-16T22:15:00Z
- **Completed:** 2026-03-16T22:30:00Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments

- Added `MIN_CLIP_SECONDS = 60` constant and cv2 duration check to run_clip.py — clips under 60s now exit with sys.exit(2) and a warning before UnifiedPipeline is constructed
- Added 5 new test functions to test_phase2.py: `test_clip_duration_validator`, `test_event_detector_shot`, `test_event_detector_dribble`, `test_event_detector_pass`, `test_event_detector_none_without_ball` — all passing
- Updated CLAUDE.md ISSUE-011 status to "Fixed by EventDetector rewrite (validated by 02-07)"
- Full test suite: 64 passed, 2 skipped, 1 pre-existing failure (test_match_team_white_slots_populated, REQ-02A, out of scope for this plan)

## Task Commits

1. **Task 1: Add clip duration validator to run_clip.py** - `9efee34` (feat)
2. **Task 2: Add EventDetector unit tests and clip duration validator test** - `d3372fa` (test)

**Plan metadata:** (docs commit follows)

## Files Created/Modified

- `run_clip.py` — Added `import cv2`, `MIN_CLIP_SECONDS = 60` constant, cv2.VideoCapture duration check block with sys.exit(2)
- `tests/test_phase2.py` — Appended 5 test functions under `# REQ-02B/C/D: EventDetector validation -- REQ-02E: clip duration` comment block

## Decisions Made

- `sys.exit(2)` chosen for short clips (distinguishes from `sys.exit(1)` used for missing file)
- `MIN_CLIP_SECONDS` placed at module level so `import run_clip; run_clip.MIN_CLIP_SECONDS` works in tests
- `test_event_detector_shot` originally followed the plan's assumption that ball at (150,140) would aim toward basket_right (x=467), but actual code finds nearest basket to the current ball position. Ball at (150,140) is nearest to basket_left (x=32), so the test was redesigned: ball starts at (200,140) and moves left to (100,140), aligning with basket_left direction
- Pass test validates via `detector._pending` dict inspection (retroactive event stored at loss frame, not consumed until a future call with that frame_idx)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed test_event_detector_shot scenario to match actual nearest-basket logic**
- **Found during:** Task 2 (TDD RED/GREEN cycle)
- **Issue:** Plan specified ball moving from (50,140) to (150,140) and claimed nearest basket would be basket_right (x=467, dist=317). Actual code picks nearest to current ball_pos=(150,140), which is basket_left (x=32, dist=118). Dot product was negative → "none" returned instead of "shot".
- **Fix:** Redesigned the scenario: ball starts at (200,140) and moves left to (100,140). Nearest to (100,140) is basket_left (x=32, dist=68). dx_ball=-100, dx_basket=-68 → dot product positive → "shot" correctly returned.
- **Files modified:** tests/test_phase2.py
- **Verification:** test_event_detector_shot passes
- **Committed in:** d3372fa (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (Rule 1 - Bug in plan's test scenario)
**Impact on plan:** Fix only affects the test scenario geometry, not the EventDetector code itself. EventDetector logic is correct — the plan's example calculation had an error in which basket would be "nearest".

## Issues Encountered

None beyond the test scenario geometry fix documented above.

## User Setup Required

None — no external service configuration required.

## Next Phase Readiness

- REQ-02B/C/D (EventDetector) and REQ-02E (clip duration guard) fully validated
- 5 new tests confirm EventDetector shot/dribble/pass events work correctly via synthetic data
- run_clip.py now protects against the known 1-21 second clip problem (ISSUE-014 partially addressed)
- Ready to proceed to 02-08 (REQ-02A dual-team slot fix validation) or Phase 3

## Self-Check: PASSED

- FOUND: run_clip.py (with MIN_CLIP_SECONDS=60 and sys.exit(2))
- FOUND: tests/test_phase2.py (with 5 new test functions)
- FOUND: .planning/phases/02-tracking-improvements/02-07-SUMMARY.md
- FOUND: commit 9efee34 (feat: clip duration validator)
- FOUND: commit d3372fa (test: EventDetector unit tests)

---
*Phase: 02-tracking-improvements*
*Completed: 2026-03-16*
