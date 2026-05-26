#!/bin/bash
# =============================================================================
# runpod_bootstrap.sh — R16: one-command fresh-pod boot (<30 min cold start)
#
# Replaces the previous 4-step manual flow (bootstrap_pod.sh → setup_pod_optimized.sh
# → build_trt_engines.sh → launch_multigpu.sh). Pushes code + critical artefacts,
# installs pinned deps, syncs videos from B2 (if configured), builds TRT engines,
# smoke-tests the pipeline.
#
# Usage (from laptop, in nba-ai-system/):
#   bash scripts/runpod_bootstrap.sh <IP> <SSH_PORT>
#
# Example:
#   bash scripts/runpod_bootstrap.sh 213.192.2.86 40045
#
# Prerequisites on laptop:
#   - Working .env with B2_* keys (optional; if absent, videos pushed manually)
#   - data/models/, data/nba/, resources/, models/weights/ populated
#   - SSH keypair (or you'll be prompted for password ~6 times)
# =============================================================================
set -euo pipefail

IP="${1:?usage: bash scripts/runpod_bootstrap.sh <IP> <PORT>}"
PORT="${2:?need <PORT>}"
SSH="ssh -o StrictHostKeyChecking=no -p ${PORT} root@${IP}"
SCP="scp -o StrictHostKeyChecking=no -P ${PORT}"
PROJ="/workspace/nba-ai-system"
MIRROR="/workspace/pred-system"   # second clone for tests

echo "================================================================================"
echo "RunPod bootstrap → root@${IP}:${PORT}"
echo "================================================================================"

# 1. Verify pod is reachable + GPU is visible
echo "[1/8] Sanity check..."
$SSH "mkdir -p ${PROJ} ${MIRROR} /root/nba_videos && nvidia-smi -L && python3 --version"

# 2. Push code (excludes data/, vault/, .git/, caches)
echo "[2/8] Pushing source tree..."
if command -v rsync >/dev/null 2>&1; then
    rsync -az -e "ssh -p ${PORT}" --delete \
        --exclude='/data' --exclude='/.git' --exclude='/vault' \
        --exclude='__pycache__' --exclude='*.pyc' --exclude='.pytest_cache' \
        --exclude='/.planning' --exclude='/.claude' --exclude='/.cache' \
        ./ "root@${IP}:${PROJ}/"
else
    echo "  (rsync unavailable — using tar over SSH)"
    tar --exclude='./data' --exclude='./.git' --exclude='./vault' \
        --exclude='__pycache__' --exclude='*.pyc' --exclude='./.planning' \
        --exclude='./.claude' --exclude='./.cache' \
        -czf - . | $SSH "tar -xzf - -C ${PROJ}"
fi

# Mirror code into /workspace/pred-system for the dual-tree test workflow
$SSH "rsync -a --delete ${PROJ}/ ${MIRROR}/"

# 3. Push critical artefacts that CANNOT be re-downloaded
echo "[3/8] Pushing models + resources + cache..."
$SSH "mkdir -p ${PROJ}/data/models ${PROJ}/data/nba ${PROJ}/data/cache ${PROJ}/resources ${PROJ}/models/weights"
if [ -d data/models ]; then
    $SCP -r data/models/ "root@${IP}:${PROJ}/data/"
fi
if [ -d data/nba ]; then
    $SCP -r data/nba/ "root@${IP}:${PROJ}/data/"
fi
if [ -d resources ]; then
    $SCP -r resources/ "root@${IP}:${PROJ}/"
fi
if [ -d models/weights ]; then
    $SCP -r models/weights/ "root@${IP}:${PROJ}/models/"
fi

# 4. Push .env (secrets)
if [ -f .env ]; then
    echo "[4/8] Pushing .env secrets..."
    $SCP .env "root@${IP}:${PROJ}/.env"
else
    echo "[4/8] WARN: no .env on laptop — copy .env.example and fill secrets first"
fi

# 5. Install Python deps (pinned via R16 requirements.txt + CUDA 12 wheels)
echo "[5/8] Installing Python deps (pinned R16)..."
$SSH "cd ${PROJ} && \
    pip install --break-system-packages -q --upgrade pip && \
    pip install --break-system-packages -q --index-url https://download.pytorch.org/whl/cu128 \
        torch==2.8.0 torchvision==0.23.0 torchaudio==2.8.0 && \
    pip install --break-system-packages -q -r requirements.txt"

# 6. Smoke-test critical imports
echo "[6/8] Verifying imports..."
$SSH "python3 -c \"
import torch, ultralytics, decord, kornia, easyocr, lightgbm, xgboost, paddleocr
import torchreid
assert torch.cuda.is_available(), 'NO CUDA available'
print(f'deps OK — GPU={torch.cuda.get_device_name(0)} CUDA={torch.version.cuda} torch={torch.__version__}')
\""

# 7. Sync videos from B2 (if B2_BUCKET configured)
echo "[7/8] Syncing videos from B2 (if configured)..."
$SSH "cd ${PROJ} && set -a && [ -f .env ] && source .env; set +a
if [ -n \"\${B2_BUCKET:-}\" ] && command -v rclone >/dev/null 2>&1; then
    rclone copy b2:\${B2_BUCKET}/full_games/ /root/nba_videos/ \
        --include '*.mp4' --transfers 8 --progress 2>&1 | tail -5
elif [ -n \"\${B2_BUCKET:-}\" ]; then
    echo '  WARN: rclone not installed. Install: curl https://rclone.org/install.sh | bash'
else
    echo '  WARN: no B2_BUCKET in .env — push videos manually:'
    echo '    scp -P ${PORT} /local/path/videos/*.mp4 root@${IP}:/root/nba_videos/'
fi"

# 8. Build TRT engines for this pod's GPU (if script exists)
echo "[8/8] Building TRT engines for this GPU..."
if $SSH "test -f ${PROJ}/scripts/build_trt_engines.sh"; then
    $SSH "cd ${PROJ} && bash scripts/build_trt_engines.sh 2>&1 | tail -10" || \
        echo "  WARN: TRT build failed — fallback to ONNX/PyTorch (slower but works)"
else
    echo "  (build_trt_engines.sh not present — skipping TRT)"
fi

echo ""
echo "================================================================================"
echo "BOOTSTRAP COMPLETE."
echo "  Project:  ${PROJ}"
echo "  Test it:  ssh -p ${PORT} root@${IP} 'cd ${PROJ} && python3 -m pytest -q tests/test_tracker.py'"
echo "  Run clip: ssh -p ${PORT} root@${IP} 'cd ${PROJ} && python3 scripts/run_clip.py --help'"
echo "================================================================================"
