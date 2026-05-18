#!/bin/bash
# stage_and_launch.sh — Runs ON THE POD via ssh. Stages videos, clears processed.txt,
# launches 4 parallel workers with OMP cap.
#
# Triggered from local machine once video upload completes.

set -euo pipefail
PROJ=/workspace/nba-ai-system
cd "$PROJ"

echo "=== Step 1: Stage videos /workspace → /root (fast overlay) ==="
mkdir -p /root/nba_videos
free_gb=$(df /root/nba_videos | awk 'NR==2{printf "%d", $4/1024/1024}')
existing=$(ls /root/nba_videos/*.mp4 2>/dev/null | wc -l)
echo "  /root free: ${free_gb}GB, existing videos: $existing"

# Only require 5GB if videos already staged (just need scratch for processing)
if [ "$existing" -eq 0 ]; then
    [ "$free_gb" -ge 60 ] || { echo "ERROR: need 60GB free on /root for fresh staging"; exit 1; }
    cp -un "$PROJ/data/videos/full_games/"*.mp4 /root/nba_videos/ 2>/dev/null || true
else
    [ "$free_gb" -ge 3 ] || { echo "ERROR: need at least 3GB scratch on /root"; exit 1; }
    # Pick up any new videos from workspace
    cp -un "$PROJ/data/videos/full_games/"*.mp4 /root/nba_videos/ 2>/dev/null || true
fi
staged=$(ls /root/nba_videos/*.mp4 2>/dev/null | wc -l)
echo "  Staged: $staged videos"

echo ""
echo "=== Step 2: Decode-test each video (quarantine bad ones) ==="
quarantined=0
for v in /root/nba_videos/*.mp4; do
    [ -f "$v" ] || continue
    name=$(basename "$v")
    if ! python3 -c "from decord import VideoReader; vr=VideoReader('$v'); _=len(vr)" 2>/dev/null; then
        mkdir -p "$PROJ/data/videos/av1_quarantine"
        mv "$v" "$PROJ/data/videos/av1_quarantine/"
        quarantined=$((quarantined+1))
        echo "  Q: $name"
    fi
done
echo "  Quarantined: $quarantined"
echo "  Ready: $(ls /root/nba_videos/*.mp4 2>/dev/null | wc -l)"

echo ""
echo "=== Step 3: Clear processed.txt to force reprocess of all 80 ==="
# Backup the 9 CLEAN games' status; force reprocess everything
[ -f "$PROJ/data/phase_g_processed.txt" ] && \
    cp "$PROJ/data/phase_g_processed.txt" "$PROJ/data/phase_g_processed.txt.bak"
> "$PROJ/data/phase_g_processed.txt"
echo "  processed.txt cleared (backup at .bak)"

echo ""
echo "=== Step 4: Verify VRAM flush interval = 3000 ==="
FLUSH=$(grep -oE '_VRAM_FLUSH_INTERVAL = [0-9]+' "$PROJ/src/pipeline/unified_pipeline.py" | head -1)
echo "  $FLUSH"
[[ "$FLUSH" == *"3000"* ]] || { echo "FATAL: _VRAM_FLUSH_INTERVAL not 3000"; exit 1; }

echo ""
echo "=== Step 5: Kill any stale workers ==="
pkill -TERM -f run_phase_g.py 2>/dev/null || true
sleep 3
pkill -KILL -f run_phase_g.py 2>/dev/null || true
pkill -KILL -f run_clip.py 2>/dev/null || true

echo ""
echo "=== Step 6: Launch 4 parallel workers ==="
rm -f "$PROJ/phase_g_batch.log"
mkdir -p "$PROJ/logs"

cd "$PROJ"
nohup env \
    MALLOC_ARENA_MAX=2 \
    MALLOC_MMAP_THRESHOLD_=65536 \
    OMP_NUM_THREADS=6 \
    MKL_NUM_THREADS=6 \
    OPENBLAS_NUM_THREADS=6 \
    NUMEXPR_NUM_THREADS=6 \
    CUDA_VISIBLE_DEVICES=0 \
    COURTV_NO_LOFTR=1 \
    YOLO_CONFIG_DIR=/tmp/Ultralytics \
    PHASE_G_VIDEO_DIR=/root/nba_videos \
    python3 scripts/run_phase_g.py --frames 18000 --parallel 4 \
    > phase_g_batch.log 2>&1 &

echo "  Launched PID $!"
sleep 5

WORKERS=$(pgrep -af "run_phase_g.py" 2>/dev/null | grep -v pgrep | wc -l)
echo "  Workers running: $WORKERS"
[ "$WORKERS" -ge 1 ] || { echo "ERROR: no workers started"; tail -30 phase_g_batch.log; exit 1; }

echo ""
echo "=== Launch complete — tail with: ssh -p 40017 root@213.192.2.107 'tail -f $PROJ/phase_g_batch.log' ==="
