#!/bin/bash
# Watchdog v3.3: also marks failed-download games as done so they don't retry
cd /workspace/nba-ai-system
LAST_BACKFILL_P=0
while true; do
  TS=$(date '+%H:%M:%S')
  # 1. Restore done log from tracking dirs with completed output
  for d in data/tracking/*/; do
    gid=$(basename "$d")
    [[ "$gid" =~ ^[0-9]{10}$ ]] || continue
    if [ -f "$d/tracking_data.csv" ]; then
      grep -qxF "$gid" data/phase_g_processed.txt || echo "$gid" >> data/phase_g_processed.txt
    fi
  done
  # 2. Mark permanent-fail games (PREFLIGHT_FAIL, RC3_ZERO_ROWS) as done
  awk -F, 'NR>1 && $3~/^[0-9]{10}$/ && ($8=="PREFLIGHT_FAIL" || $8=="RC3_ZERO_ROWS") {print $3}' data/phase_g_metrics.csv 2>/dev/null | sort -u | while read gid; do
    grep -qxF "$gid" data/phase_g_processed.txt || echo "$gid" >> data/phase_g_processed.txt
  done
  # 3. Mark "Could not download" games from fetcher log as done (prevents endless retry)
  grep -oE 'Could not download [0-9]{10}' fetcher.log 2>/dev/null | awk '{print $4}' | sort -u | while read gid; do
    grep -qxF "$gid" data/phase_g_processed.txt || echo "$gid" >> data/phase_g_processed.txt
  done
  # 4. Restart fetcher if dead
  if ! tmux has-session -t fetcher 2>/dev/null; then
    echo "[$TS] watchdog: fetcher dead, restarting" >> watchdog.log
    tmux new-session -d -s fetcher 'bash /workspace/nba-ai-system/scripts/fetcher_loop.sh'
  fi
  # 5. Restart tracker if dead
  if ! tmux has-session -t tracker 2>/dev/null; then
    echo "[$TS] watchdog: tracker dead, restarting" >> watchdog.log
    tmux new-session -d -s tracker 'bash /workspace/nba-ai-system/scripts/tracker_loop.sh'
  fi
  # 6. Delete tiny + done-on-disk videos
  for f in /root/nba_videos/*.mp4; do
    [ -f "$f" ] || continue
    s=$(stat -c%s "$f" 2>/dev/null)
    if [ -n "$s" ] && [ "$s" -lt 30000000 ]; then
      rm -f "$f"
      continue
    fi
    gid=$(basename "$f" .mp4)
    grep -qxF "$gid" data/phase_g_processed.txt && rm -f "$f"
  done
  # 7. Feature backfill at +25 games
  P=$(grep -cE '^[0-9]{10}$' data/phase_g_processed.txt)
  if [ "$P" -ge $((LAST_BACKFILL_P + 25)) ]; then
    if ! tmux has-session -t features 2>/dev/null; then
      echo "[$TS] watchdog: P=$P, triggering backfill" >> watchdog.log
      tmux new-session -d -s features 'cd /workspace/nba-ai-system && python3 scripts/backfill_cv_features.py 2>&1 | tee -a backfill_cv.log'
      LAST_BACKFILL_P=$P
    fi
  fi
  sleep 30
done
