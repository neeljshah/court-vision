# Production Runbook — CourtVision

Operational guide for local dev, RunPod deployment, and data sync.

---

## Pre-Flight Checklist

```bash
# 1. Verify environment
conda activate basketball_ai
python --version      # expect 3.9.x
nvcc --version        # expect CUDA 11.8 (optional — CPU-only mode works for API)

# 2. Verify models exist
ls data/models/*.pkl | wc -l      # expect ~85+ trained ML artifacts
ls data/models/*.json | wc -l     # expect ~20+

# 3. Run tests
python -m pytest tests/ -q
# expect: 2661+ passed (RunPod baseline 2026-05-25), ~26 transient failures (tracking + pyarrow), 0 prediction-critical

# 4. Verify VRAM flush interval (critical for RunPod performance)
grep "_VRAM_FLUSH_INTERVAL" src/pipeline/unified_pipeline.py
# must be 3000, not 100
```

---

## Local Dev

### Start API Server

```bash
conda activate basketball_ai
uvicorn api.main:app --reload
# → http://localhost:8000
# → http://localhost:8000/docs  (Swagger UI)
```

### Run Single Video (headless only)

```bash
python run_clip.py \
  --video data/videos/full_games/game.mp4 \
  --game-id 0022300001 \
  --period 1 \
  --start 0 \
  --no-show
```

### Run Tests

```bash
python -m pytest tests/ -q                    # all tests
python -m pytest tests/test_api.py -q         # API only
python -m pytest tests/ -q -k "not gpu"       # skip GPU tests
```

---

## RunPod Deployment

### Pod Setup (one-time per fresh pod)

```bash
# 1. Install decord — moves video decode to NVDEC, frees ~1.5 cores/worker
pip install decord

# 2. Stage videos to local overlay disk (NOT /workspace — 38x slower for video)
mkdir -p /root/nba_videos
# scp or rsync your H.264 .mp4 files into /root/nba_videos
ln -sf /root/nba_videos /workspace/nba-ai-system/data/videos/full_games

# 3. Quarantine AV1-encoded videos (no hw decode support)
mkdir -p data/videos/full_games_av1_quarantine
# mv <av1_files> data/videos/full_games_av1_quarantine/

# 4. Verify VRAM flush interval (mandatory — wrong value = 10x slowdown)
grep "_VRAM_FLUSH_INTERVAL" src/pipeline/unified_pipeline.py
# must print: _VRAM_FLUSH_INTERVAL = 3000

# 5. Push PBP cache to pod before launch
rsync -az -e "ssh -p $PORT" data/nba/ root@$IP:/workspace/nba-ai-system/data/nba/
```

### Launch Phase G (bash scripts/launch_single_gpu_pod.sh)

```bash
bash scripts/launch_single_gpu_pod.sh <IP> <PORT> [FRAMES]
# Example:
bash scripts/launch_single_gpu_pod.sh 213.192.2.68 40193

# What the script does:
# 1. Verifies _VRAM_FLUSH_INTERVAL = 3000 on pod
# 2. Checks CPU quota (expect ~17.85 cores on 4090 pod)
# 3. Kills stale workers
# 4. Launches: --parallel 4 with OMP_NUM_THREADS=6 (prevents CFS throttling)
```

**Launch environment variables (set by script):**
```bash
OMP_NUM_THREADS=6        # Critical — prevents thread oversubscription
MKL_NUM_THREADS=6
OPENBLAS_NUM_THREADS=6
NUMEXPR_NUM_THREADS=6
MALLOC_ARENA_MAX=2
CUDA_VISIBLE_DEVICES=0
COURTV_NO_LOFTR=1
PHASE_G_VIDEO_DIR=/root/nba_videos
```

### Health Check After Launch

```bash
ssh -p $PORT root@$IP "
  cat /proc/loadavg                                          # 1m should be < 17.85
  cat /sys/fs/cgroup/cpu,cpuacct/cpu.stat | head -3          # baseline
  sleep 60
  cat /sys/fs/cgroup/cpu,cpuacct/cpu.stat | head -3          # nr_throttled Δ should be <30
  pgrep -af run_phase_g.py | grep -v pgrep | wc -l           # expect = parallel count (4)
  grep -oE 'f=[0-9]+' phase_g_batch.log | sort -t= -k2 -n | tail -3"
```

