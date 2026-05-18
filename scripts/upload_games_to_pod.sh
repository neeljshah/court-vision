#!/bin/bash
# upload_games_to_pod.sh — scp a list of game MP4s to a RunPod.
#
# Replaces the legacy session-specific upload_2526_only.sh /
# upload_direct_overlay.sh / upload_videos_pod.sh scripts that hardcoded
# game IDs and a one-time pod IP. This script is reusable: pass game IDs
# as args or via stdin / a file.
#
# Required env:
#   RUNPOD_HOST   e.g. root@1.2.3.4
#   RUNPOD_PORT   e.g. 14149
# Optional:
#   SSH_KEY       default ~/.ssh/id_rsa
#   LOCAL_VIDEOS  default data/videos/full_games
#   REMOTE_VIDEOS default /workspace/nba-ai-system/data/videos/full_games
#   CHUNK_SIZE    default 10 (games per scp invocation)
#
# Usage:
#   RUNPOD_HOST=root@1.2.3.4 RUNPOD_PORT=14149 \
#       bash scripts/upload_games_to_pod.sh 0022500033 0022500034
#
#   echo -e "0022500033\n0022500034" | RUNPOD_HOST=... RUNPOD_PORT=... \
#       bash scripts/upload_games_to_pod.sh
#
#   RUNPOD_HOST=... RUNPOD_PORT=... \
#       bash scripts/upload_games_to_pod.sh < games.txt

set -euo pipefail
: "${RUNPOD_HOST:?Set RUNPOD_HOST=root@<ip>}"
: "${RUNPOD_PORT:?Set RUNPOD_PORT=<ssh_port>}"

SSH_KEY="${SSH_KEY:-$HOME/.ssh/id_rsa}"
LOCAL_VIDEOS="${LOCAL_VIDEOS:-data/videos/full_games}"
REMOTE_VIDEOS="${REMOTE_VIDEOS:-/workspace/nba-ai-system/data/videos/full_games}"
CHUNK_SIZE="${CHUNK_SIZE:-10}"

if [ "$#" -gt 0 ]; then
    mapfile -t GAMES < <(printf '%s\n' "$@")
else
    mapfile -t GAMES
fi

if [ "${#GAMES[@]}" -eq 0 ]; then
    echo "No game IDs provided. Pass as args, pipe stdin, or redirect a file." >&2
    exit 1
fi

total=${#GAMES[@]}
echo "Uploading $total game(s) to $RUNPOD_HOST:$RUNPOD_PORT (chunk size $CHUNK_SIZE)..."

idx=0
chunk_no=1
while [ "$idx" -lt "$total" ]; do
    end=$(( idx + CHUNK_SIZE ))
    [ "$end" -gt "$total" ] && end=$total
    paths=()
    for ((i=idx; i<end; i++)); do
        f="$LOCAL_VIDEOS/${GAMES[$i]}.mp4"
        if [ -f "$f" ]; then
            paths+=("$f")
        else
            echo "  skip ${GAMES[$i]} (not found: $f)" >&2
        fi
    done
    if [ "${#paths[@]}" -gt 0 ]; then
        echo "Chunk $chunk_no: $(( end - idx )) games..."
        scp -o StrictHostKeyChecking=no -i "$SSH_KEY" -P "$RUNPOD_PORT" \
            "${paths[@]}" "$RUNPOD_HOST:$REMOTE_VIDEOS/"
    fi
    idx=$end
    chunk_no=$(( chunk_no + 1 ))
done
echo "All chunks uploaded."
