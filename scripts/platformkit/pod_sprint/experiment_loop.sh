#!/usr/bin/env bash
# Never-idle experiment loop: drains experiment_queue.jsonl (git-pulled each
# pass, so pushing a new queue row from the laptop feeds the pod), then keeps
# the box busy with a benchmark rotation. One experiment at a time (the
# validation_loop owns the other cores). Results ledger is append-only.
#   nohup bash scripts/platformkit/pod_sprint/experiment_loop.sh &
set -u
exec 8>/workspace/experiment_loop.lock
flock -n 8 || { echo "experiment_loop already running"; exit 1; }
REPO="$(cd "$(dirname "$0")/../../.." && pwd)"
PY="${VENV_PY:-/workspace/venv/bin/python}"
LOGS="${SPRINT_LOGS:-/workspace/sprint_logs}/experiments"
LEDGER="$LOGS/experiments_done.jsonl"
QUEUE="$REPO/scripts/platformkit/pod_sprint/experiment_queue.jsonl"
mkdir -p "$LOGS"
cd "$REPO"

run_exp() { # id cmd timeout
    local id="$1" cmd="$2" timeout_s="$3"
    grep -q "\"id\": \"$id\"" "$LEDGER" 2>/dev/null && return 1  # already done
    echo "[exp] $id starting $(date -Is)"
    local t0=$SECONDS
    # unquoted on purpose: queue rows are trusted and may carry CLI args
    timeout "$timeout_s" $PY -m ${cmd#python -m } > "$LOGS/$id.log" 2>&1
    local rc=$?
    echo "{\"id\": \"$id\", \"rc\": $rc, \"secs\": $((SECONDS - t0)), \"ended\": \"$(date -Is)\"}" >> "$LEDGER"
    return 0
}

while true; do
    git pull -q 2>/dev/null || true
    ran_any=0
    while IFS= read -r line; do
        id=$($PY -c "import json,sys; print(json.loads(sys.argv[1])['id'])" "$line" 2>/dev/null) || continue
        cmd=$($PY -c "import json,sys; print(json.loads(sys.argv[1])['cmd'])" "$line")
        ts=$($PY -c "import json,sys; print(json.loads(sys.argv[1]).get('timeout_s', 7200))" "$line")
        run_exp "$id" "$cmd" "$ts" && ran_any=1
    done < "$QUEUE"
    if [ "$ran_any" = "0" ]; then
        # queue drained: rotation pass keeps the box honest + busy. Re-runs
        # are cheap re-verification (results overwrite their own artifacts).
        stamp=$(date +%Y%m%d%H)
        run_exp "rot_${stamp}_crps_ingame_mlb" "python -m scripts.platformkit.benchmarks.crps_market.ingame_mlb" 7200 \
        || run_exp "rot_${stamp}_crps_pregame_mlb" "python -m scripts.platformkit.benchmarks.crps_market.run_mlb" 7200 \
        || run_exp "rot_${stamp}_proof_nba" "python -m scripts.platformkit.proof_basketball_nba.run_proof" 7200 \
        || sleep 600  # whole rotation done this hour -- brief idle, then re-pull
    fi
done
