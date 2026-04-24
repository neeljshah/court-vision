#!/bin/bash
# pod_loop.sh — keeps run_phase_g.py running continuously until no unprocessed games remain.
# Restarts automatically when a run finishes and new videos are present.
# Safe: processed.txt prevents re-running completed games.
set -euo pipefail

WORKDIR=/workspace/nba-ai-system
LOGFILE=$WORKDIR/phase_g_batch.log
PROCESSED=$WORKDIR/data/phase_g_processed.txt
VIDEOS_DIR=/root/nba_videos
BATCH=0

log() { echo "[pod_loop $(date '+%H:%M:%S')] $*" | tee -a $WORKDIR/pod_loop.log; }

while true; do
  # Count unprocessed videos on disk
  TOTAL=$(ls "$VIDEOS_DIR"/*.mp4 2>/dev/null | wc -l)
  DONE=$(grep -cE '^0022[0-9]+$' "$PROCESSED" 2>/dev/null || echo 0)

  if [ "$TOTAL" -eq 0 ]; then
    log "No videos staged. Waiting 60s for uploads..."
    sleep 60
    continue
  fi

  BATCH=$((BATCH + 1))
  log "=== BATCH $BATCH === staged=$TOTAL already_processed=$DONE"
  log "Overlay disk: $(df -BG / | awk 'NR==2{print $3}')G used"

  # Run tracker on everything staged
  MALLOC_ARENA_MAX=2 \
  OMP_NUM_THREADS=3 MKL_NUM_THREADS=3 \
  OPENBLAS_NUM_THREADS=3 NUMEXPR_NUM_THREADS=3 \
  CUDA_VISIBLE_DEVICES=0 COURTV_NO_LOFTR=1 PYTHONUNBUFFERED=1 \
  python3 "$WORKDIR/scripts/run_phase_g.py" --frames 18000 --parallel 4 \
    >> "$LOGFILE" 2>&1

  log "Run finished. Checking results..."
  NEW_DONE=$(grep -cE '^0022[0-9]+$' "$PROCESSED" 2>/dev/null || echo 0)
  log "Processed this run: $((NEW_DONE - DONE)) games. Total processed: $NEW_DONE"

  # Delete processed videos from pod overlay to free space
  while IFS= read -r gid; do
    f="$VIDEOS_DIR/${gid}.mp4"
    if [ -f "$f" ]; then
      rm -f "$f"
      log "Deleted $f"
    fi
  done < <(grep -E '^0022[0-9]+$' "$PROCESSED" 2>/dev/null)

  log "Overlay after cleanup: $(df -BG / | awk 'NR==2{print $3}')G used"

  # Check if done
  REMAINING=$(ls "$VIDEOS_DIR"/*.mp4 2>/dev/null | wc -l)
  if [ "$REMAINING" -eq 0 ]; then
    log "All staged videos processed and deleted. Loop complete."
    break
  fi

  log "Still $REMAINING videos waiting. Restarting run..."
  sleep 5
done

log "pod_loop.sh finished."
