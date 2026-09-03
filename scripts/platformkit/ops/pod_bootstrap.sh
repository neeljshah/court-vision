#!/bin/sh
# pod_bootstrap.sh -- one idempotent command after a RunPod container restart.
#
# A restart keeps /workspace but WIPES the site-packages tree, and a deploy
# based on a guessed git baseline misses anything that landed before it (the
# S21 deploy missed spa_test / cpcv_engine / deflated_metrics from 2026-09-01).
# So: install everything, ship the FULL tracked trees, verify, then boot only
# what is not already running.
#
# Run it ON THE POD, after the caller has piped the tracked tree in. The exact
# local command (run from the repo root, ASCII, no --force anywhere):
#
#   git archive HEAD scripts/platformkit supervisor predict_service domains config \
#     | ssh -o BatchMode=yes -F ~/.ssh/config.pod pod \
#         'tar -x -C /workspace/nba-ai-system'
#   ssh -o BatchMode=yes -F ~/.ssh/config.pod pod \
#     'sh /workspace/nba-ai-system/scripts/platformkit/ops/pod_bootstrap.sh'
#
# `git archive` of whole trees carries every scripts/**/__init__.py (S46a), so
# the packages never resolve as namespace packages again.
#
# NEVER kills anything. Boots a process only when /proc shows none, so a second
# run is a no-op that just re-prints the state. ASCII only. No flag is flipped
# on: CV_CAPTURE_POD / CV_MLB_BOOK_ARCHIVE_LIVE restore existing pod state.
set -eu

REPO=${REPO:-/workspace/nba-ai-system}
PY=${PY:-/usr/local/bin/python}
CHECK="$REPO/scripts/platformkit/ops/pod_bootstrap_check.py"
TREE_CHECK="$REPO/scripts/platformkit/ops/deploy_tree_gate.py"
cd "$REPO"

# Live pids whose cmdline contains $1, EXCLUDING this shell and this script --
# a pattern that matches the checking command is how a /proc loop kills its own
# ssh session (runbook step 5).
proc_pids() {
    for d in /proc/[0-9]*; do
        pid=${d#/proc/}
        if [ "$pid" = "$$" ]; then continue; fi
        cmd=$(tr '\0' ' ' < "$d/cmdline" 2>/dev/null) || continue
        case "$cmd" in *pod_bootstrap*) continue ;; esac
        case "$cmd" in *"$1"*) echo "$pid" ;; esac
    done
}

# ---- 1. packages (PEP 668 refuses without the flag; the container is disposable)
echo "== 1. pip install"
"$PY" -m pip install --break-system-packages -q -r requirements-predictor.txt "pyarrow>=14" "statsmodels>=0.14"
"$PY" -m pip install --break-system-packages -q \
    "fastapi>=0.110" "uvicorn[standard]>=0.27" "scikit-learn>=1.3" "xgboost>=2.0"

# ---- 2. tree: shipped by the caller's `git archive | tar -x` (see header)
echo "== 2. tree: shipped by the caller (git archive | tar -x)"

# ---- 3. preflight -- import gate before anything boots
echo "== 3. preflight"
if ! "$PY" "$CHECK" --profile paper --python "$PY"; then
    echo "pod_bootstrap: preflight FAILED -- not booting anything"
    exit 1
fi
if ! "$PY" "$TREE_CHECK" --python "$PY" --repo "$REPO"; then
    echo "pod_bootstrap: tree preflight FAILED -- not booting anything"
    exit 1
fi
# Functional probes (S54): importable is not usable -- an import-only preflight
# passed 14/14 on 2026-09-03 while every parquet read failed (pyarrow wiped).
# REPORTED, not a boot gate: supervisor_lock_env needs a RUNNING supervisor,
# which is absent by definition on a cold restart (steps 4-5 boot it below).
"$PY" "$CHECK" --profile paper --python "$PY" --functional \
    || echo "pod_bootstrap: functional probe(s) FAILED above -- booting anyway"

# ---- 4. supervisor, only if absent
echo "== 4. supervisor"
if [ -n "$(proc_pids '-m supervisor')" ]; then
    echo "  already running (pids: $(proc_pids '-m supervisor' | tr '\n' ' ')) -- SKIP"
else
    CV_CAPTURE_POD=1 CV_MLB_BOOK_ARCHIVE_LIVE=1 nohup setsid \
        "$PY" -u -m supervisor --profile paper \
        </dev/null >>/workspace/paper.log 2>&1 &
    echo "  launched; expect 14 children in /proc within 80s"
fi

# ---- 5. mlb book capture (not a supervisor child), only if absent
echo "== 5. mlb book capture"
if [ -n "$(proc_pids run_pod_capture)" ]; then
    echo "  already running (pids: $(proc_pids run_pod_capture | tr '\n' ' ')) -- SKIP"
else
    CV_CAPTURE_POD=1 CV_MLB_BOOK_ARCHIVE_LIVE=1 nohup setsid "$PY" -c \
        "from scripts.platformkit.ingame.mlb_book_capture import run_pod_capture; run_pod_capture(stop=lambda: False)" \
        </dev/null >>/workspace/mlb_book_capture.log 2>&1 &
    echo "  launched (dies instantly without the two env flags -- S21 memo)"
fi

# ---- 6. state: pids + heartbeat ages
echo "== 6. state"
sleep 5
"$PY" "$CHECK" --profile paper --python "$PY"
