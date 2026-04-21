#!/bin/bash
# Runs on pod — deletes processed videos every 5 min to keep overlay free
PROCESSED=/workspace/nba-ai-system/data/phase_g_processed.txt
VIDEOS=/root/nba_videos
LOG=/workspace/nba-ai-system/cleaner.log
while true; do
  while IFS= read -r gid; do
    f="$VIDEOS/${gid}.mp4"
    [ -f "$f" ] && rm -f "$f" && echo "$(date '+%H:%M:%S') deleted $gid" >> "$LOG"
  done < <(grep -E '^002250[0-9]+$' "$PROCESSED" 2>/dev/null)
  USED=$(df -BG / | awk 'NR==2{gsub("G",""); print $3}')
  echo "$(date '+%H:%M:%S') overlay=${USED}G staged=$(ls $VIDEOS/*.mp4 2>/dev/null | wc -l)" >> "$LOG"
  sleep 300
done
