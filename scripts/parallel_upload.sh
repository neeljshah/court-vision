#!/bin/bash
# 4-way parallel scp uploader. Reads paths from .pending_uploads.txt
set -uo pipefail
IP=213.192.2.107
PORT=40017
DEST="root@${IP}:/workspace/nba-ai-system/data/videos/full_games/"

upload_one() {
    local f="$1"
    local name=$(basename "$f")
    local t0=$(date +%s)
    if scp -q -o StrictHostKeyChecking=no -o ServerAliveInterval=30 -P "$PORT" "$f" "$DEST" 2>&1; then
        local dt=$(( $(date +%s) - t0 ))
        echo "[$(date +%H:%M:%S)] OK $name (${dt}s)"
    else
        echo "[$(date +%H:%M:%S)] FAIL $name"
    fi
}
export -f upload_one
export IP PORT DEST

cat .pending_uploads.txt | xargs -n 1 -P 4 -I {} bash -c 'upload_one "$@"' _ {}
echo "[$(date +%H:%M:%S)] ALL DONE"
