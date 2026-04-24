#!/usr/bin/env bash
# CourtVision — dev environment setup (run once per new machine)
# Works on: macOS, Linux, Windows Git-Bash
set -euo pipefail

cd "$(dirname "$0")/.."
echo "=== CourtVision Dev Setup ==="
echo "Repo: $(pwd)"

# 0. Sanity: must be in repo root
if [ ! -f requirements.txt ]; then
  echo "ERROR: requirements.txt not found. Run from repo root or scripts/ dir." >&2
  exit 1
fi

# 1. Check conda
if ! command -v conda >/dev/null 2>&1; then
  echo "ERROR: conda not found. Install Miniconda first:" >&2
  echo "  https://docs.conda.io/en/latest/miniconda.html" >&2
  exit 1
fi

# 2. Create/reuse env
if conda env list | grep -q "^basketball_ai "; then
  echo "[1/5] conda env 'basketball_ai' already exists — reusing"
else
  echo "[1/5] Creating conda env 'basketball_ai' (Python 3.9)..."
  conda create -n basketball_ai python=3.9 -y
fi

echo "[2/5] Installing Python dependencies..."
conda run -n basketball_ai --no-capture-output pip install -r requirements.txt

# 3. YOLO weights (tracked in git, but re-download if missing)
if [ ! -f yolov8n.pt ]; then
  echo "[3/5] yolov8n.pt missing — downloading..."
  conda run -n basketball_ai --no-capture-output python -c "from ultralytics import YOLO; YOLO('yolov8n.pt')"
fi
if [ ! -f yolov8n-pose.pt ]; then
  echo "[3/5] yolov8n-pose.pt missing — downloading..."
  conda run -n basketball_ai --no-capture-output python -c "from ultralytics import YOLO; YOLO('yolov8n-pose.pt')"
fi

# 4. .env bootstrap
if [ ! -f .env ]; then
  echo "[4/5] Creating .env from .env.example — FILL IN API KEYS BEFORE RUNNING API"
  cp .env.example .env
else
  echo "[4/5] .env exists — skipping"
fi

# 5. Runtime dirs (gitignored but required)
mkdir -p data/tracking data/games data/videos/full_games logs data/output data/predictions

echo "[5/5] Verifying prop models load..."
conda run -n basketball_ai --no-capture-output python -c "
import sys; sys.path.insert(0, '.')
from src.prediction.prop_model_stack import PropModelStack
s = PropModelStack(); s.load_models()
print('  Prop models loaded:', sorted(s.models.keys()))
"

echo ""
echo "=== Setup complete ==="
echo "  Activate:  conda activate basketball_ai"
echo "  Tests:     python -m pytest tests/ -q"
echo "  API:       uvicorn api.main:app --reload"
echo "  .env keys: NBA_API_KEY, THE_ODDS_API_KEY, CLAUDE_API_KEY, DATABASE_URL"
