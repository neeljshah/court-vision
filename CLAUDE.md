## CourtVision — NBA CV+ML Pipeline

**What:** Possession-by-possession NBA simulator. CV tracking + NBA API + 90 ML models -> 10K Monte Carlo -> +EV edges vs sportsbooks.
**Moat:** Spatial CV data (defender_distance, spacing, fatigue) from broadcast video.
**Stack:** YOLOv8n -> SIFT homography -> Kalman+Hungarian -> OSNet re-ID -> EasyOCR -> EventDetector -> FastAPI -> Next.js

### State (Session 35+, 2026-04-13)
- Branch: `feat/gpu-pipeline` | Tests: 960 pass, 93 skip (excl PG tests)
- Phase: Phase G active. RunPod pipeline running — 17/59 Phase G games processed.
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
- `_VRAM_FLUSH_INTERVAL` in `unified_pipeline.py` must be 3000 (not 100). Flushing `torch.cuda.empty_cache()` every 100 frames forces GPU syncs that stall CPU stages → 10x slowdown.

### RunPod single-4090 runbook (READ BEFORE LAUNCHING)
Pod has CFS quota of 17.85 cores (1785000/100000 in `/sys/fs/cgroup/cpu,cpuacct/cpu.cfs_quota_us`). Sessions 33–34 burned hours rediscovering this. Don't.

**Required pod-side setup (one-time per fresh pod):**
1. `pip install decord` — moves video decode to NVDEC GPU engine, frees ~1.5 cores/worker. Without this, PyAV CPU decode is the bottleneck. `src/pipeline/unified_pipeline.py:_decord_frame_iter` already prefers it; falls back silently if missing.
2. Stage videos to `/root/nba_videos` (local overlay disk, not `/workspace`). Symlink `data/videos/full_games → /root/nba_videos`. mfs network disk is **38× slower** for video reads.
3. Quarantine AV1-encoded videos (decoder lacks AV1 hw support) to `data/videos/full_games_av1_quarantine/`. Only H.264 in the queue.
4. Verify `_VRAM_FLUSH_INTERVAL = 3000` on the pod copy of `unified_pipeline.py` (the launcher checks this).

**Launch config (current optimum, encoded in `scripts/launch_single_gpu_pod.sh`):**
- `--parallel 4` with `OMP_NUM_THREADS=6 MKL_NUM_THREADS=6 OPENBLAS_NUM_THREADS=6 NUMEXPR_NUM_THREADS=6`
- WITHOUT the OMP cap, parallel-4 oversubscribes threads → 45% of CFS periods throttled → ~3× slowdown. Earlier guidance to use parallel-3 was a workaround for this; with the cap, parallel-4 is healthy (load ~12, throttling <2%).
- WITH cap + decord: aggregate ~80 fps (4 workers × ~20 fps). Without: ~45 fps.

**Health check after launch (run before walking away):**
```
ssh -p $PORT root@$IP "
  cat /proc/loadavg                                       # 1m should be < 17.85
  cat /sys/fs/cgroup/cpu,cpuacct/cpu.stat | head -3       # baseline
  sleep 60
  cat /sys/fs/cgroup/cpu,cpuacct/cpu.stat | head -3       # nr_throttled Δ should be <30
  pgrep -af run_clip.py | grep -v pgrep | wc -l           # expect = parallel count
  grep -oE 'f=[0-9]+' phase_g_p3.log | sort -t= -k2 -n | tail -3"
```
If `nr_throttled` Δ > 50/60s, OMP cap is missing or quota changed.

**fps interpretation:**
- The PROFILE log line `TOTAL=0.3s` per frame is NOT the frame interval (decord batches decode). Real fps = `max_frame / wall_seconds_since_worker_start`. Expect ~20 fps/worker with current setup.

**Data persistence (CRITICAL — pod ephemeral disk wipes on stop):**
- RunPod tracking outputs are NOT auto-synced. After every meaningful run, pull back:
  ```
  rsync -az -e "ssh -p $PORT" root@$IP:/workspace/nba-ai-system/data/tracking/ data/tracking/
  scp -P $PORT root@$IP:/workspace/nba-ai-system/data/phase_g_processed.txt data/
  scp -P $PORT root@$IP:/workspace/nba-ai-system/data/phase_g_metrics.csv data/
  ```
- Set up a cron or post-game hook for this. A finished game on the pod with no rsync = lost work.

**Restart discipline:**
- Killing workers wastes ~7 min × N workers of in-flight progress (each game restarts from frame 0). Don't restart unless throttling is confirmed.
- The processed list (`phase_g_processed.txt`) prevents reprocessing finished games but does NOT save partial progress.

**Real wins still on the table (require code + quality test, do on a branch):**
- YOLO prefetch batching: infra in `advanced_tracker.py:898-935` (`_yolo_frame_buf`) is wired but never activates because the orchestrator is sequential. Add a `prefetch_yolo(frames)` method called by `unified_pipeline.py` with N=8. Expected: +50% fps. ~30 LOC tracker-side change. MUST quality-diff tracking JSON before merging.
- HSV team-color vectorize in `color_reid.py::classify_dyn` — second-largest hotspot.
- Skip: TensorRT (only ~5% gain, YOLO isn't the hotspot), ball-every-2nd-frame (shot detection risk).
