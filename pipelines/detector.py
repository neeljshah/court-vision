"""
ObjectDetector: YOLOv8-based player and basketball detection.

Uses ultralytics YOLOv8 to detect objects in NBA video frames.
Filters COCO class results to 'person' (mapped to 'player') and
'sports ball' (mapped to 'ball') — the two classes relevant to tracking.

Note: Standard COCO-trained YOLOv8 has imperfect basketball detection at
broadcast distance. This is acceptable for Phase 1 — the tracker (plan 01-04)
handles temporal consistency. Fine-tuning for NBA-specific detection is out of
scope for Phase 1.
"""
import os
from dataclasses import dataclass
from typing import List

import numpy as np
import torch
from ultralytics import YOLO


# COCO class names mapped to domain labels
_COCO_TO_DOMAIN = {
    "person": "player",
    "sports ball": "ball",
}


@dataclass
class Detection:
    """A single object detection result from ObjectDetector."""
    bbox: tuple  # (x1, y1, x2, y2) in pixel coordinates
    confidence: float
    class_label: str  # 'player' or 'ball'
    cx: float  # center x = (x1 + x2) / 2
    cy: float  # center y = (y1 + y2) / 2


class ObjectDetector:
    """Wraps YOLOv8 to detect players and basketballs in video frames."""

    def __init__(
        self,
        weights_path: str,
        conf_threshold: float = 0.5,
        device: str = "cuda" if torch.cuda.is_available() else "cpu",
    ) -> None:
        """
        Initialize the detector.

        Args:
            weights_path: Path to YOLOv8 .pt weights file.
                          If the file does not exist, falls back to yolov8n.pt
                          (downloaded automatically by ultralytics on first use).
            conf_threshold: Minimum confidence for a detection to be returned.
            device: Inference device ('cuda' or 'cpu').
        """
        self._conf_threshold = conf_threshold
        self._device = device

        if os.path.exists(weights_path):
            self._model = YOLO(weights_path)
        else:
            # Fallback: use pretrained yolov8n from ultralytics auto-download
            self._model = YOLO("yolov8n.pt")

        self._model.to(self._device)

    def detect(self, frame: np.ndarray) -> List[Detection]:
        """
        Run detection on a single frame.

        Args:
            frame: BGR image array (H x W x 3) as returned by cv2.

        Returns:
            List of Detection objects filtered to 'player' and 'ball' classes only.
            Returns empty list if no relevant objects detected.
        """
        results = self._model(frame, verbose=False, conf=self._conf_threshold)
        detections: List[Detection] = []

        for result in results:
            boxes = result.boxes
            if boxes is None:
                continue
            for box in boxes:
                class_idx = int(box.cls[0].item())
                class_name = self._model.names[class_idx]
                domain_label = _COCO_TO_DOMAIN.get(class_name)
                if domain_label is None:
                    # Not a class we care about (not player or ball)
                    continue

                x1, y1, x2, y2 = box.xyxy[0].tolist()
                confidence = float(box.conf[0].item())
                cx = (x1 + x2) / 2.0
                cy = (y1 + y2) / 2.0

                detections.append(
                    Detection(
                        bbox=(x1, y1, x2, y2),
                        confidence=confidence,
                        class_label=domain_label,
                        cx=cx,
                        cy=cy,
                    )
                )

        return detections
