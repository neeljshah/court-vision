#!/usr/bin/env bash
# Wave-2 saturation lane: signal-gate proofs (4 sports, PARALLEL) + full
# independent re-validation of every intel_claims family. Complements the
# sequential driver -- together they keep the 16-vCPU / 62GB box busy.
# Detached-safe; logs to $SPRINT_LOGS. Honest REJECTs are successes.
#   nohup bash scripts/platformkit/pod_sprint/wave2.sh > /dev/null 2>&1 &
set -u
REPO="$(cd "$(dirname "$0")/../../.." && pwd)"
VENV_PY="${VENV_PY:-/workspace/venv/bin/python}"
LOGS="${SPRINT_LOGS:-/workspace/sprint_logs}"
CLAIMS_DIR="$REPO/data/cache/intel_claims"
mkdir -p "$LOGS"
cd "$REPO"

# --- lane A: per-sport signal-catalog proofs, all four in parallel --------
$VENV_PY scripts/platformkit/proof_basketball_nba/run_proof.py \
    --corpus data/domains/basketball_nba > "$LOGS/proof_nba.log" 2>&1 &
$VENV_PY scripts/platformkit/proof_mlb/run_proof.py \
    --corpus data/domains/mlb > "$LOGS/proof_mlb.log" 2>&1 &
$VENV_PY scripts/platformkit/proof_soccer/run_proof.py \
    --corpus data/domains/soccer > "$LOGS/proof_soccer.log" 2>&1 &
$VENV_PY scripts/platformkit/proof_tennis/run_proof.py \
    --corpus data/domains/tennis > "$LOGS/proof_tennis.log" 2>&1 &

# --- lane B: wait for intel_claims to finish syncing, then independently
# recompute EVERY family (sequential -- validator is memory-bounded per file)
for i in $(seq 1 240); do  # up to 2h wait for the sync to land
    [ -d "$CLAIMS_DIR" ] && n=$(ls "$CLAIMS_DIR"/*.jsonl 2>/dev/null | wc -l) || n=0
    if [ "$n" -gt 0 ]; then
        sleep 120  # settle: let the tar stream finish writing
        n2=$(ls "$CLAIMS_DIR"/*.jsonl 2>/dev/null | wc -l)
        [ "$n2" -eq "$n" ] && break
    fi
    sleep 30
done
echo "claims families found: $(ls "$CLAIMS_DIR"/*.jsonl 2>/dev/null | wc -l)" \
    > "$LOGS/claims_validate_all.log"
for f in "$CLAIMS_DIR"/*.jsonl; do
    case "$f" in *_validation*) continue ;; esac
    echo "=== $(basename "$f") ===" >> "$LOGS/claims_validate_all.log"
    $VENV_PY -m scripts.platformkit.intel_validation.claims_validator "$f" \
        >> "$LOGS/claims_validate_all.log" 2>&1
done
echo "=== claims_validate_all DONE $(date -Is) ===" >> "$LOGS/claims_validate_all.log"
wait  # lane A proofs
echo "=== wave2 DONE $(date -Is) ===" >> "$LOGS/wave2_done.log"
