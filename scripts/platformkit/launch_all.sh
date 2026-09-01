#!/bin/bash
# Start the pod-side long-running loops, idempotently.
#
# Versioned here because it lived ONLY on the pod, unbacked, and its guard was
# broken. The original tested `ps aux | grep -q "[r]unner_mlb"` for a process
# whose actual command line is
#   python -m scripts.platformkit.queue_runner --queues data/footage_queue_mlb.json
# -- the string "runner_mlb" appears nowhere in it, so the guard could never
# match and every invocation started ANOTHER duplicate runner. Same bug family
# as the keepalive watchdog that grepped for a string contained in its own
# check: a guard that cannot match what it guards.
#
# The guard now tests the real command line.
#
# NOTE ON SCOPE: queue_runner is the OLD pod-side download path. YouTube blocks
# this datacenter IP, so it cannot fetch YouTube footage. Downloads now run on
# the local residential machine (scripts/platformkit/footage_bridge.py with
# --decouple) and tracking is consumed here by
# scripts/platformkit/track_daemon.py, which this script deliberately does NOT
# start -- track_daemon is owned by /workspace/keep_track_daemon.sh, and a
# second starter would race it for staged videos.
set -u
cd /workspace/nba-ai-system || exit 1
mkdir -p logs data/footage
export PYTHONPATH=/workspace/nba-ai-system
export PATH=/usr/local/bin:$PATH

# start <log-name> <full command...>  -- guards on the COMMAND, not the label.
start() {
    name="$1"
    shift
    # Match on the module path, which is what actually appears in ps output.
    pattern="$1"
    for arg in "$@"; do
        case "$arg" in
            -m) continue ;;
            scripts.platformkit.*) pattern="$arg" ;;
        esac
    done
    guard="[${pattern:0:1}]${pattern:1}"
    if ps -eo args | grep -q -- "$guard"; then
        echo "already running: $name ($pattern)"
        return
    fi
    setsid nohup "$@" < /dev/null >> "logs/${name}.log" 2>&1 &
    echo "started: $name"
}

start foundry_runner python -m scripts.platformkit.foundry_runner
start retrain_loop python -m scripts.platformkit.retrain_loop

sleep 4
echo "--- alive ---"
for m in foundry_runner retrain_loop; do
    printf '%s: %s\n' "$m" "$(ps -eo args | grep -c -- "[${m:0:1}]${m:1}")"
done
printf 'track_daemon (owned by keep_track_daemon.sh): %s\n' \
    "$(pgrep -fc 'scripts.platformkit.track_daemon' 2>/dev/null || echo 0)"
