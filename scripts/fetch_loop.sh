#!/bin/bash
# Local fetch loop — runs on residential IP to bypass YT bot-block.
# Residential = home IP; NEVER run this on the pod.
set -u
cd "$(dirname "$0")/.."

# Optional: point FFMPEG_DIR at a directory containing ffmpeg/ffprobe.
# Falls back to whatever is already on PATH.
if [ -n "${FFMPEG_DIR:-}" ]; then
    export PATH="$FFMPEG_DIR:$PATH"
fi
export PYTHONIOENCODING=utf-8
export PYTHONUTF8=1

echo "[fetch_loop] starting at $(date)  ffmpeg=$(which ffmpeg)"

while true; do
    echo "[$(date +%H:%M:%S)] fetch cycle starting"
    python -X utf8 scripts/fetch_games.py --count 8 --full \
        --from 2025-10-21 --to 2026-04-20 2>&1 | tail -40

    # Post-download 60fps purge: remove any newly-fetched 60fps videos
    for f in data/videos/full_games/*.mp4; do
        [ -f "$f" ] || continue
        r=$(ffprobe -v error -select_streams v:0 -show_entries stream=r_frame_rate \
                    -of csv=p=0 "$f" 2>/dev/null | head -1 | tr -d '\r')
        [ -z "$r" ] && continue
        num=${r%/*}; den=${r#*/}
        [ "$num" = "$den" ] && fps=$r || fps=$(( num / den ))
        if [ "$fps" -ge 50 ]; then
            echo "[$(date +%H:%M:%S)] PURGE 60fps: $(basename "$f")"
            rm -f "$f"
        fi
    done

    echo "[$(date +%H:%M:%S)] fetch cycle done. Sleeping 300s..."
    sleep 300
done
