#!/bin/bash
# Run on pod after 2025-26 videos are uploaded.
# Quarantines all 2024-25 season games (0022400xxx) — confirmed AV1/unreadable.
# Only processes 2025-26 season games (0022500xxx).
set -euo pipefail
PROJ="/workspace/nba-ai-system"
cd "$PROJ"

echo "=== Quarantine all 2024-25 games (0022400xxx — AV1/bad codec) ==="
mkdir -p data/videos/av1_quarantine
for f in data/videos/full_games/00224*.mp4 /root/nba_videos/00224*.mp4; do
    [ -f "$f" ] || continue
    mv "$f" data/videos/av1_quarantine/ 2>/dev/null || true
    echo "  Quarantined: $(basename $f)"
done

echo "=== Stage 2025-26 videos to /root/nba_videos overlay ==="
mkdir -p /root/nba_videos
cp -n data/videos/full_games/00225*.mp4 /root/nba_videos/ 2>/dev/null || true
echo "  Overlay: $(ls /root/nba_videos/*.mp4 2>/dev/null | wc -l) files"

echo "=== Free /workspace disk (delete staged videos) ==="
rm -f data/videos/full_games/00225*.mp4 2>/dev/null || true
rm -f data/videos/full_games/00224*.mp4 2>/dev/null || true
echo "  /workspace freed: $(df -h /workspace | tail -1 | awk '{print $4}') available"

echo "=== Remove already-processed from overlay ==="
while IFS= read -r key; do
    key="${key%.mp4}"
    f="/root/nba_videos/${key}.mp4"
    [ -f "$f" ] && rm -f "$f" && echo "  Removed processed: $key"
done < data/phase_g_processed.txt
echo "  Ready: $(ls /root/nba_videos/*.mp4 2>/dev/null | wc -l) files"

echo "=== Kill stale workers ==="
pgrep -f 'run_phase_g.py' | xargs -r kill -TERM 2>/dev/null || true; sleep 2
pgrep -f 'run_clip.py' | xargs -r kill -KILL 2>/dev/null || true

echo "=== Launch Phase G --parallel 4 --frames 18000 ==="
MALLOC_ARENA_MAX=2 \
MALLOC_MMAP_THRESHOLD_=65536 \
OMP_NUM_THREADS=6 \
MKL_NUM_THREADS=6 \
OPENBLAS_NUM_THREADS=6 \
NUMEXPR_NUM_THREADS=6 \
CUDA_VISIBLE_DEVICES=0 \
COURTV_NO_LOFTR=1 \
COURTV_NO_OCR=1 \
PYTORCH_CUDA_ALLOC_CONF=max_split_size_mb:512 \
PHASE_G_VIDEO_DIR=/root/nba_videos \
PYTHONUNBUFFERED=1 \
nohup python3 -u scripts/run_phase_g.py --frames 18000 --parallel 4 \
    > phase_g_batch.log 2>&1 & disown

echo "Launched PID $!"
sleep 5
echo "=== Workers ==="
pgrep -af run_phase_g.py | grep -v pgrep || echo "No workers yet"
echo "=== Monitor: tail -f $PROJ/phase_g_batch.log ==="
