#!/usr/bin/env bash
# scripts/platformkit/pod_pull_sync.sh -- pull the pod's live artifacts down to
# the laptop so the LOCAL frontend (webapp / live_board) shows the pod's real
# state without the laptop doing any compute.
#
# Pulls (read-only, pod -> laptop; never pushes anything up):
#   data/frontend/predict_service/   pregame snapshots (p0 chain)
#   data/frontend/clv_ledger.jsonl   paper ledger
#   data/frontend/ops/               ops scoreboards (settle status, forward evidence)
#   data/cache/benchmarks/           prospective scoreboard, exec calibration,
#                                    live feature gate, validity ladder, audits
#   data/cache/ingame_grade/         per-game grade series + capture heartbeat
#
# Usage:
#   bash scripts/platformkit/pod_pull_sync.sh          # one pass
#   bash scripts/platformkit/pod_pull_sync.sh --loop   # every 300s until Ctrl-C
# ponytail: scp -r whole dirs, no rsync on this box; fine at current sizes --
# switch to rsync --delete if ingame_grade grows past a few hundred MB.
set -u
POD="root@157.157.221.29"
PORT=19942
SRC="/workspace/court-vision"
DST="/c/Users/neelj/nba-ai-system"

pull_once() {
    mkdir -p "$DST/data/frontend" "$DST/data/cache"
    scp -P $PORT -q -r "$POD:$SRC/data/frontend/predict_service" "$DST/data/frontend/" 2>/dev/null
    scp -P $PORT -q "$POD:$SRC/data/frontend/clv_ledger.jsonl" "$DST/data/frontend/" 2>/dev/null
    scp -P $PORT -q -r "$POD:$SRC/data/frontend/ops" "$DST/data/frontend/" 2>/dev/null
    scp -P $PORT -q -r "$POD:$SRC/data/cache/benchmarks" "$DST/data/cache/" 2>/dev/null
    scp -P $PORT -q -r "$POD:$SRC/data/cache/ingame_grade" "$DST/data/cache/" 2>/dev/null
    echo "pod_pull_sync: pass complete $(date -u +%H:%M:%SZ)"
}

if [ "${1:-}" = "--loop" ]; then
    while true; do pull_once; sleep 300; done
else
    pull_once
fi
