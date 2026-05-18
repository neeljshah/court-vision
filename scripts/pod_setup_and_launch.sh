#!/bin/bash
# pod_setup_and_launch.sh — One-command RunPod setup: install deps, compile TRT, launch 3-GPU pipeline.
#
# Usage:
#   bash scripts/pod_setup_and_launch.sh <HOST> <PORT> [FRAMES]
#   bash scripts/pod_setup_and_launch.sh <pod-ip> <ssh-port> <frames>
#
# Assumes:
#   - Project code already synced to /workspace/nba-ai-system/ (via scp or rsync)
#   - Videos already in /workspace/nba-ai-system/data/videos/full_games/
#   - SSH key configured for root@HOST

set -euo pipefail

HOST="${1:?Usage: $0 HOST PORT [FRAMES]}"
PORT="${2:?Usage: $0 HOST PORT [FRAMES]}"
FRAMES="${3:-9000}"

SSH="ssh -o StrictHostKeyChecking=no -p $PORT root@$HOST"
PROJ="/workspace/nba-ai-system"

log() { echo "[$(date '+%H:%M:%S')] $*"; }

# ──────────────────────────────────────────────────────────────────────
# STEP 1: Install dependencies
# ──────────────────────────────────────────────────────────────────────
log "Step 1: Installing Python dependencies (CUDA-aware)..."
$SSH bash << 'DEPS'
# Detect pod CUDA version and install matching PyTorch
CUDA_VER=$(nvcc --version 2>/dev/null | grep -oP 'release \K[0-9]+\.[0-9]+' || echo "")
echo "Pod CUDA: ${CUDA_VER:-unknown}"

if [[ "$CUDA_VER" == 12.* ]]; then
    pip install -q torch torchvision --index-url https://download.pytorch.org/whl/cu121
elif [[ "$CUDA_VER" == 11.8* ]]; then
    pip install -q torch torchvision --index-url https://download.pytorch.org/whl/cu118
else
    pip install -q torch torchvision
fi

pip install -q nba_api easyocr torchreid ultralytics xgboost scikit-learn opencv-contrib-python decord av 2>&1 | tail -3
python3 -c "import torch; print(f'torch={torch.__version__} cuda={torch.cuda.is_available()} gpus={torch.cuda.device_count()}')"
python3 -c "import torch; assert torch.cuda.is_available(), 'CUDA NOT AVAILABLE — PyTorch/CUDA mismatch'"
python3 -c "from ultralytics import YOLO; print('ultralytics OK')"
echo "Dependencies installed"
DEPS

# ──────────────────────────────────────────────────────────────────────
# STEP 2: Compile TRT engines for THIS GPU (if not already done)
# ──────────────────────────────────────────────────────────────────────
log "Step 2: Checking/compiling TRT engines for this GPU..."
$SSH bash << 'TRT'
PROJ=/workspace/nba-ai-system
cd "$PROJ"

# Check if current engines match this GPU
GPU_NAME=$(python3 -c "import torch; print(torch.cuda.get_device_name(0))" 2>/dev/null)
echo "GPU: $GPU_NAME"

# Marker file tracks which GPU the engines were compiled for
MARKER="$PROJ/resources/.trt_compiled_for"
CURRENT_GPU=$(cat "$MARKER" 2>/dev/null || echo "none")

if [ "$CURRENT_GPU" = "$GPU_NAME" ]; then
    echo "TRT engines already compiled for $GPU_NAME — skipping"
else
    echo "Compiling TRT engines for $GPU_NAME..."

    # Compile yolov8n detection engine
    python3 -c "
from ultralytics import YOLO
print('  Compiling yolov8n.engine...')
m = YOLO('resources/yolov8n.pt')
path = m.export(format='engine', device=0, half=True, imgsz=640, simplify=True, workspace=4)
print(f'  Done: {path}')
# Move to resources/ if exported elsewhere
import shutil, os
if not os.path.exists('resources/yolov8n.engine') and os.path.exists(path):
    shutil.move(str(path), 'resources/yolov8n.engine')
" 2>&1

    # Compile yolov8n-pose engine
    python3 -c "
from ultralytics import YOLO
print('  Compiling yolov8n-pose.engine...')
m = YOLO('yolov8n-pose.pt')
path = m.export(format='engine', device=0, half=True, imgsz=640, simplify=True, workspace=4)
print(f'  Done: {path}')
import shutil, os
if not os.path.exists('resources/yolov8n-pose.engine') and os.path.exists(path):
    shutil.move(str(path), 'resources/yolov8n-pose.engine')
" 2>&1

    # Store marker
    echo "$GPU_NAME" > "$MARKER"
    echo "TRT engines compiled for $GPU_NAME"
fi

