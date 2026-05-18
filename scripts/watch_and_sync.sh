#!/bin/bash
# watch_and_sync.sh — watch a pod until Phase G finishes, then sync tracking back.
#
# Required env:
#   RUNPOD_HOST   e.g. root@1.2.3.4
#   RUNPOD_PORT   e.g. 14149
# Optional:
#   REMOTE_ROOT   default /workspace/nba-ai-system
#   LOCAL_ROOT    default $PWD (when run from repo root)
#   SSH_KEY       default ~/.ssh/id_rsa
#   POLL_SECONDS  default 30 (worker check); sync every SYNC_SECONDS (default 300)

set -euo pipefail
: "${RUNPOD_HOST:?Set RUNPOD_HOST=root@<ip>}"
: "${RUNPOD_PORT:?Set RUNPOD_PORT=<ssh_port>}"

REMOTE_ROOT="${REMOTE_ROOT:-/workspace/nba-ai-system}"
LOCAL_ROOT="${LOCAL_ROOT:-$PWD}"
SSH_KEY="${SSH_KEY:-$HOME/.ssh/id_rsa}"
POLL_SECONDS="${POLL_SECONDS:-30}"
SYNC_SECONDS="${SYNC_SECONDS:-300}"

SSH="ssh -o StrictHostKeyChecking=no -i $SSH_KEY -p $RUNPOD_PORT $RUNPOD_HOST"
SCP="scp -o StrictHostKeyChecking=no -i $SSH_KEY -P $RUNPOD_PORT"

log() { echo "[$(date '+%H:%M:%S')] $*"; }

log "Watching $RUNPOD_HOST:$RUNPOD_PORT for Phase G completion (sync every ${SYNC_SECONDS}s)..."

last_sync=$(date +%s)
while true; do
    sleep "$POLL_SECONDS"

    now=$(date +%s)
    WORKERS=$($SSH "pgrep -f run_clip.py | grep -v pgrep | wc -l" 2>/dev/null || echo 0)

    if (( now - last_sync >= SYNC_SECONDS )) || [ "$WORKERS" -eq 0 ]; then
        log "Syncing data (workers=${WORKERS})..."
        $SCP -r "$RUNPOD_HOST:${REMOTE_ROOT}/data/tracking/" "${LOCAL_ROOT}/data/" 2>/dev/null || true
        $SCP -r "$RUNPOD_HOST:${REMOTE_ROOT}/data/events/"   "${LOCAL_ROOT}/data/" 2>/dev/null || true
        $SCP    "$RUNPOD_HOST:${REMOTE_ROOT}/data/phase_g_metrics.csv" "${LOCAL_ROOT}/data/" 2>/dev/null || true
        last_sync=$(date +%s)
    fi

    if [ "$WORKERS" -eq 0 ]; then
        $SCP "$RUNPOD_HOST:${REMOTE_ROOT}/data/phase_g_processed.txt" "${LOCAL_ROOT}/data/" 2>/dev/null || true
        DONE=$(wc -l < "${LOCAL_ROOT}/data/phase_g_processed.txt" 2>/dev/null || echo 0)
        log "All workers done. ${DONE} games in processed list."
        log "Tracking data: ${LOCAL_ROOT}/data/tracking/"
        break
    else
        FRAME=$($SSH "grep -oE 'Frame [0-9]+' ${REMOTE_ROOT}/phase_g_batch.log 2>/dev/null | tail -1" 2>/dev/null || echo "...")
        log "  ${WORKERS} workers active | last log: ${FRAME}"
    fi
done
