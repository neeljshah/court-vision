#!/usr/bin/env bash
# runpod_4gpu.sh — Launch parallel batch workers, one per GPU on RunPod.
#
# Auto-detects GPU count. Each worker processes every Nth game:
#   GPU 0 → games 0, 4, 8, ...
#   GPU 1 → games 1, 5, 9, ...
#   etc.
#
# Usage (on RunPod pod):
#   conda activate basketball_ai
#   cd /workspace/nba-ai-system
#   bash scripts/runpod_4gpu.sh [--limit 20] [--frames 0]
#
# Logs:  logs/worker_0.log  …  logs/worker_N.log
# Watch: tail -f logs/worker_*.log
set -euo pipefail

REMOTE_DIR="/workspace/nba-ai-system"
PYTHON="/opt/conda/envs/basketball_ai/bin/python"
LOG_DIR="$REMOTE_DIR/logs"

# Pass through any extra args (--limit, --frames, etc.)
EXTRA_ARGS="$*"

mkdir -p "$LOG_DIR"
cd "$REMOTE_DIR"

# ── Auto-detect GPU count ────────────────────────────────────────────────────
NUM_GPUS=$($PYTHON -c "import torch; print(torch.cuda.device_count())" 2>/dev/null || echo 0)
if [[ "$NUM_GPUS" -eq 0 ]]; then
    # Fallback: count nvidia-smi lines
    NUM_GPUS=$(nvidia-smi -L 2>/dev/null | wc -l || echo 1)
fi
[[ "$NUM_GPUS" -lt 1 ]] && NUM_GPUS=1

echo "==> Detected $NUM_GPUS GPU(s)"

# ── Verify GPU access before launching workers ───────────────────────────────
$PYTHON -c "
import torch
assert torch.cuda.is_available(), 'CUDA not available — check PyTorch install vs pod CUDA version'
for i in range(torch.cuda.device_count()):
    name = torch.cuda.get_device_name(i)
    mem  = torch.cuda.get_device_properties(i).total_mem / 1e9
    print(f'  GPU {i}: {name} ({mem:.1f} GB)')
torch.backends.cudnn.benchmark = True
print(f'  cuDNN benchmark: enabled')
"

echo ""
echo "==> Launching $NUM_GPUS workers on GPUs 0-$((NUM_GPUS-1))"
echo "    Extra args: ${EXTRA_ARGS:-none}"
echo ""

# ── GPU optimization env vars ───────────────────────────────────────────────
# cuDNN autotuner: benchmark convolution algorithms on first run, cache fastest
export TORCH_CUDNN_V8_API_ENABLED=1
# Disable TF32 for reproducibility (marginal speed loss, better precision)
export NVIDIA_TF32_OVERRIDE=1
# OpenCV: disable CPU threading (all heavy work is GPU; CPU threads just contend)
export OMP_NUM_THREADS=2
export OPENBLAS_NUM_THREADS=2
export MKL_NUM_THREADS=2
# Python hash randomization off for reproducible worker assignment
export PYTHONHASHSEED=0

PIDS=()
for GPU_ID in $(seq 0 $((NUM_GPUS-1))); do
    LOG="$LOG_DIR/worker_${GPU_ID}.log"
    echo "  GPU $GPU_ID → $LOG"
    CUDA_VISIBLE_DEVICES=$GPU_ID \
    OMP_NUM_THREADS=2 \
    $PYTHON scripts/batch_season.py \
        --gpu $GPU_ID \
        --worker-id $GPU_ID \
        --num-workers $NUM_GPUS \
        $EXTRA_ARGS \
        > "$LOG" 2>&1 &
    PIDS+=($!)
done

echo ""
echo "==> All $NUM_GPUS workers started. PIDs: ${PIDS[*]}"
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
    $PYTHON -c "
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
