#!/bin/bash
# Watches pod until Phase G finishes, then syncs all tracking data + metrics back locally.
# Also handles the mid-upload relaunch when bl3tl1k66 upload completes.
set -euo pipefail

IP="103.196.86.195"
PORT="14149"
SSH="ssh -o StrictHostKeyChecking=no -i ~/.ssh/id_rsa -p ${PORT} root@${IP}"
SCP="scp -o StrictHostKeyChecking=no -i ~/.ssh/id_rsa -P ${PORT}"
PROJ="/workspace/nba-ai-system"
# pod→windows backpull: override via NBA_LOCAL_PATH when running from the pod
#   e.g.  export NBA_LOCAL_PATH="neelj@192.168.1.X:/Users/neelj/nba-ai-system"
LOCAL="${NBA_LOCAL_PATH:-C:/Users/neelj/nba-ai-system}"

log() { echo "[$(date '+%H:%M:%S')] $*"; }

log "Watching pod for Phase G completion (syncing every 5 min)..."

last_sync=$(date +%s)
while true; do
    sleep 30

    now=$(date +%s)
    WORKERS=$($SSH "pgrep -f run_clip.py | grep -v pgrep | wc -l" 2>/dev/null || echo 0)

    # Sync every 5min or when workers finish
    if (( now - last_sync >= 300 )) || [ "$WORKERS" -eq 0 ]; then
        log "Syncing data (workers=${WORKERS})..."
        $SCP -r root@${IP}:${PROJ}/data/tracking/ "${LOCAL}/data/" 2>/dev/null || true
        $SCP -r root@${IP}:${PROJ}/data/events/ "${LOCAL}/data/" 2>/dev/null || true
        $SCP root@${IP}:${PROJ}/data/phase_g_metrics.csv "${LOCAL}/data/" 2>/dev/null || true
        last_sync=$(date +%s)
    fi

    if [ "$WORKERS" -eq 0 ]; then
        $SCP root@${IP}:${PROJ}/data/phase_g_processed.txt "${LOCAL}/data/" 2>/dev/null || true
        DONE=$(cat "${LOCAL}/data/phase_g_processed.txt" 2>/dev/null | wc -l || echo 0)
        log "All workers done. ${DONE} games in processed list."
        log "Tracking data: ${LOCAL}/data/tracking/"
        break
    else
        FRAME=$($SSH "grep -oE 'Frame [0-9]+' ${PROJ}/phase_g_batch.log 2>/dev/null | tail -1" 2>/dev/null || echo "...")
        log "  ${WORKERS} workers active | last log: ${FRAME}"
    fi
done
