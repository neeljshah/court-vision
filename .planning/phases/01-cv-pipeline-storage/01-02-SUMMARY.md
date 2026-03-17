---
phase: 01-cv-pipeline-storage
plan: "02"
subsystem: pipelines
tags: [yolov8, opencv, cv2, hough-lines, object-detection, video-ingestion, court-detection, numpy]

requires:
  - phase: 01-cv-pipeline-storage
    plan: "01"
    provides: "pipelines/ package directory, requirements.txt with ultralytics/cv2/torch declared"

provides:
  - VideoIngestor: cv2.VideoCapture frame generator yielding (frame_number, frame, timestamp_ms)
  - ObjectDetector: YOLOv8n player and basketball detection returning List[Detection]
  - Detection dataclass: bbox, confidence, class_label ('player'|'ball'), cx, cy
  - CourtDetector: Hough line detection and HSV-based zone boundary extraction
  - CourtLine dataclass: rho, theta (polar), x1, y1, x2, y2 (Cartesian endpoints)
  - CourtZones dataclass: paint_region, three_point_arc_points, half_court_line (all nullable)
  - data/models/ directory for YOLOv8 weight files
  - 36 passing unit tests across two test modules

affects:
  - 01-03
  - 01-04
  - all downstream phases using player/ball positions (features, models, analytics)

tech-stack:
  added:
    - pytest>=9.0 (test runner, installed in executor environment)
  patterns:
    - "TDD cycle: failing test commit (RED) then implementation commit (GREEN) per task"
    - "COCO-to-domain mapping: 'person' -> 'player', 'sports ball' -> 'ball' in ObjectDetector"
    - "Graceful degradation: CourtDetector returns [] / None fields on detection failure, never raises"
    - "Auto-download fallback: ObjectDetector loads yolov8n.pt from ultralytics if weights_path missing"

key-files:
  created:
    - pipelines/video_ingestor.py
    - pipelines/detector.py
    - pipelines/court_detector.py
    - data/models/.gitkeep
    - tests/__init__.py
    - tests/test_video_ingestor_and_detector.py
    - tests/test_court_detector.py
  modified: []

key-decisions:
  - "YOLOv8n pretrained COCO weights used without fine-tuning; NBA-specific accuracy deferred to later phases"
  - "ObjectDetector falls back to yolov8n.pt auto-download if weights_path not found on disk"
  - "CourtDetector is stateless (no __init__ state); designed to be called periodically, not per-frame"
  - "HSV hardwood floor range (10,50,100)-(30,255,255) as starting values with tuning comment"
  - "rho/theta computed from Cartesian endpoints for consistency (HoughLinesP doesn't return polar form)"
  - "detect_zones wraps entire body in try/except to never crash callers on malformed frames"

patterns-established:
  - "TDD pattern: RED commit (failing tests) then GREEN commit (implementation) per task"
  - "Detection filtering pattern: filter COCO class names by string key in _COCO_TO_DOMAIN dict"
  - "Generator pattern: VideoIngestor.frames() releases VideoCapture in finally block"

requirements-completed: [CV-01, CV-02, CV-03]

duration: 5min
completed: 2026-03-09
---

# Phase 1 Plan 02: CV Pipeline Modules Summary

**YOLOv8n-based player/ball detector, cv2 frame generator, and Hough+HSV court line detector — the sensory layer feeding all downstream tracking and feature components**

## Performance

- **Duration:** ~5 min
- **Started:** 2026-03-09T18:26:30Z
- **Completed:** 2026-03-09T18:31:00Z
- **Tasks:** 2 (each with TDD RED + GREEN commits)
- **Files modified:** 7 created

## Accomplishments

- VideoIngestor yields (frame_number, frame_array, timestamp_ms) tuples from any local video file with FileNotFoundError on missing path and cap.release() in finally block
- ObjectDetector wraps YOLOv8n, filters COCO detections to 'player' (person) and 'ball' (sports ball) only, falls back to auto-downloaded yolov8n.pt if weights file missing
- CourtDetector.detect_lines() returns List[CourtLine] using Canny+HoughLinesP pipeline; CourtDetector.detect_zones() extracts paint region, half-court line via HSV masking — returns None for undetected zones without raising
- 36 unit tests covering dataclass structure, generator behavior, empty-frame safety, and class label constraints

## Task Commits

Each task was committed atomically with TDD commits preceding implementation:

1. **Task 1 RED: Failing tests for VideoIngestor and ObjectDetector** - `13cc281` (test)
2. **Task 1 GREEN: VideoIngestor and ObjectDetector implementation** - `e5b4575` (feat)
3. **Task 2 RED: Failing tests for CourtDetector** - `3607234` (test)
4. **Task 2 GREEN: CourtDetector implementation** - `0dddb8f` (feat)

## Files Created/Modified

- `pipelines/video_ingestor.py` - VideoIngestor class: cv2.VideoCapture frame generator with frame_count/fps properties
- `pipelines/detector.py` - ObjectDetector + Detection dataclass: YOLOv8n inference filtered to player/ball
- `pipelines/court_detector.py` - CourtDetector + CourtLine + CourtZones: Hough lines + HSV zone boundaries
- `data/models/.gitkeep` - Ensures model weights directory tracked in git
- `tests/__init__.py` - Tests package marker
- `tests/test_video_ingestor_and_detector.py` - 10 tests for VideoIngestor and ObjectDetector
- `tests/test_court_detector.py` - 16 tests for CourtDetector, CourtLine, CourtZones

## Decisions Made

- YOLOv8n pretrained on COCO used without fine-tuning — basketball detection at broadcast distance is imperfect but acceptable for Phase 1; tracker (plan 01-04) handles temporal consistency
- ObjectDetector falls back to yolov8n.pt auto-download so the module works out-of-box without pre-downloaded weights
- CourtDetector is stateless and designed to be called once per game (periodic calibration), not per-frame
- rho/theta computed from Cartesian line endpoints since HoughLinesP does not return polar form directly
- detect_zones() wraps entire body in try/except to guarantee callers never receive an exception from heuristic zone extraction

## Deviations from Plan

None - plan executed exactly as written. TDD cycle followed as specified (RED commit before GREEN commit per task).

## Issues Encountered

None. All dependencies (ultralytics, opencv-python, torch, numpy) were already installed from plan 01-01's requirements.txt. pytest was not installed but was added as a non-blocking deviation Rule 3 (installed to run tests).

## User Setup Required

None - no external service configuration required. Model weights download automatically on first ObjectDetector instantiation.

## Next Phase Readiness

- All three CV modules import cleanly from `pipelines.*`
- VideoIngestor + ObjectDetector can be chained immediately: `for frame_num, frame, ts in vi.frames(): detections = od.detect(frame)`
- CourtDetector ready for spatial calibration on first real video frame
- plan 01-03 (seed data) and plan 01-04 (tracker) can depend on Detection and VideoIngestor interfaces

---
*Phase: 01-cv-pipeline-storage*
*Completed: 2026-03-09*

## Self-Check: PASSED

All files present and all commits verified:
- pipelines/video_ingestor.py: FOUND
- pipelines/detector.py: FOUND
- pipelines/court_detector.py: FOUND
- data/models/.gitkeep: FOUND
- .planning/phases/01-cv-pipeline-storage/01-02-SUMMARY.md: FOUND
- 13cc281 (RED tests task 1): FOUND
- e5b4575 (feat task 1): FOUND
- 3607234 (RED tests task 2): FOUND
- 0dddb8f (feat task 2): FOUND
