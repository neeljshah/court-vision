#!/bin/bash
# pod_cleaner_and_round2.sh — Runs ON THE POD.
# Continuously:
#   1. Watches phase_g_processed.txt for newly-completed games
#   2. Deletes the corresponding video from /root/nba_videos (frees space)
#   3. When round 1 workers exit AND there are unprocessed videos locally on USER side,
#      signals "ROUND_1_DONE" via a flag file. Local-side script will upload round 2.

set -uo pipefail
PROJ=/workspace/nba-ai-system
PROCESSED="$PROJ/data/phase_g_processed.txt"
VIDEOS=/root/nba_videos
FLAG="/root/round1_done.flag"

ts() { date '+%Y-%m-%dT%H:%M:%S'; }

echo "[$(ts)] cleaner started"
prev_done=""

while true; do
    # Sleep 30s between checks
    sleep 30

    # Delete any video whose stem is in processed.txt (idempotent, simple)
    deleted=0
    if [ -f "$PROCESSED" ]; then
        while IFS= read -r stem; do
            [ -z "$stem" ] && continue
            stem=$(echo "$stem" | tr -d '[:space:]')
            [ -z "$stem" ] && continue
            video="$VIDEOS/${stem}.mp4"
            if [ -f "$video" ]; then
                rm -f "$video"
                deleted=$((deleted+1))
                echo "[$(ts)] cleaned ${stem}.mp4"
            fi
        done < "$PROCESSED"
    fi
    if [ $deleted -gt 0 ]; then
        free_gb=$(df /root | awk 'NR==2{printf "%d", $4/1024/1024}')
        remaining=$(ls "$VIDEOS"/*.mp4 2>/dev/null | wc -l)
        echo "[$(ts)] deleted=$deleted remaining_videos=$remaining /root_free=${free_gb}GB"
    fi

    # Check if worker process still alive
    if ! pgrep -f run_phase_g.py >/dev/null 2>&1; then
        # Workers exited — round complete
        remaining=$(ls "$VIDEOS"/*.mp4 2>/dev/null | wc -l)
        if [ -f "$FLAG" ]; then
            # Already flagged; idle
            :
        else
            echo "[$(ts)] ROUND COMPLETE — workers exited. Remaining videos: $remaining"
            echo "$(date)" > "$FLAG"
        fi
    fi
done
