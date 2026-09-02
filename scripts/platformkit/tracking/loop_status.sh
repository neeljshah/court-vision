#!/bin/sh
# loop_status.sh -- the one-command morning read for the tracking loop.
# Prints: codex job states (ALIVE / DONE / WEDGED), register OPEN rows, pod alive,
# last ledger lines, unpushed commits. Read-only. ASCII. Git Bash on Windows.
REPO="/c/Users/neelj/nba-ai-system"
TMP="/c/Users/neelj/AppData/Local/Temp"
now=$(date +%s)
echo "== codex jobs (cx_g*.log, newest first)"
ls -t "$TMP"/cx_g*.log 2>/dev/null | head -14 | while read -r f; do
  m=$(stat -c %Y "$f"); age=$(( (now - m) / 60 )); b=$(basename "$f" .log | cut -c4-)
  if grep -q "^EXIT:" "$f"; then st="DONE($(grep -m1 '^EXIT:' "$f"))"
  elif grep -q "^tokens used" "$f" && [ $age -gt 4 ]; then st="DONE(orphan)"
  elif [ $age -gt 15 ]; then st="WEDGED?"
  else st="ALIVE"; fi
  printf "  %-34s %-14s age=%3dm size=%s\n" "$b" "$st" "$age" "$(stat -c %s "$f")"
done
echo "== register: next id + OPEN rows"
grep -m1 "^NEXT_GAP_ID" "$REPO/docs/evidence/tracking/TRACKING_GAPS_2026-09-01.md"
grep -E "^\| G[0-9]+ \|" "$REPO/docs/evidence/tracking/TRACKING_GAPS_2026-09-01.md" \
  | grep -iE "\| (OPEN|AWAITING|codex a[0-9] done|dispatched)" | cut -c1-110
echo "== ledger (last 5)"
tail -5 "$REPO/docs/evidence/tracking/RESULTS_LEDGER.md" | cut -c1-140
echo "== git"
cd "$REPO" && git fetch -q origin master 2>/dev/null; echo "  unpushed=$(git rev-list --count origin/master..HEAD) tip=$(git log --oneline -1 | cut -c1-70)"
echo "== pod (read-only)"
ssh -o ConnectTimeout=15 -p "${POD_PORT:-40193}" "root@${POD_HOST:-213.192.2.83}" \
  'ls /proc/$(cat /workspace/track_daemon.pid) >/dev/null 2>&1 && echo "  daemon_alive" || echo "  daemon_DEAD"; \
   for p in /proc/[0-9]*/cmdline; do c=$(tr "\0" " " < $p 2>/dev/null); case "$c" in *run_pod_capture*) echo "  capture_alive";; esac; done | head -1; \
   nvidia-smi --query-gpu=utilization.gpu,memory.used --format=csv,noheader | sed "s/^/  gpu /"; \
   tail -1 /workspace/track_daemon_ledger.jsonl 2>/dev/null | cut -c1-120' 2>/dev/null || echo "  pod unreachable"
