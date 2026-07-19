#!/usr/bin/env bash
# Continuous validation loop -- the pod re-validates the WHOLE system on a
# cycle until the pod dies. Each cycle: pull new code/bank -> SELF-HEAL
# regen any family whose producer changed this pull -> re-validate every
# claim family (independent recompute) -> QA bank FULL -> coverage stress ->
# prediction_eval refresh -> append one trend line to
# validation_cycles.jsonl. Honest by construction: every number in the
# trend line comes from a fail-closed artifact written this cycle.
#
# SELF-HEAL (added 2026-07-18): re-validating a store against changed
# producer code without ever REGENERATING it inflates the mismatch counter
# on a stale store, not real data corruption -- see
# scripts/platformkit/pod_sprint/regen_manifest.py's module docstring.
#   nohup bash scripts/platformkit/pod_sprint/validation_loop.sh &
set -u
exec 9>/workspace/validation_loop.lock
flock -n 9 || { echo "validation_loop already running"; exit 1; }
REPO="$(cd "$(dirname "$0")/../../.." && pwd)"
PY="${VENV_PY:-/workspace/venv/bin/python}"
LOGS="${SPRINT_LOGS:-/workspace/sprint_logs}"
CYCLES="$LOGS/validation_cycles.jsonl"
SLEEP_BETWEEN="${SLEEP_BETWEEN:-1200}"  # 20 min between cycles
REGEN_TIMEOUT="${REGEN_TIMEOUT:-900}"   # per-family regen bound (pod has GNU timeout)
mkdir -p "$LOGS"
cd "$REPO"

cycle=0
while true; do
    cycle=$((cycle + 1))
    T0=$(date -Is)
    BEFORE=$(git rev-parse HEAD 2>/dev/null || echo "")
    git pull -q 2>/dev/null || true   # pick up new families/bank/code
    AFTER=$(git rev-parse HEAD 2>/dev/null || echo "")

    # 0. SELF-HEAL: regen any family whose producer changed this pull. No
    # change this cycle -> skip entirely (cheap, the common case).
    RLOG="$LOGS/cycle_regen.log"; : > "$RLOG"
    N_REGEN_OK=0
    N_REGEN_FAIL=0
    if [ -n "$BEFORE" ] && [ -n "$AFTER" ] && [ "$BEFORE" != "$AFTER" ]; then
        CHANGED=$(git diff --name-only "$BEFORE" "$AFTER" -- 'scripts/platformkit/intel_validation/*.py' 'domains/*.py' 'domains/**/*.py' 2>/dev/null)
        FAMILIES=$(
            for f in $CHANGED; do
                "$PY" -m scripts.platformkit.pod_sprint.regen_manifest --producer "$f" 2>>"$RLOG"
            done | sort -u
        )
        for fam in $FAMILIES; do
            CMD=$("$PY" -m scripts.platformkit.pod_sprint.regen_manifest --family "$fam" 2>>"$RLOG")
            if [ -z "$CMD" ]; then
                echo "[regen] $fam: no resolvable regen command, skipped" >> "$RLOG"
                continue
            fi
            echo "[regen] $fam starting $(date -Is): $CMD" >> "$RLOG"
            # unquoted on purpose: CMD is our own trusted "python -m ..." string
            timeout "$REGEN_TIMEOUT" $PY -m ${CMD#python -m } >> "$RLOG" 2>&1
            if [ $? -eq 0 ]; then
                N_REGEN_OK=$((N_REGEN_OK + 1))
            else
                N_REGEN_FAIL=$((N_REGEN_FAIL + 1))
            fi
            echo "[regen] $fam ended $(date -Is)" >> "$RLOG"
        done
    fi

    # 1. re-validate every claim family (skip sidecars); count verdicts
    VLOG="$LOGS/cycle_claims.log"; : > "$VLOG"
    for f in data/cache/intel_claims/*.jsonl; do
        case "$f" in *_validation*|*.index.jsonl) continue ;; esac
        "$PY" -m scripts.platformkit.intel_validation.claims_validator "$f" \
            --output "${f%.jsonl}_validation.json" >> "$VLOG" 2>&1
    done
    # awk, not bc: the pod image ships without bc, which silently zeroed
    # these counters in the trend line (caught 2026-07-18 cycle 1).
    N_VER=$(grep -ho 'n_claims=[0-9]*' "$VLOG" | cut -d= -f2 | awk '{s+=$1} END {print s+0}')
    N_OK=$(grep -ho 'verified=[0-9]*' "$VLOG" | cut -d= -f2 | awk '{s+=$1} END {print s+0}')
    N_MIS=$(grep -ho 'mismatch=[0-9]*' "$VLOG" | cut -d= -f2 | awk '{s+=$1} END {print s+0}')

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

    # 5. pregame snapshot refresh EVERY cycle -- the in-play paper chain's p0
    # (live_p0 -> mlb_live_model) reads data/frontend/predict_service/<sport>/
    # latest.json; a missing/stale snapshot silently kills MLB pair capture
    # (root-caused 2026-07-19: pod had NO snapshot store -> zero MLB pairs).
    for s in mlb wnba nba; do
        timeout 300 "$PY" -m predict_service.produce --sport "$s" \
            >> "$LOGS/cycle_snapshot.log" 2>&1
    done
    # 5b. settle open paper_ingame ledger rows (single idempotent pass; a game
    # not yet final stays open, never force-settled). Without this the median-
    # CLV breaker never sees graded rows and the channel stays capped forever.
    timeout 300 "$PY" -m scripts.platformkit.ingame.ingame_paper_settle \
        >> "$LOGS/cycle_settle.log" 2>&1

    # 6. DAILY forward-measurement scoreboards (once per UTC day): prospective
    # checkpoint grading (PENDING until the CI earns it), exec calibration,
    # live-feature leak-free gate. Cheap, honest, append their own history.
    TODAY=$(date -u +%F)
    if [ "${LAST_SCOREBOARD_DAY:-}" != "$TODAY" ]; then
        "$PY" -m scripts.platformkit.ingame.prospective_scoreboard \
            > "$LOGS/cycle_prospective.log" 2>&1
        "$PY" -m scripts.platformkit.ingame.exec_calibration \
            > "$LOGS/cycle_execcal.log" 2>&1
        "$PY" -m scripts.platformkit.tip_capture.feature_gate_runner \
            > "$LOGS/cycle_featgate.log" 2>&1
        LAST_SCOREBOARD_DAY="$TODAY"
    fi

    echo "{\"cycle\":$cycle,\"started\":\"$T0\",\"ended\":\"$(date -Is)\",\"regen_ok\":$N_REGEN_OK,\"regen_failed\":$N_REGEN_FAIL,\"claims_total\":${N_VER:-0},\"claims_verified\":${N_OK:-0},\"claims_mismatch\":${N_MIS:-0},\"qa\":\"${QA:-na}\",\"coverage_rate\":${COV:-null}}" >> "$CYCLES"
    sleep "$SLEEP_BETWEEN"
done
