#!/bin/bash
# cleanup_videos.sh — Post-pipeline video cleanup for the auto-ingest loop.
#
# Called from auto_ingest_track_loop.sh in two modes:
#   1. Per-game cleanup (called immediately after a game succeeds):
#      bash cleanup_videos.sh --game <game_id>
#   2. Periodic sweep (called every ~6h by the loop):
#      bash cleanup_videos.sh --sweep
#
# SAFETY: never deletes data/tracking/ content; only removes source videos
# from /root/nba_videos/ after confirmed successful tracking output.
#
# Successful = tracking_data.csv exists with >= MIN_ROWS data rows.

set -uo pipefail

WORKDIR="${WORKDIR:-/workspace/nba-ai-system}"
VIDEOS_DIR="${NBA_VIDEOS_DIR:-/root/nba_videos}"
TRACKING_DIR="$WORKDIR/data/tracking"
LOG="$WORKDIR/data/ingest/cleanup_videos.log"
MIN_ROWS="${CLEANUP_MIN_ROWS:-50000}"        # full-game signal
SWEEP_MIN_ROWS="${CLEANUP_SWEEP_MIN_ROWS:-5000}"  # conservative for older games
SWEEP_AGE_DAYS="${CLEANUP_SWEEP_AGE_DAYS:-7}"

mkdir -p "$(dirname "$LOG")"
ts() { date '+%Y-%m-%dT%H:%M:%S'; }
log() { echo "[$(ts)] cleanup_videos: $*" | tee -a "$LOG"; }

# Count data rows in a CSV (excluding header line)
_csv_rows() {
    local f="$1"
    [ -f "$f" ] || { echo 0; return; }
    # Use awk for speed — wc -l counts the header too
    awk 'NR>1{c++} END{print c+0}' "$f"
}

# --- Mode 1: per-game cleanup after confirmed success ---
if [ "${1:-}" = "--game" ]; then
    game_id="${2:?--game requires a game_id argument}"
    video="$VIDEOS_DIR/${game_id}.mp4"
    csv="$TRACKING_DIR/${game_id}/tracking_data.csv"

    if [ ! -f "$video" ]; then
        log "SKIP $game_id — no video file at $video"
        exit 0
    fi

    rows=$(_csv_rows "$csv")
    if [ "$rows" -ge "$MIN_ROWS" ]; then
        rm -f "$video"
        log "DELETED $video (tracking rows=$rows >= $MIN_ROWS)"
    else
        log "KEEP $video (tracking rows=$rows < $MIN_ROWS threshold; not a full-game run)"
    fi
    exit 0
fi

# --- Mode 2: periodic sweep ---
if [ "${1:-}" = "--sweep" ]; then
    log "Sweep started (age>=${SWEEP_AGE_DAYS}d, rows>=${SWEEP_MIN_ROWS})"
    deleted=0
    skipped=0

    for video in "$VIDEOS_DIR"/*.mp4; do
        [ -f "$video" ] || continue
        game_id=$(basename "$video" .mp4)

        # Check age — skip if newer than SWEEP_AGE_DAYS
        if find "$video" -mtime -"$SWEEP_AGE_DAYS" -maxdepth 0 | grep -q .; then
            skipped=$((skipped+1))
            continue
        fi

        csv="$TRACKING_DIR/${game_id}/tracking_data.csv"
        rows=$(_csv_rows "$csv")
        if [ "$rows" -ge "$SWEEP_MIN_ROWS" ]; then
            rm -f "$video"
            log "SWEEP DELETED $video (age>=${SWEEP_AGE_DAYS}d, rows=$rows)"
            deleted=$((deleted+1))
        else
            log "SWEEP KEEP $video (rows=$rows < $SWEEP_MIN_ROWS or no tracking output)"
            skipped=$((skipped+1))
        fi
    done

    log "Sweep complete: deleted=$deleted skipped=$skipped"
    # Emit post-sweep disk state
    use=$(df --output=pcent /root 2>/dev/null | tail -1 | tr -d ' %' || echo "?")
    log "Overlay disk after sweep: ${use}%"
    exit 0
fi

echo "Usage: $0 --game <game_id> | --sweep" >&2
exit 1
