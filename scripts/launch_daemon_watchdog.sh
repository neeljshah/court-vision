#!/usr/bin/env bash
# launch_daemon_watchdog.sh — R19_L3
# Starts scripts/daemon_watchdog.py in a detached tmux session named
# "daemon_watchdog".  Idempotent: if the session already exists, exits 0.
#
# Usage:
#   bash scripts/launch_daemon_watchdog.sh
#   bash scripts/launch_daemon_watchdog.sh --dry-run
#
# Notes
# -----
# * The watchdog itself is launched with --check-interval-sec 60.
# * stdout/stderr stream to logs/daemon_watchdog.log.
# * To stop:  tmux kill-session -t daemon_watchdog
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
SESSION="daemon_watchdog"
LOG="${PROJECT_DIR}/logs/daemon_watchdog.log"
EXTRA_ARGS="${*:-}"

mkdir -p "${PROJECT_DIR}/logs"

if tmux has-session -t "${SESSION}" 2>/dev/null; then
    echo "tmux session '${SESSION}' already exists — not relaunching."
    tmux ls | grep "${SESSION}" || true
    exit 0
fi

cd "${PROJECT_DIR}"
tmux new-session -d -s "${SESSION}" \
    "python -u scripts/daemon_watchdog.py --check-interval-sec 60 ${EXTRA_ARGS} >> '${LOG}' 2>&1"

sleep 1
echo "Launched watchdog in tmux session '${SESSION}'."
tmux ls | grep "${SESSION}" || true
echo "Log: ${LOG}"
echo "Stop with: tmux kill-session -t ${SESSION}"
