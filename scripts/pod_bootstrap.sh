#!/bin/bash
# pod_bootstrap.sh — Take a freshly-synced RunPod box from zero to processing,
# with every issue from docs/operations/pod-run-issues.md guarded against.
#
# Prerequisites (do these LOCALLY before running this):
#   1. rsync/tar code to /workspace/nba-ai-system on the pod
#      (must include: scripts/, src/, models/weights/, resources/, requirements.txt)
#   2. push data/nba/ and data/ingest/queue.db to /workspace/nba-ai-system/data/
#   3. push data/videos/youtube_cookies.txt to /workspace/nba-ai-system/data/videos/
#   4. ssh in and: bash /workspace/nba-ai-system/scripts/pod_bootstrap.sh
#
# Idempotent — safe to re-run after a crash or partial failure.
#
# Env knobs (defaults are the verified-best from the 2026-05-22 benchmark):
#   WORKERS=6                  # parallel processors per GPU (3090 mps-6 = 104 fps)
#   OMP_PER_WORKER=12          # per-worker OpenMP threads (avoids issue #12)
#   USE_MPS=1                  # CUDA MPS for kernel concurrency (+10% at 6 workers)
#   RSS_KILL_GB=40             # per-worker RAM kill (memory-safety backstop)
#   TRT_VERSION=10.16.1.11     # tensorrt-cu12 pin (must match .engine file build)

set -uo pipefail
PROJ=/workspace/nba-ai-system
cd "$PROJ"
ts() { date '+%F %T'; }
log() { echo "[$(ts)] $*"; }

WORKERS="${WORKERS:-6}"
# Verified-best 2026-05-22 (RTX 3090): OMP=8 gave 113 fps (+9% over OMP=4, +3%
# over OMP=12 with load 33). OMP=12 oversubscribed the CFS quota.
OMP_PER_WORKER="${OMP_PER_WORKER:-8}"
USE_MPS="${USE_MPS:-1}"
RSS_KILL_GB="${RSS_KILL_GB:-40}"
TRT_VERSION="${TRT_VERSION:-10.16.1.11}"

