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
# Live pod as of 2026-09-04: 213.192.2.123:40034, from ~/.ssh/config.pod.
# The prior pod address was recorded dead on 2026-09-03.
POD="root@${CV_POD_HOST:-213.192.2.123}"
PORT="${CV_POD_PORT:-40034}"
SRC="/workspace/nba-ai-system"
DST="${POD_SYNC_DST:-/c/Users/neelj/nba-ai-system}"

pull_target() {
    local target="$1"
    shift
    if ! "$@"; then
        echo "pod_pull_sync: WARN $target pull failed" >&2
        fail=$((fail + 1))
    fi
}

pull_once() {
    local fail=0
    mkdir -p "$DST/data/frontend" "$DST/data/cache"
    pull_target "predict_service" scp -P "$PORT" -q -r "$POD:$SRC/data/frontend/predict_service" "$DST/data/frontend/"
    pull_target "clv_ledger" scp -P "$PORT" -q "$POD:$SRC/data/frontend/clv_ledger.jsonl" "$DST/data/frontend/"
    pull_target "ops" scp -P "$PORT" -q -r "$POD:$SRC/data/frontend/ops" "$DST/data/frontend/"
    pull_target "benchmarks" scp -P "$PORT" -q -r "$POD:$SRC/data/cache/benchmarks" "$DST/data/cache/"
    pull_target "ingame_grade" scp -P "$PORT" -q -r "$POD:$SRC/data/cache/ingame_grade" "$DST/data/cache/"
    pull_target "ingame_books" scp -P "$PORT" -q -r "$POD:$SRC/data/cache/ingame_books" "$DST/data/cache/"
    # Tracking reports and the bridge ledger: without these the tracking corpus
    # produced on the pod never reaches the box where the A/B harnesses run.
    mkdir -p "$DST/data/tracking_reports"
    pull_target "tracking_reports" scp -P "$PORT" -q -r "$POD:$SRC/data/tracking_reports/." "$DST/data/tracking_reports/"
    # track_daemon_ledger carries the HARNESS VERDICT per game (passed +
    # failures), not just row counts -- it is the only record of whether a
    # tracked game is actually usable, and night_report's headline reads it.
    pull_target "track_daemon_ledger" scp -P "$PORT" -q "$POD:$SRC/data/tracking/track_daemon_ledger.jsonl" "$DST/data/tracking/"
    # NOT pulled: footage_bridge_ledger.jsonl. Downloads run on THIS box now, so
    # the local copy is the producer (1200+ rows) and the pod has none. Copying
    # the pod's version back would overwrite the real history with nothing.
    if [ "$fail" -eq 0 ]; then
        echo "pod_pull_sync: pass complete $(date -u +%H:%M:%SZ)"
    else
        echo "pod_pull_sync: pass INCOMPLETE ($fail target(s) failed) $(date -u +%H:%M:%SZ)"
    fi
    return "$fail"
}

if [ "${1:-}" = "--loop" ]; then
    while true; do pull_once; sleep 300; done
else
    pull_once
    exit $?
fi