ls -lh resources/*.engine 2>/dev/null || echo "No .engine files found"
TRT

# ──────────────────────────────────────────────────────────────────────
# STEP 3: Quick validation — test one frame on GPU0
# ──────────────────────────────────────────────────────────────────────
log "Step 3: Validating GPU inference..."
$SSH bash << VALIDATE
cd $PROJ
CUDA_VISIBLE_DEVICES=0 python3 -c "
import sys, time, numpy as np, torch
sys.path.insert(0, '.')
from ultralytics import YOLO

# YOLO test
m = YOLO('resources/yolov8n.pt')
frame = np.zeros((720, 1280, 3), dtype=np.uint8)
m(frame, verbose=False, device=0, half=True)  # warmup
t = time.time()
for _ in range(10): m(frame, classes=[0], conf=0.3, verbose=False, imgsz=640, device=0, half=True)
yolo_ms = (time.time() - t) / 10 * 1000
print(f'YOLO: {yolo_ms:.1f}ms/frame (device={next(m.model.parameters()).device})')

# OSNet test
from src.tracking.osnet_reid import DeepAppearanceExtractor
ext = DeepAppearanceExtractor()
crops = [np.random.randint(0,255,(64,32,3),dtype=np.uint8) for _ in range(10)]
ext.batch_extract(crops)  # warmup
t = time.time()
for _ in range(5): ext.batch_extract(crops)
osnet_ms = (time.time() - t) / 5 * 1000
print(f'OSNet: {osnet_ms:.1f}ms/batch (device={ext._device})')

total_est = (yolo_ms + osnet_ms) / 1000 + 0.15  # +homog/ball overhead
print(f'Estimated: {total_est:.2f}s/frame → {$FRAMES * total_est / 3600:.1f}h/game → {$FRAMES * total_est * 19 / 3 / 3600:.1f}h total (57 games / 3 GPUs)')
" 2>&1
VALIDATE

# ──────────────────────────────────────────────────────────────────────
# STEP 4: Launch 3-GPU pipeline
# ──────────────────────────────────────────────────────────────────────
log "Step 4: Launching 3-GPU pipeline ($FRAMES frames/game)..."
$SSH bash << LAUNCH
set -euo pipefail
PROJ=/workspace/nba-ai-system
VIDEOS=\$PROJ/data/videos/full_games

# Kill stale
ps aux | grep run_phase_g | grep -v grep | awk '{print \$2}' | xargs kill 2>/dev/null || true
sleep 1

# Clean incomplete tracking
for d in \$PROJ/data/tracking/*/; do
  [ -d "\$d" ] || continue
  rows=\$(wc -l < "\$d/tracking_data.csv" 2>/dev/null || echo 0)
  [ "\$rows" -lt 1000 ] && rm -rf "\$d"
done

# Build game list
mapfile -t ALL < <(find "\$VIDEOS" -name "*.mp4" | xargs -I{} basename {} .mp4 | sort)
# Remove already-complete games
QUEUE=()
for gid in "\${ALL[@]}"; do
  rows=\$(wc -l < "\$PROJ/data/tracking/\$gid/tracking_data.csv" 2>/dev/null || echo 0)
  [ "\$rows" -lt 1000 ] && QUEUE+=("\$gid")
done
TOTAL=\${#QUEUE[@]}
[ "\$TOTAL" -eq 0 ] && echo "All games already processed!" && exit 0

PER=\$(( (TOTAL + 2) / 3 ))
G0=("\${QUEUE[@]:0:\$PER}")
G1=("\${QUEUE[@]:\$PER:\$PER}")
G2=("\${QUEUE[@]:\$((\$PER*2))}")

cd "\$PROJ"
echo "[\$(date '+%H:%M:%S')] \$TOTAL games — GPU0:\${#G0[@]} GPU1:\${#G1[@]} GPU2:\${#G2[@]}"

CUDA_VISIBLE_DEVICES=0 nohup python3 -u scripts/run_phase_g.py --game-ids "\${G0[@]}" --frames $FRAMES > /workspace/gpu0.log 2>&1 &
echo "GPU0 PID=\$! — \${G0[*]}"

CUDA_VISIBLE_DEVICES=1 nohup python3 -u scripts/run_phase_g.py --game-ids "\${G1[@]}" --frames $FRAMES > /workspace/gpu1.log 2>&1 &
echo "GPU1 PID=\$! — \${G1[*]}"

CUDA_VISIBLE_DEVICES=2 nohup python3 -u scripts/run_phase_g.py --game-ids "\${G2[@]}" --frames $FRAMES > /workspace/gpu2.log 2>&1 &
echo "GPU2 PID=\$! — \${G2[*]}"

echo "All 3 GPUs launched. Monitor: ssh -p $PORT root@$HOST 'tail -f /workspace/gpu0.log'"
LAUNCH

log "Done. Pipeline running on pod."
log "To auto-sync results: bash scripts/sync_tracking_results.sh"
