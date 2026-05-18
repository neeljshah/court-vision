#!/bin/bash
# bootstrap_pod.sh — One-shot setup + launch for a fresh RunPod.
#
# Usage:
#   bash scripts/bootstrap_pod.sh <IP> <PORT>
#   # Example: bash scripts/bootstrap_pod.sh <pod-ip> <ssh-port>
#
# What it does:
#   1. Pushes current code to pod (scp, no rsync needed)
#   2. Installs all Python deps
#   3. Copies videos to fast overlay disk (/root/nba_videos)
#   4. Quarantines AV1 videos + removes already-processed ones
#   5. Verifies VRAM flush, CPU quota, GPU
#   6. Launches Phase G batch (parallel 4, --frames 18000)
#   7. Runs 60s health check
#
# Handles: no rsync, no ffprobe, no bc, full_games as real dir (not symlink)

set -euo pipefail

IP="${1:?Usage: bash scripts/bootstrap_pod.sh <IP> <PORT>}"
PORT="${2:?Usage: bash scripts/bootstrap_pod.sh <IP> <PORT>}"
KEY="${3:-$HOME/.ssh/id_rsa}"
SSH="ssh -o StrictHostKeyChecking=no -o ConnectTimeout=15 -i ${KEY} -p ${PORT} root@${IP}"
SCP="scp -o StrictHostKeyChecking=no -i ${KEY} -P ${PORT}"
PROJ="/workspace/nba-ai-system"

log() { echo "[$(date '+%H:%M:%S')] $*"; }

# ── Step 1: Test connection ───────────────────────────────────────────
log "Step 1: Testing SSH to ${IP}:${PORT}..."
$SSH "echo 'connected' && nvidia-smi --query-gpu=name,memory.total --format=csv,noheader && cat /proc/loadavg" || {
    echo "ERROR: Cannot SSH to pod. Check IP/PORT."; exit 1
}

# ── Step 2: Push code via scp (no rsync on Windows) ──────────────────
log "Step 2: Pushing code to pod..."
# Create all src subdirs
$SSH "mkdir -p ${PROJ}/src/{analytics,data,detection,features,fusion,ingest,nlp,pipeline,prediction,re_id/models,re_id/module,simulation,stats_tracker,tracking/utils,utils,websocket} ${PROJ}/scripts ${PROJ}/api ${PROJ}/data/models"

