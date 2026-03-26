#!/usr/bin/env bash
# setup_runpod.sh -- Phase G/H: One-command RunPod A100 environment setup
#
# Usage (on RunPod SSH):
#   bash setup_runpod.sh [--repo-url <git-url>] [--db-url <postgres-url>] [--redis-url <redis-url>]
#
# What this does:
#   1. Clone repo (or pull latest if already exists)
#   2. Create conda env from environment.yml (or requirements.txt)
#   3. Set DATABASE_URL + REDIS_URL env vars
#   4. Run migrations to create DB schema
#   5. Export TensorRT engines for A100
#   6. Start Redis + Celery workers

set -e

REPO_URL="${1:-}"
DB_URL="${2:-${DATABASE_URL:-}}"
REDIS_URL="${3:-${REDIS_URL:-redis://localhost:6379/0}}"
PROJECT_DIR="${HOME}/nba-ai-system"
CONDA_ENV="basketball_ai"
N_WORKERS=8

echo "=== NBA AI System — RunPod Setup ==="
echo "Project: ${PROJECT_DIR}"
echo "Workers: ${N_WORKERS}"
echo ""

# ── 1. Clone or update repo ───────────────────────────────────────────────────
if [ -d "${PROJECT_DIR}" ]; then
    echo "[1/6] Pulling latest..."
    cd "${PROJECT_DIR}" && git pull --ff-only
else
    if [ -z "${REPO_URL}" ]; then
        echo "ERROR: --repo-url required for first-time setup"
        exit 1
    fi
    echo "[1/6] Cloning repo..."
    git clone "${REPO_URL}" "${PROJECT_DIR}"
fi
cd "${PROJECT_DIR}"

# ── 2. Conda environment ──────────────────────────────────────────────────────
echo ""
echo "[2/6] Setting up conda environment..."
if conda env list | grep -q "^${CONDA_ENV}"; then
    echo "  Env '${CONDA_ENV}' exists — updating..."
    conda env update -n "${CONDA_ENV}" -f environment.yml --prune 2>/dev/null \
        || pip install -r requirements.txt
else
    echo "  Creating env '${CONDA_ENV}'..."
    conda env create -f environment.yml 2>/dev/null \
        || conda create -n "${CONDA_ENV}" python=3.10 -y && conda run -n "${CONDA_ENV}" pip install -r requirements.txt
fi

# ── 3. Environment variables ──────────────────────────────────────────────────
echo ""
echo "[3/6] Setting environment variables..."
export DATABASE_URL="${DB_URL}"
export REDIS_URL="${REDIS_URL}"

# Persist for this session
echo "export DATABASE_URL='${DB_URL}'" >> "${HOME}/.bashrc"
echo "export REDIS_URL='${REDIS_URL}'" >> "${HOME}/.bashrc"
echo "export PYTHONPATH='${PROJECT_DIR}'" >> "${HOME}/.bashrc"

# ── 4. Database migrations ────────────────────────────────────────────────────
echo ""
echo "[4/6] Running database migrations..."
if [ -n "${DB_URL}" ]; then
    conda run -n "${CONDA_ENV}" python src/data/migrations.py \
        && echo "  Migrations applied."
else
    echo "  SKIP: DATABASE_URL not set. Set it and run: python src/data/migrations.py"
fi

# ── 5. Export TensorRT engines ────────────────────────────────────────────────
echo ""
echo "[5/6] Exporting TensorRT engines for A100..."
conda run -n "${CONDA_ENV}" python scripts/export_tensorrt.py \
    && echo "  TensorRT export done." \
    || echo "  TensorRT export skipped (will use .pt fallback)"

# ── 6. Start Redis + Celery ───────────────────────────────────────────────────
echo ""
echo "[6/6] Starting Redis + Celery workers..."

# Start Redis in background (if not already running)
if command -v redis-server &>/dev/null; then
    redis-server --daemonize yes --loglevel warning
    echo "  Redis started."
else
    echo "  Redis not found — install: apt-get install redis-server"
    echo "  Or use Redis Cloud free tier and set REDIS_URL"
fi

# Start Celery workers
echo "  Starting ${N_WORKERS} Celery workers..."
conda run -n "${CONDA_ENV}" \
    celery -A src.pipeline.tasks worker \
    --concurrency=${N_WORKERS} \
    --loglevel=info \
    --logfile=/tmp/celery_worker.log \
    --detach 2>/dev/null \
    && echo "  Celery started (log: /tmp/celery_worker.log)" \
    || echo "  Celery not available (pip install celery[redis])"

echo ""
echo "=== Setup complete! ==="
echo ""
echo "To process games:"
echo "  conda activate ${CONDA_ENV}"
echo "  python scripts/batch_process.py --folder recordings/ --workers ${N_WORKERS}"
echo ""
echo "To monitor progress:"
echo "  conda run -n ${CONDA_ENV} celery -A src.pipeline.tasks flower &"
echo "  # Open: http://localhost:5555"
echo ""
echo "Model milestone schedule:"
echo "  20 games  -> Tier 3 unlocks (xFG v2, play type, pressure, spacing)"
echo "  50 games  -> Tier 4 unlocks (fatigue, rebound positioning)"
echo " 100 games  -> Tier 5 unlocks (lineup chemistry, matchup matrix)"
echo " 200 games  -> Tier 6 unlocks (full simulator, live LSTM)"
