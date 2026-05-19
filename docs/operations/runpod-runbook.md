# RunPod Runbook — GPU Cloud Operations

*GPU cloud operations — CFS quota, OMP thread cap, VRAM flush, data sync.*

---

## Overview

The CV pipeline requires a GPU. Local development runs on an RTX 4060 (8GB). Production ingest runs on RunPod community cloud GPU instances, primarily RTX 3090 ($0.35–0.50/hr) or RTX 4090 ($0.34/hr). Two sessions of RunPod operations (Sessions 33–34) burned hours rediscovering CFS quota behavior — this runbook is the distilled operational knowledge.

---

## Session Quick-Start — Verified Optimized Method (use this)

This is the canonical procedure. It supersedes the parallelism guidance lower in the
runbook. Last verified 2026-05-18: full game (194K frames) processed end-to-end in
68 min, stability 1.000, ball 79%, **zero OOM**.

```bash
export PORT=<ssh_port>  IP=<pod_ip>

# 1. Sync code (pod is NOT a git repo)
rsync -az -e "ssh -p $PORT" --exclude data --exclude '.git' ./ root@$IP:/workspace/nba-ai-system/

# 2. One-time setup on a fresh pod
ssh -p $PORT root@$IP 'bash /workspace/nba-ai-system/scripts/setup_pod_optimized.sh'
ssh -p $PORT root@$IP 'cd /workspace/nba-ai-system && bash scripts/build_trt_engines.sh'

# 3. Launch — full games, max safe parallelism
ssh -p $PORT root@$IP 'cd /workspace/nba-ai-system && FULL_GAME=1 OMP_PER_WORKER=12 RSS_KILL_GB=40 bash scripts/launch_multigpu.sh <N>'
```

**`<N>` = workers per GPU. GPU VRAM is the hard limit — each worker ≈ 3.3 GB VRAM:**

| GPU | Safe `<N>` | Notes |
|-----|-----------|-------|
| RTX 3090 / 4090 (24 GB) | **6** | verified — GPU steady ~20 GB, RAM ~15 GB |
| 40–48 GB (A6000, etc.) | 10–12 | RAM (~5 GB/worker) becomes the limit |

Rule: `N ≈ floor(VRAM_GB / 3.5)`. The old "1 per GPU" guidance below was a
pre-fix workaround for the memory leak — **obsolete since the CSRT init fix**.

**Why this is the optimized method:**
- TRT engines rebuilt for the pod GPU with `dynamic=True, batch=16` (FP16) — no CPU fallback
- CSRT degenerate-bbox guard (`ball_detect_track.py`) — kills the deterministic full-game OOM
- `RSS_KILL_GB=40` per-worker abort — graceful flush instead of cgroup SIGKILL
- `MALLOC_ARENA_MAX=1`, `PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True` — RAM/VRAM frag caps
- Memory holds flat (~2.5 GB/worker steady) for the entire game — verified 194K frames

**Watch during the run:** GPU must stay < 23 GB, cgroup < 80 GB. `nvidia-smi`,
`cat /sys/fs/cgroup/memory.current`. A worker count is `ps -C python3 | grep -c run_clip`.

For the full data-collection sequence (NBA API Tier 1 + this as Tier 2) see
`.planning/DATA_VISION.md` §Data Acquisition Strategy.

---

## Current Run Spec

**Target:** Full-game processing (all frames, not 10-min clips)  
**Hardware:** RTX 3090 (24 GB) — 6 workers in parallel on one GPU  
**Verified time per game:** ~68 min (194K-frame game, 6-way GPU share)  
**Verified cost per game:** ~$0.10–0.13 (one $0.40/hr pod ÷ 6 workers)  
**Quality:** stability 1.000, id_switches 0, ball detection ~79%  
**Launch command:** `FULL_GAME=1 OMP_PER_WORKER=12 bash scripts/launch_multigpu.sh 6` (see §Session Quick-Start)  
**Full config doc:** [`docs/operations/full-game-production.md`](full-game-production.md)

