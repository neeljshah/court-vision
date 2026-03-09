---
phase: 01-cv-pipeline-storage
plan: "03"
subsystem: database
tags: [postgresql, python, sql, seeding, nba, historical-data]

requires:
  - phase: 01-cv-pipeline-storage/01-01
    provides: games and players table DDL with UUID PKs; get_connection() from tracking/database.py

provides:
  - data/seeds/seed_games.sql with 40 representative NBA games across 2022-23 and 2023-24 seasons
  - data/seeds/seed_players.sql with 38 player records across 16 NBA teams
  - tracking/seed_historical.py runner that executes both SQL files idempotently and prints row counts

affects:
  - 01-04
  - Phase 3 ML training pipeline (needs game/player FK targets for tracking_coordinates joins)

tech-stack:
  added: []
  patterns:
    - "Hardcoded UUID strings in seed SQL (no gen_random_uuid() — plain SQL INSERT compatibility)"
    - "ON CONFLICT (id) DO NOTHING for idempotent seed inserts"
    - "Pathlib-relative seed file resolution: Path(__file__).parent.parent / 'data/seeds/...'"
    - "EnvironmentError catch in runner → print to stderr + sys.exit(1) (no unhandled exception)"

key-files:
  created:
    - data/__init__.py
    - data/seeds/__init__.py
    - data/seeds/seed_games.sql
    - data/seeds/seed_players.sql
    - tracking/seed_historical.py
    - tests/test_seed_historical.py
  modified: []

key-decisions:
  - "Hardcoded UUID strings used in SQL (gen_random_uuid() requires DB connection; plain INSERT files need literal values)"
  - "38 players across 16 teams chosen to cover all 16 teams appearing in the game seed records"
  - "seed_historical() uses a single connection and cursor for both SQL files then commits once (atomic)"
  - "EnvironmentError from get_connection() caught in runner; exits with code 1 rather than propagating"

patterns-established:
  - "Dimension table seeding pattern: plain SQL files with ON CONFLICT DO NOTHING + Python runner"
  - "TDD for seed runner: 10 tests covering import, structure, SQL references, error handling, mock DB interaction"

requirements-completed: [DB-02]

duration: 3min
completed: 2026-03-09
---

# Phase 1 Plan 03: Historical Game and Player Seed Data Summary

**40 NBA games (2022-23 and 2023-24) and 38 player records across 16 teams seeded via idempotent SQL files with a Python runner that handles missing DATABASE_URL gracefully**

## Performance

- **Duration:** ~3 min
- **Started:** 2026-03-09T18:26:34Z
- **Completed:** 2026-03-09T18:29:04Z
- **Tasks:** 2 (Task 2 with TDD: 3 commits — test RED, feat GREEN, skip REFACTOR)
- **Files modified:** 6

## Accomplishments

- data/seeds/seed_games.sql: 40 game records (20 per season) covering 2022-23 and 2023-24 with 16 representative NBA teams, hardcoded UUID PKs, and ON CONFLICT (id) DO NOTHING
- data/seeds/seed_players.sql: 38 player records with name, team, jersey_number, and position across all 16 teams, ON CONFLICT (id) DO NOTHING
- tracking/seed_historical.py: importable runner that connects via get_connection(), executes both SQL files atomically, commits, queries and prints row counts, prints tracking_coordinates NOTE, and exits with code 1 on missing DATABASE_URL

## Task Commits

Each task was committed atomically:

1. **Task 1: Historical game and player seed SQL files** - `fcb7a9a` (feat)
2. **Task 2 RED: Failing tests for seed runner** - `e44cb26` (test)
3. **Task 2 GREEN: seed_historical implementation** - `a78def0` (feat)

_TDD task had RED (test) and GREEN (feat) commits; REFACTOR skipped — code needed no cleanup._

## Files Created/Modified

- `data/__init__.py` - Package marker for data module
- `data/seeds/__init__.py` - Package marker for data/seeds module
- `data/seeds/seed_games.sql` - 40 INSERT statements for games table across 2022-23 and 2023-24 seasons
- `data/seeds/seed_players.sql` - 38 INSERT statements for players table covering LAL, GSW, BOS, MIL, PHX, DEN, MIA, PHI, NYK, CLE, SAC, MIN, OKC, MEM, DAL, NOP
- `tracking/seed_historical.py` - Runner: get_connection(), execute SQL files, commit, print counts + NOTE
- `tests/test_seed_historical.py` - 10 unit tests covering all behaviors (mocked DB, no real connection needed)

## Decisions Made

- Hardcoded UUID strings chosen over gen_random_uuid() because plain SQL INSERT files have no DB function context
- 38 players selected to ensure every team appearing in seed_games.sql has at least two players (provides realistic FK variety)
- Single connection and single commit for both seed files to keep seeding atomic
- EnvironmentError caught at the runner level (not function level) — exits with code 1 for scripting compatibility

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - seed files are standalone SQL. To run against a live database:
```bash
# Set DATABASE_URL in .env, then:
python -m tracking.seed_historical
```

## Next Phase Readiness

- games and players tables can be populated immediately once a PostgreSQL instance is available (DATABASE_URL set)
- tracking_coordinates FK targets (game_id, player_id) now exist in seed data for plan 01-04 video pipeline testing
- Phase 3 ML training pipeline can join tracking_coordinates against these game/player dimension records

---
*Phase: 01-cv-pipeline-storage*
*Completed: 2026-03-09*
