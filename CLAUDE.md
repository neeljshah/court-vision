## CourtVision — NBA CV+ML Pipeline

**What:** Possession-by-possession NBA simulator. CV tracking + NBA API + 90 ML models -> 10K Monte Carlo -> +EV edges vs sportsbooks.
**Moat:** Spatial CV data (defender_distance, spacing, fatigue) from broadcast video.
**Stack:** YOLOv8n -> SIFT homography -> Kalman+Hungarian -> OSNet re-ID -> EasyOCR -> EventDetector -> FastAPI -> Next.js

### State (Session 33, 2026-04-07)
- Branch: `master` | Tests: 960 pass, 93 skip (excl PG tests)
- Phase: Pre-F. Next: season batch (`select_season_games.py` -> `batch_season.py`)
- CV games: 16 A/B-grade / 20 target (5A + 11B). 7 C-grade, 65 F-grade.
- CV registry: 24 player-game records (6 games) via jersey chain resolution
- 2024-25 gamelog_full: DONE (569/569). Props retrained — all 7 models updated.
- Props R2: pts=0.47, reb=0.40, ast=0.46, fg3m=0.28, blk=0.18, tov=0.25 (STL=0.07 still weak)

### Open Issues (priority)
1. 59 unprocessed 2025-26 videos in data/videos/full_games/ — run `python scripts/run_phase_g.py` (GPU needed)
2. STL prop model R2=0.07 — needs more features or different approach
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
- Single-4090 RunPod has ~18-core CFS quota — use `--parallel 3` (NOT 4). `--parallel 4` exhausts quota, CFS throttles, ~3x slower. Launch via `scripts/launch_single_gpu_pod.sh`.
- `_VRAM_FLUSH_INTERVAL` in `unified_pipeline.py` must be 3000 (not 100). Flushing `torch.cuda.empty_cache()` every 100 frames forces GPU syncs that stall CPU stages → 10x slowdown.