### Previous Run (80-game clips)
**Target:** 80 games, 18K frames each (10-min clips)  
**Hardware:** Single RTX 3090  
**Actual time:** ~7 hours  
**Actual cost:** ~$3.00

---

## Critical Configuration (Read Before Launch)

### CPU CFS Quota

RunPod pods have a CFS (Completely Fair Scheduler) quota. On the typical community 3090, this is approximately 17.85 virtual cores (`cat /sys/fs/cgroup/cpu,cpuacct/cpu.cfs_quota_us` ÷ 100000). Sessions 33–34 burned hours chasing apparent GPU bottlenecks that were actually CPU throttling from thread oversubscription.

**Required thread cap:** Set these environment variables before launching workers:
```bash
export OMP_NUM_THREADS=6
export MKL_NUM_THREADS=6
export OPENBLAS_NUM_THREADS=6
export NUMEXPR_NUM_THREADS=6
```

Without this cap, 4 parallel workers each spawn default thread pools (~16 threads each = 64 threads for 17.85-core quota) → 45% of CFS periods throttled → ~3× slowdown. With the cap: load stays at ~12, throttling < 2%, aggregate throughput ~80 fps.

**Wrong guidance from Session 33:** Using parallel=3 was a workaround for thread oversubscription. With the OMP cap, parallel=4 is healthy and correct.

### VRAM Flush Interval

`_VRAM_FLUSH_INTERVAL` in `unified_pipeline.py` **must** be 3000. Do not change to 100. Flushing `torch.cuda.empty_cache()` every 100 frames forces GPU sync barriers between frames, stalling the CPU stages → 10× slowdown. The launcher script checks this value and will refuse to start if it's wrong.

### Video Decode: decord vs PyAV

Install decord on the pod before launching:
```bash
pip install decord
```

decord uses NVDEC GPU hardware for video decode, freeing ~1.5 CPU cores per worker. Without it, PyAV CPU decode becomes the bottleneck at ~4 cores per worker. The pipeline falls back silently to PyAV if decord is missing; performance will be materially lower.

### Video Location

Stage videos to local disk, not the network filesystem:
```bash
mkdir -p /root/nba_videos
# Copy videos from /workspace (network) to /root (local SSD)
cp /workspace/nba-ai-system/data/videos/full_games/*.mp4 /root/nba_videos/
# Create symlink for pipeline to find them
ln -sf /root/nba_videos /workspace/nba-ai-system/data/videos/full_games_local
```

NFS reads are ~38× slower for sequential video access. Missing this step converts a 7-hour run into a 60-hour run.

### H.264 Only

AV1-encoded videos must be quarantined before processing — the decoder lacks AV1 hardware support:
```bash
python scripts/quarantine_av1.py --scan data/videos/full_games/
# Moves AV1 files to data/videos/full_games_av1_quarantine/
```

---

## Pre-Launch Checklist

```bash
# On the pod:

# 1. Confirm CFS quota
cat /sys/fs/cgroup/cpu,cpuacct/cpu.cfs_quota_us
# Should be >= 1785000 (17.85 cores)

# 2. Confirm VRAM flush interval
grep _VRAM_FLUSH_INTERVAL src/pipeline/unified_pipeline.py
# Must show: _VRAM_FLUSH_INTERVAL = 3000

# 3. Install decord
pip install decord
python -c "import decord; print('decord OK')"

# 4. Stage videos to local disk (see above)

# 5. Quarantine AV1 videos
python scripts/quarantine_av1.py --scan data/videos/full_games/

# 6. Export YouTube cookies (doubles download success)
# On local machine: install "Get cookies.txt LOCALLY" Chrome extension
# Go to youtube.com while logged in → Export as data/videos/youtube_cookies.txt
# Upload to pod: scp -P $PORT youtube_cookies.txt root@$IP:/workspace/.../data/videos/

# 7. Push PBP cache to pod (ensures possession_outcome_model has data)
rsync -az -e "ssh -p $PORT" data/nba/ root@$IP:/workspace/nba-ai-system/data/nba/

# 8. Import legacy games to ingest queue
python -m src.ingest.manifest migrate
```

