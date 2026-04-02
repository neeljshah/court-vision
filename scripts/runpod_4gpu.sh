#!/usr/bin/env bash
# runpod_4gpu.sh — Launch 4 parallel batch workers on a 4x RTX 4090 RunPod pod.
#
# Each worker gets its own GPU and processes every 4th game from the target list:
#   GPU 0 → games 0, 4, 8, 12, 16 ...
#   GPU 1 → games 1, 5, 9, 13, 17 ...
#   GPU 2 → games 2, 6, 10, 14, 18 ...
#   GPU 3 → games 3, 7, 11, 15, 19 ...
#
# Usage (on RunPod pod):
#   conda activate basketball_ai
#   cd /workspace/nba-ai-system
#   bash scripts/runpod_4gpu.sh [--limit 20] [--frames 0]
#
# Logs:  logs/worker_0.log  …  logs/worker_3.log
# Watch: tail -f logs/worker_*.log
set -euo pipefail

REMOTE_DIR="/workspace/nba-ai-system"
PYTHON="/opt/conda/envs/basketball_ai/bin/python"
LOG_DIR="$REMOTE_DIR/logs"
NUM_GPUS=4

# Pass through any extra args (--limit, --frames, etc.)
EXTRA_ARGS="$*"

mkdir -p "$LOG_DIR"
cd "$REMOTE_DIR"

echo "==> Launching $NUM_GPUS workers on GPUs 0-$((NUM_GPUS-1))"
echo "    Extra args: ${EXTRA_ARGS:-none}"
echo ""

PIDS=()
for GPU_ID in $(seq 0 $((NUM_GPUS-1))); do
    LOG="$LOG_DIR/worker_${GPU_ID}.log"
    echo "  GPU $GPU_ID → $LOG"
    CUDA_VISIBLE_DEVICES=$GPU_ID $PYTHON scripts/batch_season.py \
        --gpu $GPU_ID \
        --worker-id $GPU_ID \
        --num-workers $NUM_GPUS \
        $EXTRA_ARGS \
        > "$LOG" 2>&1 &
    PIDS+=($!)
done

echo ""
echo "==> All 4 workers started. PIDs: ${PIDS[*]}"
echo "    Watch all logs:   tail -f logs/worker_*.log"
echo "    Watch one:        tail -f logs/worker_0.log"
echo "    Kill all:         kill ${PIDS[*]}"
echo ""

# Save PIDs for monitoring
printf '%s\n' "${PIDS[@]}" > "$LOG_DIR/worker_pids.txt"

# Wait for all workers and report final status
echo "Waiting for all workers to finish..."
ALL_OK=true
for i in "${!PIDS[@]}"; do
    if wait "${PIDS[$i]}"; then
        echo "  Worker $i (GPU $i): DONE"
    else
        echo "  Worker $i (GPU $i): FAILED (exit $?)"
        ALL_OK=false
    fi
done

echo ""
if $ALL_OK; then
    echo "==> All workers completed successfully."
else
    echo "==> Some workers failed — check logs/worker_*.log"
fi

# Print combined summary from batch log
if [[ -f "$REMOTE_DIR/data/season_batch_log.csv" ]]; then
    echo ""
    echo "==> Batch log summary:"
    python3 -c "
import csv
rows = list(csv.DictReader(open('$REMOTE_DIR/data/season_batch_log.csv')))
ok  = [r for r in rows if r.get('status') == 'success']
fail = [r for r in rows if r.get('status') not in ('success', 'started', '')]
print(f'  Completed: {len(ok)} games')
print(f'  Failed:    {len(fail)} games')
for r in ok:
    print(f'    ✓ {r[\"game_id\"]}  {r.get(\"matchup\",\"\")}  rows={r.get(\"rows\",\"?\")}  grade={r.get(\"quality_grade\",\"?\")}')
for r in fail:
    print(f'    ✗ {r[\"game_id\"]}  {r.get(\"matchup\",\"\")}  {r.get(\"error\",\"\")}')
"
fi
