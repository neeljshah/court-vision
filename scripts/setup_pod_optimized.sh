#!/bin/bash
# setup_pod_optimized.sh — One-shot bootstrap for a fresh pod with all optimizations.
#
# Usage (from local):
#   bash scripts/bootstrap_pod.sh <IP> <PORT>          # original — pushes code
#   ssh -p <PORT> root@<IP> 'bash /workspace/nba-ai-system/scripts/setup_pod_optimized.sh'
#
# Does:
#   1. PEP 668 override on pip (Python 3.12)
#   2. Install all deps including kornia, onnxruntime-gpu, decord
#   3. Verify CUDA + GPU detected
#   4. Build TensorRT engines for THIS pod's GPU (3-15 min)
#   5. Set up YOLO config dirs
#   6. Stage videos with quarantine + size guard
#
# Run AFTER bootstrap_pod.sh has pushed code.

set -euo pipefail
PROJ=/workspace/nba-ai-system
cd "$PROJ"

ts() { date '+%H:%M:%S'; }
log() { echo "[$(ts)] $*"; }

log "=== Step 1: Install dependencies (PEP 668 override) ==="
pip install --break-system-packages -q \
    ultralytics decord av pandas xgboost scikit-learn nba_api easyocr scipy \
    torchreid kornia onnxruntime-gpu paddleocr 2>&1 | tail -5 || true

log "=== Step 2: Verify CUDA + GPUs ==="
python3 -c "
import torch
print(f'  torch: {torch.__version__}')
print(f'  cuda available: {torch.cuda.is_available()}')
print(f'  device count: {torch.cuda.device_count()}')
for i in range(torch.cuda.device_count()):
    p = torch.cuda.get_device_properties(i)
    print(f'  GPU {i}: {p.name} {p.total_memory/1024**3:.1f}GB compute={p.major}.{p.minor}')
import kornia, ultralytics, decord, easyocr
print(f'  kornia: {kornia.__version__}')
print(f'  ultralytics: {ultralytics.__version__}')
print(f'  decord OK')
"

log "=== Step 3: VRAM flush interval check (must be 3000) ==="
FLUSH=$(grep -oE '_VRAM_FLUSH_INTERVAL = [0-9]+' src/pipeline/unified_pipeline.py | head -1)
echo "  $FLUSH"
[[ "$FLUSH" == *"3000"* ]] || { echo "ERROR: must be 3000"; exit 1; }

log "=== Step 4: Build TensorRT engines (3-15 min) ==="
if [ "${SKIP_TRT:-0}" = "1" ]; then
    echo "  SKIP_TRT=1 → skipping engine build"
else
    bash scripts/build_trt_engines.sh
fi

log "=== Step 5: YOLO config dirs (one per GPU) ==="
N_GPUS=$(nvidia-smi --query-gpu=count --format=csv,noheader,nounits | head -1)
for i in $(seq 0 $((N_GPUS - 1))); do
    mkdir -p /tmp/Ultralytics_gpu${i}
done
echo "  created $N_GPUS YOLO config dirs"

log "=== Step 6: Stage videos to /root (fast overlay) ==="
mkdir -p /root/nba_videos
SRC="$PROJ/data/videos/full_games"
if [ -d "$SRC" ]; then
    cp -un "$SRC"/*.mp4 /root/nba_videos/ 2>/dev/null || true
    cnt=$(ls /root/nba_videos/*.mp4 2>/dev/null | wc -l)
    echo "  staged: $cnt videos"
else
    echo "  SRC dir empty/missing — upload videos first"
fi

log "=== Step 7: Decode-test + quarantine bad videos ==="
quarantined=0
for v in /root/nba_videos/*.mp4; do
    [ -f "$v" ] || continue
    if ! python3 -c "from decord import VideoReader; VideoReader('$v')" 2>/dev/null; then
        mkdir -p $PROJ/data/videos/av1_quarantine
        mv "$v" $PROJ/data/videos/av1_quarantine/
        quarantined=$((quarantined+1))
    fi
done
echo "  quarantined $quarantined bad videos"
echo "  ready: $(ls /root/nba_videos/*.mp4 2>/dev/null | wc -l)"

log "=== Setup complete. Launch with: ==="
echo "  bash scripts/launch_multigpu.sh [PARALLEL_PER_GPU]"
echo "  (1 = safe, 2 = aggressive on 2× GPU pods)"