If `nr_throttled` delta > 50/60s: OMP cap is missing or quota changed. Kill and relaunch.

**Expected performance:**
- ~20 fps/worker on 4090 with decord
- ~80 fps aggregate (4 workers)
- WITHOUT decord: ~45 fps aggregate

---

## Data Sync

### Pull Results from Pod (run while pod is active)

```bash
rsync -az -e "ssh -p $PORT" root@$IP:/workspace/nba-ai-system/data/tracking/ data/tracking/
rsync -az -e "ssh -p $PORT" root@$IP:/workspace/nba-ai-system/data/events/ data/events/
scp -P $PORT root@$IP:/workspace/nba-ai-system/data/phase_g_processed.txt data/
scp -P $PORT root@$IP:/workspace/nba-ai-system/data/phase_g_metrics.csv data/
```

### Automated Watch-and-Sync

```bash
bash scripts/watch_and_sync.sh
# Syncs every 5 min while workers are active
# Breaks when all workers finish
# Pulls final processed list on completion
```

**CRITICAL:** Pod ephemeral disk wipes on stop. Always pull results before stopping the pod.

---

## Monitor Progress

```bash
# Tail the batch log
ssh -p $PORT root@$IP "tail -f /workspace/nba-ai-system/phase_g_batch.log"

# Count completed games
wc -l data/phase_g_processed.txt

# Real fps (not the PROFILE log line)
# Real fps = max_frame / wall_seconds_since_worker_start
```

---

## Restart Discipline

**Do NOT restart workers unnecessarily.** Killing workers wastes ~7 min × N workers (each game restarts from frame 0). The processed list prevents reprocessing finished games but does NOT save partial progress.

Only restart if:
- `nr_throttled` delta > 50 (OMP cap missing)
- Workers have stalled (no frame progress for 10+ minutes)
- Pod memory OOM

---

## Troubleshooting

| Symptom | Diagnosis | Fix |
|---------|-----------|-----|
| `nr_throttled` > 50/60s | OMP cap missing, threads oversubscribing | Kill workers, relaunch with `OMP_NUM_THREADS=6` |
| fps < 10/worker | decord not installed or videos on /workspace (slow disk) | `pip install decord`, symlink videos to /root/nba_videos |
| `_VRAM_FLUSH_INTERVAL != 3000` | Pod copy has wrong value | `sed -i 's/_VRAM_FLUSH_INTERVAL = 100/_VRAM_FLUSH_INTERVAL = 3000/' src/pipeline/unified_pipeline.py` |
| One bad video kills queue | No crash isolation | Fixed in d265ece — each game runs in isolated subprocess |
| Empty tracking JSON | Video decode failure (AV1) | Quarantine to `data/videos/full_games_av1_quarantine/` |
| `prop_model_stack` import error | Module path issue | Verify `conda activate basketball_ai` and `PYTHONPATH=.` |
| `load avg > 17.85` | CFS quota hit | OMP cap must be 6 — check all threads |

---

## Watch-and-Sync Script Reference

```bash
# scripts/watch_and_sync.sh env vars
export RUNPOD_HOST=root@<pod_ip>
export RUNPOD_PORT=<pod_port>
# Optional overrides: REMOTE_ROOT, LOCAL_ROOT, SSH_KEY, POLL_SECONDS, SYNC_SECONDS
# Syncs every SYNC_SECONDS (default 300), exits when workers = 0
```

---

*Last verified: 2026-05-25*

---

## Post-Run Checklist

```bash
# 1. Pull all data
rsync -az -e "ssh -p $PORT" root@$IP:/workspace/nba-ai-system/data/tracking/ data/tracking/
rsync -az -e "ssh -p $PORT" root@$IP:/workspace/nba-ai-system/data/events/ data/events/
scp -P $PORT root@$IP:/workspace/nba-ai-system/data/phase_g_metrics.csv data/

# 2. Verify processed list
wc -l data/phase_g_processed.txt     # how many games completed

# 3. Run feature engineering on new tracking data
python src/features/feature_engineering.py --update

# 4. Retrain prop models if new CV features available
python src/prediction/player_props.py --train

# 5. Run tests to verify nothing broke
python -m pytest tests/ -q
```
