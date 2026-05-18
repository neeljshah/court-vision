#!/bin/bash
# Upload local MP4s to pod + register as 'verified' in pod SQLite.
# Loops forever — picks up newly-downloaded games too.
#
# Required env:
#   RUNPOD_HOST   e.g. root@1.2.3.4
#   RUNPOD_PORT   e.g. 40045
# Optional:
#   FFMPEG_DIR    prepended to PATH so ffprobe resolves
#   SSH_KEY       default ~/.ssh/id_rsa
#   POD_VIDEOS    default /root/nba_videos

set -u
cd "$(dirname "$0")/.."

: "${RUNPOD_HOST:?Set RUNPOD_HOST=root@<ip>}"
: "${RUNPOD_PORT:?Set RUNPOD_PORT=<ssh_port>}"

[ -n "${FFMPEG_DIR:-}" ] && export PATH="$FFMPEG_DIR:$PATH"

SSH_KEY="${SSH_KEY:-$HOME/.ssh/id_rsa}"
SSH_CFG="${SSH_CFG:-$HOME/.ssh/config.pod}"
POD_VIDEOS="${POD_VIDEOS:-/root/nba_videos}"

# Returns fps as integer (truncated). 60fps → 60, 30fps → 30, NTSC 29.97 → 29
video_fps_int() {
    local f="$1"
    local r=$(ffprobe -v error -select_streams v:0 -show_entries stream=r_frame_rate \
                       -of csv=p=0 "$f" 2>/dev/null | head -1 | tr -d '\r')
    [ -z "$r" ] && { echo 0; return; }
    local num=${r%/*}; local den=${r#*/}
    [ "$num" = "$den" ] && { echo "$r"; return; }
    echo $(( num / den ))
}

echo "[upload_pipeline] starting at $(date)"

while true; do
    count=0
    for f in data/videos/full_games/*.mp4; do
        [ -f "$f" ] || continue
        gid=$(basename "$f" .mp4)

        # Skip games already processed locally (have tracking output)
        if [ -d "data/tracking/$gid" ]; then continue; fi

        # Skip 60fps (too slow — halves parallel throughput)
        fps=$(video_fps_int "$f")
        if [ "$fps" -ge 50 ]; then
            echo "[$(date +%H:%M:%S)] SKIP $gid (${fps}fps — 60fps rejected)"
            continue
        fi

        # Check pod SQLite status
        pod_status=$(ssh -F "$SSH_CFG" pod "cd /workspace/nba-ai-system && python -c \"
import sqlite3
c = sqlite3.connect('data/ingest/queue.db')
r = c.execute('SELECT status FROM games WHERE game_id=?',('$gid',)).fetchone()
print(r[0] if r else 'none')
\"" 2>/dev/null | tr -d '\r\n ')

        if [[ "$pod_status" =~ ^(processed|processing|verified)$ ]]; then
            continue
        fi

        size=$(stat -c%s "$f" 2>/dev/null || stat -f%z "$f" 2>/dev/null)
        echo "[$(date +%H:%M:%S)] UPLOAD $gid ($(( size / 1024 / 1024 ))MB) status=$pod_status"
        if scp -i "$SSH_KEY" -P "$RUNPOD_PORT" -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
            "$f" "$RUNPOD_HOST:$POD_VIDEOS/$gid.mp4" 2>&1 | tail -1; then

            ssh -F "$SSH_CFG" pod "cd /workspace/nba-ai-system && python -c \"
from src.ingest.db import connect, migrate
from src.ingest.manifest import add_game, update_game, get_game
c = connect('data/ingest/queue.db'); migrate(c)
if get_game(c, '$gid') is None:
    add_game(c, '$gid', source='local_upload', status='verified')
else:
    update_game(c, '$gid', status='verified')
print('REGISTERED $gid')
\"" 2>&1 | tail -2
            count=$((count+1))
        else
            echo "[$(date +%H:%M:%S)] UPLOAD FAILED $gid"
        fi
    done

    echo "[$(date +%H:%M:%S)] cycle done: $count uploaded. Sleeping 120s..."
    sleep 120
done
