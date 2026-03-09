---
phase: 01-cv-pipeline-storage
plan: "01"
subsystem: database
tags: [postgresql, psycopg2, python, schema, tracking]

requires: []
provides:
  - Five-table PostgreSQL schema (games, players, tracking_coordinates, possessions, shot_logs)
  - Python package structure with eight module directories
  - psycopg2 connection factory and schema initializer in tracking/database.py
  - requirements.txt with pinned ML and pipeline dependencies
affects:
  - 01-02
  - 01-03
  - all downstream phases that write to PostgreSQL

tech-stack:
  added:
    - ultralytics>=8.0
    - deep-sort-realtime>=1.3
    - psycopg2-binary>=2.9
    - opencv-python>=4.8
    - torch>=2.0
    - numpy>=1.24
    - python-dotenv>=1.0
  patterns:
    - "Schema-as-SQL: DDL lives in schema.sql, init_schema() reads and executes it — tables created idempotently with IF NOT EXISTS"
    - "Environment-driven connection: DATABASE_URL drives psycopg2.connect(); EnvironmentError raised if missing"
    - "Package layout mirrors domain: tracking, pipelines, features, models, analytics, api, frontend, dashboards"

key-files:
  created:
    - requirements.txt
    - .env.example
    - tracking/schema.sql
    - tracking/database.py
    - tracking/__init__.py
    - pipelines/__init__.py
    - features/__init__.py
    - models/__init__.py
    - analytics/__init__.py
    - api/__init__.py
    - frontend/__init__.py
    - dashboards/__init__.py
  modified: []

key-decisions:
  - "Used psycopg2-binary (not psycopg2) to avoid requiring libpq headers on host"
  - "UUID primary keys via gen_random_uuid() (pgcrypto extension) for all five tables"
  - "Composite index on tracking_coordinates(game_id, frame_number) for frame-range queries"
  - "player_id is nullable on tracking_coordinates to represent ball detections"
  - "Installed psycopg2-binary and python-dotenv in executor environment to satisfy import verification (Rule 3 - blocking)"

patterns-established:
  - "Schema-as-SQL pattern: DDL in schema.sql, not ORM migrations"
  - "EnvironmentError with actionable message when DATABASE_URL unset"
  - "init_schema() idempotent via CREATE TABLE IF NOT EXISTS"

requirements-completed: [DB-01]

duration: 2min
completed: 2026-03-09
---

# Phase 1 Plan 01: Environment Bootstrap and PostgreSQL Schema Summary

**Five-table PostgreSQL schema (games, players, tracking_coordinates, possessions, shot_logs) with psycopg2 connection factory, eight Python package directories, and pinned ML dependency manifest**

## Performance

- **Duration:** ~2 min
- **Started:** 2026-03-09T18:23:05Z
- **Completed:** 2026-03-09T18:24:28Z
- **Tasks:** 2
- **Files modified:** 12

## Accomplishments

- Eight Python package directories created (tracking, pipelines, features, models, analytics, api, frontend, dashboards)
- requirements.txt with all seven dependencies including ultralytics, psycopg2-binary, torch
- tracking/schema.sql: five tables with UUID PKs, FK constraints, IF NOT EXISTS guards, and composite index on (game_id, frame_number)
- tracking/database.py: get_connection() from DATABASE_URL env var, init_schema() reads and executes schema.sql, EnvironmentError with clear message if DATABASE_URL unset

## Task Commits

Each task was committed atomically:

1. **Task 1: Project structure and Python dependencies** - `9f5e779` (chore)
2. **Task 2: PostgreSQL schema and database module** - `6623b28` (feat)

## Files Created/Modified

- `requirements.txt` - Seven pinned pipeline dependencies (ultralytics, deep-sort-realtime, psycopg2-binary, opencv-python, torch, numpy, python-dotenv)
- `.env.example` - DATABASE_URL, VIDEO_INPUT_DIR, MODEL_WEIGHTS_DIR template
- `tracking/schema.sql` - DDL for all five tables with pgcrypto extension, FK relationships, and composite index
- `tracking/database.py` - get_connection() and init_schema() exports; EnvironmentError on missing DATABASE_URL
- `tracking/__init__.py` - Package marker
- `pipelines/__init__.py` - Package marker
- `features/__init__.py` - Package marker
- `models/__init__.py` - Package marker
- `analytics/__init__.py` - Package marker
- `api/__init__.py` - Package marker
- `frontend/__init__.py` - Package marker
- `dashboards/__init__.py` - Package marker

## Decisions Made

- Used psycopg2-binary instead of psycopg2 to avoid needing libpq headers
- UUID primary keys via gen_random_uuid() requiring pgcrypto extension (included in schema.sql)
- player_id nullable on tracking_coordinates (ball has no player association)
- Composite index on (game_id, frame_number) for the primary query pattern

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Installed psycopg2-binary and python-dotenv to satisfy import verification**
- **Found during:** Task 2 verification
- **Issue:** Task 2 done criteria requires `from tracking.database import get_connection, init_schema` to import without error, but psycopg2 and python-dotenv were not installed in the executor environment
- **Fix:** Ran `pip install psycopg2-binary python-dotenv` in executor environment
- **Files modified:** None (packages installed globally; requirements.txt already listed them)
- **Verification:** `from tracking.database import get_connection, init_schema` returned without error
- **Committed in:** Part of Task 2 context; no code changes needed

---

**Total deviations:** 1 auto-fixed (1 blocking)
**Impact on plan:** Package install was necessary to run the import verification. requirements.txt already declared both packages — no scope creep.

## Issues Encountered

None beyond the package installation required for verification.

## User Setup Required

None - no external service configuration required beyond copying `.env.example` to `.env` and filling in the PostgreSQL connection string.

## Next Phase Readiness

- All downstream pipeline tasks can `from tracking.database import get_connection, init_schema` to connect and initialize the schema
- schema.sql is complete and idempotent; any developer can run `python -m tracking.database` against their PostgreSQL instance
- requirements.txt ready for `pip install -r requirements.txt` on any developer machine

---
*Phase: 01-cv-pipeline-storage*
*Completed: 2026-03-09*
