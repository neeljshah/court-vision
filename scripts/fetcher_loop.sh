#!/bin/bash
# Continuous fetcher: rotates through season date windows for better YT coverage
cd /workspace/nba-ai-system
export MALLOC_ARENA_MAX=2
export OMP_NUM_THREADS=6
export PHASE_G_VIDEO_DIR=/root/nba_videos
mkdir -p /root/nba_videos
ln -sfn /root/nba_videos data/videos/full_games
DONE=data/phase_g_processed.txt

# Date windows to rotate through (different parts of season have different YT coverage)
WINDOWS=(
  "2026-04-01 2026-04-20"  # late playoffs run-up
  "2026-03-01 2026-03-31"  # mid March
  "2026-02-01 2026-02-28"  # February
  "2026-01-01 2026-01-31"  # January
  "2025-12-01 2025-12-31"  # December
  "2025-11-01 2025-11-30"  # November
  "2025-10-21 2025-10-31"  # October opener
)
WIN_IDX=0

while true; do
  # Count videos that AREN'T already in done log
  NOT_DONE=$(ls /root/nba_videos/*.mp4 2>/dev/null | xargs -n1 basename 2>/dev/null | sed 's/\.mp4$//' | while read gid; do
    grep -qxF "$gid" "$DONE" 2>/dev/null || echo "$gid"
  done | wc -l)
  if [ "$NOT_DONE" -lt 16 ]; then
    FROM=$(echo "${WINDOWS[$WIN_IDX]}" | cut -d' ' -f1)
    TO=$(echo "${WINDOWS[$WIN_IDX]}" | cut -d' ' -f2)
    echo "[$(date '+%H:%M:%S')] fetcher: $NOT_DONE not-done, fetching from $FROM..$TO" >> fetcher.log
    timeout 600 python3 scripts/fetch_games.py --count 8 --from "$FROM" --to "$TO" --segment 900 2>&1 | tail -60 >> fetcher.log
    # Rotate window for next iteration
    WIN_IDX=$(( (WIN_IDX + 1) % ${#WINDOWS[@]} ))
  else
    echo "[$(date '+%H:%M:%S')] fetcher: $NOT_DONE not-done buffered, sleeping" >> fetcher.log
    sleep 60
  fi
  sleep 5
done
