#!/bin/bash
# pull_tracking.sh — pulls tracking data from a RunPod every 30 min.
#
# Required env (set before running):
#   RUNPOD_HOST   e.g. root@1.2.3.4         (pod user@ip)
#   RUNPOD_PORT   e.g. 19528                (ssh port advertised by pod)
# Optional:
#   REMOTE_ROOT   default /workspace/nba-ai-system
#   LOCAL_ROOT    default $PWD (when run from repo root)
#   POLL_SECONDS  default 1800
#   STOP_AT       default 100 (processed-game count to halt at)
#
# Usage: RUNPOD_HOST=root@1.2.3.4 RUNPOD_PORT=19528 bash scripts/pull_tracking.sh

set -euo pipefail
: "${RUNPOD_HOST:?Set RUNPOD_HOST=root@<ip>}"
: "${RUNPOD_PORT:?Set RUNPOD_PORT=<ssh_port>}"

REMOTE_ROOT="${REMOTE_ROOT:-/workspace/nba-ai-system}"
LOCAL_ROOT="${LOCAL_ROOT:-$PWD}"
POLL_SECONDS="${POLL_SECONDS:-1800}"
STOP_AT="${STOP_AT:-100}"

echo "[$(date)] Starting pull loop ($RUNPOD_HOST:$RUNPOD_PORT every ${POLL_SECONDS}s)..."
while true; do
  echo "[$(date)] Pulling..."
  scp -o StrictHostKeyChecking=no -P "$RUNPOD_PORT" \
    "$RUNPOD_HOST:$REMOTE_ROOT/data/phase_g_processed.txt" \
    "$LOCAL_ROOT/data/phase_g_processed.txt"
  scp -o StrictHostKeyChecking=no -P "$RUNPOD_PORT" -r \
    "$RUNPOD_HOST:$REMOTE_ROOT/data/tracking/." \
    "$LOCAL_ROOT/data/tracking/"
  scp -o StrictHostKeyChecking=no -P "$RUNPOD_PORT" \
    "$RUNPOD_HOST:$REMOTE_ROOT/data/phase_g_metrics.csv" \
    "$LOCAL_ROOT/data/phase_g_metrics.csv" 2>/dev/null || true
  COUNT=$(grep -cE '^002250[0-9]{4}$' "$LOCAL_ROOT/data/phase_g_processed.txt" 2>/dev/null || echo 0)
  echo "[$(date)] Done. 2025-26 games processed: $COUNT"
  if [ "$COUNT" -ge "$STOP_AT" ]; then
    echo "[$(date)] $STOP_AT games reached! Run complete."
    break
  fi
  sleep "$POLL_SECONDS"
done
