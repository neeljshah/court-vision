## CourtVision — NBA CV+ML Pipeline

**What:** Possession-by-possession NBA simulator. CV tracking + NBA API + 90 ML models -> 10K Monte Carlo -> +EV edges vs sportsbooks.
**Moat:** Spatial CV data (defender_distance, spacing, fatigue) from broadcast video.
**Stack:** YOLOv8n -> SIFT homography -> Kalman+Hungarian -> OSNet re-ID -> EasyOCR -> EventDetector -> FastAPI -> Next.js

### State (Session 31, 2026-04-07)
- Branch: `master` | Tests: 1040 pass, 2 skip (PG)
- Phase: Pre-F. Next: season batch (`select_season_games.py` -> `batch_season.py`)
- CV games: 5 clean / 20 target. Season 2025-26: 0/50.
- ISSUE-065 ball bypass + ISSUE-066 team_abbrev: both FIXED
- ISSUE-054 shot overcounting: code-fixed, unvalidated

### Open Issues (priority)
1. Shot overcounting 2-3x — validate with batch run (ISSUE-054)
2. CV features not wired into ML models — core moat unused
3. Possession simulator unbuilt (Phase 8)
4. No frontend/API serving predictions
5. Gamelog 2023-24 stalled ~200/600 — props retrain blocked
6. Homography low on newer games — reprocess needed

### Task -> Files Cheatsheet
| Task | Load only |
|------|-----------|
| Tracking/detection bug | `unified_pipeline.py` + relevant tracker |
| ML feature | `feature_engineering.py` |
| Prop model | `player_props.py` + `prop_model_stack.py` |
| Betting logic | `betting_portfolio.py` |
| API endpoint | `api/main.py` |
| Batch issue | `batch_season.py` + `unified_pipeline.py` |
| Shot detection | `unified_pipeline.py` (EventDetector section) |
| Homography | `unified_pipeline.py` (_build_panorama, _compute_homography) |
| Re-ID | `osnet_reid.py` + `color_reid.py` |

### Key Paths
```
src/tracking/advanced_tracker.py    # AdvancedFeetDetector
src/tracking/color_reid.py          # TeamColorTracker
src/tracking/osnet_reid.py          # OSNet re-ID 512-dim
src/pipeline/unified_pipeline.py    # Orchestrator
src/features/feature_engineering.py # 60+ features
src/prediction/win_probability.py   # XGBoost win prob
src/prediction/player_props.py      # 7 prop models
src/prediction/betting_portfolio.py # Kelly + CLV
api/main.py                         # FastAPI (10 endpoints)
scripts/batch_season.py             # Batch runner
scripts/select_season_games.py      # Game selector
database/schema.sql                 # PostgreSQL
```

### Rules
- Py3.9 | conda: `basketball_ai` | CUDA 11.8 | RTX 4060 8GB
- Max 300 LOC/file | type hints | docstrings on public API only
- Models -> `data/models/` | Logs -> `vault/Improvements/`
- `# ... existing code ...` for unchanged blocks
- Never re-read data dirs unless asked
- Never run: `run.py`, `loop_processor.py`
- Video: headless only (`--no-show`), never `cv2.imshow`
- No permission prompts — execute autonomously
- Tests: `python -m pytest tests/ -q`
- Full plan: `.planning/ROADMAP.md`
- Full history: `SYSTEM_OPTIMIZED.md` + `vault/Sessions/`
- Game data ref: see `SYSTEM_OPTIMIZED.md` (CLEAN/PARTIAL/BLOCKED list)
