#!/bin/bash
# launch_multigpu.sh — Multi-GPU launch with auto-detection, memory-safe parallelism.
#
# Runs ON THE POD. Spawns N independent run_phase_g.py processes, one per GPU,
# each pinned to a single GPU via CUDA_VISIBLE_DEVICES. Workers share
# phase_g_processed.txt for coordination (file-locked).
#
# Usage:
#   bash scripts/launch_multigpu.sh [PARALLEL_PER_GPU]
#   FULL_GAME=1 bash scripts/launch_multigpu.sh 1    # full-game mode
#   PARALLEL_PER_GPU defaults to 1 (safest, no OOM)
#
# Memory math (RTX 3090/4090, 24GB VRAM, 125GB RAM cgroup):
#   parallel=1: ~30GB RAM peak per GPU worker → safe up to 4 GPUs
#   parallel=2: ~60GB RAM peak per GPU worker → safe up to 2 GPUs
#   parallel=3: ~90GB peak → 1 GPU only
#   parallel=4: ~125GB peak → OOM risk even on 1 GPU
#
# Env vars (override):
#   FULL_GAME=1               (process entire video, no frame cap)
#   FRAMES=18000              (per-game frame cap, ignored if FULL_GAME=1)
#   RSS_KILL_GB=40            (RSS abort threshold per worker)
#   OMP_PER_WORKER=12         (CPU thread cap)
#   BATCH=12                  (YOLO batch size)

set -euo pipefail
PROJ=/workspace/nba-ai-system
PARALLEL_PER_GPU="${1:-1}"
FULL_GAME="${FULL_GAME:-0}"
FRAMES="${FRAMES:-18000}"
RSS_KILL_GB="${RSS_KILL_GB:-40}"
OMP_PER_WORKER="${OMP_PER_WORKER:-12}"

# Build --frames or --full flag
if [ "$FULL_GAME" = "1" ]; then
    FRAMES_FLAG="--full"
    echo "Mode: FULL GAME (no frame cap, RSS kill at ${RSS_KILL_GB}GB)"
else
    FRAMES_FLAG="--frames $FRAMES"
    echo "Mode: CLIP ($FRAMES frames per game)"
fi

cd "$PROJ"

# ── Detect available GPUs ────────────────────────────────────────────────
N_GPUS=$(nvidia-smi --query-gpu=count --format=csv,noheader,nounits | head -1)
[ -z "$N_GPUS" ] || [ "$N_GPUS" -eq 0 ] && { echo "ERROR: no GPUs detected"; exit 1; }
echo "Detected $N_GPUS GPU(s)"
nvidia-smi --query-gpu=index,name,memory.total --format=csv,noheader

# ── Verify VRAM flush interval ───────────────────────────────────────────
FLUSH=$(grep -oE '_VRAM_FLUSH_INTERVAL = [0-9]+' src/pipeline/unified_pipeline.py | head -1)
[[ "$FLUSH" == *"3000"* ]] || { echo "ERROR: $FLUSH (must be 3000)"; exit 1; }

# ── Verify CFS quota ─────────────────────────────────────────────────────
CFS_CORES=$(python3 -c "
try:
    with open('/sys/fs/cgroup/cpu.max') as f:
        q, p = f.read().split()
        if q == 'max': print(64)
        else: print(int(q) // int(p))
except:
    try:
        q = int(open('/sys/fs/cgroup/cpu,cpuacct/cpu.cfs_quota_us').read().strip())
        p = int(open('/sys/fs/cgroup/cpu,cpuacct/cpu.cfs_period_us').read().strip())
        print(q // p)
    except: print(8)
")
echo "CFS cores: $CFS_CORES"

TOTAL_WORKERS=$((N_GPUS * PARALLEL_PER_GPU))
THREADS_PER_WORKER=$(( CFS_CORES / TOTAL_WORKERS ))
[ "$THREADS_PER_WORKER" -lt 4 ] && THREADS_PER_WORKER=4
[ "$THREADS_PER_WORKER" -gt 12 ] && THREADS_PER_WORKER=12
echo "Total workers: $TOTAL_WORKERS, threads per worker: $THREADS_PER_WORKER"

# ── Kill any stale workers ───────────────────────────────────────────────
pkill -KILL -f run_phase_g.py 2>/dev/null || true
pkill -KILL -f run_clip.py 2>/dev/null || true
sleep 2

# ── Launch one run_phase_g.py per GPU ────────────────────────────────────
mkdir -p logs
rm -f phase_g_batch_gpu*.log
for gpu in $(seq 0 $((N_GPUS - 1))); do
    LOG="phase_g_batch_gpu${gpu}.log"
    echo "Launching GPU $gpu (parallel=$PARALLEL_PER_GPU, OMP=$THREADS_PER_WORKER)..."
    nohup env \
        MALLOC_ARENA_MAX=1 \
        MALLOC_MMAP_THRESHOLD_=65536 \
        RSS_KILL_GB=$RSS_KILL_GB \
        OMP_NUM_THREADS=$THREADS_PER_WORKER \
        MKL_NUM_THREADS=$THREADS_PER_WORKER \
        OPENBLAS_NUM_THREADS=$THREADS_PER_WORKER \
        NUMEXPR_NUM_THREADS=$THREADS_PER_WORKER \
        CUDA_VISIBLE_DEVICES=$gpu \
        COURTV_NO_LOFTR=1 \
        YOLO_CONFIG_DIR=/tmp/Ultralytics_gpu${gpu} \
        PHASE_G_VIDEO_DIR=/root/nba_videos \
        PYTORCH_CUDA_ALLOC_CONF="expandable_segments:True,max_split_size_mb:512" \
        python3 scripts/run_phase_g.py $FRAMES_FLAG --parallel "$PARALLEL_PER_GPU" \
        > "$LOG" 2>&1 &
    echo "  PID $! → $LOG"
done

sleep 6
echo ""
echo "Active workers across GPUs:"
nvidia-smi --query-compute-apps=gpu_uuid,pid,process_name,used_memory --format=csv,noheader
echo ""
echo "Monitor with:"
echo "  tail -f phase_g_batch_gpu*.log"
echo "  watch -n 5 nvidia-smi"
