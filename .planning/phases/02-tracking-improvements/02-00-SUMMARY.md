---
phase: 02-tracking-improvements
plan: "00"
subsystem: testing
tags: [pytest, conftest, fixtures, test-stubs, xfail, importorskip]

requires:
  - phase: 01-data-infrastructure
    provides: src/data/db.py, src/data/nba_stats.py — modules referenced by test stubs

provides:
  - pytest.ini with testpaths=tests — `pytest tests/` runs without arguments
  - tests/conftest.py with three shared fixtures: synthetic_crop_bgr, mock_roster_dict, temp_db_url
  - tests/test_phase2.py with all 11 REQ-04 through REQ-08 stub tests

affects: [02-01, 02-02, 02-03, 02-04, 02-05, every subsequent plan with automated verify]

tech-stack:
  added: [pytest, numpy (fixtures), pytest.importorskip, pytest.mark.integration]
  patterns: [Wave 0 test-first infrastructure, importorskip guard for missing modules, integration marker for DB-gated tests]

key-files:
  created:
    - pytest.ini
    - tests/conftest.py
    - tests/test_phase2.py
  modified: []

key-decisions:
  - "pytest.importorskip used (not xfail) for module-level guards — skips entire group cleanly when implementation doesn't exist"
  - "temp_db_url fixture uses pytest.skip (not xfail) — integration tests simply absent from non-DB runs"
  - "synthetic_crop_bgr uses solid green + white pixels to simulate jersey fabric without real video"

patterns-established:
  - "Wave 0 pattern: test stubs committed before implementation — all stubs use importorskip so suite stays green"
  - "Integration marker: @pytest.mark.integration gates all tests requiring live PostgreSQL — skipped by default"

requirements-completed: [REQ-04, REQ-05, REQ-06, REQ-07, REQ-08]

duration: 5min
completed: 2026-03-17
---

# Phase 2 Plan 00: Test Infrastructure Summary

**pytest Wave 0 scaffolding — pytest.ini, conftest.py with 3 shared fixtures, and test_phase2.py with all 11 REQ-04 through REQ-08 stubs guarded by importorskip**

## Performance

- **Duration:** ~5 min (artifacts created as part of 02-01 setup)
- **Started:** 2026-03-15T20:12:00Z
- **Completed:** 2026-03-15T20:12:56Z
- **Tasks:** 2 of 2
- **Files modified:** 3

## Accomplishments

- `pytest.ini` in project root — `testpaths = tests`, integration marker declared, `pytest tests/` works without arguments
- `tests/conftest.py` — three shared fixtures: `synthetic_crop_bgr` (120x60 BGR jersey crop), `mock_roster_dict` (jersey num → player dict), `temp_db_url` (skips when DATABASE_URL unset)
- `tests/test_phase2.py` — all 11 stub tests for REQ-04 through REQ-08, using `pytest.importorskip` so suite stays green before implementation exists

## Task Commits

Both tasks were committed atomically in a single commit (created during 02-01 wave-0 setup):

1. **Task 1: pytest.ini + conftest.py with shared fixtures** - `1884c5d` (test)
2. **Task 2: test_phase2.py — stub tests for REQ-04 through REQ-08** - `1884c5d` (test)

_Note: Both tasks were captured in a single commit as the 02-01 planner created Wave 0 infrastructure before implementing the OCR module._

## Files Created/Modified

- `pytest.ini` — testpaths, python_files/classes/functions config, integration marker
- `tests/conftest.py` — synthetic_crop_bgr, mock_roster_dict, temp_db_url fixtures with type hints and docstrings
- `tests/test_phase2.py` — 11 test stubs: test_ocr_reader_init, test_jersey_number_extraction, test_voting_buffer, test_voting_buffer_none_breaks_streak, test_kmeans_color_descriptor, test_roster_lookup, test_db_connection, test_player_identity_persist, test_reid_with_jersey_tiebreaker, test_referee_excluded_from_spacing, test_referee_excluded_from_pressure

## Decisions Made

- `pytest.importorskip` used instead of `@pytest.mark.xfail` — importorskip skips the whole group at collection time, giving clean "skipped" output rather than "xfailed" noise
- Integration tests use `pytest.skip()` inside the `temp_db_url` fixture rather than a marker on each test — keeps DB skip logic centralized
- `synthetic_crop_bgr` fixture is deterministic numpy array — no file I/O, no external dependencies, runs in microseconds

## Deviations from Plan

None - plan executed exactly as written. The three artifacts were created with the specified content. All 11 required stubs are present. Suite exits 0 (57 passed, 2 skipped for integration tests).

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Wave 0 test infrastructure is complete
- All subsequent Phase 2 plans (02-01 through 02-05) have `<automated>` verify commands pointing at `tests/test_phase2.py`
- Suite verified: 57 passed, 2 skipped (DB-gated), exit code 0

---
*Phase: 02-tracking-improvements*
*Completed: 2026-03-17*
