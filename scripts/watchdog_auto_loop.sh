#!/bin/bash
# Watchdog for auto_ingest_track_loop.sh — checks every 5 min, restarts if dead.
# Also runs archive_prime_clean.py when /root disk usage > 78%.
# Designed to be daemonized via setsid + nohup; logs to /workspace/watchdog.log.
set -u

LOG=/workspace/watchdog.log
LOOP_SCRIPT=/workspace/nba-ai-system/scripts/auto_ingest_track_loop.sh
LOOP_LOG=/workspace/auto_loop_stdout.log
ARCHIVE_SCRIPT=/workspace/nba-ai-system/scripts/archive_prime_clean.py
ARCHIVE_LOG=/workspace/archive.log
STUCK_SCRIPT=/workspace/nba-ai-system/scripts/kill_stuck_workers.py
DISK_THRESHOLD=78
TICK_SEC=300

ts() { date '+%Y-%m-%d %H:%M:%S'; }

log() { echo "[$(ts)] $*" >> "$LOG"; }

restart_loop() {
  log "RESTART: auto_ingest_track_loop.sh — no live pid found"
  nohup setsid bash "$LOOP_SCRIPT" > "$LOOP_LOG" 2>&1 < /dev/null &
  sleep 3
  if pgrep -af "auto_ingest_track_loop\.sh" > /dev/null 2>&1; then
    log "RESTART OK: pid=$(pgrep -af 'auto_ingest_track_loop\.sh' | awk '{print $1}' | tr '\n' ' ')"
  else
    log "RESTART FAILED: loop did not come up"
  fi
}

log "watchdog started (pid=$$ tick=${TICK_SEC}s threshold=${DISK_THRESHOLD}%)"

while true; do
  # 1. Loop alive?
  if ! pgrep -af "auto_ingest_track_loop\.sh" > /dev/null 2>&1; then
    restart_loop
  fi

  # 2. Disk pressure?
  use=$(df --output=pcent /root | tail -1 | tr -d ' %')
  if [ -n "$use" ] && [ "$use" -ge "$DISK_THRESHOLD" ]; then
    log "DISK ${use}% >= ${DISK_THRESHOLD}% — running archive"
    cd /workspace/nba-ai-system && python3 "$ARCHIVE_SCRIPT" >> "$ARCHIVE_LOG" 2>&1
    new_use=$(df --output=pcent /root | tail -1 | tr -d ' %')
    log "DISK after archive: ${new_use}%"
  fi

  # 3. Stuck workers? (>90 min, no frame progress in 5 min)
  if [ -f "$STUCK_SCRIPT" ]; then
    python3 "$STUCK_SCRIPT" 2>&1 | while IFS= read -r line; do log "STUCK $line"; done
  fi

  sleep "$TICK_SEC"
done