# Push all Python files in every src subdir
for subdir in src src/analytics src/data src/detection src/features src/fusion src/ingest src/nlp src/pipeline src/prediction src/re_id src/re_id/models src/re_id/module src/simulation src/stats_tracker src/tracking src/tracking/utils src/utils src/websocket; do
    files=()
    for f in ${subdir}/*.py; do [ -f "$f" ] && files+=("$f"); done
    [ ${#files[@]} -gt 0 ] && $SCP "${files[@]}" root@${IP}:${PROJ}/${subdir}/ 2>/dev/null || true
done

# Scripts and data
$SCP scripts/run_clip.py scripts/run_phase_g.py scripts/quality_gate_gpu_pipeline.py root@${IP}:${PROJ}/scripts/
$SCP data/phase_g_processed.txt data/phase_g_metrics.csv root@${IP}:${PROJ}/data/ 2>/dev/null || true

# Resources (court map, panos, model weights) — required for pipeline startup
$SSH "mkdir -p ${PROJ}/resources"
for f in resources/2d_map.png resources/pano_enhanced.png resources/pano.png resources/yolov8n.pt resources/osnet_x025.onnx resources/Rectify1.npy resources/RectifyL.npy resources/RectifyR.npy; do
    [ -f "$f" ] && $SCP "$f" root@${IP}:${PROJ}/${f} 2>/dev/null || true
done

log "  Code pushed."

# ── Step 3: Install all deps ─────────────────────────────────────────
log "Step 3: Installing Python deps..."
$SSH bash <<'DEPS'
set -e
pip install -q decord av pandas xgboost scikit-learn nba_api easyocr ultralytics scipy gdown tensorboard 2>&1 | tail -3
pip install -q torchreid 2>&1 | tail -3
python3 -c "
import torch, ultralytics, decord, av, easyocr, torchreid, pandas, scipy
print(f'torch {torch.__version__} CUDA={torch.cuda.is_available()} GPU={torch.cuda.get_device_name(0)}')
print('ALL DEPS OK')
" 2>&1 | grep -E 'torch|ALL DEPS|Error'
DEPS

# ── Step 4: Stage videos to fast overlay disk ─────────────────────────
log "Step 4: Staging videos to /root/nba_videos (overlay, 38x faster than mfs)..."
$SSH bash <<'STAGE'
set -e
mkdir -p /root/nba_videos
# Fix 6: require >=100GB free on overlay disk before staging videos
free_kb=$(df /root/nba_videos 2>/dev/null | awk 'NR==2{print $4}')
free_gb=$(( ${free_kb:-0} / 1024 / 1024 ))
if [ "$free_gb" -lt 100 ]; then
    echo "ERROR: /root/nba_videos has only ${free_gb}GB free — need at least 100GB. Aborting."
    exit 1
fi
echo "  Disk free on /root: ${free_gb}GB — OK"
# Copy from network disk to overlay (if videos exist on network disk)
SRC="/workspace/nba-ai-system/data/videos/full_games"
if [ -d "$SRC" ] && [ ! -L "$SRC" ]; then
    count=$(ls "$SRC"/*.mp4 2>/dev/null | wc -l)
    if [ "$count" -gt 0 ]; then
        echo "  Copying $count videos from network disk to overlay..."
        cp -n "$SRC"/*.mp4 /root/nba_videos/ 2>/dev/null || true
    fi
fi
echo "  Videos on overlay: $(ls /root/nba_videos/*.mp4 2>/dev/null | wc -l)"
ls -lhS /root/nba_videos/*.mp4 2>/dev/null || echo "  (none)"
STAGE

# ── Step 5: Quarantine bad videos (AV1, non-decodable, already processed) ─
log "Step 5: Quarantining AV1 + removing already-processed..."
$SSH bash <<'QUARANTINE'
set -e
cd /root/nba_videos

# Read processed list
DONE="/workspace/nba-ai-system/data/phase_g_processed.txt"
processed=""
[ -f "$DONE" ] && processed=$(cat "$DONE")

removed=0
quarantined=0

shopt -s nullglob
for v in *.mp4; do
    [ -f "$v" ] || continue
    stem="${v%.mp4}"

    # Skip already-processed games
    if echo "$processed" | grep -qw "$stem"; then
        echo "  SKIP (done): $v"
        rm -f "$v"
        removed=$((removed+1))
        continue
    fi

    # Test with decord — if it fails, quarantine
    result=$(python3 -c "
from decord import VideoReader
try:
    vr = VideoReader('$v')
    print(f'OK {len(vr)}')
    del vr
except Exception as e:
    print(f'FAIL {e}')
" 2>/dev/null)

    if echo "$result" | grep -q "^FAIL"; then
        echo "  QUARANTINE (decode fail): $v — $result"
        mkdir -p /workspace/nba-ai-system/data/videos/av1_quarantine
        mv "$v" /workspace/nba-ai-system/data/videos/av1_quarantine/
        quarantined=$((quarantined+1))
    else
        frames=$(echo "$result" | grep -oE '[0-9]+')
        echo "  OK: $v — $frames frames"
    fi
done

echo "  Removed (already done): $removed"
echo "  Quarantined (bad codec): $quarantined"
echo "  Ready to process: $(ls /root/nba_videos/*.mp4 2>/dev/null | wc -l)"
QUARANTINE
# Fix 8: print final AV1 quarantine count from the workspace dir
$SSH "echo \"AV1 quarantined: \$(ls /workspace/nba-ai-system/data/videos/av1_quarantine/*.mp4 2>/dev/null | wc -l)\""

# ── Step 6: Verify critical settings ─────────────────────────────────
log "Step 6: Verifying pipeline settings..."
FLUSH=$($SSH "grep -oE '_VRAM_FLUSH_INTERVAL = [0-9]+' ${PROJ}/src/pipeline/unified_pipeline.py | head -1")
echo "  ${FLUSH}"
if [[ "$FLUSH" != *"3000"* ]]; then
    echo "  ERROR: _VRAM_FLUSH_INTERVAL must be 3000. Aborting."; exit 1
fi

# CPU + RAM check — auto-select parallel count
PARALLEL=$($SSH 'python3 -c "
import os
# CPU quota
try:
    q = int(open(\"/sys/fs/cgroup/cpu,cpuacct/cpu.cfs_quota_us\").read().strip())
    p = int(open(\"/sys/fs/cgroup/cpu,cpuacct/cpu.cfs_period_us\").read().strip())
    cores = q / p
except:
    cores = os.cpu_count() or 4

# RAM (MemAvailable from /proc/meminfo, in GB)
try:
    mem_kb = int([l for l in open(\"/proc/meminfo\").readlines() if l.startswith(\"MemTotal\")][0].split()[1])
    mem_gb = mem_kb / 1024 / 1024
except:
    mem_gb = 32

# Each worker needs ~12GB RSS (YOLO + OSNet + SIFT + tracking state + PyAV decode).
# With COURTV_NO_OCR=1, PaddleOCR is skipped (saves ~10GB/worker).
# Leave 20GB headroom for system + shared CUDA context.
max_by_ram = max(1, int((mem_gb - 20) / 12))
max_by_cpu = max(1, int(cores / 4))
parallel = min(4, max_by_ram, max_by_cpu)

print(f\"  CPU quota: {cores:.1f} cores | RAM: {mem_gb:.0f}GB | → --parallel {parallel}\")
print(parallel)
" 2>/dev/null | tail -1')
PARALLEL="${PARALLEL:-2}"
echo "  Using --parallel ${PARALLEL}"

# GPU check
$SSH "nvidia-smi --query-gpu=name,memory.total,memory.free --format=csv,noheader | sed 's/^/  GPU: /'"

OMP_THREADS=6

# ── Step 7: Launch Phase G ────────────────────────────────────────────
log "Step 7: Killing stale workers + launching Phase G (parallel=${PARALLEL})..."
$SSH "pgrep -f '[r]un_phase_g.py' | xargs -r kill -TERM 2>/dev/null; sleep 2; pgrep -f '[r]un_clip.py' | xargs -r kill -KILL 2>/dev/null; true"

$SSH "sysctl -w vm.max_map_count=1048576 2>/dev/null || true"
$SSH "cd ${PROJ} && rm -f phase_g_batch.log && \
    MALLOC_ARENA_MAX=2 \
    MALLOC_MMAP_THRESHOLD_=65536 \
    OMP_NUM_THREADS=${OMP_THREADS} \
    MKL_NUM_THREADS=${OMP_THREADS} \
    OPENBLAS_NUM_THREADS=${OMP_THREADS} \
    NUMEXPR_NUM_THREADS=${OMP_THREADS} \
    CUDA_VISIBLE_DEVICES=0 \
    COURTV_NO_LOFTR=1 \
    COURTV_NO_OCR=1 \
    PYTORCH_CUDA_ALLOC_CONF=max_split_size_mb:512 \
    PHASE_G_VIDEO_DIR=/root/nba_videos \
    PYTHONUNBUFFERED=1 \
    nohup python3 -u scripts/run_phase_g.py --frames 18000 --parallel ${PARALLEL} \
    > phase_g_batch.log 2>&1 & disown"

sleep 5

# ── Step 8: Health check ─────────────────────────────────────────────
log "Step 8: Health check (waiting 60s for workers to warm up)..."
$SSH bash <<'HEALTH'
echo "=== WORKERS ==="
workers=$(pgrep -f 'run_clip.py' | grep -v grep | wc -l)
echo "  run_clip.py workers: $workers"

echo "=== LOAD ==="
cat /proc/loadavg

echo "=== GPU ==="
nvidia-smi --query-gpu=memory.used,memory.total,utilization.gpu --format=csv,noheader | sed 's/^/  /'

echo "=== LOG (first games) ==="
grep -E '^\[' /workspace/nba-ai-system/phase_g_batch.log 2>/dev/null | head -8

echo "=== BASELINE THROTTLE ==="
cat /sys/fs/cgroup/cpu,cpuacct/cpu.stat 2>/dev/null | head -3

echo "Waiting 60s for throttle delta..."
sleep 60

echo "=== AFTER 60s ==="
cat /sys/fs/cgroup/cpu,cpuacct/cpu.stat 2>/dev/null | head -3
cat /proc/loadavg

echo "=== LATEST PROGRESS ==="
tail -5 /workspace/nba-ai-system/phase_g_batch.log 2>/dev/null
HEALTH

log "DONE. Pod is running Phase G."
log ""
log "Monitor:  ssh -p ${PORT} root@${IP} 'tail -f ${PROJ}/phase_g_batch.log'"
log "Sync:     scp -P ${PORT} root@${IP}:${PROJ}/data/phase_g_processed.txt data/"
log "          scp -P ${PORT} root@${IP}:${PROJ}/data/phase_g_metrics.csv data/"
log "          scp -r -P ${PORT} root@${IP}:${PROJ}/data/tracking/ data/tracking/"
