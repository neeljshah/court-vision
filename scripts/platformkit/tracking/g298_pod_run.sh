#!/usr/bin/env bash
# pod_run <aN> [--fetch <path> ...] -- <command...>
# Ships THIS worktree's code tree (scripts tests domains kernel src + the docs/evidence/harness files named by
# --ship) to /workspace/wt/<aN> on the pod, links data/ to the deployed tree's data (read-only use), runs the
# command there under nohup with a log, waits, prints the log tail, fetches the listed paths back into the
# worktree. User decision 2026-09-04 09:30: heavy compute runs on the pod in per-worktree scratch dirs; the
# deployed tree /workspace/nba-ai-system is never written. Never ships data/, .git, *.local_*, or any of
# backtest_fwer.jsonl / hypotheses*.sqlite / data/registry.
set -u
H="$1"; shift
[ "$H" = a6 ] || exit 2
WT="/c/Users/neelj/nba-track-a6"
[ -d "$WT" ] || exit 2
SSH="ssh -F $HOME/.ssh/config.pod pod"
FETCH=(); SHIP=()
while [ $# -gt 0 ]; do
  case "$1" in
    --fetch) FETCH+=("$2"); shift 2;;
    --ship) case "$2" in data/*|*/data/*) echo "pod_run: refuse --ship under data/ ($2): the worktree data/ is a link to the DEPLOYED pod tree; scp the file to /workspace/wt/<aN>/inputs/ and pass its path to the command instead"; exit 2;; esac; SHIP+=("$2"); shift 2;;
    --) shift; break;;
    *) break;;
  esac
done
CMD="$*"; [ -n "$CMD" ] || { echo "usage: pod_run <aN> [--ship <path>] [--fetch <path>] -- <command>"; exit 2; }
R="/workspace/wt/$H"; TAG="$(date +%Y%m%d%H%M%S)"; LOG="$R/pod_run_$TAG.log"
$SSH "mkdir -p $R/g298_scratch && dd if=/dev/zero of=$R/g298_scratch/wrapper_fsync_probe.bin bs=1M count=8 conv=fsync" || { echo "POD FSYNC WRITE PROBE FAILED -- not running"; exit 3; }
echo "POD /workspace UNKNOWN; /workspace/wt UNKNOWN (MooseFS walk omitted; successful fsync is the disk gate)"

# ship code (tracked + untracked, excluding data/.git/local dirs); tar exit 1 = files changed while reading (ok)
( cd "$WT" && { find scripts tests domains kernel src -name '*.py' -not -path '*/__pycache__/*' 2>/dev/null; for x in "${SHIP[@]}"; do [ -e "$x" ] && { [ -d "$x" ] && find "$x" -type f || echo "$x"; }; done; } | tar -cf - -T - 2>/dev/null ) | $SSH "cd $R && tar -x --no-same-owner" ; rc=${PIPESTATUS[0]}; [ "$rc" -le 1 ] || { echo "SHIP FAILED rc=$rc"; exit 4; }
$SSH "cd $R && ([ -e data ] || ln -s /workspace/nba-ai-system/data data) && mkdir -p docs/evidence/harness && echo SHIPPED && ls scripts | head -3"
$SSH "cd $R && nohup bash -c 'cd $R && PYTHONPATH=$R:/workspace/wt/_pylib $CMD; echo POD_RUN_DONE rc=\$?' > $LOG 2>&1 & echo POD_PID=\$!"
# wait for the done sentinel (max 4 h), polling every 20 s
i=0; while [ $i -lt 720 ]; do sleep 20; i=$((i+1)); if $SSH "grep -q POD_RUN_DONE $LOG 2>/dev/null"; then break; fi; done
echo "== pod log tail ($LOG)"; $SSH "tail -n 40 $LOG; echo; echo RSS_PEAK_KB=\$(grep -h VmHWM /proc/*/status 2>/dev/null | sort -k2 -n | tail -1)"
for f in "${FETCH[@]}"; do mkdir -p "$WT/$(dirname "$f")"; scp -q -F "$HOME/.ssh/config.pod" "pod:$R/$f" "$WT/$f" && echo "FETCHED $f" || echo "FETCH FAILED $f"; done