# ── 1. CRLF strip (issue #1) ──────────────────────────────────────────────────
log "step 1: strip CRLF from all shell scripts"
find scripts -name '*.sh' -exec sed -i 's/\r$//' {} + 2>/dev/null
sed -i 's/\r$//' /workspace/*.sh 2>/dev/null || true

# ── 2. Install deps incl. tensorrt + yt-dlp (issue #4) ────────────────────────
log "step 2: install python deps (incl tensorrt-cu12 — issue #4)"
pip install --break-system-packages -q \
    ultralytics decord av pandas xgboost scikit-learn nba_api easyocr scipy \
    torchreid kornia onnxruntime-gpu paddleocr yt-dlp py-spy \
    "tensorrt-cu12==${TRT_VERSION}" 2>&1 | tail -3
python3 -c "import torch,ultralytics,decord,tensorrt; print(f'  torch={torch.__version__} cuda={torch.cuda.is_available()} trt={tensorrt.__version__}')"

# ── 3. Verify VRAM flush interval and CUDA ────────────────────────────────────
log "step 3: pipeline self-checks"
grep -q '_VRAM_FLUSH_INTERVAL = 3000' src/pipeline/unified_pipeline.py || { echo "FATAL: _VRAM_FLUSH_INTERVAL != 3000"; exit 1; }
nvidia-smi --query-gpu=name,memory.total --format=csv,noheader | head -1

# ── 4. Build TRT engines if missing ───────────────────────────────────────────
log "step 4: TRT engines"
if [ ! -f resources/yolov8n.engine ] || [ ! -f resources/yolov8n_ball.engine ] || [ ! -f resources/yolov8n-pose.engine ]; then
    log "  some engines missing — building (3-15 min)"
    bash scripts/build_trt_engines.sh
else
    log "  all 3 engines present — skipping rebuild"
fi
ls -lh resources/*.engine | awk '{print "  "$NF" "$5}'

# ── 5. YOLO config dirs (per-GPU) ─────────────────────────────────────────────
log "step 5: YOLO config dirs"
N_GPUS=$(nvidia-smi --query-gpu=count --format=csv,noheader,nounits | head -1)
for i in $(seq 0 $((N_GPUS - 1))); do mkdir -p /tmp/Ultralytics_gpu${i}; done

# ── 6. Stage + codec-scan videos (issue #2 — AV1 quarantine) ──────────────────
log "step 6: codec-scan /root/nba_videos (quarantine non-h264 — issue #2)"
mkdir -p /root/nba_videos /root/codec_quarantine
quarantined=0
for v in /root/nba_videos/*.mp4; do
    [ -f "$v" ] || continue
    codec=$(ffprobe -v error -select_streams v:0 -show_entries stream=codec_name -of csv=p=0 "$v" 2>/dev/null)
    if [ "$codec" != "h264" ]; then
        mv "$v" /root/codec_quarantine/ && quarantined=$((quarantined+1))
    fi
done
log "  quarantined $quarantined non-h264 videos; h264 ready: $(ls /root/nba_videos/*.mp4 2>/dev/null | wc -l)"

# ── 7. CUDA MPS daemon (issue: GPU context serialization across workers) ─────
log "step 7: CUDA MPS daemon"
if [ "$USE_MPS" = "1" ]; then
    echo quit | CUDA_MPS_PIPE_DIRECTORY=/tmp/nvidia-mps nvidia-cuda-mps-control 2>/dev/null
    mkdir -p /tmp/nvidia-mps /tmp/nvidia-mps-log
    CUDA_MPS_PIPE_DIRECTORY=/tmp/nvidia-mps CUDA_MPS_LOG_DIRECTORY=/tmp/nvidia-mps-log nvidia-cuda-mps-control -d
    sleep 3
    pgrep -a nvidia-cuda-mps-server >/dev/null && log "  MPS daemon up" || log "  WARN: MPS daemon not detected"
    export CUDA_MPS_PIPE_DIRECTORY=/tmp/nvidia-mps CUDA_MPS_LOG_DIRECTORY=/tmp/nvidia-mps-log
fi

# ── 8. Kill any stale loops (clean slate, singleton-safe) ────────────────────
log "step 8: kill any stale loops"
for pidfile in /workspace/supervisor.pid /workspace/downloader.pid /workspace/watchdog.pid; do
    [ -f "$pidfile" ] && pid=$(cat "$pidfile" 2>/dev/null) && [ -n "$pid" ] && kill "$pid" 2>/dev/null
done
for pid in $(ps -eo pid,args | awk '/[s]upervisor.sh|[d]ownloader.sh|[d]isk_watchdog.sh/ {print $1}'); do kill -9 "$pid" 2>/dev/null; done
for pid in $(ps -eo pid,comm,args | awk '$2=="python3" && /run_clip.py|run_phase_g.py/ {print $1}'); do kill -9 "$pid" 2>/dev/null; done
rm -f /workspace/supervisor.pid /workspace/downloader.pid /workspace/watchdog.pid
sleep 3

# ── 9. Start loops: watchdog + supervisor + downloader ───────────────────────
log "step 9: start loops"
[ -f /workspace/disk_watchdog.sh ] || { echo "FATAL: /workspace/disk_watchdog.sh missing"; exit 1; }
[ -f /workspace/supervisor.sh ]   || { echo "FATAL: /workspace/supervisor.sh missing";   exit 1; }
[ -f /workspace/downloader.sh ]   || { echo "FATAL: /workspace/downloader.sh missing";   exit 1; }

setsid bash /workspace/disk_watchdog.sh >/dev/null 2>&1 </dev/null & disown
sleep 1
setsid env WORKERS="$WORKERS" OMP_PER_WORKER="$OMP_PER_WORKER" \
    bash /workspace/supervisor.sh >/dev/null 2>&1 </dev/null & disown
sleep 1
setsid bash /workspace/downloader.sh >/dev/null 2>&1 </dev/null & disown
sleep 8

# ── 10. Final status ──────────────────────────────────────────────────────────
log "step 10: status"
sv=$(ps -eo args | awk '$1=="bash" && $2=="/workspace/supervisor.sh"' | wc -l)
dl=$(ps -eo args | awk '$1=="bash" && $2=="/workspace/downloader.sh"' | wc -l)
wd=$(ps -eo args | awk '$1=="bash" && $2=="/workspace/disk_watchdog.sh"' | wc -l)
pg=$(ps -eo pid,comm | awk '$2=="python3"{print $1}' | while read x; do
       tr '\0' ' ' </proc/$x/cmdline 2>/dev/null | grep -q run_phase_g.py && echo y
     done | wc -l)
echo "  supervisor=$sv  downloader=$dl  watchdog=$wd  run_phase_g=$pg"
echo "  videos ready: $(ls /root/nba_videos/*.mp4 2>/dev/null | wc -l)"
df -h /root | tail -1 | awk '{print "  /root free: " $4}'
nvidia-smi --query-gpu=memory.used,memory.total,utilization.gpu --format=csv,noheader | awk '{print "  GPU: " $0}'

log "bootstrap done — pipeline is running"
echo
echo "Monitor:  tail -f /workspace/supervisor.log /workspace/downloader.log /workspace/disk_watchdog.log"
echo "         tail -f $PROJ/phase_g_batch_gpu0.log"
