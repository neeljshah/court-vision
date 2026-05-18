#!/bin/bash
# local_sync_watchdog.sh — Pulls tracking/events data from pod to local every N min.
# Uses scp (Windows has no rsync). Runs in background.

set -uo pipefail

IP="${1:?Usage: bash scripts/local_sync_watchdog.sh <IP> <PORT>}"
PORT="${2:?Usage: bash scripts/local_sync_watchdog.sh <IP> <PORT>}"
PROJ="/workspace/nba-ai-system"
INTERVAL="${SYNC_INTERVAL:-900}"

cd "$(dirname "$0")/.."
mkdir -p logs data/tracking data/events data/ingest

ts() { date '+%Y-%m-%dT%H:%M:%S'; }
SSH_OPTS="-o StrictHostKeyChecking=no -o ConnectTimeout=10 -o ServerAliveInterval=30"

while true; do
    echo "[$(ts)] Sync cycle starting..."

    # 1. Pull metrics/processed files (small, fast)
    scp $SSH_OPTS -P "$PORT" \
        "root@$IP:$PROJ/data/phase_g_processed.txt" \
        "root@$IP:$PROJ/data/phase_g_metrics.csv" \
        data/ 2>/dev/null || echo "[$(ts)] WARN: metrics pull failed"

    scp $SSH_OPTS -P "$PORT" \
        "root@$IP:$PROJ/data/ingest/queue.db" \
        data/ingest/ 2>/dev/null || true

    # 2. List remote tracking dirs and pull each (scp -r is recursive)
    TRACK_DIRS=$(ssh $SSH_OPTS -p "$PORT" "root@$IP" \
        "find $PROJ/data/tracking -maxdepth 1 -mindepth 1 -type d 2>/dev/null" 2>/dev/null)

    pulled=0
    if [ -n "$TRACK_DIRS" ]; then
        while IFS= read -r remote_dir; do
            [ -z "$remote_dir" ] && continue
            game_id=$(basename "$remote_dir")
            local_dir="data/tracking/$game_id"
            # Compare remote vs local: only pull if remote has newer/more data
            remote_size=$(ssh $SSH_OPTS -p "$PORT" "root@$IP" "du -sb $remote_dir 2>/dev/null | cut -f1" 2>/dev/null)
            local_size=0
            [ -d "$local_dir" ] && local_size=$(du -sb "$local_dir" 2>/dev/null | cut -f1)
            if [ -n "$remote_size" ] && [ "${remote_size:-0}" -gt "${local_size:-0}" ]; then
                # scp -r overwrites files; this brings in updates
                scp -r $SSH_OPTS -P "$PORT" "root@$IP:$remote_dir" data/tracking/ 2>/dev/null && \
                    pulled=$((pulled+1))
            fi
        done <<< "$TRACK_DIRS"
    fi

    PROCESSED=$(wc -l < data/phase_g_processed.txt 2>/dev/null || echo "?")
    CLEAN=$(awk -F, 'NR>1 && tolower($8)=="clean"{c++} END{print c+0}' data/phase_g_metrics.csv 2>/dev/null || echo 0)
    echo "[$(ts)] Synced. processed=$PROCESSED clean=$CLEAN new_dirs=$pulled"

    sleep "$INTERVAL"
done
