#!/bin/bash
# launch_single_gpu_pod.sh — (Re)launch Phase G on an already-bootstrapped pod.
#
# Usage:
#   bash scripts/launch_single_gpu_pod.sh <IP> <PORT> [FRAMES]
#   # Example: bash scripts/launch_single_gpu_pod.sh <pod-ip> <ssh-port>
#
# For first-time pod setup, use bootstrap_pod.sh instead.
# This script assumes deps are installed and videos staged.

set -euo pipefail

IP="${1:?Usage: bash scripts/launch_single_gpu_pod.sh <IP> <PORT> [FRAMES]}"
PORT="${2:?Usage: bash scripts/launch_single_gpu_pod.sh <IP> <PORT> [FRAMES]}"
FRAMES="${3:-18000}"
SSH="ssh -o StrictHostKeyChecking=no -p ${PORT} root@${IP}"
PROJ="/workspace/nba-ai-system"

log() { echo "[$(date '+%H:%M:%S')] $*"; }

log "Launching Phase G on ${IP}:${PORT} (--parallel 4, --frames ${FRAMES}, OMP=6)"

# ── Pre-flight: VRAM flush ────────────────────────────────────────────
FLUSH=$($SSH "grep -oE '_VRAM_FLUSH_INTERVAL = [0-9]+' ${PROJ}/src/pipeline/unified_pipeline.py | head -1")
echo "  pod has: ${FLUSH}"
[[ "$FLUSH" == *"3000"* ]] || { echo "ERROR: _VRAM_FLUSH_INTERVAL != 3000"; exit 1; }

# ── Pre-flight: CPU quota ─────────────────────────────────────────────
$SSH 'python3 -c "
q = int(open(\"/sys/fs/cgroup/cpu,cpuacct/cpu.cfs_quota_us\").read().strip())
p = int(open(\"/sys/fs/cgroup/cpu,cpuacct/cpu.cfs_period_us\").read().strip())
print(f\"  CPU quota: {q/p:.1f} cores\")
" 2>/dev/null || echo "  CPU quota: unknown"'

# ── Kill stale workers ────────────────────────────────────────────────
log "Killing stale workers..."
$SSH "pgrep -f '[r]un_phase_g.py' | xargs -r kill -TERM 2>/dev/null; sleep 2; pgrep -f '[r]un_clip.py' | xargs -r kill -KILL 2>/dev/null; true"

# ── Launch ────────────────────────────────────────────────────────────
log "Starting phase_g --parallel 4 --frames ${FRAMES}..."
$SSH "cd ${PROJ} && rm -f phase_g_batch.log && \
    MALLOC_ARENA_MAX=2 \
    MALLOC_MMAP_THRESHOLD_=65536 \
    OMP_NUM_THREADS=6 \
    MKL_NUM_THREADS=6 \
    OPENBLAS_NUM_THREADS=6 \
    NUMEXPR_NUM_THREADS=6 \
    CUDA_VISIBLE_DEVICES=0 \
    COURTV_NO_LOFTR=1 \
    PHASE_G_VIDEO_DIR=/root/nba_videos \
    SYNC_TARGET="root@${IP}:/workspace/nba-ai-system/data/tracking/" \
    nohup python3 scripts/run_phase_g.py --frames ${FRAMES} --parallel 4 \
    > phase_g_batch.log 2>&1 & disown"

sleep 5
COUNT=$($SSH "pgrep -af run_phase_g.py | grep -v pgrep | wc -l" 2>/dev/null || echo 0)
[ "$COUNT" -ge 1 ] && echo "Launched OK ($COUNT process)" || echo "ERROR: no process"

log "Monitor: ssh -p ${PORT} root@${IP} 'tail -f ${PROJ}/phase_g_batch.log'"
