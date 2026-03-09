---
phase: 01-cv-pipeline-storage
plan: "04"
subsystem: tracking
tags: [deepsort, tracking, postgresql, psycopg2, pipeline, cli, tdd]

requires:
  - phase: 01-cv-pipeline-storage
    plan: "01"
    provides: "tracking/database.py get_connection(); tracking_coordinates schema"
  - phase: 01-cv-pipeline-storage
    plan: "02"
    provides: "VideoIngestor, ObjectDetector, Detection dataclass"

provides:
  - ObjectTracker: DeepSORT wrapper with persistent track IDs and velocity computation
  - TrackedObject dataclass: 12-field row type ready for DB insertion
  - CoordinateWriter: parameterized batch INSERT to tracking_coordinates
  - pipelines/run_pipeline.py: end-to-end CLI pipeline (video in, DB rows out)

affects:
  - Phase 2 feature engineering (velocity/direction fields feed ML features)
  - Phase 3 model training (tracking_coordinates populated for training data)

tech-stack:
  added:
    - deep-sort-realtime>=1.3 (DeepSort tracker, already in requirements.txt)
  patterns:
    - "TDD cycle: RED commit (failing tests) then GREEN commit (implementation) per task"
    - "track_id coercion: DeepSort returns str internally; cast to int on extraction"
    - "Nearest-centroid matching: object_type resolved from original Detection list, not track.get_det_class()"
    - "Velocity as delta * fps: (cx_now - cx_prev) * self.fps per axis"
    - "Batch buffer pattern: extend buffer, auto-flush at batch_size, explicit flush at end"
    - "Class-level SQL constant: INSERT template as _INSERT_SQL on CoordinateWriter class"

key-files:
  created:
    - tracking/tracker.py
    - tracking/coordinate_writer.py
    - pipelines/run_pipeline.py
    - tests/test_tracker.py
    - tests/test_coordinate_writer_and_pipeline.py
  modified: []

key-decisions:
  - "DeepSort returns track_id as str; coerce to int via int(track.track_id) for consistent dict keys"
  - "Nearest-centroid matching preferred over get_det_class() for object_type — more reliable across DeepSort versions"
  - "CoordinateWriter stores SQL as class-level _INSERT_SQL constant, not inline in _flush_buffer"
  - "player_id=None for all Phase 1 tracking_coordinates rows — track-to-player mapping deferred to Phase 2"
  - "n_init=1 used in tests only for speed; production default remains n_init=3 (noise rejection)"

requirements-completed: [CV-04, CV-05, CV-06, DB-03]

duration: 9min
completed: 2026-03-09
---

# Phase 1 Plan 04: DeepSORT Tracking, Velocity Computation, and DB Storage Summary

**DeepSORT tracker with per-frame velocity/speed/direction, batch PostgreSQL writer, and single-command end-to-end CLI pipeline — closing the loop from raw video to persistent tracked coordinates**

## Performance

- **Duration:** ~9 min
- **Started:** 2026-03-09T18:35:37Z
- **Completed:** 2026-03-09T18:45:02Z
- **Tasks:** 2 (both TDD: RED + GREEN commits)
- **Files modified:** 5 created

## Accomplishments

- TrackedObject dataclass with all 12 fields: track_id, object_type, cx, cy, bbox, confidence, frame_number, timestamp_ms, velocity_x, velocity_y, speed, direction_degrees
- ObjectTracker wraps DeepSort(max_age=30, n_init=3); update() converts Detection list to DeepSORT raw format, processes confirmed tracks, computes velocity as (delta_cx * fps), speed as sqrt(vx^2+vy^2), direction_degrees normalized to [0, 360)
- CoordinateWriter buffers TrackedObject rows and batch-inserts via cursor.executemany() with parameterized %s SQL; player_id=None throughout Phase 1
- run_pipeline.py orchestrates VideoIngestor → ObjectDetector → ObjectTracker → CoordinateWriter with set_fps() call from ingestor.fps; --help works without error
- 53 new unit tests across two test modules (27 for tracker, 26 for writer + pipeline); 89 total tests pass

## Task Commits

Each task committed atomically with TDD RED + GREEN commits:

1. **Task 1 RED: Failing tests for ObjectTracker and TrackedObject** — `71b7f35` (test)
2. **Task 1 GREEN: ObjectTracker implementation** — `d2cca94` (feat)
3. **Task 2 RED: Failing tests for CoordinateWriter and run_pipeline** — `c27f1e7` (test)
4. **Task 2 GREEN: CoordinateWriter and run_pipeline implementation** — `e5a2f89` (feat)

## Files Created/Modified

