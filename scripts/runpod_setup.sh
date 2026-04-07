#!/usr/bin/env bash
# runpod_setup.sh — One-time environment setup ON the RunPod pod
#
# Triggered automatically by runpod_push.sh if env doesn't exist.
# Can also be run manually: bash scripts/runpod_setup.sh
#
# Safe to re-run — skips steps already done.
set -euo pipefail

REMOTE_DIR="/workspace/nba-ai-system"
CONDA="/opt/conda/bin/conda"
PIP="/opt/conda/envs/basketball_ai/bin/pip"
PYTHON="/opt/conda/envs/basketball_ai/bin/python"

echo "==> RunPod environment setup"
echo "    Project: $REMOTE_DIR"
echo ""

cd "$REMOTE_DIR"

# ── 0. Detect CUDA version on this pod ───────────────────────────────────────
CUDA_VER=$(nvcc --version 2>/dev/null | grep -oP 'release \K[0-9]+\.[0-9]+' || echo "")
echo "Detected CUDA: ${CUDA_VER:-unknown}"

# ── 1. Create conda env (Python 3.9) ─────────────────────────────────────────
if [[ ! -d /opt/conda/envs/basketball_ai ]]; then
    echo "[1/6] Creating conda env basketball_ai (Python 3.9)..."
    $CONDA create -n basketball_ai python=3.9 -y
else
    echo "[1/6] Conda env already exists — skipping."
fi

# ── 2. Install pip dependencies ───────────────────────────────────────────────
echo ""
echo "[2/6] Installing pip dependencies..."
$PIP install --upgrade pip -q

# PyTorch: install version matching the pod's CUDA driver.
# RunPod templates ship CUDA 12.x — cu118 torch will silently fall back to CPU.
if [[ "$CUDA_VER" == 12.* ]]; then
    echo "  Installing PyTorch for CUDA 12.x..."
    $PIP install torch torchvision --index-url https://download.pytorch.org/whl/cu121 -q
elif [[ "$CUDA_VER" == 11.8* ]]; then
    echo "  Installing PyTorch for CUDA 11.8..."
    $PIP install torch torchvision --index-url https://download.pytorch.org/whl/cu118 -q
else
    # Let pip pick the best available wheel
    echo "  Installing PyTorch (auto-detect CUDA)..."
    $PIP install torch torchvision -q
fi

# Core deps
$PIP install \
    ultralytics \
    opencv-python-headless \
    easyocr \
    numpy \
    scipy \
    scikit-learn \
    xgboost \
    lightgbm \
    joblib \
    pandas \
    pyarrow \
    networkx \
    nba_api \
    requests \
    yt-dlp \
    fastapi \
    uvicorn \
    psycopg2-binary \
    sqlalchemy \
    python-dotenv \
    tqdm \
    -q

# ── 3. GPU video decode (decord with NVDEC) ─────────────────────────────────
echo ""
echo "[3/6] Installing decord (GPU NVDEC video decode) + TensorRT..."
$PIP install decord -q 2>/dev/null || {
    # decord wheel sometimes unavailable — build from source
    echo "  decord pip install failed; trying conda..."
    $CONDA install -n basketball_ai -c conda-forge decord -y 2>/dev/null || {
        echo "  WARNING: decord unavailable — will use PyAV CPU decode (slower)"
    }
}
# PyAV as fallback
$PIP install av -q

# TensorRT — 2-4x speedup for YOLO + OSNet inference
echo "  Installing TensorRT..."
$PIP install tensorrt -q 2>/dev/null || {
    echo "  TensorRT pip install failed — trying nvidia-tensorrt..."
    $PIP install nvidia-tensorrt -q 2>/dev/null || {
        echo "  WARNING: TensorRT unavailable — will use PyTorch FP16 (still fast)"
    }
}

# ── 4. torchreid (OSNet re-ID) ───────────────────────────────────────────────
echo ""
echo "[4/6] Installing torchreid (OSNet)..."
if ! $PYTHON -c "import torchreid" 2>/dev/null; then
    $PIP install torchreid -q || {
        $PIP install git+https://github.com/KaiyangZhou/deep-person-reid.git -q || true
    }
