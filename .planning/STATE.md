---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
status: planning
stopped_at: Completed 03-ml-models-03-PLAN.md
last_updated: "2026-03-09T20:12:05.690Z"
last_activity: 2026-03-09 — Roadmap created, phases 1-6 defined
progress:
  total_phases: 6
  completed_phases: 2
  total_plans: 12
  completed_plans: 11
  percent: 25
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-03-09)

**Core value:** Raw video goes in, betting-relevant predictions come out — every layer (tracking → features → models → conversational AI) wired together and working.
**Current focus:** Phase 1 — CV Pipeline + Storage

## Current Position

Phase: 1 of 6 (CV Pipeline + Storage)
Plan: 0 of TBD in current phase
Status: Ready to plan
Last activity: 2026-03-09 — Roadmap created, phases 1-6 defined

Progress: [███░░░░░░░] 25%

## Performance Metrics

**Velocity:**
- Total plans completed: 0
- Average duration: -
- Total execution time: 0 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| - | - | - | - |

**Recent Trend:**
- Last 5 plans: none yet
- Trend: -

*Updated after each plan completion*
| Phase 01-cv-pipeline-storage P01 | 2 | 2 tasks | 12 files |
| Phase 01-cv-pipeline-storage P03 | 3 | 2 tasks | 6 files |
| Phase 01-cv-pipeline-storage P02 | 5 | 2 tasks | 7 files |
| Phase 01-cv-pipeline-storage P04 | 9 | 2 tasks | 5 files |
| Phase 02-feature-engineering P01 | 2 | 2 tasks | 5 files |
| Phase 02-feature-engineering P02 | 2 | 2 tasks | 4 files |
| Phase 02-feature-engineering P03 | 3 | 2 tasks | 4 files |
| Phase 02-feature-engineering P04 | 8 | 2 tasks | 6 files |
| Phase 03-ml-models P01 | 4 | 2 tasks | 4 files |
| Phase 03-ml-models P02 | 6 | 2 tasks | 4 files |
| Phase 03-ml-models P03 | 15 | 2 tasks | 3 files |

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- Stack locked: YOLOv8, DeepSORT, PostgreSQL, Streamlit, Plotly, FastAPI, Claude API
- Heavy ML training offloaded to cloud; local GPU used for inference and dev iteration
- Each module must be independently testable
- [Phase 01-cv-pipeline-storage]: Used psycopg2-binary (not psycopg2) to avoid requiring libpq headers on host
- [Phase 01-cv-pipeline-storage]: UUID PKs via gen_random_uuid() (pgcrypto), composite index on tracking_coordinates(game_id, frame_number)
- [Phase 01-cv-pipeline-storage]: Schema-as-SQL pattern: DDL in schema.sql, init_schema() reads and executes idempotently
- [Phase 01-cv-pipeline-storage]: Hardcoded UUID strings in seed SQL (gen_random_uuid() requires DB context; plain INSERT files need literal values)
- [Phase 01-cv-pipeline-storage]: ON CONFLICT (id) DO NOTHING for idempotent seed inserts across games and players dimension tables
- [Phase 01-cv-pipeline-storage]: YOLOv8n pretrained COCO weights without fine-tuning; NBA-specific accuracy deferred to later phases
- [Phase 01-cv-pipeline-storage]: ObjectDetector falls back to yolov8n.pt auto-download if weights_path not found on disk
- [Phase 01-cv-pipeline-storage]: CourtDetector is stateless; designed for periodic calibration (once per game), not per-frame
- [Phase 01-cv-pipeline-storage]: DeepSort returns track_id as str; coerce to int via int(track.track_id) for consistent dict keys in previous_positions
- [Phase 01-cv-pipeline-storage]: Nearest-centroid matching preferred over get_det_class() for object_type — more reliable across DeepSort versions
- [Phase 01-cv-pipeline-storage]: player_id=None for all Phase 1 tracking_coordinates rows — track-to-player mapping deferred to Phase 2
- [Phase 02-feature-engineering]: Shared type contracts as stdlib @dataclass in features/types.py — zero extra dependencies for types module
- [Phase 02-feature-engineering]: Schema extensions in separate features/schema_extensions.sql loaded by init_schema() after base schema — preserves schema-as-SQL pattern
- [Phase 02-feature-engineering]: scipy ConvexHull.volume is 2D area (not .area which is perimeter) — catches silent wrong-value bug
- [Phase 02-feature-engineering]: QhullError imported from scipy.spatial directly — future-proof for scipy 2.0 (deprecated scipy.spatial.qhull removed)
- [Phase 02-feature-engineering]: Screen detection requires nearby player to exceed SCREEN_SPEED_THRESHOLD (not just be relatively faster) — prevents mutual slow-player false positives
- [Phase 02-feature-engineering]: PnR timestamps taken from middle frame of window representing screen contact moment, not setup or separation
- [Phase 02-feature-engineering]: Ball holder = nearest player to ball position each frame; None ball frames leave holder unchanged
- [Phase 02-feature-engineering]: Passing network edges logged to stdout as JSON lines in Phase 2 — no DB table yet (Phase 5 will consume)
- [Phase 02-feature-engineering]: Possession boundary heuristic: speed < 20 px/s for 3+ consecutive frames = ball held/reset (DB-03)
- [Phase 02-feature-engineering]: Shot detection: speed > 400 px/s AND |y - 240| < 60 AND near basket x — completes DB-03
- [Phase 03-ml-models]: BaseModel uses ABC abstractmethod enforcement — compile-time guarantee subclasses implement fit/predict
- [Phase 03-ml-models]: ARTIFACTS_DIR resolved relative to base.py via pathlib — portable across environments
- [Phase 03-ml-models]: load_momentum_data computes lag features via pandas groupby/shift — keeps SQL simple, logic testable
- [Phase 03-ml-models]: load_possession_data won=0 placeholder documented — real win labels require play-by-play data, deferred to v2
- [Phase 03-ml-models]: Synthetic data for ShotProbabilityModel encodes lower defender_dist → higher made rate per plan spec, achieved by splitting rows into close/far halves
- [Phase 03-ml-models]: MomentumDetector synthetic data uses deterministic rule (|scoring_run|>=6 AND streak_delta>=3) with 10% label noise
- [Phase 03-ml-models]: CLI --train blocks catch DB exceptions and fall back to empty DataFrame, enabling dev use without PostgreSQL
- [Phase 03-ml-models]: WinProbabilityModel wraps Pipeline(StandardScaler, RandomForestClassifier) for consistent interface; synthetic label uses momentum-correlated rule
- [Phase 03-ml-models]: PlayerImpactModel is RandomForestRegressor (regression) computing EPA deviation per 100 possessions; rank_players() uses direct regressor call for full aggregated feature vectors

### Pending Todos

None yet.

### Blockers/Concerns

None yet.

## Session Continuity

Last session: 2026-03-09T20:12:05.688Z
Stopped at: Completed 03-ml-models-03-PLAN.md
Resume file: None
