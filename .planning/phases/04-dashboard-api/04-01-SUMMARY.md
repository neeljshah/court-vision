---
phase: 04-dashboard-api
plan: 01
subsystem: api
tags: [fastapi, uvicorn, rest-api, predictions, analytics, cors]

# Dependency graph
requires:
  - phase: 03-ml-models
    provides: ShotProbabilityModel, WinProbabilityModel, PlayerImpactModel, LineupOptimizer (joblib artifacts)
  - phase: 01-cv-pipeline-storage
    provides: tracking.database.get_connection(), shot_logs + tracking_coordinates tables
provides:
  - FastAPI REST layer with 7 endpoints (1 health + 3 predictions + 3 analytics)
  - Stable HTTP interface for Phase 5 (Conversational AI) and Streamlit dashboard
  - api/main.py (app factory), api/models_router.py (API-01), api/analytics_router.py (API-02)
affects: [05-conversational-ai, streamlit-dashboard, external-tools]

# Tech tracking
tech-stack:
  added: [fastapi>=0.110.0, uvicorn>=0.29.0, httpx (for TestClient)]
  patterns: [lazy model loading with module-level cache, APIRouter prefix mounting, CORS wildcard for Streamlit]

key-files:
  created:
    - api/main.py
    - api/models_router.py
    - api/analytics_router.py
    - tests/test_models_router.py
  modified:
    - requirements.txt
    - models/artifacts/win_probability.joblib
    - models/artifacts/lineup_optimizer.joblib

key-decisions:
  - "Lazy model loading: models loaded once per process via module-level cache (_get_shot_model etc.) — avoids artifact I/O on every request"
  - "CORS allow_origins=['*'] — intentional for Streamlit dashboard on same host (not public API)"
  - "Analytics endpoints return empty list (not 404) when no game data exists — consumers handle empty states gracefully"
  - "lineup-stats takes comma-separated track_ids string query param (not JSON body) — GET request convention"
  - "Re-saved win_probability and lineup_optimizer artifacts via module import to fix joblib pickle namespace (__main__ -> models.win_probability / models.lineup_optimizer)"

patterns-established:
  - "Router pattern: separate router files (models_router, analytics_router) mounted via app.include_router with prefix"
  - "Model error handling: FileNotFoundError -> 503 (artifact missing), Exception -> 500, invalid params -> 422 (FastAPI native)"
  - "TDD for API routes: write failing tests with mocked model getters, then implement router"

requirements-completed: [API-01, API-02]

# Metrics
duration: 7min
completed: 2026-03-09
---

# Phase 4 Plan 01: Dashboard API Summary

**FastAPI REST layer with 7 endpoints exposing all Phase 3 model predictions and Phase 1-2 analytics via HTTP, including CORS and Swagger docs**

## Performance

- **Duration:** 7 min
- **Started:** 2026-03-09T20:29:04Z
- **Completed:** 2026-03-09T20:36:00Z
- **Tasks:** 3
- **Files modified:** 7

## Accomplishments

- Built FastAPI app factory (api/main.py) with CORSMiddleware, health check, and dual router mounting
- Implemented 3 prediction endpoints (shot probability, win probability, player EPA/100) with lazy model caching
- Implemented 3 analytics endpoints (shot-chart, lineup-stats, tracking) via PostgreSQL and LineupOptimizer
- Fixed joblib pickle namespace bug that prevented WinProbabilityModel and LineupOptimizer from deserializing in production

## Task Commits

Each task was committed atomically:

1. **Task 2 RED - Failing tests for prediction endpoints** - `0aa91d9` (test)
2. **Task 1 - FastAPI app factory** - `43de348` (feat)
3. **Task 2 GREEN - Prediction endpoints router (API-01)** - `5e519d2` (feat)
4. **Task 3 - Analytics endpoints router (API-02)** - `8b4f119` (feat)
5. **Artifact pickle fix** - `e0cab97` (fix)

_Note: TDD tasks have multiple commits (test RED -> feat GREEN)_

## Files Created/Modified

- `api/main.py` - FastAPI app factory, CORSMiddleware, router includes, /health endpoint
- `api/models_router.py` - Prediction endpoints: /predictions/shot, /predictions/win, /predictions/player-impact
- `api/analytics_router.py` - Analytics endpoints: /analytics/shot-chart, /analytics/lineup-stats, /analytics/tracking
- `tests/test_models_router.py` - 8 TDD tests for prediction endpoints (mocked model artifacts)
- `requirements.txt` - Added fastapi>=0.110.0, uvicorn>=0.29.0
- `models/artifacts/win_probability.joblib` - Re-saved with correct module namespace
- `models/artifacts/lineup_optimizer.joblib` - Re-saved with correct module namespace

## Decisions Made

- Lazy model loading via module-level cache: models loaded once per process, avoiding artifact I/O on every prediction request
- CORS allow_origins=["*"]: intentional for Streamlit dashboard integration (not a public API)
- Analytics endpoints return empty list on no-data, not 404: analytics consumers handle empty states gracefully
- lineup-stats uses comma-separated query string for track_ids: GET request convention
- Re-saved joblib artifacts via module import: fixes pickle __main__ namespace bug from CLI training scripts

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed joblib pickle __main__ namespace on win_probability and lineup_optimizer artifacts**
- **Found during:** Task 2 verification (running live server calls)
- **Issue:** WinProbabilityModel and LineupOptimizer artifacts were serialized with `__main__` as the class module (saved via CLI `python models/win_probability.py --train`). When uvicorn or TestClient loaded these, joblib raised `AttributeError: Can't get attribute 'WinProbabilityModel' on <module '__main__' (built-in)>` because the class wasn't in `__main__` in the server context.
- **Fix:** Re-saved both artifacts by importing the classes from their modules (not via __main__) and calling model.fit() + model.save() — pickle now encodes `models.win_probability.WinProbabilityModel` as the class path.
- **Files modified:** models/artifacts/win_probability.joblib, models/artifacts/lineup_optimizer.joblib
- **Verification:** `python -c "joblib.load('win_probability.joblib').__class__.__module__"` returns `models.win_probability`. Full TestClient verification returns 200 for /predictions/win and /analytics/lineup-stats.
- **Committed in:** e0cab97

---

**Total deviations:** 1 auto-fixed (Rule 1 - Bug)
**Impact on plan:** Essential for correctness — win probability and lineup optimizer endpoints would have been non-functional in any production context without this fix.

## Issues Encountered

- fastapi and uvicorn were not installed in the environment but were available via pip (already installed as transitive deps). TestClient also required httpx which was already present.

## User Setup Required

None - no external service configuration required for the API layer itself. Analytics endpoints that query PostgreSQL will return 500 until DATABASE_URL is configured (same requirement as tracking/features phases).

## Next Phase Readiness

- All 7 endpoints functional and verified via TestClient
- /docs Swagger UI available at http://localhost:8000/docs when server running
- Phase 5 (Conversational AI) can call /predictions/* and /analytics/* endpoints
- Streamlit dashboard can call endpoints with CORS already enabled
- Server launch: `python -m uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload`

---
*Phase: 04-dashboard-api*
*Completed: 2026-03-09*

## Self-Check: PASSED

- All 5 files verified to exist on disk
- All 5 commits verified in git log
