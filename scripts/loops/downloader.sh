#!/bin/bash
# Downloads queued games into /root/nba_videos. 720p h264 only (default yt-dlp
# client — the android client caps at 360p). Disk-gated, codec/res-checked.
PROJ=/workspace/nba-ai-system
VID=/root/nba_videos
LOG=/workspace/downloader.log
COOKIES="$PROJ/data/videos/youtube_cookies.txt"
QUEUE=/workspace/dl_queue.txt
ATT=/workspace/dl_attempted.txt
PIDFILE=/workspace/downloader.pid
MIN_FREE_GB="${MIN_FREE_GB:-15}"   # was 20 — too conservative; ~5 game-downloads of headroom is enough (watchdog drains as games finish).
FMT="bestvideo[ext=mp4][vcodec^=avc][height<=720]+bestaudio[ext=m4a]/best[ext=mp4][height<=720]/best[height<=720]"

# singleton guard
if [ -f "$PIDFILE" ] && kill -0 "$(cat $PIDFILE 2>/dev/null)" 2>/dev/null; then
  echo "$(date '+%F %T') another downloader alive — exiting" >> "$LOG"; exit 0
fi
echo $$ > "$PIDFILE"; trap 'rm -f "$PIDFILE"' EXIT

if [ ! -f "$QUEUE" ]; then
  python3 -c "
import sqlite3
c=sqlite3.connect('$PROJ/data/ingest/queue.db')
for gid,url in c.execute(\"SELECT game_id,source_url FROM games WHERE status='queued' AND source_url IS NOT NULL AND source_url!='' ORDER BY created_at\"):
    print(gid+'\t'+url)
" > "$QUEUE"
fi
touch "$ATT"
echo "$(date '+%F %T') downloader started pid=$$, $(wc -l < $QUEUE) games queued" >> "$LOG"

ok=0; fail=0
while IFS=$'\t' read -r gid url; do
  [ -z "$gid" ] && continue
  grep -qx "$gid" "$ATT" && continue
  [ -f "$VID/$gid.mp4" ] && { echo "$gid" >> "$ATT"; continue; }
  grep -qx "$gid" "$PROJ/data/phase_g_processed.txt" 2>/dev/null && { echo "$gid" >> "$ATT"; continue; }
  while [ "$(( $(df -m --output=avail /root|tail -1|tr -d ' ') / 1024 ))" -lt "$MIN_FREE_GB" ]; do
    echo "$(date '+%F %T') disk full, waiting 5m..." >> "$LOG"; sleep 300
  done
  echo "$(date '+%F %T') downloading $gid" >> "$LOG"
  tmp="$VID/.dl_${gid}.mp4"
  rm -f "$VID/.dl_${gid}"* 2>/dev/null
  timeout 2400 yt-dlp -f "$FMT" --merge-output-format mp4 --no-playlist --no-warnings --quiet \
    --cookies "$COOKIES" -o "$tmp" "$url" </dev/null >> "$LOG" 2>&1
  echo "$gid" >> "$ATT"
  if [ ! -f "$tmp" ]; then echo "$(date '+%F %T') $gid FAIL (download)" >> "$LOG"; fail=$((fail+1)); continue; fi
  codec=$(ffprobe -v error -select_streams v:0 -show_entries stream=codec_name -of csv=p=0 "$tmp" 2>/dev/null)
  h=$(ffprobe -v error -select_streams v:0 -show_entries stream=height -of csv=p=0 "$tmp" 2>/dev/null)
  sz=$(du -m "$tmp" 2>/dev/null | cut -f1)
  if [ "$codec" != "h264" ]; then echo "$(date '+%F %T') $gid REJECT codec=$codec" >> "$LOG"; rm -f "$tmp"; fail=$((fail+1)); continue; fi
  if [ "${h:-0}" -lt 600 ]; then echo "$(date '+%F %T') $gid REJECT res=${h}p (need >=600)" >> "$LOG"; rm -f "$tmp"; fail=$((fail+1)); continue; fi
  if [ "${sz:-0}" -lt 150 ]; then echo "$(date '+%F %T') $gid REJECT size=${sz}MB" >> "$LOG"; rm -f "$tmp"; fail=$((fail+1)); continue; fi
  mv "$tmp" "$VID/$gid.mp4"
  ok=$((ok+1))
  echo "$(date '+%F %T') $gid OK ${sz}MB ${h}p h264 (ok=$ok fail=$fail)" >> "$LOG"
done < "$QUEUE"
echo "$(date '+%F %T') downloader done — ok=$ok fail=$fail" >> "$LOG"
