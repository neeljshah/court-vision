"""
ObjectDetector: YOLOv8-based player and basketball detection.

Uses YOLOv8x (largest/most accurate) with fp16 inference on GPU.
Supports both single-frame and batched inference for throughput.

Ball detections use a lower confidence threshold than players because
basketballs are small at broadcast distance and harder to detect.
"""
import os
from dataclasses import dataclass
from typing import List

import numpy as np
import torch
from ultralytics import YOLO

_COCO_TO_DOMAIN = {
    "person":      "player",
    "sports ball": "ball",
}

# Separate confidence thresholds — ball is harder to detect at broadcast distance
_CONF_PLAYER = 0.45
_CONF_BALL   = 0.20


@dataclass
class Detection:
    """Single YOLO detection result."""
    bbox:        tuple   # (x1, y1, x2, y2) pixels
    confidence:  float
    class_label: str     # 'player' or 'ball'
    cx:          float
    cy:          float


class ObjectDetector:
    """
    YOLOv8x wrapper for player and ball detection.

    Uses fp16 on GPU for speed. Supports batched inference via detect_batch()
    to maximize GPU utilization when processing many frames.
    """

    def __init__(
        self,
        weights_path: str = "yolov8x.pt",
        device: str = "cuda" if torch.cuda.is_available() else "cpu",
    ) -> None:
        if os.path.exists(weights_path):
            self._model = YOLO(weights_path)
        else:
            self._model = YOLO("yolov8x.pt")

        self._device = device
        self._model.to(self._device)

    def detect(self, frame: np.ndarray) -> List[Detection]:
        """Detect players and ball in a single frame."""
        return self.detect_batch([frame])[0]

    def detect_batch(self, frames: List[np.ndarray]) -> List[List[Detection]]:
        """
        Detect players and ball in a batch of frames simultaneously.

        Runs all frames through YOLO in a single GPU forward pass.
        Significantly faster than calling detect() N times.

        Args:
            frames: List of BGR frame arrays.

        Returns:
            List of Detection lists, one per input frame.
        """
        if not frames:
            return []

        # Run all frames in one forward pass
        # conf=0 here — we apply per-class thresholds below
        results = self._model(
            frames,
            verbose=False,
            conf=_CONF_BALL,   # use the lower threshold; filter players separately
            half=(self._device == "cuda"),
            stream=False,
        )

        all_detections: List[List[Detection]] = []

        for result in results:
            frame_dets: List[Detection] = []
            boxes = result.boxes
            if boxes is not None:
                for box in boxes:
                    class_idx = int(box.cls[0].item())
                    class_name = self._model.names[class_idx]
                    domain = _COCO_TO_DOMAIN.get(class_name)
                    if domain is None:
                        continue

                    conf = float(box.conf[0].item())

                    # Apply per-class confidence filtering
                    threshold = _CONF_BALL if domain == "ball" else _CONF_PLAYER
                    if conf < threshold:
                        continue

                    x1, y1, x2, y2 = box.xyxy[0].tolist()
                    cx = (x1 + x2) / 2.0
                    cy = (y1 + y2) / 2.0

                    frame_dets.append(Detection(
                        bbox=(x1, y1, x2, y2),
                        confidence=conf,
                        class_label=domain,
                        cx=cx,
                        cy=cy,
                    ))

            all_detections.append(frame_dets)

        return all_detections
