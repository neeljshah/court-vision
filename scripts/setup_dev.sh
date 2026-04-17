#!/usr/bin/env bash
# CourtVision — dev environment setup (run once per new machine)
set -euo pipefail

echo "=== CourtVision Dev Setup ==="

# 1. Conda env
if ! conda env list | grep -q basketball_ai; then
  echo "[1/5] Creating conda env basketball_ai (Python 3.9)..."
  conda create -n basketball_ai python=3.9 -y
fi

echo "[2/5] Installing Python dependencies..."
conda run -n basketball_ai pip install -r requirements.txt

# 2. YOLO weights (public Ultralytics — tracked in git, but re-download if missing)
if [ ! -f yolov8n.pt ]; then
  echo "[3/5] Downloading yolov8n.pt..."
  conda run -n basketball_ai python -c "from ultralytics import YOLO; YOLO('yolov8n.pt')"
fi
if [ ! -f yolov8n-pose.pt ]; then
  echo "[3/5] Downloading yolov8n-pose.pt..."
  conda run -n basketball_ai python -c "from ultralytics import YOLO; YOLO('yolov8n-pose.pt')"
fi

# 3. .env
if [ ! -f .env ]; then
  echo "[4/5] Creating .env from template — fill in API keys before running the API"
  cp .env.example .env
fi

# 4. Placeholder dirs (gitignored but required at runtime)
mkdir -p data/tracking data/games data/videos/full_games logs

echo "[5/5] Verifying models load..."
conda run -n basketball_ai python -c "
import sys, os; sys.path.insert(0, '.')
from src.prediction.prop_model_stack import PropModelStack
s = PropModelStack(); s.load_models()
print('  prop models OK:', list(s.models.keys()))
"

echo ""
echo "=== Setup complete ==="
echo "Activate env:  conda activate basketball_ai"
echo "Run tests:     python -m pytest tests/ -q"
echo "Start API:     uvicorn api.main:app --reload"
echo "Fill .env with: NBA_API_KEY, THE_ODDS_API_KEY, CLAUDE_API_KEY, DATABASE_URL"
