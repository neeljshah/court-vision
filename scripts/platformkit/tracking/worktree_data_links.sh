#!/bin/sh
# worktree_data_links.sh aN [aM ...] -- provision READ-ONLY-BY-CONVENTION junctions of the local data stores into a
# codex worktree (data/ is gitignored, so a fresh worktree cannot see any parquet/jsonl store; S01 and S02 returned
# NO STORE on 2026-09-03 for exactly this reason). Junctions, not copies: zero disk, always current.
# NEVER links data/cache/eval_gate (the FWER ledger backtest_fwer.jsonl stays main-repo-only) and NEVER data/registry.
# Idempotent; Windows directory junctions need no admin. ASCII.
MAIN="C:\Users\neelj\nba-ai-system"
for H in "$@"; do
  WT="/c/Users/neelj/nba-track-$H"; WTW="C:\Users\neelj\nba-track-$H"
  [ -d "$WT" ] || { echo "SKIP $H: no worktree"; continue; }
  mkdir -p "$WT/data/cache" "$WT/data/videos"
  for rel in domains models frontend "cache/combo" "cache/ingame_grade_joined" "cache/ingame" "cache/pit" "cache/inplay_odds" "cache/ingame_grade" "cache/clv" "cache/pm_paper"; do
    [ -d "/c/Users/neelj/nba-ai-system/data/$rel" ] || continue
    win=$(printf '%s' "$rel" | tr '/' '\')
    if [ -e "$WT/data/$rel" ]; then continue; fi
    cmd //c "mklink /J \"$WTW\data\$win\" \"$MAIN\data\$win\"" >/dev/null 2>&1 && echo "LINK $H data/$rel" || echo "FAIL $H data/$rel"
  done
  [ -e "$WT/data/cache/eval_gate" ] && echo "WARN $H has data/cache/eval_gate -- must not be a junction to main" || true
done
