#!/usr/bin/env bash
# Launch the pod sprint driver detached. Survives SSH disconnect.
#   bash scripts/platformkit/pod_sprint/run_sprint.sh
set -u
REPO="$(cd "$(dirname "$0")/../../.." && pwd)"
VENV_PY="${VENV_PY:-/workspace/venv/bin/python}"
LOGS="${SPRINT_LOGS:-/workspace/sprint_logs}"
mkdir -p "$LOGS"
cd "$REPO"
nohup "$VENV_PY" -m scripts.platformkit.pod_sprint.driver "$@" \
    >> "$LOGS/driver.log" 2>&1 &
echo "sprint driver pid $! -> $LOGS/driver.log"
