---
phase: 02-feature-engineering
plan: "01"
subsystem: database
tags: [python, dataclasses, postgresql, scipy, networkx, feature-engineering]

# Dependency graph
requires:
  - phase: 01-cv-pipeline-storage
    provides: tracking/database.py with init_schema(), tracking/schema.sql with games/possessions/shot_logs tables

provides:
  - features/types.py with 6 shared dataclass contracts (SpacingMetrics, DefensivePressure, OffBallEvent, PickAndRollEvent, PassingEdge, MomentumSnapshot)
  - features/schema_extensions.sql with feature_vectors, detected_events, momentum_snapshots tables
  - tracking/database.py updated to apply schema extensions on init
  - scipy>=1.11 and networkx>=3.2 declared in requirements.txt

affects:
  - 02-feature-engineering/02-02 (spacing module imports SpacingMetrics, DefensivePressure)
  - 02-feature-engineering/02-03 (off-ball detection imports OffBallEvent, PickAndRollEvent)
  - 02-feature-engineering/02-04 (passing network imports PassingEdge; momentum imports MomentumSnapshot)

# Tech tracking
tech-stack:
  added: [scipy>=1.11, networkx>=3.2]
  patterns:
    - Shared type contracts via stdlib dataclasses (no external libs in types module)
    - Schema-as-SQL extension pattern: separate SQL files loaded sequentially in init_schema()

key-files:
  created:
    - features/types.py
    - features/schema_extensions.sql
    - tests/test_feature_types.py
  modified:
    - tracking/database.py
    - requirements.txt

key-decisions:
  - "Shared type contracts defined as stdlib @dataclass (no Pydantic/attrs) — zero extra dependencies for the types module"
  - "Schema extensions in separate features/schema_extensions.sql file, loaded after base schema.sql in init_schema() — preserves schema-as-SQL pattern from Phase 1"
  - "All feature type fields are positional (no defaults) — enforces callers provide all data explicitly"

patterns-established:
  - "Type contract pattern: downstream feature modules import from features.types rather than defining local dataclasses"
  - "Schema extension pattern: new phases add SQL files loaded by init_schema() rather than modifying tracking/schema.sql"

requirements-completed: [FE-01, FE-02, FE-03, FE-04, FE-05, FE-06]

# Metrics
duration: 2min
completed: 2026-03-09
---

# Phase 02 Plan 01: Feature Engineering Foundations Summary

**Six stdlib dataclass type contracts and three PostgreSQL schema extension tables enabling all Phase 2 feature modules to share a common output format and persist computed features**

## Performance

- **Duration:** 2 min
- **Started:** 2026-03-09T19:16:27Z
- **Completed:** 2026-03-09T19:18:46Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments
- Created `features/types.py` with 6 shared dataclasses: SpacingMetrics, DefensivePressure, OffBallEvent, PickAndRollEvent, PassingEdge, MomentumSnapshot — all using stdlib only
- Created `features/schema_extensions.sql` with `feature_vectors`, `detected_events`, and `momentum_snapshots` tables (IF NOT EXISTS guards, composite indexes)
- Updated `tracking/database.py` `init_schema()` to also execute `schema_extensions.sql` after the base schema, using pathlib project-root discovery
- Added `scipy>=1.11` and `networkx>=3.2` to requirements.txt for downstream feature modules
- 13 tests covering field presence and behavioral invariants for all 6 types

## Task Commits

Each task was committed atomically:

1. **Task 1: Feature type contracts (TDD)** - `54c20a8` (feat)
2. **Task 2: Schema extensions + dependency declarations** - `75e4573` (feat)

**Plan metadata:** (docs commit follows)

_Note: Task 1 used TDD — tests written first (RED), then implementation (GREEN), all 13 passed._

## Files Created/Modified
- `features/types.py` - Six shared dataclass contracts for all Phase 2 feature modules
- `features/schema_extensions.sql` - DDL for feature_vectors, detected_events, momentum_snapshots tables
- `tests/test_feature_types.py` - 13 unit tests verifying field presence and behavioral invariants
- `tracking/database.py` - init_schema() updated to load schema_extensions.sql after base schema
- `requirements.txt` - Added scipy>=1.11 and networkx>=3.2

## Decisions Made
- Used stdlib `@dataclass` (no Pydantic/attrs) for `features/types.py` — zero extra dependencies for the shared types module; behavioral validation is the caller's responsibility
- All fields are positional with no defaults — forces callers to provide all data explicitly, preventing silent omissions
- Schema extension lives in `features/schema_extensions.sql` (not modifying `tracking/schema.sql`) — clean separation between base tracking schema and computed feature tables
- init_schema() loads both files in one transaction — atomic: either both schemas apply or neither does

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- `features/types.py` is ready for immediate import by 02-02 (spacing), 02-03 (off-ball detection), 02-04 (passing/momentum)
- `features/schema_extensions.sql` will be applied to the database when `init_schema()` is next called against a live PostgreSQL instance
- scipy and networkx are declared in requirements.txt; install with `pip install -r requirements.txt` before running spatial feature modules

---
*Phase: 02-feature-engineering*
*Completed: 2026-03-09*
