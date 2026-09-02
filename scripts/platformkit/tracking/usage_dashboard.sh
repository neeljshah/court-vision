#!/bin/sh
# usage_dashboard.sh -- read-only daily usage counts for BOTH loops (tracking cx_g*, harness cx_s*).
# PLAN_AI_ENGINEERING s7. ASCII. Git Bash on Windows. Never writes.
R=/c/Users/neelj/nba-ai-system/docs/evidence/tracking/RESULTS_LEDGER.md
S=/c/Users/neelj/nba-ai-system/docs/evidence/RESULTS_LEDGER_SYSTEM.md
T=/c/Users/neelj/AppData/Local/Temp
D=$(date +%F)
echo "== usage $D"
for P in g s; do
  L=$(find "$T" -maxdepth 1 -name "cx_${P}*.log" -newermt "$D" 2>/dev/null)
  n=$(echo "$L" | grep -c .); d=0; tok=0
  if [ -n "$L" ]; then
    d=$(grep -l '^EXIT:' $L 2>/dev/null | wc -l)
    tok=$(cat $L 2>/dev/null | awk '/^tokens used/{getline; gsub(",",""); s+=$1} END{print s+0}')
  fi
  echo "  ${P}-loop codex_jobs=$n done=$d codex_tokens=$tok"
done
for F in "$R" "$S"; do
  [ -f "$F" ] || continue
  echo "  $(basename "$F"): verified=$(grep -c "^$D .*verified" "$F") landings=$(grep -c "^$D .*| \(LANDED\|ACCEPT\)" "$F") rejects_nulls=$(grep -c "^$D .*| \(REJECT\|FAIL\|CLOSED AT LIMIT\|NOT VALIDATED\|NULL\|BEHIND\|FALSIFIED\)" "$F") hook_only=$(grep -c "^$D | hook" "$F")"
done
echo "  token=$(head -1 /c/Users/neelj/nba-ai-system/docs/evidence/SHARED_MODULE_TOKEN.md 2>/dev/null)"
echo "  ceilings: 30-40 codex jobs/day, 12-18 REQUIRED + 6-8 LIGHT verifiers; hook_only>0 at night = a verifier line is missing"