else
    echo "  torchreid already installed."
fi

$PIP install deep-sort-realtime -q

# ── 5. Download OSNet weights if missing ─────────────────────────────────────
echo ""
echo "[5/6] Checking OSNet weights..."
OSNET_WEIGHTS="$REMOTE_DIR/data/models/osnet_x0_25_imagenet.pth"
if [[ ! -f "$OSNET_WEIGHTS" ]]; then
    echo "  Downloading osnet_x0_25_imagenet.pth..."
    mkdir -p "$REMOTE_DIR/data/models"
    $PYTHON -c "
import torch, os
url = 'https://drive.google.com/uc?id=1Kkx2zW89jq_NETu4u42CFZTMVD5Hwm6s'
try:
    torch.hub.download_url_to_file(
        'https://github.com/KaiyangZhou/deep-person-reid/releases/download/v1.1.0/osnet_x0_25_imagenet.pth',
        '$OSNET_WEIGHTS'
    )
    print(f'  Downloaded to $OSNET_WEIGHTS')
except Exception as e:
    print(f'  WARNING: could not download OSNet weights: {e}')
    print('  Re-ID will use fallback embeddings (less accurate)')
" 2>&1
else
    echo "  OSNet weights already present."
fi

# ── 6. Export TensorRT engines for this GPU ──────────────────────────────────
echo ""
echo "[6/7] Exporting TensorRT engines (GPU-specific, ~2 min)..."
$PYTHON "$REMOTE_DIR/scripts/export_tensorrt.py" 2>&1 || {
    echo "  TRT export failed — will use PyTorch FP16 fallback (still GPU)"
}

# ── 7. Verify GPU access + project imports ───────────────────────────────────
echo ""
echo "[7/7] Verifying GPU + project imports..."
mkdir -p "$REMOTE_DIR/logs"

$PYTHON -c "
import sys, os
sys.path.insert(0, '$REMOTE_DIR')

# GPU verification
import torch
print(f'  PyTorch {torch.__version__}')
print(f'  CUDA available: {torch.cuda.is_available()}')
if torch.cuda.is_available():
    print(f'  GPU count: {torch.cuda.device_count()}')
    for i in range(torch.cuda.device_count()):
        name = torch.cuda.get_device_name(i)
        mem  = torch.cuda.get_device_properties(i).total_mem / 1e9
        print(f'    GPU {i}: {name} ({mem:.1f} GB)')
    # Enable cuDNN benchmark for fixed-size inputs (broadcast frames)
    torch.backends.cudnn.benchmark = True
    print(f'  cuDNN benchmark: enabled')
else:
    print('  *** WARNING: CUDA NOT AVAILABLE — pipeline will run on CPU (very slow) ***')
    print('  Check: nvcc --version, nvidia-smi, and PyTorch CUDA version match')

# decord GPU decode check
try:
    from decord import gpu
    print(f'  decord GPU decode: available')
except ImportError:
    print(f'  decord GPU decode: NOT available (will use PyAV CPU)')

# Module imports
ok = []
fail = []
for mod in ['cv2','torch','ultralytics','easyocr','nba_api','yt_dlp','xgboost','sklearn']:
    try:
        __import__(mod)
        ok.append(mod)
    except ImportError as e:
        fail.append(f'{mod}: {e}')
print(f'  OK: {\", \".join(ok)}')
if fail:
    print(f'  MISSING: {\", \".join(fail)}')
else:
    print(f'  All imports OK.')
"

echo ""
echo "==> Setup complete. To run the batch:"
echo "    conda activate basketball_ai"
echo "    cd $REMOTE_DIR"
echo "    nohup python scripts/batch_season.py --limit 20 > logs/batch.log 2>&1 &"
echo "    tail -f logs/batch.log"
echo ""
echo "    Multi-GPU:"
echo "    bash scripts/runpod_4gpu.sh --limit 20"