---

## Launch — Optimized Multi-GPU (recommended, Phase G2+)

For pods on Python 3.12 / CUDA 12.8+ with any number of GPUs:

```bash
# One-time setup on a fresh pod (after bootstrap_pod.sh pushes code):
ssh -p <PORT> root@<IP> 'bash /workspace/nba-ai-system/scripts/setup_pod_optimized.sh'

# Launch (auto-detects GPU count):
ssh -p <PORT> root@<IP> 'cd /workspace/nba-ai-system && bash scripts/launch_multigpu.sh 1'
# Arg = PARALLEL_PER_GPU. Use 1 (safe), 2 (aggressive, needs >40GB VRAM/GPU).
```

The optimized launcher:
1. Detects available GPUs and pins one `run_phase_g.py` to each via `CUDA_VISIBLE_DEVICES`
2. Auto-sizes OMP threads from CFS quota / total workers
3. Sets `PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True,max_split_size_mb:512` (cuts VRAM frag)
4. Sets `MALLOC_ARENA_MAX=1` (cuts glibc RAM frag)
5. Each GPU writes to its own `phase_g_batch_gpu<N>.log` for isolated debugging

**Critical fixes vs legacy `launch_single_3090_pod.sh`:**

| Issue | Legacy | Optimized |
|-------|--------|-----------|
| YOLO ball inference | FP32, imgsz=640, device unset → CPU fallback | FP16 (`half=True`), imgsz=384, `device=0` |
| Python 3.12 pip | Blocked by PEP 668 | `--break-system-packages` |
| Pod has different GPU than dev | TRT engines fail to load → CPU fallback | `build_trt_engines.sh` rebuilds for pod GPU |
| Multi-GPU pod | Single-GPU only | Auto-distributes workers per GPU |
| Memory peaks at 116GB | parallel=4 caused 1.7M cgroup hits → OOM kills | parallel=1 per GPU + memory caps |
| Kornia GPU blob fallback | Not installed → falls through to CPU Hough | Installed by setup script |

**Settings (optimized):**
- `--parallel 1` per GPU (no OOM risk; bump to 2 only on 40GB+ VRAM)
- `OMP_NUM_THREADS=$(CFS_cores / total_workers)` (auto)
- `PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True`
- `MALLOC_ARENA_MAX=1`
- `device=0`, `half=True`, `imgsz=384` for ball YOLO

## Launch — Legacy (single 3090, RTX 4060-derived TRT engines)

```bash
bash scripts/ingest_preflight.sh && bash scripts/launch_single_3090_pod.sh
```

The legacy launcher:
1. Validates VRAM flush interval
2. Sets OMP thread caps
3. Launches 4 parallel workers
4. Starts log monitoring

**Legacy settings:**
- `--parallel 4` (causes OOM on Python 3.12 + RTX 3090 — use optimized launcher instead)
- `OMP_NUM_THREADS=6`
- `BATCH=12`
- `CUDA_VISIBLE_DEVICES=0`

---

## Health Check (Run 60 Seconds After Launch)

```bash
# Confirm load is reasonable (should be < 17.85)
cat /proc/loadavg

# Baseline CPU throttle stats
cat /sys/fs/cgroup/cpu,cpuacct/cpu.stat | head -3

# Wait 60 seconds, then check delta
sleep 60
cat /sys/fs/cgroup/cpu,cpuacct/cpu.stat | head -3
# nr_throttled delta should be < 30 per 60s

# Confirm expected number of workers running
pgrep -af "ingest_process" | grep -v pgrep | wc -l
# Expect: 4

# Check fps from log
grep -oE 'fps=[0-9.]+' logs/ingest.log | tail -10
# Expect: ~20 fps per worker
```

