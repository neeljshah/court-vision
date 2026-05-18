#!/usr/bin/env bash
# Local monitor: runs every CHECK_S seconds.
# - Counts good games
# - Uploads H264 videos to pod when queue is low
# - Pulls tracking data
# - Prints status

# Required env: RUNPOD_HOST=root@<ip>, RUNPOD_PORT=<ssh_port>
# Optional:     FFPROBE=path/to/ffprobe (default: 'ffprobe' on PATH)
set -u
: "${RUNPOD_HOST:?Set RUNPOD_HOST=root@<ip>}"
: "${RUNPOD_PORT:?Set RUNPOD_PORT=<ssh_port>}"
POD_PORT="$RUNPOD_PORT"
POD_HOST="$RUNPOD_HOST"
POD_SSH="ssh -p $POD_PORT $POD_HOST"
FFPROBE="${FFPROBE:-ffprobe}"
UPLOAD_THRESHOLD=10
MAX_UPLOAD=8      # never upload more than this at once — keeps pod disk bounded
METRICS="data/phase_g_metrics.csv"

log() { echo "[$(date '+%H:%M:%S')] $*"; }

count_good() {
    awk -F',' 'NR>1 {latest[$2]=$8} END {n=0; for(g in latest) if(latest[g]=="high"||latest[g]=="medium") n++; print n}' \
        "$METRICS" 2>/dev/null || echo 0
}

rescan_codecs() {
    for f in data/videos/full_games/*.mp4; do
        [ -f "$f" ] || continue
        g=$(basename "$f" .mp4)
        grep -q "|${g}.mp4$" /tmp/codec_scan.txt 2>/dev/null && continue
        codec=$($FFPROBE -v error -select_streams v:0 -show_entries stream=codec_name -of csv=p=0 "$f" 2>/dev/null)
        [ -n "$codec" ] && echo "${codec}|${g}.mp4" >> /tmp/codec_scan.txt
    done
}

upload_new_h264() {
    $POD_SSH "ls /root/nba_videos/*.mp4 2>/dev/null | xargs -I{} basename {} .mp4 || true" 2>/dev/null | sort > /tmp/pod_now.txt
    # Also exclude games already in processed.txt (cleaner deletes video after processing)
    # Strip suffixes (_RC3, _PREFLIGHT_FAIL, etc.) to get base game IDs
    $POD_SSH "grep -oE '^002250[0-9]+' /workspace/nba-ai-system/data/phase_g_processed.txt 2>/dev/null" | sort -u > /tmp/pod_processed.txt
    # Only upload 2025-26 season games (002250*) — 2024-25 games skip pod cleaner regex
    grep "^h264|" /tmp/codec_scan.txt | awk -F'|' '{print $2}' | sed 's/\.mp4$//' | grep '^002250' | sort > /tmp/local_h264_now.txt
    uploaded=0
    while IFS= read -r g; do
        [ "$uploaded" -ge "$MAX_UPLOAD" ] && break
        f="data/videos/full_games/${g}.mp4"
        [ -f "$f" ] || continue
        scp -P $POD_PORT "$f" "${POD_HOST}:/root/nba_videos/" 2>/dev/null && log "  Uploaded $g" && ((uploaded++)) || true
    done < <(comm -23 /tmp/local_h264_now.txt /tmp/pod_now.txt | comm -23 - /tmp/pod_processed.txt)
    [ $uploaded -gt 0 ] && log "Uploaded $uploaded videos" || log "No new videos to upload"
}

good=$(count_good)
processed=$($POD_SSH "grep -cE '^002250[0-9]+\$' /workspace/nba-ai-system/data/phase_g_processed.txt 2>/dev/null" || echo "?")
workers=$($POD_SSH "pgrep -f run_clip.py | wc -l" 2>/dev/null || echo "?")
pod_queue=$($POD_SSH "ls /root/nba_videos/*.mp4 2>/dev/null | wc -l" 2>/dev/null || echo "?")
ram_gb=$($POD_SSH "cat /sys/fs/cgroup/memory.current 2>/dev/null | awk '{printf \"%.0f\", \$1/1024/1024/1024}'" 2>/dev/null || echo "?")

log "=== STATUS === good=$good/100  processed=$processed  workers=$workers  pod_queue=$pod_queue  ram=${ram_gb}GB"

rescan_codecs

if [ "${pod_queue:-99}" -le "$UPLOAD_THRESHOLD" ] 2>/dev/null; then
    log "Pod queue low ($pod_queue) — uploading more H264..."
    upload_new_h264
fi

bash scripts/pull_tracking.sh >> /tmp/pull_tracking.log 2>&1 &
