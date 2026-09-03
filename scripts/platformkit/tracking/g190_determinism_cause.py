"""Run one isolated, route-matched detector reproducibility observation."""

from __future__ import annotations

import argparse
import hashlib
import json
import random
from pathlib import Path
from typing import Any, Mapping, Sequence

import cv2
import numpy as np

CONDITIONS: Mapping[str, Mapping[str, bool]] = {
    "A": {"benchmark": True, "seeded": False, "half": True},
    "B": {"benchmark": False, "seeded": False, "half": True},
    "C": {"benchmark": False, "seeded": True, "half": True},
    "D": {"benchmark": False, "seeded": True, "half": False},
}
DEFAULT_FRAME_INDEX = 474
ROUTE_CONFIDENCE = 0.22
ROUTE_IMAGE_SIZE = 640


def condition_comparison(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Return bit-exact status and largest aligned deltas for run records."""
    if len(records) < 2:
        raise ValueError("at least two run records are required")
    tensors = [np.asarray(record["box_tensor"], dtype=np.float32) for record in records]
    reference = tensors[0]
    exact = all(tensor.shape == reference.shape and np.array_equal(tensor, reference)
                for tensor in tensors[1:])
    coordinate_delta = 0.0
    confidence_delta = 0.0
    shape_mismatch = False
    for tensor in tensors[1:]:
        if tensor.shape != reference.shape:
            shape_mismatch = True
        rows = min(reference.shape[0], tensor.shape[0])
        cols = min(reference.shape[1], tensor.shape[1])
        if rows and cols:
            delta = np.abs(reference[:rows, :cols] - tensor[:rows, :cols])
            coordinate_delta = max(coordinate_delta, float(delta[:, :min(4, cols)].max()))
            if cols > 4:
                confidence_delta = max(confidence_delta, float(delta[:, 4].max()))
    return {
        "identical_across_runs": exact,
        "reference_run": 1,
        "run_count": len(records),
        "shape_mismatch": shape_mismatch,
        "largest_aligned_coordinate_abs_delta": coordinate_delta,
        "largest_aligned_confidence_abs_delta": confidence_delta,
    }


def _configure_torch(condition: str) -> tuple[bool, int]:
    import torch

    config = CONDITIONS[condition]
    if not torch.cuda.is_available():
        raise RuntimeError("G190 requires CUDA; do not run this observation locally")
    if config["seeded"]:
        random.seed(0)
        np.random.seed(0)
        torch.manual_seed(0)
        torch.cuda.manual_seed_all(0)
    torch.backends.cudnn.benchmark = config["benchmark"]
    return config["half"], 0


def run_once(video_path: Path, condition: str, frame_index: int) -> dict[str, Any]:
    """Decode one source frame and emit the route-matched raw detector tensor."""
    if condition not in CONDITIONS:
        raise ValueError(f"unknown condition: {condition}")
    from ultralytics import YOLO
    from src.pipeline.unified_pipeline import TOPCUT
    from src.tracking.player_detection import _best_yolo_model

    half, device = _configure_torch(condition)
    cap = cv2.VideoCapture(str(video_path))
    cap.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
    ok, frame = cap.read()
    cap.release()
    if not ok:
        raise RuntimeError(f"could not decode source frame {frame_index}")
    route_frame = frame[TOPCUT:]
    weight = _best_yolo_model("yolov8n")
    model = YOLO(weight)
    model(np.zeros((640, 640, 3), dtype=np.uint8), verbose=False, half=half, device=device)
    result = model(
        route_frame,
        classes=[0],
        conf=ROUTE_CONFIDENCE,
        verbose=False,
        imgsz=ROUTE_IMAGE_SIZE,
        half=half,
        device=device,
    )[0]
    tensor = (result.boxes.data.detach().cpu().numpy().astype(np.float32, copy=False)
              if result.boxes is not None else np.empty((0, 6), dtype=np.float32))
    return {
        "condition": condition,
        "condition_config": dict(CONDITIONS[condition]),
        "video_path": str(video_path),
        "video_bytes": video_path.stat().st_size,
        "frame_index": frame_index,
        "topcut": TOPCUT,
        "decoded_shape_bgr": list(frame.shape),
        "detector_weight": weight,
        "device": device,
        "tensor_dtype": str(tensor.dtype),
        "tensor_shape": list(tensor.shape),
        "tensor_sha256": hashlib.sha256(tensor.tobytes()).hexdigest(),
        "box_tensor": tensor.tolist(),
    }


def main() -> None:
    """Print exactly one JSON record for an isolated detector execution."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--condition", choices=sorted(CONDITIONS), required=True)
    parser.add_argument("--video", type=Path, required=True)
    parser.add_argument("--frame-index", type=int, default=DEFAULT_FRAME_INDEX)
    args = parser.parse_args()
    print(json.dumps(run_once(args.video, args.condition, args.frame_index), sort_keys=True))


if __name__ == "__main__":
    main()
