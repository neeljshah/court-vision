---
phase: 025-cv-tracker-quality-upgrades
plan: "06"
subsystem: tests
tags: [tests, court-detection, synthetic-images, issue-017]
dependency_graph:
  requires: [025-04]
  provides: [test-coverage-court-detector]
  affects: [tests/test_court_detector.py]
tech_stack:
  added: []
  patterns: [synthetic-cv2-frames, pytest]
key_files:
  created: [tests/test_court_detector.py]
  modified: []
decisions:
  - "Replaced existing stub test_court_detector.py (tested non-existent pipelines.court_detector) with new tests for src.tracking.court_detector"
  - "test_synthetic_court_returns_matrix asserts non-None AND shape AND dtype in one block — no separate skip-able tests"
metrics:
  duration: "~5 minutes"
  completed: "2026-03-17"
  tasks_completed: 1
  files_changed: 1
---

# Phase 025 Plan 06: test_court_detector.py Summary

**One-liner:** 7 synthetic-image tests for detect_court_homography() — all passing, no real video needed.

## What Was Built

`tests/test_court_detector.py` — 7 tests using cv2-generated synthetic frames:

| Test | Result |
|---|---|
| test_detect_court_homography_importable | PASS |
| test_empty_list_returns_none | PASS |
| test_single_blank_frame_returns_none | PASS |
| test_uniform_grey_frames_return_none | PASS |
| test_synthetic_court_returns_matrix | PASS |
| test_single_hardwood_frame_accepted | PASS |
| test_large_frame_list_subsampled | PASS |

Synthetic hardwood frame: orange-brown background (HSV H=20, S=100, V=180) + 3 horizontal and 3 vertical white lines = 9 intersections, well above the 4-corner minimum.

Key design: `test_synthetic_court_returns_matrix` asserts all three properties (non-None, shape (3,3), dtype float64) in one block — returning None on synthetic input is a real bug, not a skip condition.

## Deviations from Plan

None — tests match spec exactly. The existing test_court_detector.py (which tested `pipelines.court_detector.CourtDetector` — a non-existent module) was replaced as part of this task.

## Self-Check: PASSED

- tests/test_court_detector.py exists: FOUND
- 7 test functions present: CONFIRMED
- pytest tests/test_court_detector.py -v: 7 passed
- pytest tests/ -q: 637 passed, 2 skipped (no regressions)
