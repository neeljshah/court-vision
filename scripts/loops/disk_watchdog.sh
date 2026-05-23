#!/bin/bash
# Deletes processed videos from /root/nba_videos to keep the overlay drained.
# Safe: only removes a video whose tracking_data.csv exists and is non-empty.
PROJ=/workspace/nba-ai-system
VIDEODIR=/root/nba_videos
LOG=/workspace/disk_watchdog.log
PIDFILE=/workspace/watchdog.pid

# Singleton guard — duplicate watchdogs are harmless but waste rm calls.
if [ -f "$PIDFILE" ]; then
  oldpid=$(cat "$PIDFILE" 2>/dev/null)
  if [ -n "$oldpid" ] && kill -0 "$oldpid" 2>/dev/null; then
    echo "$(date '+%F %T') another watchdog (pid $oldpid) alive — exiting" >> "$LOG"
    exit 0
  fi
fi
echo $$ > "$PIDFILE"
trap 'rm -f "$PIDFILE"' EXIT
echo "$(date '+%F %T') watchdog started pid=$$" >> "$LOG"
while true; do
  DONE="$PROJ/data/phase_g_processed.txt"
  if [ -f "$DONE" ]; then
    while IFS= read -r gid; do
      gid="${gid%$'\r'}"
      [ -z "$gid" ] && continue
      case "$gid" in hash:*) continue;; esac
      vid="$VIDEODIR/$gid.mp4"
      trk="$PROJ/data/tracking/$gid/tracking_data.csv"
      if [ -f "$vid" ] && [ -s "$trk" ]; then
        sz=$(du -m "$vid" | cut -f1)
        rm -f "$vid" && echo "$(date '+%F %T') freed ${sz}MB: $gid.mp4" >> "$LOG"
      fi
    done < "$DONE"
  fi
  avail=$(df -m --output=avail /root | tail -1 | tr -d ' ')
  echo "$(date '+%F %T') /root avail=${avail}MB videos=$(ls $VIDEODIR/*.mp4 2>/dev/null|wc -l)" >> "$LOG"
  sleep 300
done
