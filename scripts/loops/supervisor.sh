#!/bin/bash
# Supervisor: keeps ONE run_phase_g alive. Singleton-guarded (PID file).
# Relaunches run_phase_g when it exits so new downloads get picked up.
PROJ=/workspace/nba-ai-system
LOG=/workspace/supervisor.log
PIDFILE=/workspace/supervisor.pid
WORKERS="${WORKERS:-6}"            # verified-best for RTX 3090 (mps-6 = 113 fps)
OMP_PER_WORKER="${OMP_PER_WORKER:-8}"   # OMP=8 beat OMP=12 (load 21 vs 33)

# --- singleton guard ---
if [ -f "$PIDFILE" ]; then
  oldpid=$(cat "$PIDFILE" 2>/dev/null)
  if [ -n "$oldpid" ] && kill -0 "$oldpid" 2>/dev/null; then
    echo "$(date '+%F %T') another supervisor (pid $oldpid) alive — exiting" >> "$LOG"
    exit 0
  fi
fi
echo $$ > "$PIDFILE"
trap 'rm -f "$PIDFILE"' EXIT
echo "$(date '+%F %T') supervisor started pid=$$ workers=$WORKERS" >> "$LOG"

while true; do
  if ! pgrep -f 'scripts/run_phase_g.py' >/dev/null 2>&1; then
    DONE="$PROJ/data/phase_g_processed.txt"
    for d in "$PROJ"/data/tracking/*/; do
      [ -d "$d" ] || continue
      gid=$(basename "$d")
      grep -qx "$gid" "$DONE" 2>/dev/null || { rm -rf "$d"; echo "$(date '+%F %T') cleared partial $gid" >> "$LOG"; }
    done
    unproc=0
    for v in /root/nba_videos/*.mp4; do
      [ -f "$v" ] || continue
      gid=$(basename "$v" .mp4)
      grep -qx "$gid" "$DONE" 2>/dev/null || unproc=$((unproc+1))
    done
    if [ "$unproc" -gt 0 ]; then
      echo "$(date '+%F %T') relaunching run_phase_g ($unproc unprocessed)" >> "$LOG"
      cd "$PROJ"
      FULL_GAME=1 OMP_PER_WORKER="$OMP_PER_WORKER" RSS_KILL_GB=40 PHASE_G_VIDEO_DIR=/root/nba_videos bash scripts/launch_multigpu.sh "$WORKERS" >> "$LOG" 2>&1
      sleep 40
    else
      echo "$(date '+%F %T') no unprocessed videos — idle" >> "$LOG"
    fi
  fi
  sleep 90
done
