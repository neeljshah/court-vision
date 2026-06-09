#!/usr/bin/env bash
# bootstrap_new_pod.sh — Set up a fresh RunPod for the NBA tracker.
#
# Run THIS script on the pod after rsync-ing the repo. It installs Python
# deps, verifies models load, and prepares /root/nba_videos/.
#
# Usage (on the pod, after `cd /workspace/nba-ai-system`):
#     bash scripts/bootstrap_new_pod.sh
#
# Side-effects:
#   - pip installs deps from requirements (or fallback list)
#   - mkdirs /root/nba_videos, data/tracking, logs
#   - tests model loading with a 1-frame dummy
#   - prints final readiness status

set -e  # exit on error

echo "===================="
echo " POD BOOTSTRAP START"
echo "===================="

REPO_DIR="${REPO_DIR:-/workspace/nba-ai-system}"
cd "$REPO_DIR"

echo
echo "[1/6] System checks"
echo "  python3: $(python3 --version)"
echo "  GPU:     $(nvidia-smi --query-gpu=name,memory.total --format=csv,noheader 2>/dev/null || echo 'no GPU detected')"
echo "  Disk:    $(df -h /root /workspace 2>/dev/null | tail -2 | head -1 | awk '{print $4}')  free on /root"

echo
echo "[2/6] Python deps (best-effort install)"
# Critical deps — if requirements.txt exists, use it; otherwise minimal list
if [ -f requirements.txt ]; then
    pip3 install -q -r requirements.txt 2>&1 | tail -5 || echo "  [warn] some pip installs failed; check manually"
else
    pip3 install -q ultralytics yt-dlp opencv-python-headless pandas numpy \
        torchreid easyocr requests 2>&1 | tail -5
fi
# Verify key packages
for pkg in torch ultralytics cv2 yt_dlp pandas numpy; do
    if python3 -c "import $pkg" 2>/dev/null; then
        echo "  [ok]   $pkg"
    else
        echo "  [MISS] $pkg — install manually!"
    fi
done

echo
echo "[3/6] Directories"
mkdir -p /root/nba_videos
mkdir -p data/tracking
mkdir -p data/cache
mkdir -p logs
echo "  /root/nba_videos: $(ls /root/nba_videos | wc -l) files"
echo "  data/tracking:    $(ls data/tracking 2>/dev/null | wc -l) games"

echo
echo "[4/6] Models + resources"
for f in resources/yolov8n.pt resources/yolov8n-pose.engine resources/2d_map.png resources/Rectify1.npy; do
    if [ -f "$f" ]; then
        echo "  [ok]   $f ($(stat -c%s "$f" 2>/dev/null || echo '?') bytes)"
    else
        echo "  [MISS] $f"
    fi
done

echo
echo "[5/6] Model load smoke test"
python3 -c "
import sys
try:
    from ultralytics import YOLO
    import numpy as np
    m = YOLO('resources/yolov8n.pt')
    r = m(np.zeros((640, 640, 3), dtype=np.uint8), verbose=False)
    print('  [ok] YOLOv8n detection model loaded')
except Exception as e:
    print(f'  [FAIL] detection load: {e}')
    sys.exit(1)

try:
    mp = YOLO('resources/yolov8n-pose.engine' if __import__('os').path.exists('resources/yolov8n-pose.engine') else 'yolov8n-pose.pt')
    rp = mp(np.zeros((640, 640, 3), dtype=np.uint8), verbose=False)
    print('  [ok] YOLOv8n-pose model loaded')
except Exception as e:
    print(f'  [warn] pose load: {e}')
    print('         (TRT engine may need rebuild on new GPU; will fall back to .pt)')
" 2>&1

echo
echo "[6/6] yt-dlp check"
python3 -c "
try:
    import yt_dlp
    print(f'  [ok] yt_dlp {yt_dlp.version.__version__}')
except ImportError:
    print('  [FAIL] yt_dlp not installed — pip3 install yt-dlp')
" 2>&1

# Cookie file check
if [ -f "data/videos/youtube_cookies.txt" ]; then
    AGE_DAYS=$(( ($(date +%s) - $(stat -c %Y data/videos/youtube_cookies.txt)) / 86400 ))
    echo "  cookies file age: ${AGE_DAYS} days"
    if [ "$AGE_DAYS" -gt 14 ]; then
        echo "  [WARN] cookies > 2 weeks old — refresh from local Chrome before downloads"
    fi
else
    echo "  [WARN] data/videos/youtube_cookies.txt missing — yt-dlp will fail bot-detection"
fi

echo
echo "===================="
echo " BOOTSTRAP COMPLETE"
echo "===================="
echo "Next step: from your LOCAL machine, run"
echo "  NBA_POD_IP=<new-pod-ip> NBA_POD_PORT=<new-pod-port> \\"
echo "    python scripts/ingest_pulse.py"
echo "to verify connectivity, then kick off the batch."