- `tracking/tracker.py` — ObjectTracker + TrackedObject: DeepSORT wrapper with velocity, speed, direction
- `tracking/coordinate_writer.py` — CoordinateWriter: buffered batch INSERT to tracking_coordinates
- `pipelines/run_pipeline.py` — End-to-end CLI pipeline: argparse + orchestration loop + summary print
- `tests/test_tracker.py` — 27 tests for TrackedObject fields, ObjectTracker init, velocity computation
- `tests/test_coordinate_writer_and_pipeline.py` — 26 tests for CoordinateWriter API, buffering, SQL quality, pipeline wiring

## Decisions Made

- DeepSort returns track_id as a Python str internally; coerced to int via `int(track.track_id)` to ensure consistent dict key types in previous_positions
- Nearest-centroid matching (min Euclidean distance from track center to Detection.cx/cy) chosen over `get_det_class()` to resolve object_type — more reliable across deep-sort-realtime versions
- SQL template stored as `_INSERT_SQL` class-level constant on CoordinateWriter rather than inline in `_flush_buffer`, keeping the method readable and testable
- player_id hardcoded to None for all Phase 1 rows — track_id to players table mapping requires Phase 2 feature engineering (player identification by jersey number or embedding)
- n_init=3 in production (reduces false positive tracks on transient detections); n_init=1 used only in unit tests to get confirmed tracks without running many frames

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] DeepSort track_id is str, not int**
- **Found during:** Task 1 GREEN implementation
- **Issue:** `track.track_id` returns a Python `str` (e.g., `'1'`), but `previous_positions` dict was being populated and looked up with int keys, causing velocity to always be 0.0 after the first frame
- **Fix:** Added `int(track.track_id)` coercion at extraction point; previous_positions now keyed consistently by int
- **Files modified:** `tracking/tracker.py`
- **Commit:** `d2cca94`

**2. [Rule 1 - Bug] Test expected confirmed track on frame 0 with n_init=1**
- **Found during:** Task 1 GREEN verification
- **Issue:** Two tests assumed `ObjectTracker(n_init=1).update()` returns a result on the first call. DeepSort actually needs two calls even with n_init=1: first call creates a tentative track, second call confirms it.
- **Fix:** Updated both test bodies to call update() twice; clarified docstrings to explain DeepSort's confirmation lifecycle
- **Files modified:** `tests/test_tracker.py`
- **Commit:** `d2cca94`

**3. [Rule 1 - Bug] Test inspected _flush_buffer for table name that lives in class constant**
- **Found during:** Task 2 GREEN verification
- **Issue:** `test_inserts_to_tracking_coordinates_table` used `inspect.getsource(CoordinateWriter._flush_buffer)` but `tracking_coordinates` appears in `_INSERT_SQL` (class attribute), which is out of scope for method-level introspection
- **Fix:** Changed to `inspect.getsource(CoordinateWriter)` to capture the full class including class-level constants
- **Files modified:** `tests/test_coordinate_writer_and_pipeline.py`
- **Commit:** `e5a2f89`

---

**Total deviations:** 3 auto-fixed (2 bugs, 1 test fix)
**Impact on plan:** All deviations discovered during TDD cycle; all fixed inline. No scope additions.

## Issues Encountered

None beyond the three auto-fixed deviations above.

## User Setup Required

None for code correctness. To run the pipeline end-to-end against real video:
```bash
# Set DATABASE_URL in .env, ensure schema initialized, then:
python -m pipelines.run_pipeline --video path/to/game.mp4 --game-id <UUID-from-seed>
```

## Next Phase Readiness

- tracking_coordinates writes are fully wired; all Phase 1 requirements satisfied (CV-04, CV-05, CV-06, DB-03)
- Phase 2 feature engineering can query `SELECT * FROM tracking_coordinates WHERE game_id = $1 ORDER BY frame_number` to get timestamped coordinate streams
- ObjectTracker and CoordinateWriter are independently importable and testable; Phase 2 can extend without touching Phase 1 modules
- All 89 tests pass; no regressions in earlier modules

## Self-Check: PASSED

Files present on disk:
- tracking/tracker.py: FOUND
- tracking/coordinate_writer.py: FOUND
- pipelines/run_pipeline.py: FOUND
- tests/test_tracker.py: FOUND
- tests/test_coordinate_writer_and_pipeline.py: FOUND
- .planning/phases/01-cv-pipeline-storage/01-04-SUMMARY.md: FOUND (this file)

Commits present in git log:
- 71b7f35 (test RED task 1): FOUND
- d2cca94 (feat GREEN task 1): FOUND
- c27f1e7 (test RED task 2): FOUND
- e5a2f89 (feat GREEN task 2): FOUND

---
*Phase: 01-cv-pipeline-storage*
*Completed: 2026-03-09*
