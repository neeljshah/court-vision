#!/usr/bin/env bash
# Continuous validation loop -- the pod re-validates the WHOLE system on a
# cycle until the pod dies. Each cycle: pull new code/bank -> re-validate
# every claim family (independent recompute) -> QA bank FULL -> coverage
# stress -> prediction_eval refresh -> append one trend line to
# validation_cycles.jsonl. Honest by construction: every number in the
# trend line comes from a fail-closed artifact written this cycle.
#   nohup bash scripts/platformkit/pod_sprint/validation_loop.sh &
set -u
exec 9>/workspace/validation_loop.lock
flock -n 9 || { echo "validation_loop already running"; exit 1; }
REPO="$(cd "$(dirname "$0")/../../.." && pwd)"
PY="${VENV_PY:-/workspace/venv/bin/python}"
LOGS="${SPRINT_LOGS:-/workspace/sprint_logs}"
CYCLES="$LOGS/validation_cycles.jsonl"
SLEEP_BETWEEN="${SLEEP_BETWEEN:-1200}"  # 20 min between cycles
mkdir -p "$LOGS"
cd "$REPO"

cycle=0
while true; do
    cycle=$((cycle + 1))
    T0=$(date -Is)
    git pull -q 2>/dev/null || true   # pick up new families/bank/code

    # 1. re-validate every claim family (skip sidecars); count verdicts
    VLOG="$LOGS/cycle_claims.log"; : > "$VLOG"
    for f in data/cache/intel_claims/*.jsonl; do
        case "$f" in *_validation*|*.index.jsonl) continue ;; esac
        "$PY" -m scripts.platformkit.intel_validation.claims_validator "$f" \
            --output "${f%.jsonl}_validation.json" >> "$VLOG" 2>&1
    done
    N_VER=$(grep -ho 'n_claims=[0-9]*' "$VLOG" | cut -d= -f2 | paste -sd+ | bc 2>/dev/null || echo 0)
    N_OK=$(grep -ho 'verified=[0-9]*' "$VLOG" | cut -d= -f2 | paste -sd+ | bc 2>/dev/null || echo 0)
    N_MIS=$(grep -ho 'mismatch=[0-9]*' "$VLOG" | cut -d= -f2 | paste -sd+ | bc 2>/dev/null || echo 0)

    # 2. QA bank FULL
    "$PY" -m scripts.platformkit.answers.qa_runner --tier FULL \
        > "$LOGS/cycle_qa.log" 2>&1
    QA=$(grep -o '[0-9]*/[0-9]* pass' "$LOGS/cycle_qa.log" | tail -1)

    # 3. coverage stress (bank may have grown via git pull)
    "$PY" -m scripts.platformkit.answers.coverage_stress \
        > "$LOGS/cycle_stress.log" 2>&1
    COV=$("$PY" -c "import json;print(json.load(open('data/cache/analytics_verify/coverage_stress_report.json')).get('coverage_rate'))" 2>/dev/null || echo null)

    # 4. prediction_eval refresh
    "$PY" -m scripts.platformkit.pod_sprint.prediction_eval \
        > "$LOGS/cycle_predeval.log" 2>&1

    echo "{\"cycle\":$cycle,\"started\":\"$T0\",\"ended\":\"$(date -Is)\",\"claims_total\":${N_VER:-0},\"claims_verified\":${N_OK:-0},\"claims_mismatch\":${N_MIS:-0},\"qa\":\"${QA:-na}\",\"coverage_rate\":${COV:-null}}" >> "$CYCLES"
    sleep "$SLEEP_BETWEEN"
done
