#!/bin/bash
# budget_watchdog.sh — Stops pod-side workers when budget hit or 80 CLEAN reached.
#
# Note: this only KILLS WORKERS on the pod. It does NOT delete the RunPod instance
# — you must stop the pod in the RunPod web UI (or it stops billing on its own
# when you destroy it). Without runpodctl + API key we cannot programmatically
# destroy the pod.
#
# What it does:
#   - Every 5 min: check elapsed time and tally cost at GPU hourly rate
#   - When cost >= $14 OR phase_g_processed.txt has 80+ CLEAN games (via metrics CSV): kill workers
#   - Writes status to logs/budget_watchdog.log

set -uo pipefail

IP="${1:?Usage}"
PORT="${2:?Usage}"
HOURLY="${HOURLY_RATE:-0.69}"   # RTX 4090 default. Override with HOURLY_RATE=0.99 for 5090.
CAP_DOLLARS="${BUDGET_CAP:-14}"
CAP_CLEAN="${CLEAN_CAP:-80}"
INTERVAL=300

cd "$(dirname "$0")/.."
mkdir -p logs

START=$(date +%s)
ts() { date '+%Y-%m-%dT%H:%M:%S'; }

while true; do
    NOW=$(date +%s)
    ELAPSED_HR=$(awk "BEGIN{printf \"%.3f\", ($NOW - $START)/3600}")
    COST=$(awk "BEGIN{printf \"%.2f\", $ELAPSED_HR * $HOURLY}")

    # Count CLEAN tier from latest metrics CSV (synced by local_sync_watchdog.sh)
    CLEAN=$(awk -F, 'NR>1 && tolower($8)=="clean"{c++} END{print c+0}' data/phase_g_metrics.csv 2>/dev/null || echo 0)

    echo "[$(ts)] elapsed=${ELAPSED_HR}h  cost=\$${COST}  clean=${CLEAN}/${CAP_CLEAN}"

    OVER_BUDGET=$(awk "BEGIN{print ($COST >= $CAP_DOLLARS)}")
    HIT_TARGET=$(awk "BEGIN{print ($CLEAN >= $CAP_CLEAN)}")

    if [ "$OVER_BUDGET" = "1" ] || [ "$HIT_TARGET" = "1" ]; then
        REASON="budget"; [ "$HIT_TARGET" = "1" ] && REASON="80-clean target"
        echo "[$(ts)] STOPPING: $REASON hit. Killing workers on pod..."
        ssh -p "$PORT" -o StrictHostKeyChecking=no -o ConnectTimeout=10 "root@$IP" \
            "pgrep -f run_phase_g.py | xargs -r kill -TERM; sleep 5; pgrep -f run_phase_g.py | xargs -r kill -KILL; true" || \
            echo "[$(ts)] WARN: could not reach pod to kill workers"
        echo "[$(ts)] Workers killed. PLEASE STOP THE POD IN RUNPOD WEB UI to halt billing."
        exit 0
    fi

    sleep "$INTERVAL"
done
