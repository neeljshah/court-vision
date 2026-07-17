#!/usr/bin/env bash
# Launch the pod sprint driver detached. Survives SSH disconnect.
#   bash scripts/platformkit/pod_sprint/run_sprint.sh
set -u
REPO="$(cd "$(dirname "$0")/../../.." && pwd)"
VENV_PY="${VENV_PY:-/workspace/venv/bin/python}"
LOGS="${SPRINT_LOGS:-/workspace/sprint_logs}"
mkdir -p "$LOGS"
cd "$REPO"
if [ ! -x "$VENV_PY" ]; then
    echo "FATAL: VENV_PY not executable: $VENV_PY" >&2
    exit 1
fi
nohup "$VENV_PY" -m scripts.platformkit.pod_sprint.driver "$@" \
    >> "$LOGS/driver.log" 2>&1 &
PID=$!
sleep 3
if kill -0 "$PID" 2>/dev/null; then
    echo "sprint driver pid $PID RUNNING -> $LOGS/driver.log"
else
    wait "$PID"; RC=$?
    echo "FATAL: driver died instantly (rc=$RC) -- tail of log:" >&2
    tail -5 "$LOGS/driver.log" >&2 2>/dev/null
    exit "${RC:-1}"
fi
