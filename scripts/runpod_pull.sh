#!/usr/bin/env bash
# runpod_pull.sh — Pull processed game data from RunPod back to local PC
#
# Usage:
#   source .runpod
#   bash scripts/runpod_pull.sh           # pull once
#   bash scripts/runpod_pull.sh --watch   # pull every 5 min until batch done
#
# What it syncs back:
#   data/games/          — per-game CSVs (tracking, shots, possessions, features)
#   data/tracking/       — alternate output dir
#   data/season_batch_log.csv — progress log
#   logs/batch.log       — live run log
set -euo pipefail

WATCH=false
INTERVAL=300  # seconds between syncs in watch mode

for arg in "$@"; do
    [[ "$arg" == "--watch" ]] && WATCH=true
    [[ "$arg" =~ ^--interval=([0-9]+)$ ]] && INTERVAL="${BASH_REMATCH[1]}"
done

# ── Load config ──────────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

if [[ -z "${RUNPOD_IP:-}" ]]; then
    if [[ -f "$ROOT_DIR/.runpod" ]]; then
        source "$ROOT_DIR/.runpod"
    else
        echo "ERROR: .runpod config not found."
        exit 1
    fi
fi

SSH_OPTS="-o StrictHostKeyChecking=no -o ConnectTimeout=10 -p $RUNPOD_PORT"
[[ -n "${RUNPOD_KEY:-}" ]] && SSH_OPTS="$SSH_OPTS -i $RUNPOD_KEY"
RSYNC_SSH="ssh $SSH_OPTS"
SRC="${RUNPOD_USER}@${RUNPOD_IP}"

do_pull() {
    echo "[$(date '+%H:%M:%S')] Pulling from $SRC:$REMOTE_DIR ..."

    # Game data (primary output)
    rsync -az --progress \
        -e "$RSYNC_SSH" \
        "$SRC:${REMOTE_DIR}/data/games/" \
        "$ROOT_DIR/data/games/" 2>/dev/null || true

    # Alternate tracking output dir
    rsync -az --progress \
        -e "$RSYNC_SSH" \
        "$SRC:${REMOTE_DIR}/data/tracking/" \
        "$ROOT_DIR/data/tracking/" 2>/dev/null || true

    # Batch log
    rsync -az \
        -e "$RSYNC_SSH" \
        "$SRC:${REMOTE_DIR}/data/season_batch_log.csv" \
        "$ROOT_DIR/data/season_batch_log.csv" 2>/dev/null || true

    # Live batch log
    rsync -az \
        -e "$RSYNC_SSH" \
        "$SRC:${REMOTE_DIR}/logs/batch.log" \
        "$ROOT_DIR/logs/batch.log" 2>/dev/null || true

    # Count completed games
    DONE=$(ls "$ROOT_DIR/data/games/" 2>/dev/null | wc -l | tr -d ' ')
    echo "  Done: $DONE game dirs in data/games/"

    # Show last 3 lines of batch log if it exists
    if [[ -f "$ROOT_DIR/logs/batch.log" ]]; then
        echo "  Last log lines:"
        tail -3 "$ROOT_DIR/logs/batch.log" | sed 's/^/    /'
    fi
}

if [[ "$WATCH" == "true" ]]; then
    echo "==> Watch mode — syncing every ${INTERVAL}s. Ctrl+C to stop."
    while true; do
        do_pull
        echo "  Next sync in ${INTERVAL}s..."
        sleep "$INTERVAL"
    done
else
    do_pull
    echo "==> Pull complete."
fi
