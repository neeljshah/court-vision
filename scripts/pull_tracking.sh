#!/bin/bash
# pull_tracking.sh — pulls tracking data from pod every 30 min.
# Run from Git Bash: bash scripts/pull_tracking.sh
POD="root@103.196.86.195"
PORT=19528
REMOTE="/workspace/nba-ai-system"
LOCAL="/c/Users/neelj/nba-ai-system"

echo "[$(date)] Starting pull loop (every 30 min)..."
while true; do
  echo "[$(date)] Pulling..."
  scp -o StrictHostKeyChecking=no -P $PORT \
    $POD:$REMOTE/data/phase_g_processed.txt $LOCAL/data/phase_g_processed.txt
  scp -o StrictHostKeyChecking=no -P $PORT -r \
    $POD:$REMOTE/data/tracking/. $LOCAL/data/tracking/
  scp -o StrictHostKeyChecking=no -P $PORT \
    $POD:$REMOTE/data/phase_g_metrics.csv $LOCAL/data/phase_g_metrics.csv 2>/dev/null
  COUNT=$(grep -cE '^002250[0-9]{4}$' $LOCAL/data/phase_g_processed.txt 2>/dev/null || echo 0)
  echo "[$(date)] Done. 2025-26 games processed: $COUNT"
  if [ "$COUNT" -ge 100 ]; then
    echo "[$(date)] 100 games reached! Run complete."
    break
  fi
  sleep 1800
done