**If nr_throttled Δ > 50 per 60s:** OMP cap is missing or the CFS quota is lower than expected. Stop, re-check thread environment variables, restart.

**fps interpretation:** The PROFILE log shows `TOTAL=0.3s` per frame — this is NOT the frame interval (decord batches decode). Real fps = `max_frame / wall_seconds_since_worker_start`. Expect ~20 fps/worker.

---

## Monitoring During Run

```bash
# Watch ingest queue status
watch -n 30 python scripts/ingest_status.py

# Stream a worker's log
tail -f logs/ingest_worker_0.log | grep -E 'fps|ERROR|game_id'

# Watch GPU utilization
watch -n 5 nvidia-smi
```

---

## Post-Run Data Pull

**Critical: RunPod ephemeral disk wipes on pod stop. Pull data before stopping.**

```bash
# From local machine:
export PORT=<ssh_port>
export IP=<pod_ip>

# Pull tracking and events data
rsync -az -e "ssh -p $PORT" root@$IP:/workspace/nba-ai-system/data/tracking/ data/tracking/
rsync -az -e "ssh -p $PORT" root@$IP:/workspace/nba-ai-system/data/events/ data/events/

# Pull ingest queue state
scp -P $PORT root@$IP:/workspace/nba-ai-system/data/ingest/queue.db data/ingest/

# Pull metrics
scp -P $PORT root@$IP:/workspace/nba-ai-system/data/phase_g_processed.txt data/
scp -P $PORT root@$IP:/workspace/nba-ai-system/data/phase_g_metrics.csv data/
```

If B2 credentials are configured in `.env`, use auto-sync:
```bash
python scripts/sync_remote.py --push
```

---

## Restart Discipline

Do NOT restart workers unless throttling is confirmed. Killing a worker loses all in-flight progress for that game — each game restarts from frame 0. This wastes ~7 minutes × N workers of in-flight work.

The `phase_g_processed.txt` file prevents reprocessing of already-finished games but does NOT save partial progress on in-flight games.

**When to restart:** Only if `nr_throttled` Δ is confirmed > 50/60s and the OMP cap fix has been applied. Then stop workers cleanly and restart with corrected configuration.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| `nr_throttled` Δ > 50/60s | OMP cap missing | Add thread env vars; restart |
| fps < 5 | Video on NFS | Stage to local disk; restart |
| CUDA OOM | `_VRAM_FLUSH_INTERVAL` too high | Confirm it's 3000 (not higher) |
| Worker hangs + RAM → 124 GB → SIGKILL mid-game | CSRT `.init()` on out-of-frame ball bbox (fixed 2026-05-18) | Confirm `ball_detect_track.py` has the degenerate-bbox guard before `.init()`; rebuild pod copy if missing |
| `ball_track_suspended` True for whole game | Known bug, ~8% of games | Skip; will triage at N=80 |
| re-ID coverage < 8 players | Lighting / broadcast angle | Game excluded from CV training set |
| Worker stuck on same game > 2 hours | Crashed worker | `python scripts/reset_stale_jobs.py --hours 2` |

---

## After the 80-Game Run

Next steps (see Phase 1 in [MASTER_PLAN.md](../../MASTER_PLAN.md)):
1. Run `python scripts/ingest_backfill_quality.py` to score all 80 games
2. Run `python scripts/build_residuals.py --from-tracking` to regenerate prop_residuals.json
3. Retrain Tier 3–4 models: `python scripts/train_cv_models.py --tier 3,4`
4. Validate A/B: Δ R² ≥ +0.05 on holdout vs pre-80-game model
5. Run calibration: `python scripts/calibrate_models.py --all-props`
6. Run SportVU validation on any 2015-16 games in the set

---

*See [data-pipeline.md](data-pipeline.md) for the ingest system architecture. See [cv-pipeline.md](../architecture/cv-pipeline.md) for the pipeline being run on the pod.*
