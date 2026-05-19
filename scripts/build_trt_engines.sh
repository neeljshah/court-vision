#!/bin/bash
# build_trt_engines.sh — Build TensorRT engines for the pod's specific GPU + CUDA.
#
# TRT engines are GPU+CUDA+TRT-version specific. The shipped .engine files in
# resources/ were built for the original dev GPU (RTX 4060 + CUDA 11.8) and
# won't load on different hardware.
#
# This rebuilds them on the pod for ~3× faster YOLO inference (vs .pt).
# Takes ~5-15 min per engine depending on GPU.
#
# Usage: bash scripts/build_trt_engines.sh

set -euo pipefail
PROJ=/workspace/nba-ai-system
cd "$PROJ"

mkdir -p resources

build_engine() {
    local pt_path="$1"
    local engine_path="$2"
    local input_size="${3:-640}"

    if [ ! -f "$pt_path" ]; then
        echo "  [SKIP] $pt_path not found"
        return
    fi
    if [ -f "$engine_path" ]; then
        echo "  [EXISTS] $engine_path"
        return
    fi

    echo "  Building: $pt_path → $engine_path (imgsz=$input_size)"
    # dynamic=True + batch=16 — code calls YOLO with batches of 1-16 frames
    # (16-frame prefetch deque in advanced_tracker.py). dynamic=False forces
    # batch=1 and crashes with "input size [N, ...] not equal to max model size".
    python3 -c "
from ultralytics import YOLO
import os
os.environ['YOLO_CONFIG_DIR'] = '/tmp/Ultralytics'
m = YOLO('$pt_path')
m.export(format='engine', imgsz=$input_size, half=True, dynamic=True, batch=16, verbose=False)
"
    # Ultralytics writes engine next to .pt — move to resources/
    local src_engine="${pt_path%.pt}.engine"
    if [ -f "$src_engine" ] && [ "$src_engine" != "$engine_path" ]; then
        mv "$src_engine" "$engine_path"
    fi
    [ -f "$engine_path" ] && echo "  [OK] $engine_path ($(du -h "$engine_path" | cut -f1))"
}

echo "=== Building TRT engines for $(nvidia-smi --query-gpu=name --format=csv,noheader | head -1) ==="
build_engine "models/weights/yolov8n.pt"      "resources/yolov8n.engine"      640
build_engine "models/weights/yolov8n_ball.pt" "resources/yolov8n_ball.engine" 384
# Pose model (downloaded by ultralytics on first run)
if [ -f "yolov8n-pose.pt" ]; then
    build_engine "yolov8n-pose.pt" "resources/yolov8n-pose.engine" 640
fi

echo ""
echo "Built engines:"
ls -lh resources/*.engine 2>/dev/null
