#!/bin/bash
# season_100_orchestrator.sh — pod-side loop to download + track 100 games of 2025-26 season.
#
# Strategy: download a small batch → phase_g --parallel 4 → delete processed videos → loop.
# Keeps pod disk footprint bounded (~20 GB) while saturating the GPU.
#
# Usage (on pod, from /workspace/nba-ai-system):
#   TARGET=100 BATCH=8 bash scripts/season_100_orchestrator.sh
#
# Env vars:
#   TARGET       — total successful games to process (default 100)
#   BATCH        — games to download + process per iteration (default 8)
#   FRAMES       — frames per game passed to phase_g (default 18000 = ~10 min)
#   PARALLEL     — phase_g worker count (default 4)
#   FROM / TO    — date range for fetch_games (default: full 2025-26 season)
#   KEEP_VIDEOS  — set to 1 to skip the post-processing delete (default 0 = delete)

set -uo pipefail

TARGET="${TARGET:-100}"
BATCH="${BATCH:-8}"
FRAMES="${FRAMES:-18000}"
PARALLEL="${PARALLEL:-4}"
FROM="${FROM:-2025-10-21}"
TO="${TO:-2026-04-20}"
KEEP_VIDEOS="${KEEP_VIDEOS:-0}"
SEGMENT="${SEGMENT:-900}"

PROJ="/workspace/nba-ai-system"
cd "$PROJ"

VIDEOS="${PHASE_G_VIDEO_DIR:-/root/nba_videos}"
mkdir -p "$VIDEOS"
ln -sfn "$VIDEOS" data/videos/full_games

DONE="data/phase_g_processed.txt"
LOG="season_100.log"

log() { echo "[$(date '+%H:%M:%S')] $*" | tee -a "$LOG"; }

# Count games in done log that look like real game IDs (10 digits, no suffix)
count_done() {
  [ -f "$DONE" ] || { echo 0; return; }
  grep -cE '^[0-9]{10}$' "$DONE" 2>/dev/null || echo 0
}

# Required env for phase_g (from launch_single_gpu_pod.sh)
export MALLOC_ARENA_MAX=2
export MALLOC_MMAP_THRESHOLD_=65536
export OMP_NUM_THREADS=6
export MKL_NUM_THREADS=6
export OPENBLAS_NUM_THREADS=6
export NUMEXPR_NUM_THREADS=6
export CUDA_VISIBLE_DEVICES="${CUDA_VISIBLE_DEVICES:-0,1,2,3}"
export COURTV_NO_LOFTR=1
export PHASE_G_VIDEO_DIR="$VIDEOS"

# Preflight: verify _VRAM_FLUSH_INTERVAL=3000 on pod copy
FLUSH=$(grep -oE '_VRAM_FLUSH_INTERVAL = [0-9]+' src/pipeline/unified_pipeline.py | head -1 || echo "")
case "$FLUSH" in
  *3000*) log "preflight OK: $FLUSH" ;;
  *)      log "ERROR: _VRAM_FLUSH_INTERVAL != 3000 (got: $FLUSH). Abort."; exit 1 ;;
esac

START_DONE=$(count_done)
log "=== season_100 start  target=$TARGET  batch=$BATCH  frames=$FRAMES  parallel=$PARALLEL"
log "    window=$FROM..$TO  videos=$VIDEOS  already_done=$START_DONE"

ITER=0
while :; do
  ITER=$((ITER + 1))
  DONE_NOW=$(count_done)
  REMAINING=$((TARGET - DONE_NOW + START_DONE - DONE_NOW))
  # simpler: remaining = TARGET - (DONE_NOW - START_DONE)
  PROGRESS=$((DONE_NOW - START_DONE))
  REMAINING=$((TARGET - PROGRESS))

  if [ "$REMAINING" -le 0 ]; then
    log "=== target reached: $PROGRESS/$TARGET games processed this run"
    break
  fi

  # Size this batch
  THIS_BATCH=$BATCH
  [ "$REMAINING" -lt "$THIS_BATCH" ] && THIS_BATCH=$REMAINING

  log "--- iter $ITER: progress=$PROGRESS/$TARGET  batch=$THIS_BATCH"

  # ── Step 1: download batch ──────────────────────────────────────────────
  # fetch_games.py --count N downloads N *new* games from the 2025-26 season.
  # It auto-skips any game_id already present on disk.
  log "    downloading $THIS_BATCH games via fetch_games.py..."
  python3 scripts/fetch_games.py \
    --count "$THIS_BATCH" \
    --from "$FROM" \
    --to "$TO" \
    --segment "$SEGMENT" \
    2>&1 | tee -a "$LOG"

  # Collect newly-present game IDs (not yet in done log)
  NEW_IDS=$(ls "$VIDEOS"/*.mp4 2>/dev/null | xargs -n1 basename 2>/dev/null | sed 's/\.mp4$//' | \
            while read gid; do
              grep -qxF "$gid" "$DONE" 2>/dev/null || echo "$gid"
            done | tr '\n' ' ')

  if [ -z "${NEW_IDS// /}" ]; then
    log "    no new downloads produced — may be coverage gap. Retrying with wider window."
    # If the season window is exhausted, quit.
    if [ "$ITER" -gt 3 ] && [ "$PROGRESS" -lt "$TARGET" ]; then
      log "    giving up after 3 empty iterations. processed=$PROGRESS/$TARGET"
      break
    fi
    continue
  fi

  log "    new game_ids queued: $NEW_IDS"

  # ── Step 2: track via phase_g ───────────────────────────────────────────
  log "    running phase_g --parallel $PARALLEL on $(echo $NEW_IDS | wc -w) games..."
  python3 scripts/run_phase_g.py \
    --frames "$FRAMES" \
    --parallel "$PARALLEL" \
    --game-ids $NEW_IDS \
    2>&1 | tee -a "$LOG"

  # ── Step 3: delete processed videos to bound disk ───────────────────────
  if [ "$KEEP_VIDEOS" != "1" ]; then
    for gid in $NEW_IDS; do
      if grep -qxF "$gid" "$DONE" 2>/dev/null; then
        rm -f "$VIDEOS/$gid.mp4" && log "    deleted $gid.mp4 (tracking saved)"
      else
        log "    kept $gid.mp4 (not in done log — will retry next iter)"
      fi
    done
  fi

  # Disk guard — if pod storage is low, pause
  FREE_GB=$(df --output=avail -BG / 2>/dev/null | tail -1 | tr -dc '0-9')
  if [ -n "$FREE_GB" ] && [ "$FREE_GB" -lt 10 ]; then
    log "    WARN: only ${FREE_GB}G free — pausing. Clean up and rerun to continue."
    break
  fi
done

FINAL_DONE=$(count_done)
PROGRESS=$((FINAL_DONE - START_DONE))
log "=== season_100 end  progress=$PROGRESS/$TARGET  total_done=$FINAL_DONE"
log "    metrics: data/phase_g_metrics.csv"
log "    tracking outputs: data/tracking/"
