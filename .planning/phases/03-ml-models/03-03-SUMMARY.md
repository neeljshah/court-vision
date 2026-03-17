---
phase: 03-ml-models
plan: "03"
subsystem: models
tags: [sklearn, joblib, pandas, numpy, random-forest, regression, classification, tdd]

# Dependency graph
requires:
  - phase: 03-ml-models
    plan: "01"
    provides: "BaseModel ABC, ARTIFACTS_DIR, load_possession_data, load_player_event_data"
provides:
  - "WinProbabilityModel — RandomForestClassifier wrapper, predict() returns float [0,1]"
  - "PlayerImpactModel — RandomForestRegressor EPA per 100 possessions, rank_players() sorted list"
  - "models/artifacts/win_probability.joblib — trained and serialized"
  - "models/artifacts/player_impact.joblib — trained and serialized"
affects:
  - "03-04-lineup-optimization"
  - "04-api"

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Synthetic fallback pattern — both models fall back to seeded numpy data when DB empty (seed=42)"
    - "Momentum-correlated synthetic labels — win labels derived from scoring_run/possession_streak rule"
    - "EPA deviation formula — (made_rate - 0.45) * 2.2 * 100 for per-100 scaling"
    - "groupby.apply with include_groups=False — forward-compatible pandas aggregation"

key-files:
  created:
    - "models/win_probability.py — WinProbabilityModel (already present from prior session)"
    - "models/player_impact.py — PlayerImpactModel with fit, predict, rank_players, _aggregate"
    - "tests/test_player_impact.py — 12 tests covering all behaviors"
  modified: []

key-decisions:
  - "WinProbabilityModel wraps Pipeline(StandardScaler, RandomForestClassifier) — keeps interface consistent even though RF is scale-invariant"
  - "Synthetic win label: scoring_run > 0 AND possession_streak >= 2, OR swing_point=1 AND scoring_run > 0 — momentum-correlated approximation for v1"
  - "PlayerImpactModel uses RandomForestRegressor (regression, not classification) because EPA is a continuous deviation from league average"
  - "rank_players() uses pre-aggregated features directly in predict to ensure consistent EPA values with fit() training"
  - "groupby.apply include_groups=False applied to suppress pandas 2.x deprecation warning — future-proof"
  - "Both models' --train CLIs catch DB exceptions and fall back to empty DataFrame — dev use without PostgreSQL"

patterns-established:
  - "Pattern: Synthetic data always uses seed=42 for reproducibility across all models"
  - "Pattern: predict() at inference time uses fixed avg_confidence=0.75 and x_mean=400.0 (neutral) when per-player stats unavailable"
  - "Pattern: rank_players() bypasses predict() dict interface in favor of direct regressor call for aggregated feature rows"

requirements-completed: [ML-02, ML-04]

# Metrics
duration: 15min
completed: "2026-03-09"
---

# Phase 3 Plan 03: Win Probability and Player Impact Models Summary

**WinProbabilityModel (RandomForestClassifier, float [0,1]) and PlayerImpactModel (RandomForestRegressor, EPA per 100 possessions) both trained on synthetic data, serialized to joblib, and validated with 20 combined TDD tests.**

## Performance

- **Duration:** ~15 min
- **Started:** 2026-03-09T20:05:00Z
- **Completed:** 2026-03-09T20:20:00Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments

- WinProbabilityModel: predicts win probability [0,1] per possession using convex_hull_area, avg_inter_player_dist, scoring_run, possession_streak, swing_point — synthetic label encodes momentum-correlated win patterns
- PlayerImpactModel: predicts EPA deviation from league average per 100 possessions; _aggregate() computes per-player made_rate, shots_taken, cut_rate, screen_rate, avg_confidence, x_mean from event log; rank_players() returns sorted list by EPA
- Both models have --train CLI with DB fallback, serialize to models/artifacts/, and round-trip correctly through joblib save/load

## Task Commits

Each task was committed atomically:

1. **Task 1: Win probability model (ML-02) — RED** - `3872a71` (test)
2. **Task 1: Win probability model (ML-02) — GREEN** - `fb8bd53` (feat)
3. **Task 2: Player impact model (ML-04) — RED** - `b7db14a` (test)
4. **Task 2: Player impact model (ML-04) — GREEN** - `941791a` (feat)

_TDD tasks have test (RED) + feat (GREEN) commits._

## Files Created/Modified

- `models/win_probability.py` — WinProbabilityModel: Pipeline(StandardScaler, RandomForestClassifier(200 estimators, depth 5)); synthetic fallback 200 rows
- `models/player_impact.py` — PlayerImpactModel: RandomForestRegressor(100 estimators, depth 4); EPA formula; rank_players(); synthetic fallback 10 players
- `tests/test_player_impact.py` — 12 tests: predict(), epa_per_100 type, monotonicity, fit fallbacks, save/load, rank_players(), _aggregate() columns

## Decisions Made

- WinProbabilityModel wraps sklearn Pipeline with StandardScaler even though RF is scale-invariant — keeps the interface consistent with other models that need scaling
- Synthetic win label uses momentum rule (scoring_run > 0 AND streak >= 2, OR swing_point with positive run) — appropriate v1 approximation while play-by-play data is unavailable
- PlayerImpactModel is a regressor, not classifier, because EPA is a continuous value (deviation from league average), not a binary outcome
- rank_players() uses direct regressor.predict() with full aggregated feature vectors rather than routing through predict() dict interface — ensures EPA values align with what the model actually learned

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Suppressed pandas 2.x deprecation warning in _aggregate()**
- **Found during:** Task 2 (PlayerImpactModel implementation)
- **Issue:** `groupby.apply` without `include_groups=False` triggers DeprecationWarning in pandas 2.x (grouping columns will be excluded in future version — would silently break aggregation)
- **Fix:** Added `include_groups=False` to `df.groupby("track_id").apply(...)` call
- **Files modified:** models/player_impact.py
- **Verification:** 12 tests pass with no warnings
- **Committed in:** 941791a (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (Rule 1 — forward compatibility fix)
**Impact on plan:** Fix prevents silent breakage on pandas 2.x upgrade. No scope creep.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- PlayerImpactModel.rank_players() is the prerequisite for Plan 04 lineup optimization — epa_per_100 per player is the scoring signal for lineup EPA
- Both models are serialized and loadable — Phase 4 API can load artifacts without retraining
- models/artifacts/win_probability.joblib and models/artifacts/player_impact.joblib are present

---
*Phase: 03-ml-models*
*Completed: 2026-03-09*
