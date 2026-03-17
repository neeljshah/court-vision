---
phase: 025-cv-tracker-quality-upgrades
plan: "05"
subsystem: pipeline
tags: [homography, unified-pipeline, issue-017, wiring]
dependency_graph:
  requires: [025-04]
  provides: [per-clip-M1-in-pipeline]
  affects: [src/pipeline/unified_pipeline.py]
tech_stack:
  added: []
  patterns: [opencv-videocapture, startup-frame-collection]
key_files:
  created: []
  modified: [src/pipeline/unified_pipeline.py]
decisions:
  - "Startup VideoCapture opened and immediately released — not persisted as self attribute"
  - "TOPCUT slice applied to startup frames to match gameplay frame geometry"
metrics:
  duration: "~8 minutes"
  completed: "2026-03-17"
  tasks_completed: 2
  files_changed: 1
---

# Phase 025 Plan 05: unified_pipeline.py Wiring Summary

**One-liner:** Wire detect_court_homography into _build_court() with per-clip M1 detection and Rectify1.npy fallback, closing ISSUE-017 end-to-end.

## What Was Built

Two targeted edits to `src/pipeline/unified_pipeline.py`:

**Edit 1 — Import:**
```python
from src.tracking.court_detector import detect_court_homography
```
Added after existing tracking imports.

**Edit 2 — _build_court() signature + detection/fallback logic:**
- Signature changed to `_build_court(self, pano, startup_frames: list = None)`
- When `startup_frames` provided: calls `detect_court_homography(startup_frames)`
- When detection returns non-None: uses detected M1 (logs "Using per-clip detected homography M1")
- When detection returns None or startup_frames is None: loads `np.load(rect1)` (logs "Using fallback static homography Rectify1.npy")

**Edit 3 — Call site in __init__:**
- Reads first 60 frames from video_path via temporary VideoCapture
- TOPCUT slice applied to each frame
- Temporary cap released immediately
- `_build_court(pano, startup_frames=_startup_frames)` — detection actually invoked

## Deviations from Plan

None — plan executed exactly as written.

## Self-Check: PASSED

- detect_court_homography import in unified_pipeline.py: FOUND
- startup_frames parameter in _build_court: CONFIRMED
- Both detection and fallback log messages present: CONFIRMED
- np.load(rect1) fallback present: CONFIRMED
- startup_frames=_startup_frames at call site: CONFIRMED
- _startup_cap = cv2.VideoCapture present: CONFIRMED
- _startup_cap.release() present: CONFIRMED
- File parses without syntax errors: CONFIRMED
- pytest tests/ -q: 637 passed, 2 skipped
