#!/usr/bin/env bash
# runpod_push.sh — Push code + weights from local PC to RunPod (no persistent storage needed)
#
# Usage:
#   source .runpod && bash scripts/runpod_push.sh
#
# What it does:
#   1. rsync the full repo (excluding videos, generated data, venv)
#   2. rsync model weights (.pt only — .engine won't work on different GPU)
#   3. rsync NBA API cache + trained models + targets file
#   4. Upload runpod_setup.sh and trigger it remotely if env not built yet
set -euo pipefail

# ── Load config ──────────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

if [[ -z "${RUNPOD_IP:-}" ]]; then
    if [[ -f "$ROOT_DIR/.runpod" ]]; then
        source "$ROOT_DIR/.runpod"
    else
        echo "ERROR: .runpod config not found. Copy .runpod, fill in IP/PORT, then: source .runpod"
        exit 1
    fi
fi

if [[ -z "$RUNPOD_IP" || -z "$RUNPOD_PORT" ]]; then
    echo "ERROR: RUNPOD_IP and RUNPOD_PORT must be set in .runpod"
    exit 1
fi

SSH_OPTS="-o StrictHostKeyChecking=no -o ConnectTimeout=10 -p $RUNPOD_PORT"
[[ -n "${RUNPOD_KEY:-}" ]] && SSH_OPTS="$SSH_OPTS -i $RUNPOD_KEY"
RSYNC_SSH="ssh $SSH_OPTS"
DEST="${RUNPOD_USER}@${RUNPOD_IP}:${REMOTE_DIR}"

echo "==> Pushing to $RUNPOD_USER@$RUNPOD_IP:$RUNPOD_PORT → $REMOTE_DIR"

# ── 1. Create remote directories ─────────────────────────────────────────────
ssh $SSH_OPTS "${RUNPOD_USER}@${RUNPOD_IP}" "mkdir -p ${REMOTE_DIR}/data/models ${REMOTE_DIR}/data/nba ${REMOTE_DIR}/models/weights ${REMOTE_DIR}/resources"

# ── 2. Sync repo code (fast — excludes large binary/data dirs) ────────────────
echo ""
echo "[1/4] Syncing repo code..."
rsync -az --progress \
    -e "$RSYNC_SSH" \
    --exclude='.git/' \
    --exclude='__pycache__/' \
    --exclude='*.pyc' \
    --exclude='data/videos/' \
    --exclude='data/games/' \
    --exclude='data/tracking/' \
    --exclude='data/nba_ai.db' \
    --exclude='data/season_batch_log.csv' \
    --exclude='resources/*.engine' \
    --exclude='*.engine' \
    --exclude='node_modules/' \
    --exclude='.conda/' \
    --exclude='logs/' \
    "$ROOT_DIR/" \
    "$DEST/"

# ── 3. Sync .pt model weights (skip .engine — compiled for RTX 4060, won't work on pod GPU) ──
echo ""
echo "[2/4] Syncing model weights (.pt only)..."
rsync -az --progress \
    -e "$RSYNC_SSH" \
    --include='*.pt' \
    --exclude='*' \
    "$ROOT_DIR/resources/" \
    "$DEST/resources/"

rsync -az --progress \
    -e "$RSYNC_SSH" \
    --include='*.pt' \
    --exclude='*' \
    "$ROOT_DIR/models/weights/" \
    "$DEST/models/weights/"

# ── 4. Sync trained ML models + NBA API cache ────────────────────────────────
echo ""
echo "[3/4] Syncing data/models/ and data/nba/ cache..."
rsync -az --progress \
    -e "$RSYNC_SSH" \
    "$ROOT_DIR/data/models/" \
    "$DEST/data/models/"

rsync -az --progress \
    -e "$RSYNC_SSH" \
    "$ROOT_DIR/data/nba/" \
    "$DEST/data/nba/"

# ── 5. Sync targets file ─────────────────────────────────────────────────────
echo ""
echo "[4/4] Syncing targets + jersey map..."
rsync -az --progress \
    -e "$RSYNC_SSH" \
    "$ROOT_DIR/data/season_2025-26_targets.json" \
    "$DEST/data/" 2>/dev/null || true

rsync -az --progress \
    -e "$RSYNC_SSH" \
    "$ROOT_DIR/data/jersey_name_map.json" \
    "$DEST/data/" 2>/dev/null || true

# ── 6. Run setup on pod if conda env doesn't exist or GPU isn't working ──────
echo ""
echo "[5/5] Checking conda env + GPU on pod..."
GPU_OK=$(ssh $SSH_OPTS "${RUNPOD_USER}@${RUNPOD_IP}" \
    "/opt/conda/envs/basketball_ai/bin/python -c 'import torch; print(\"yes\" if torch.cuda.is_available() else \"no\")' 2>/dev/null" || echo "no")

if [[ "$GPU_OK" != "yes" ]]; then
    echo "  GPU not working (CUDA mismatch?) — running setup..."
    ssh $SSH_OPTS "${RUNPOD_USER}@${RUNPOD_IP}" \
        "bash ${REMOTE_DIR}/scripts/runpod_setup.sh"
else
    echo "  Env exists + GPU working — skipping setup."
fi

echo ""
echo "==> Push complete."
echo ""
echo "To start the batch run on the pod:"
echo "  ssh $SSH_OPTS ${RUNPOD_USER}@${RUNPOD_IP}"
echo "  cd $REMOTE_DIR && conda activate basketball_ai"
echo "  nohup python scripts/batch_season.py --limit 20 > logs/batch.log 2>&1 &"
echo ""
echo "Multi-GPU:"
echo "  bash scripts/runpod_4gpu.sh --limit 20"
echo ""
echo "Then on your local machine, pull data back as it runs:"
echo "  bash scripts/runpod_pull.sh --watch"
