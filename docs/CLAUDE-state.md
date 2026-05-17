# CourtVision — Current State

> Loaded by Claude on demand. Update this file at session start or when state changes.

## Session State (2026-05-17)
- Branch: `master` | Tests: 960+ pass, 93 skip (excl PG/GPU tests). Phase 8-13 suites all green.
- Phase 13.5 done. In-progress: 80-game run on single RTX 3090 ($5 budget).
- CV games: 17 high/medium quality locally. Goal: 80 total.
- Models: 75 .pkl/.json in `data/models/`. 7 prop models registered (pts/reb/ast/fg3m/blk/tov/stl).
- Props R²: pts=0.47, reb=0.40, ast=0.46, fg3m=0.28, blk=0.18, tov=0.25, stl=0.09
- Prediction: 73 modules in `src/prediction/`. API: 6 endpoints. Stack fully functional on NBA API data.
- Calibration: CalibrationLayer.win_prob() added. Needs prop_residuals.json to train.

## Open Issues
1. `betting_portfolio.kelly_corr` — correlation matrix not populated. Run `--build-residuals` then `--compute-corr`.
2. CV registry sparse (17 games) — target 80 to meaningfully improve R².
3. `ball_valid_pct=0%` on some games: `ball_track_suspended` stays True entire video — investigate after 80-game run.

## Recent Fixes Applied
- `unified_pipeline.py`: max_frames stride bug — `gameplay_frames` (decoded) vs `max_frames` (source units) mismatch at 60fps. Fix: `self.max_frames //= _stride` after stride computed.
- `fetch_games.py`: archive.org fallback (Pass 2.5), android player client for YouTube bot bypass, highlights min_dur=1800s, PREFLIGHT retry loop reads `phase_g_processed.txt` at startup.

## Next Pod Run: RTX 3090 → 80 games
```bash
bash scripts/ingest_preflight.sh && bash scripts/launch_single_3090_pod.sh
```

### Ingest commands
```bash
python -m src.ingest.manifest migrate          # import legacy games to SQLite
python scripts/ingest_fetch.py --count N       # download + verify
python scripts/ingest_process.py --max-games N --parallel K
python scripts/ingest_backfill_quality.py      # score all processed
python scripts/ingest_status.py                # dashboard
python scripts/sync_remote.py --push           # push to B2
python scripts/reset_stale_jobs.py [--hours N] # unstick crashed jobs
```

### Pod settings
PARALLEL=4, OMP=4, BATCH=12, TARGET=90, CUDA_VISIBLE_DEVICES=0
Est: 7-9 hrs | $2.50-4.50 on 3090 (~$0.35-0.50/hr)

### Data sync after run
```bash
scp -P <PORT> root@<IP>:/workspace/nba-ai-system/data/ingest/queue.db data/ingest/
rsync -az -e "ssh -p <PORT>" root@<IP>:/workspace/nba-ai-system/data/tracking/ data/tracking/
rsync -az -e "ssh -p <PORT>" root@<IP>:/workspace/nba-ai-system/data/events/ data/events/
```

## Performance Wins Still On Table
- YOLO prefetch batching: `advanced_tracker.py:898-935` (`_yolo_frame_buf`) wired but inactive. Add `prefetch_yolo(frames)` in `unified_pipeline.py` N=8. Expected: +50% fps. ~30 LOC. MUST quality-diff before merging.
- HSV vectorize in `color_reid.py::classify_dyn` — second-largest hotspot.
