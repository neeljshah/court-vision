"""
train_ball_yolo.py — Fine-tune YOLOv8n on basketball detection labels.

Starts from yolov8n.pt (transfer learning) and trains on data/ball_yolo/.
Saves to models/weights/yolov8n_ball.pt.

Run label_ball_yolo.py first to generate the training data.

Usage:
    conda activate basketball_ai
    python scripts/train_ball_yolo.py

After training, run export_tensorrt.py to convert to TRT engine.
"""

from __future__ import annotations

import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)

DATASET_YAML = os.path.join(ROOT, "data", "ball_yolo", "dataset.yaml")
OUT_WEIGHTS  = os.path.join(ROOT, "models", "weights")
os.makedirs(OUT_WEIGHTS, exist_ok=True)


def main() -> None:
    if not os.path.exists(DATASET_YAML):
        print(f"ERROR: {DATASET_YAML} not found.")
        print("Run scripts/label_ball_yolo.py first to generate training data.")
        sys.exit(1)

    try:
        from ultralytics import YOLO  # type: ignore
    except ImportError:
        print("ERROR: ultralytics not installed. Run: pip install ultralytics")
        sys.exit(1)

    print("=== YOLOv8n ball detection fine-tune ===")
    print(f"  Dataset:   {DATASET_YAML}")
    print(f"  Weights:   {OUT_WEIGHTS}/yolov8n_ball.pt")

    model = YOLO("yolov8n.pt")

    results = model.train(
        data=DATASET_YAML,
        epochs=30,
        imgsz=480,
        batch=16,
        device=0,          # GPU
        name="yolov8n_ball",
        project=os.path.join(ROOT, "models", "runs"),
        exist_ok=True,
        pretrained=True,   # use imagenet weights
        lr0=0.01,
        patience=5,        # early stop after 5 non-improving epochs
        save=True,
        verbose=True,
    )

    # Copy best weights to OUT_WEIGHTS
    best = os.path.join(ROOT, "models", "runs", "yolov8n_ball", "weights", "best.pt")
    if os.path.exists(best):
        import shutil
        dest = os.path.join(OUT_WEIGHTS, "yolov8n_ball.pt")
        shutil.copy(best, dest)
        print(f"\n✓ Best weights saved: {dest}")
        print("Run scripts/export_tensorrt.py to export to TRT engine.")
    else:
        print(f"\nWARNING: best.pt not found at {best}")

    return results


if __name__ == "__main__":
    main()
