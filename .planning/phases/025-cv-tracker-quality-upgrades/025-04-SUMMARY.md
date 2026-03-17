---
phase: 025-cv-tracker-quality-upgrades
plan: "04"
subsystem: tracking
tags: [court-detection, homography, cv, issue-017]
dependency_graph:
  requires: []
  provides: [detect_court_homography]
  affects: [src/pipeline/unified_pipeline.py]
tech_stack:
  added: []
  patterns: [opencv-hough-lines, hsv-floor-mask, perspective-transform]
key_files:
  created: [src/tracking/court_detector.py]
  modified: []
decisions:
  - "Use bright threshold directly (not bitwise_and with floor_mask) because white court lines have HSV S~0 and are excluded from the hardwood floor mask range S:40-160"
metrics:
  duration: "~10 minutes"
  completed: "2026-03-17"
  tasks_completed: 1
  files_changed: 1
---

# Phase 025 Plan 04: court_detector.py Summary

**One-liner:** Per-clip M1 homography from broadcast frame Hough lines, replacing static Rectify1.npy for ISSUE-017.

## What Was Built

`src/tracking/court_detector.py` — new module with single public function `detect_court_homography(frames)`.

Detection pipeline:
1. Sample up to 10 evenly-spaced frames from input list
2. Accumulate hardwood floor mask (HSV H:10-30, S:40-160, V:100-230)
3. Build white-line mask via brightness threshold > 200 (floor V~180 excluded naturally)
4. HoughLinesP detection (threshold=50, minLineLength=60, maxLineGap=20)
5. Classify lines into horizontal/vertical by atan2 angle
6. Compute all horizontal×vertical intersections within frame bounds
7. Bin into 4 quadrants, pick corner representative closest to each frame corner
8. getPerspectiveTransform to 940×500 2D court space → float64 (3,3) matrix
9. Return None on any failure (< 4 corners, exceptions, empty input)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Floor mask excludes white court lines**
- **Found during:** Task 1 verification (test_synthetic_court_returns_matrix failed)
- **Issue:** The plan specified `line_mask = cv2.bitwise_and(bright, floor_mask)`. White court lines have HSV saturation ~0, outside the floor mask range S:40-160. This made line_mask have only 36 non-zero pixels — too sparse for Hough detection.
- **Fix:** Changed to `line_mask = bright` directly. Hardwood floor has V~180 which doesn't pass the >200 threshold, so white lines stand out cleanly without the floor intersection.
- **Files modified:** `src/tracking/court_detector.py`
- **Commit:** 7d3a81c

## Self-Check: PASSED

- src/tracking/court_detector.py exists: FOUND
- detect_court_homography importable: CONFIRMED
- Returns None on empty input: CONFIRMED
- Returns None on blank frames: CONFIRMED
- Returns float64 (3,3) on synthetic court frames: CONFIRMED
- All basic verification checks passed
