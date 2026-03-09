---
phase: 03-ml-models
plan: 04
subsystem: models
tags: [lineup-optimizer, epa, defensive-pressure, joblib, numpy, ml-05]

# Dependency graph
requires:
  - phase: 03-ml-models/03-02
    provides: BaseModel ABC with fit/predict/save/load contract
  - phase: 03-ml-models/03-03
    provides: PlayerImpactModel with rank_players() EPA per 100 possessions

provides:
  - LineupOptimizer — scores any 5-player lineup by offensive_gravity + defensive_disruption
  - models/artifacts/lineup_optimizer.joblib — serialized lineup optimizer artifact
  - score_lineup() and compare_lineups() convenience methods

affects: [04-api, 05-conversational-ai]

# Tech tracking
tech-stack:
  added: []
  patterns: [lookup-and-score model (no sklearn estimator), per-player stats dict serialized via joblib]

key-files:
  created:
    - models/lineup_optimizer.py
    - models/artifacts/lineup_optimizer.joblib
    - tests/test_lineup_optimizer.py
  modified:
    - models/artifacts/player_impact.joblib

key-decisions:
  - "LineupOptimizer is a lookup + scoring model (not traditional classifier) — stores per-player stats dict, computes scores analytically at predict time"
  - "offensive_gravity = (mean_epa + 10) / 20 clipped to [0,1] — normalizes EPA range [-10, +10] to unit interval"
  - "defensive_disruption = mean_closing_speed / 15 clipped to [0,1] — closing speed max ~15 px/s is normalization ceiling"
  - "Unknown track_ids use league-average fallback stats (epa=0, def_dist=150, closing_speed=5) — no exception raised"
  - "Synthetic fallback generates 20 players with deterministic seed=42 when both DB and PlayerImpactModel unavailable"
  - "player_impact.joblib re-serialized via module import (not __main__) to fix pickle namespace issue from prior plan"

patterns-established:
  - "Lookup-and-score pattern: fit() builds a dict of stats, predict() looks up and computes — no sklearn pipeline needed"
  - "Graceful degradation: DB unavailable -> try PlayerImpactModel artifact -> synthetic fallback, each level logged as warning"

requirements-completed: [ML-05]

# Metrics
duration: 25min
completed: 2026-03-09
---

# Phase 3 Plan 4: Lineup Optimizer Summary

**Lookup-and-score lineup optimizer (ML-05) scoring 5-player lineups by EPA-based offensive gravity and closing-speed-based defensive disruption, serialized to joblib artifact**

## Performance

- **Duration:** 25 min
- **Started:** 2026-03-09T20:15:00Z
- **Completed:** 2026-03-09T20:40:00Z
- **Tasks:** 1 (TDD: 2 commits — test + feat)
- **Files modified:** 4

## Accomplishments
- LineupOptimizer.predict() returns offensive_gravity, defensive_disruption, lineup_score all in [0, 1]
- score_lineup() and compare_lineups() convenience methods with descending sort
- Graceful fallback for unknown track_ids (league-average stats) and missing DB/artifact
- Save/load round-trip verified; lineup_optimizer.joblib artifact at models/artifacts/
- 14 unit tests all passing; all 5 Phase 3 artifacts present

## Task Commits

Each task was committed atomically:

1. **Task 1 RED: add failing tests for LineupOptimizer** - `c83baa1` (test)
2. **Task 1 GREEN: implement LineupOptimizer (ML-05)** - `af32924` (feat)

**Plan metadata:** (docs commit)

_Note: TDD tasks have multiple commits (test RED -> feat GREEN)_

## Files Created/Modified
- `models/lineup_optimizer.py` - LineupOptimizer class: fit/predict/save/load, score_lineup, compare_lineups, _load_defensive_stats, _synthetic_stats, __main__ block
- `models/artifacts/lineup_optimizer.joblib` - Serialized LineupOptimizer artifact
- `tests/test_lineup_optimizer.py` - 14 unit tests covering all behavior specs
- `models/artifacts/player_impact.joblib` - Re-serialized with correct module path (models.player_impact, not __main__)

## Decisions Made
- LineupOptimizer is a lookup + scoring model, not a traditional classifier — stores per-player stats dict and computes analytically, matching plan's architecture spec
- Normalization: offensive_gravity = (mean_epa + 10) / 20 (clips EPA [-10,+10] to [0,1]); defensive_disruption = mean_closing_speed / 15
- Unknown track_ids use league-average fallback (epa=0, def_dist=150, closing_speed=5) without raising exceptions
- Synthetic fallback uses deterministic numpy seed=42 for reproducibility

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Re-serialized player_impact.joblib with correct module namespace**
- **Found during:** Task 1 (GREEN implementation)
- **Issue:** Existing player_impact.joblib was saved with `__main__.PlayerImpactModel` (run as `python models/player_impact.py --train`), causing pickle AttributeError when loaded from any other module context
- **Fix:** Re-ran training via `python -c "from models.player_impact import PlayerImpactModel; ..."` to serialize with `models.player_impact` namespace
- **Files modified:** models/artifacts/player_impact.joblib
- **Verification:** `m2.__class__.__module__ == 'models.player_impact'` confirmed; LineupOptimizer now loads it without error
- **Committed in:** af32924 (feat commit)

---

**Total deviations:** 1 auto-fixed (Rule 1 - Bug)
**Impact on plan:** Necessary fix for PlayerImpactModel integration to work. No scope creep.

## Issues Encountered
- joblib serializes class with whatever `__name__` the module has at save time — running as `__main__` permanently embeds `__main__` as the class module. Fixed by saving from a non-main import context.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- All 5 Phase 3 model artifacts present: shot_probability, momentum_detector, win_probability, player_impact, lineup_optimizer
- Phase 4 API can import LineupOptimizer and call predict({'lineup': [...]}) to get scoring dicts
- PlayerImpactModel.rank_players() feeds lineup optimizer EPA when DB available

## Self-Check: PASSED

- models/lineup_optimizer.py: FOUND
- models/artifacts/lineup_optimizer.joblib: FOUND
- tests/test_lineup_optimizer.py: FOUND
- .planning/phases/03-ml-models/03-04-SUMMARY.md: FOUND
- commit c83baa1 (test RED): FOUND
- commit af32924 (feat GREEN): FOUND

---
*Phase: 03-ml-models*
*Completed: 2026-03-09*
