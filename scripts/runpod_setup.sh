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

# ── 1. Create conda env (Python 3.9) ─────────────────────────────────────────
if [[ ! -d /opt/conda/envs/basketball_ai ]]; then
    echo "[1/5] Creating conda env basketball_ai (Python 3.9)..."
    $CONDA create -n basketball_ai python=3.9 -y
else
    echo "[1/5] Conda env already exists — skipping."
fi

# ── 2. Install pip dependencies ───────────────────────────────────────────────
echo ""
echo "[2/5] Installing pip dependencies..."
$PIP install --upgrade pip -q

# PyTorch CUDA 11.8 — matches RunPod's CUDA version on most templates
$PIP install torch==2.0.1 torchvision==0.15.2 --index-url https://download.pytorch.org/whl/cu118 -q

# Core deps from requirements.txt (skip torch — already installed above)
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

# torchreid (OSNet re-ID) — install from source for Linux
echo ""
echo "[3/5] Installing torchreid (OSNet)..."
if ! $PYTHON -c "import torchreid" 2>/dev/null; then
    $PIP install torchreid -q || {
        # Fallback: install from GitHub
        $PIP install git+https://github.com/KaiyangZhou/deep-person-reid.git -q || true
    }
else
    echo "  torchreid already installed."
fi

# deep-sort-realtime
$PIP install deep-sort-realtime -q

# ── 3. Install yt-dlp (video downloader) ────────────────────────────────────
echo ""
echo "[4/5] Verifying yt-dlp..."
yt-dlp --version 2>/dev/null || $PIP install yt-dlp -q

# ── 4. Create log dir + verify project imports ────────────────────────────────
echo ""
echo "[5/5] Verifying project imports..."
mkdir -p "$REMOTE_DIR/logs"

$PYTHON -c "
import sys
sys.path.insert(0, '$REMOTE_DIR')
ok = []
fail = []
for mod in ['cv2','torch','ultralytics','easyocr','nba_api','yt_dlp','xgboost','sklearn']:
    try:
        __import__(mod)
        ok.append(mod)
    except ImportError as e:
        fail.append(f'{mod}: {e}')
print('  OK:', ', '.join(ok))
if fail:
    print('  MISSING:', ', '.join(fail))
else:
    print('  All imports OK.')
"

echo ""
echo "==> Setup complete. To run the batch:"
echo "    conda activate basketball_ai"
echo "    cd $REMOTE_DIR"
echo "    nohup python scripts/batch_season.py --limit 20 > logs/batch.log 2>&1 &"
echo "    tail -f logs/batch.log"
