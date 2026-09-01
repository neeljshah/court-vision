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
# Live pod as of 2026-09-01. The previous values (157.157.221.29:19942,
# /workspace/court-vision) pointed at a decommissioned pod, and because every
# scp below sends errors to /dev/null the script reported success while
# pulling nothing at all.
POD="root@213.192.2.83"
PORT=40048
SRC="/workspace/nba-ai-system"
DST="/c/Users/neelj/nba-ai-system"

pull_once() {
    mkdir -p "$DST/data/frontend" "$DST/data/cache"
    scp -P $PORT -q -r "$POD:$SRC/data/frontend/predict_service" "$DST/data/frontend/" 2>/dev/null
    scp -P $PORT -q "$POD:$SRC/data/frontend/clv_ledger.jsonl" "$DST/data/frontend/" 2>/dev/null
    scp -P $PORT -q -r "$POD:$SRC/data/frontend/ops" "$DST/data/frontend/" 2>/dev/null
    scp -P $PORT -q -r "$POD:$SRC/data/cache/benchmarks" "$DST/data/cache/" 2>/dev/null
    scp -P $PORT -q -r "$POD:$SRC/data/cache/ingame_grade" "$DST/data/cache/" 2>/dev/null
    # Tracking reports and the bridge ledger: without these the tracking corpus
    # produced on the pod never reaches the box where the A/B harnesses run.
    mkdir -p "$DST/data/tracking_reports"
    if ! scp -P $PORT -q -r "$POD:$SRC/data/tracking_reports/." "$DST/data/tracking_reports/"; then
        echo "pod_pull_sync: WARN tracking_reports pull failed" >&2
    fi
    # track_daemon_ledger carries the HARNESS VERDICT per game (passed +
    # failures), not just row counts -- it is the only record of whether a
    # tracked game is actually usable, and night_report's headline reads it.
    if ! scp -P $PORT -q "$POD:$SRC/data/tracking/track_daemon_ledger.jsonl" "$DST/data/tracking/"; then
        echo "pod_pull_sync: WARN track_daemon_ledger pull failed" >&2
    fi
    # NOT pulled: footage_bridge_ledger.jsonl. Downloads run on THIS box now, so
    # the local copy is the producer (1200+ rows) and the pod has none. Copying
    # the pod's version back would overwrite the real history with nothing.
    echo "pod_pull_sync: pass complete $(date -u +%H:%M:%SZ)"
}

if [ "${1:-}" = "--loop" ]; then
    while true; do pull_once; sleep 300; done
else
    pull_once
fi
