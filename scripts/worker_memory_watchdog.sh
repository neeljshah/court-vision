#!/bin/bash
# worker_memory_watchdog.sh — Kills any worker whose RSS exceeds threshold.
#
# Some NBA videos trigger memory leaks in the tracker (e.g. 0022500066 grew to
# 112GB before OOM). Without a watchdog, one bad worker can spike cgroup memory
# and trigger OS-level OOM kills of *other* healthy workers in the same pod.
#
# This watchdog catches it FIRST: SIGTERM the bloated worker, let run_phase_g
# retry mechanism re-schedule the game (or mark it RC3_ZERO_ROWS).
#
# Usage: bash scripts/worker_memory_watchdog.sh &
# Env: THRESHOLD_GB=50 INTERVAL_SEC=10

set -uo pipefail
# Watchdog samples /proc/$pid/status VmRSS between worker GC cycles, so it
# catches PEAK RSS not steady-state. Steady-state after gc.collect+malloc_trim
# is ~3GB; transient peaks reach 50-70GB for 5-10s before being trimmed back.
# Set threshold to 150GB so we only kill TRULY runaway workers (e.g. the
# 112GB pathological case from 0022500066).
THRESHOLD_GB="${THRESHOLD_GB:-150}"
INTERVAL_SEC="${INTERVAL_SEC:-30}"
# Require N consecutive over-threshold samples before killing — avoids
# false kills on transient YOLO/OSNet alloc spikes that GC will trim.
CONSEC_KILLS="${CONSEC_KILLS:-3}"
THRESHOLD_KB=$((THRESHOLD_GB * 1024 * 1024))
declare -A over_count
LOG=/workspace/nba-ai-system/logs/memory_watchdog.log
mkdir -p $(dirname "$LOG")

ts() { date '+%Y-%m-%dT%H:%M:%S'; }
echo "[$(ts)] memory watchdog started (threshold=${THRESHOLD_GB}GB, interval=${INTERVAL_SEC}s)" >> "$LOG"

while true; do
    for pid in $(pgrep -f run_clip.py 2>/dev/null); do
        [ -d /proc/$pid ] || continue
        rss_kb=$(awk '/VmRSS/{print $2}' /proc/$pid/status 2>/dev/null)
        [ -z "$rss_kb" ] && continue
        if [ "$rss_kb" -gt "$THRESHOLD_KB" ]; then
            game=$(cat /proc/$pid/cmdline 2>/dev/null | tr '\0' ' ' | grep -oE 'game-id [0-9]+' || echo "?")
            rss_gb=$(awk -v k=$rss_kb 'BEGIN{printf "%.1f", k/1024/1024}')
            echo "[$(ts)] KILL PID $pid ${game} RSS=${rss_gb}GB > ${THRESHOLD_GB}GB threshold" >> "$LOG"
            kill -TERM $pid 2>/dev/null
            sleep 5
            kill -KILL $pid 2>/dev/null || true
        fi
    done
    sleep "$INTERVAL_SEC"
done
