#!/usr/bin/env bash
# start_scraper_orchestrator.sh - clean launch + restart for the R16_E6
# unified scraper orchestrator. Kills any existing orchestrator + the 3
# legacy standalone daemons, then nohup-launches the orchestrator.
#
# Usage:
#   bash scripts/start_scraper_orchestrator.sh
#   bash scripts/start_scraper_orchestrator.sh stop
#   bash scripts/start_scraper_orchestrator.sh status

set -u

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR" || exit 1

LOG_DIR="$PROJECT_DIR/vault/Improvements"
LOG_FILE="$LOG_DIR/unified_scraper.log"
PID_FILE="$PROJECT_DIR/data/cache/scraper_daemon_pids.json"
mkdir -p "$LOG_DIR" "$(dirname "$PID_FILE")"

cmd="${1:-start}"

kill_legacy_daemons() {
    # Three legacy scripts that had their own PID/process each.
    for pat in probe_R15_curl_cffi_fanduel bov_scraper_daemon pinnacle_scraper; do
        pids=$(pgrep -f "$pat" || true)
        if [ -n "$pids" ]; then
            echo "[start_scraper_orchestrator] killing legacy $pat pids: $pids"
            # shellcheck disable=SC2086
            kill $pids 2>/dev/null || true
            sleep 1
            # shellcheck disable=SC2086
            kill -9 $pids 2>/dev/null || true
        fi
    done
    # And any prior orchestrator instance.
    pids=$(pgrep -f "unified_scraper_orchestrator" || true)
    if [ -n "$pids" ]; then
        echo "[start_scraper_orchestrator] killing prior orchestrator pids: $pids"
        # shellcheck disable=SC2086
        kill $pids 2>/dev/null || true
        sleep 1
        # shellcheck disable=SC2086
        kill -9 $pids 2>/dev/null || true
    fi
}

start_orchestrator() {
    kill_legacy_daemons
    echo "[start_scraper_orchestrator] launching orchestrator -> $LOG_FILE"
    nohup python "$PROJECT_DIR/scripts/unified_scraper_orchestrator.py" \
        --books fd,bov,pin \
        --fd-interval-sec 60 \
        --bov-interval-sec 60 \
        --pin-interval-sec 30 \
        --health-port 8765 \
        >>"$LOG_FILE" 2>&1 &
    NEW_PID=$!
    disown || true
    sleep 2
    if kill -0 "$NEW_PID" 2>/dev/null; then
        echo "[start_scraper_orchestrator] started pid=$NEW_PID"
        echo "[start_scraper_orchestrator] log: tail -f $LOG_FILE"
        echo "[start_scraper_orchestrator] health: curl http://127.0.0.1:8765/health"
    else
        echo "[start_scraper_orchestrator] ERROR: process exited immediately"
        tail -30 "$LOG_FILE" 2>/dev/null || true
        exit 2
    fi
}

stop_orchestrator() {
    pids=$(pgrep -f "unified_scraper_orchestrator" || true)
    if [ -z "$pids" ]; then
        echo "[start_scraper_orchestrator] no orchestrator running"
    else
        echo "[start_scraper_orchestrator] stopping pids: $pids"
        # shellcheck disable=SC2086
        kill $pids 2>/dev/null || true
        sleep 2
        # shellcheck disable=SC2086
        kill -9 $pids 2>/dev/null || true
    fi
}

status() {
    pids=$(pgrep -f "unified_scraper_orchestrator" || true)
    if [ -z "$pids" ]; then
        echo "[start_scraper_orchestrator] not running"
        return 1
    fi
    echo "[start_scraper_orchestrator] running pids: $pids"
    if command -v curl >/dev/null 2>&1; then
        curl -s --max-time 3 http://127.0.0.1:8765/health || echo "(health endpoint unreachable)"
    fi
}

case "$cmd" in
    start)   start_orchestrator ;;
    stop)    stop_orchestrator ;;
    restart) stop_orchestrator; sleep 1; start_orchestrator ;;
    status)  status ;;
    *) echo "usage: $0 {start|stop|restart|status}"; exit 1 ;;
esac
