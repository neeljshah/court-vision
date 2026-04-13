#!/bin/bash
# Auto-sync completed game tracking data from RunPod to local.
# Polls every 60s, pulls each game dir as soon as tracking_data.csv appears.
# Run this in a terminal and leave it — it stops automatically when all 57 games are synced.
#
# Usage: bash scripts/sync_tracking_results.sh

# Reads RUNPOD_IP / RUNPOD_PORT from .runpod (source it first)
: "${RUNPOD_IP:?source .runpod first}"
: "${RUNPOD_PORT:?source .runpod first}"
REMOTE="${RUNPOD_USER:-root}@${RUNPOD_IP}"
RPORT="${RUNPOD_PORT}"
REMOTE_DIR="/workspace/nba-ai-system"
LOCAL_DIR="data/tracking"
TARGET=${TARGET_GAMES:-50}

SSH="ssh -o StrictHostKeyChecking=no -p $RPORT"
SCP="scp -o StrictHostKeyChecking=no -P $RPORT"

mkdir -p "$LOCAL_DIR"

log() { echo "[$(date '+%H:%M:%S')] $*"; }

SYNCED=()
TOTAL_SYNCED=0

log "=== Sync watcher started — target: $TARGET games ==="
log "Polling pod every 60s..."

while true; do
  # Get list of completed game dirs on pod (has tracking_data.csv with >1000 lines)
  DONE_ON_POD=$($SSH "$REMOTE" "
    for d in $REMOTE_DIR/data/tracking/*/; do
      gid=\$(basename \"\$d\")
      rows=\$(wc -l < \"\$d/tracking_data.csv\" 2>/dev/null || echo 0)
      [ \"\$rows\" -gt 1000 ] && echo \"\$gid\"
    done
  " 2>/dev/null)

  for gid in $DONE_ON_POD; do
    # Skip if already synced
    already=0
    for s in "${SYNCED[@]:-}"; do [ "$s" = "$gid" ] && already=1 && break; done
    [ "$already" -eq 1 ] && continue

    # Pull the game dir
    log "Syncing $gid..."
    mkdir -p "$LOCAL_DIR/$gid"
    $SCP -r "$REMOTE:$REMOTE_DIR/data/tracking/$gid/" "$LOCAL_DIR/" 2>/dev/null
    ROWS=$(wc -l < "$LOCAL_DIR/$gid/tracking_data.csv" 2>/dev/null || echo 0)
    log "  $gid — $ROWS rows pulled ✓"

    SYNCED+=("$gid")
    TOTAL_SYNCED=${#SYNCED[@]}
    log "  Progress: $TOTAL_SYNCED / $TARGET games synced"
  done

  if [ "$TOTAL_SYNCED" -ge "$TARGET" ]; then
    log "=== All $TARGET games synced to $LOCAL_DIR/ — done ==="
    break
  fi

  # Print GPU status every poll
  GPU_STATUS=$($SSH "$REMOTE" "ps aux | grep run_phase_g | grep -v grep | wc -l" 2>/dev/null || echo "?")
  VIDS_ON_POD=$($SSH "$REMOTE" "ls $REMOTE_DIR/data/videos/full_games/*.mp4 2>/dev/null | wc -l" 2>/dev/null || echo "?")
  log "Pod: $GPU_STATUS GPU worker(s) running | $VIDS_ON_POD videos on pod | $TOTAL_SYNCED/$TARGET synced"

  sleep 60
done
