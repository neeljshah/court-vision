#!/bin/bash
# launch_single_gpu_pod.sh — Launch Phase G on a single-GPU RunPod.
#
# Usage:
#   source .runpod && bash scripts/launch_single_gpu_pod.sh [FRAMES]
#   bash scripts/launch_single_gpu_pod.sh 18000
#
# Why this exists (Session 34, 2026-04-09):
#   RunPod single-4090 templates ship with a cgroup CFS quota of ~18 CPU cores
#   (cpu.cfs_quota_us=1785000 / period=100000). With --parallel 4, each worker
#   wants 6-10 cores for SIFT/ball/adaptive_colors, total demand ~24-40 cores
#   → exceeds quota → CFS throttles → workers take turns being hot, effective
#   throughput drops 2-3x. --parallel 3 fits the quota (3 × ~6 cores ≈ 18) and
#   runs all workers concurrently. CPU pressure drops from 80% → 60%.
#
#   Also: unified_pipeline.py:_VRAM_FLUSH_INTERVAL must be 3000, NOT 100.
#   Flushing torch.cuda.empty_cache() every 100 frames forces GPU syncs that
#   stall CPU stages → 10x slowdown. Verified by comparing before/after PROFILE
#   lines (0.05s/frame vs 3.0s/frame).
#
#   MPS does NOT help — the bottleneck is CPU quota, not GPU serialization.
#
# Assumes:
#   - .runpod config sourced (RUNPOD_IP, RUNPOD_PORT, RUNPOD_USER)
#   - Repo already pushed to /workspace/nba-ai-system/ on pod
#   - Videos in /workspace/nba-ai-system/data/videos/full_games/

set -euo pipefail

FRAMES="${1:-18000}"

: "${RUNPOD_IP:?Set RUNPOD_IP — source .runpod first}"
: "${RUNPOD_PORT:?Set RUNPOD_PORT — source .runpod first}"
: "${RUNPOD_USER:=root}"

SSH_OPTS="-p ${RUNPOD_PORT} -o StrictHostKeyChecking=no"
SSH="ssh ${SSH_OPTS} ${RUNPOD_USER}@${RUNPOD_IP}"
PROJ="/workspace/nba-ai-system"

log() { echo "[$(date '+%H:%M:%S')] $*"; }

log "Launching Phase G on ${RUNPOD_IP}:${RUNPOD_PORT} (--parallel 3, --frames ${FRAMES})"

# ── Pre-flight: verify the VRAM-flush fix is on the pod ────────────────
log "Pre-flight: checking _VRAM_FLUSH_INTERVAL on pod..."
FLUSH=$($SSH "grep -oE '_VRAM_FLUSH_INTERVAL = [0-9]+' ${PROJ}/src/pipeline/unified_pipeline.py | head -1")
echo "  pod has: ${FLUSH}"
if [[ "$FLUSH" != *"3000"* ]]; then
    echo "  ERROR: _VRAM_FLUSH_INTERVAL is not 3000 on the pod."
    echo "  Re-upload src/pipeline/unified_pipeline.py before continuing."
    exit 1
fi

# ── Pre-flight: verify CPU quota (warn if changed) ─────────────────────
QUOTA=$($SSH "cat /sys/fs/cgroup/cpu/cpu.cfs_quota_us 2>/dev/null || echo -1")
PERIOD=$($SSH "cat /sys/fs/cgroup/cpu/cpu.cfs_period_us 2>/dev/null || echo 100000")
if [ "$QUOTA" != "-1" ]; then
    CORES=$(awk "BEGIN {printf \"%.1f\", $QUOTA / $PERIOD}")
    log "Pod CPU quota: ${CORES} cores (quota=${QUOTA} period=${PERIOD})"
    if (( $(echo "$CORES < 15" | bc -l) )); then
        echo "  WARNING: quota is <15 cores, --parallel 3 may still throttle."
        echo "  Consider --parallel 2 instead."
    fi
fi

# ── Kill stale workers (bracket pattern avoids killing self) ───────────
log "Killing any stale workers..."
$SSH "pgrep -f '[r]un_phase_g.py' | xargs -r kill -TERM 2>/dev/null; sleep 1; pgrep -f '[r]un_clip.py' | xargs -r kill -TERM 2>/dev/null; sleep 5; pgrep -f '[r]un_clip.py' | xargs -r kill -KILL 2>/dev/null; pgrep -f '[r]un_phase_g.py' | xargs -r kill -KILL 2>/dev/null; true"

# ── Launch ─────────────────────────────────────────────────────────────
log "Starting phase_g --parallel 3 --frames ${FRAMES}..."
$SSH "cd ${PROJ} && rm -f phase_g_p3.log && CUDA_VISIBLE_DEVICES=0 nohup python3 scripts/run_phase_g.py --frames ${FRAMES} --parallel 3 > phase_g_p3.log 2>&1 & disown"

sleep 5
WORKERS=$($SSH "pgrep -f '[r]un_phase_g.py' | wc -l")
log "phase_g launched. run_phase_g processes: ${WORKERS}"
log "Tail log with:  ${SSH} 'tail -f ${PROJ}/../phase_g_p3.log'"
log "Done."
