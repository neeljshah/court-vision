#!/bin/bash
# Restart the footage track_daemon if it dies. The pod must never idle: a dead
# daemon means staged games pile up, the bridge's backlog cap shuts, and the
# GPU drops to 0% for the rest of the night.
#
# Liveness is checked with a PID FILE, never pgrep. `pgrep -f track_daemon`
# matches ANY command line mentioning the daemon -- including this check itself
# and any operator ssh diagnostic -- so a pgrep watchdog reports "up" precisely
# because it ran. That is not a hypothetical: it left the daemon dead here for
# ten minutes while the watchdog sat happily in its sleep loop.
#
# Deploy: scp to the pod and run  (nohup /workspace/keep_track_daemon.sh &)
set -u
REPO=/workspace/nba-ai-system
PID_FILE=/workspace/track_daemon.pid
LOG=/workspace/track_daemon.log
KEEPALIVE_LOG=/workspace/keepalive.log
WORKERS=${WORKERS:-24}

cd "$REPO" || exit 1

# One watchdog only. A second copy double-starts the daemon, and two daemons
# race to claim the same staged video.
MINE=$$
for pid in $(pgrep -f keep_track_daemon.sh); do
    [ "$pid" = "$MINE" ] && continue
    kill -9 "$pid" 2>/dev/null
done

while true; do
    alive=0
    if [ -f "$PID_FILE" ]; then
        pid=$(cat "$PID_FILE" 2>/dev/null)
        if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
            alive=1
        fi
    fi
    if [ "$alive" -eq 0 ]; then
        echo "$(date -Is) track_daemon down -- restarting" >> "$KEEPALIVE_LOG"
        nohup python -u -m scripts.platformkit.track_daemon \
            --workers "$WORKERS" --forever --interval 15 >> "$LOG" 2>&1 &
    fi
    sleep 60
done
