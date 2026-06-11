#!/usr/bin/env bash
# cv_monitor.sh — watch the live CourtVision page for tip-off / failure.
# Polls /health + /api/cv_live every INTERVAL secs for up to MAXITERS.
# Exits (so the harness re-engages) on: game TIPPED (is_live), SERVER_DOWN,
# game FINAL, or TIMEOUT. Appends each check to logs/cv_monitor.log.
cd /c/Users/neelj/nba-ai-system || exit 1
PY=/c/Users/neelj/anaconda3/envs/basketball_ai/python.exe
LOG=logs/cv_monitor.log
BASE="http://127.0.0.1:8077"
INTERVAL=${1:-30}
MAXITERS=${2:-30}
MODE=${3:-tip}   # tip = exit when game tips (LIVE); game = exit only on FINAL/down
echo "=== monitor start $(date +%H:%M:%S) (every ${INTERVAL}s x ${MAXITERS}, mode=${MODE}) ===" >> "$LOG"
FAILS=0   # consecutive non-200; only alarm after 2 in a row (tolerate a slow tick)
for i in $(seq 1 "$MAXITERS"); do
  H=$(curl -s -m 12 -o /dev/null -w '%{http_code}' "$BASE/health" 2>/dev/null)
  STATE=$(curl -s -m 5 "$BASE/api/cv_live?date=2026-06-10&game_id=0042500404" 2>/dev/null | "$PY" -c "
import sys,json
try:
    lv=json.load(sys.stdin)['live']
    tag='FINAL' if lv['is_final'] else 'LIVE' if lv['is_live'] else 'PRE'
    print(f\"{tag} {lv['home_score']}-{lv['away_score']} Q{lv['period']} {lv['clock']} wp={round((lv['win_prob_home_live'] or 0)*100)}\")
except Exception:
    print('PARSE_ERR')" 2>/dev/null)
  echo "$(date +%H:%M:%S) health=$H $STATE" >> "$LOG"
  if [ "$H" != "200" ]; then
    FAILS=$((FAILS+1))
    # Transient ~30s machine freezes recover on their own; only alarm on a REAL
    # outage = 3 consecutive misses (~90s+ down). Retry quickly in between.
    if [ "$FAILS" -ge 3 ]; then echo "RESULT=SERVER_DOWN health=$H (3x consecutive)"; exit 0; fi
    sleep 8; continue
  fi
  FAILS=0
  case "$STATE" in
    FINAL*) echo "RESULT=FINAL $STATE"; exit 0;;
    LIVE*)  if [ "$MODE" = "tip" ]; then echo "RESULT=TIPPED $STATE"; exit 0; fi;;
    PRE*)   if [ "$MODE" = "game" ]; then echo "RESULT=WENT_PREGAME $STATE"; exit 0; fi;;
  esac
  sleep "$INTERVAL"
done
echo "RESULT=TIMEOUT last=$STATE"
