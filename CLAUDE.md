## CourtVision — NBA CV+ML Pipeline

**What:** Possession-by-possession NBA simulator. CV tracking + NBA API + 90 ML models -> 10K Monte Carlo -> +EV edges vs sportsbooks.
**Moat:** Spatial CV data (defender_distance, spacing, fatigue) from broadcast video.
**Stack:** YOLOv8n -> SIFT homography -> Kalman+Hungarian -> OSNet re-ID -> EasyOCR -> EventDetector -> FastAPI -> Next.js

### State (Session 33, 2026-04-07)
- Branch: `master` | Tests: 1042 pass, 93 skip
- Phase: Pre-F. Next: season batch (`select_season_games.py` -> `batch_season.py`)
- CV games: 14 A/B-grade / 20 target. Season 2025-26: 2 processed, 59 videos waiting
- CV registry: 24 player-game records (backfill improved jersey chain resolution)
- 2024-25 gamelog_full: DONE (569/569). Props retrain running.
- A1 shot dashboard 2025-26: MISSING (fetching)

### Open Issues (priority)
1. 59 unprocessed 2025-26 videos in data/videos/full_games/ — run `python scripts/run_phase_g.py` (GPU needed)
2. Props models: retrain in progress with 2024-25 data (all 7 flagged needs_retrain)
3. CV registry sparsity — 24 records across 6 games; needs better OCR/player resolution
4. Possession simulator unbuilt (Phase 8)
5. No frontend/API serving predictions
6. Homography low on older games — reprocess needed

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
