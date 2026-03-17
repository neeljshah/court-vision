---
phase: 025-cv-tracker-quality-upgrades
plan: "03"
subsystem: testing
tags: [pytest, yolo, easyocr, monkeypatch, synthetic-images, broadcast-mode, jersey-ocr]

# Dependency graph
requires:
  - phase: 025-01
    provides: broadcast_mode config flag, conf_threshold=0.35 in AdvancedFeetDetector, count_detections_on_frame helper
  - phase: 025-02
    provides: 3-pass OCR in read_jersey_number, brightness normalisation in preprocess_crop

provides:
  - 14-test suite covering all Phase 2.5 broadcast-detection and jersey-OCR additions
  - Monkeypatch patterns for YOLO and EasyOCR without GPU in CI

affects:
  - future Phase 2.5 plans that touch player_detection, jersey_ocr, advanced_tracker

# Tech tracking
tech-stack:
  added: []
  patterns:
    - Monkeypatch _yolo_model_cache at module level to avoid GPU inference in unit tests
    - Monkeypatch _reader (EasyOCR singleton) to count OCR pass calls without real model
    - Patch FeetDetector.__init__ to skip warmup call when testing AdvancedFeetDetector subclass

key-files:
  created:
    - tests/test_broadcast_detection.py
  modified: []

key-decisions:
  - "Patched FeetDetector.__init__ directly (not YOLO constructor) to avoid the warmup inference call that breaks without a real GPU"
  - "Player(ID, team, color) takes 3 args — plan template had Player(i, 'green') which would fail; fixed to pass BGR tuple as third arg"
  - "Used module-level _reader monkeypatch (not get_reader()) so the 3-pass call-count test captures all three readtext calls correctly"

patterns-established:
  - "Fake YOLO: inner class with __init__ and __call__ returning list of R() with boxes attribute"
  - "Fake OCR reader: class with readtext() method returning list of (bbox, text, conf) tuples"

requirements-completed: []

# Metrics
duration: 12min
completed: 2026-03-17
---

# Phase 2.5 Plan 03: Tests for Broadcast Detection + Jersey OCR Summary

**14-test suite for Phase 2.5 CV upgrades — covers broadcast_mode config, conf_threshold override, count_detections_on_frame, preprocess_crop pipeline, and 3-pass OCR validation using synthetic images only (no GPU required)**

## Performance

- **Duration:** 12 min
- **Started:** 2026-03-17T00:00:00Z
- **Completed:** 2026-03-17T00:12:00Z
- **Tasks:** 1 (C1)
- **Files modified:** 1

## Accomplishments

- Created `tests/test_broadcast_detection.py` with 14 tests across 5 test classes
- All 14 new tests pass; full suite stays at 646 passed, 2 skipped (no regressions)
- Verified 3-pass OCR (normal + inverted + 2x upscale) by counting readtext calls

## Task Commits

1. **Task C1: Create tests/test_broadcast_detection.py** - `1e4eea2` (test)

## Files Created/Modified

- `tests/test_broadcast_detection.py` - 14 tests covering tracker config, AdvancedFeetDetector conf override, count_detections_on_frame, preprocess_crop, and jersey OCR 3-pass logic

## Decisions Made

- Patched `FeetDetector.__init__` rather than just `YOLO` to skip the warmup inference call that fires during `__init__` and crashes without a real GPU/model file.
- Player constructor requires 3 args `(ID, team, color)` — plan template omitted color; fixed to pass `(0, 180, 0)` / `(255, 255, 255)` BGR tuples.
- Monkeypatched `_reader` directly (not `get_reader()`) so all three `reader.readtext()` calls in `read_jersey_number` are captured by the counting stub.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed Player constructor call signature**
- **Found during:** Task C1 (writing TestAdvancedTrackerBroadcastConf)
- **Issue:** Plan template used `Player(i, "green")` but `Player.__init__` requires 3 args: `(ID, team, color)` where color is a BGR tuple
- **Fix:** Changed to `Player(i, "green", (0, 180, 0))` / `Player(i, "white", (255, 255, 255))`
- **Files modified:** tests/test_broadcast_detection.py
- **Verification:** Test passes without TypeError
- **Committed in:** 1e4eea2

**2. [Rule 1 - Bug] Patched FeetDetector.__init__ to skip GPU warmup**
- **Found during:** Task C1 (running TestAdvancedTrackerBroadcastConf)
- **Issue:** `FeetDetector.__init__` calls `self.model(warmup_frame)` immediately after loading YOLO; even with YOLO patched, the warmup call on a FakeYOLO instance returned wrong shape — and real YOLO would need the .pt file on disk
- **Fix:** Monkeypatched `FeetDetector.__init__` directly to set `self.model`, `self._use_half`, `self.players` without running warmup
- **Files modified:** tests/test_broadcast_detection.py
- **Verification:** AdvancedFeetDetector instantiates cleanly; `_conf_threshold == 0.35` assertion passes
- **Committed in:** 1e4eea2

---

**Total deviations:** 2 auto-fixed (both Rule 1 - bug fixes in test fixture setup)
**Impact on plan:** Both fixes required for the tests to run correctly. No scope creep.

## Issues Encountered

None beyond the two auto-fixed constructor/warmup issues above.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Phase 2.5 test coverage complete for 025-01 and 025-02 additions
- Ready to proceed to next Phase 2.5 plan (per-clip homography fix, ISSUE-017)

## Self-Check: PASSED

- `tests/test_broadcast_detection.py` — FOUND
- Commit `1e4eea2` — FOUND (git log confirms)
- 14/14 tests green, 646 total passing

---
*Phase: 025-cv-tracker-quality-upgrades*
*Completed: 2026-03-17*
