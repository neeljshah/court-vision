#!/bin/bash
# Run on RunPod after games50.tar upload completes (see RUNPOD.md workflow).
set -euo pipefail
PROJ="${PROJ:-/workspace/nba-ai-system}"
TAR="$PROJ/data/videos/full_games/games50.tar"
EXPECTED_SIZE="${EXPECTED_SIZE:-13585029120}"

cd "$PROJ"
if [[ ! -f "$TAR" ]]; then
  echo "Missing $TAR"; exit 1
fi
SZ=$(stat -c%s "$TAR")
if [[ "$SZ" -lt "$EXPECTED_SIZE" ]]; then
  echo "games50.tar still uploading: $SZ / $EXPECTED_SIZE bytes — wait for scp to finish."
  exit 2
fi

mkdir -p /root/nba_videos
tar -xf "$TAR" -C /root/nba_videos
rm -f "$TAR"
echo "Videos: $(ls /root/nba_videos/*.mp4 2>/dev/null | wc -l) files in /root/nba_videos"

export PHASE_G_VIDEO_DIR=/root/nba_videos
export PHASE_G_STAGGER_S=90
export COURTV_NO_LOFTR=1
export OMP_NUM_THREADS=6 MKL_NUM_THREADS=6 OPENBLAS_NUM_THREADS=6 NUMEXPR_NUM_THREADS=6
export MALLOC_ARENA_MAX=2
export CUDA_VISIBLE_DEVICES=0

# Partial runs (~5 min @ 30fps); parallel 2 on one 3090 to limit VRAM spikes.
nohup python3 scripts/run_phase_g.py --frames 9000 --limit 50 --parallel 2 \
  >> phase_g_batch.log 2>&1 &
echo $! > phase_g.pid
echo "Started PID $(cat phase_g.pid) — tail -f $PROJ/phase_g_batch.log"
