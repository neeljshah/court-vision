"""License-clean detection seam for commercial CourtVision builds.

Replace AGPL Ultralytics detection with Apache-2.0 YOLOX, or our own trained
weights, without changing callers before commercial sale.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import numpy as np

_INPUT_SIZE = 640
_STRIDES = (8, 16, 32)
_COCO_PERSON = 0


@dataclass(frozen=True)
class Detection:
    x1: float
    y1: float
    x2: float
    y2: float
    conf: float
    cls_name: str


class DetectorBackend(Protocol):
    license: str

    def detect(self, frame_bgr: np.ndarray) -> list[Detection]:
        """Return detections for one BGR image."""


def _grids_and_strides(input_size: int = _INPUT_SIZE) -> tuple[np.ndarray, np.ndarray]:
    grids, strides = [], []
    for stride in _STRIDES:
        height = width = input_size // stride
        y, x = np.meshgrid(np.arange(height), np.arange(width), indexing="ij")
        grids.append(np.stack((x, y), axis=-1).reshape(-1, 2))
        strides.append(np.full((height * width, 1), stride, dtype=np.float32))
    return np.concatenate(grids).astype(np.float32), np.concatenate(strides)


def _decode_yolox(predictions: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Decode raw YOLOX output into xyxy boxes, confidence, and COCO class ids."""
    output = np.asarray(predictions, dtype=np.float32)
    if output.ndim == 3:
        output = output[0]
    if output.ndim != 2 or output.shape[1] < 6:
        raise ValueError("YOLOX output must have shape (anchors, 5 + classes)")
    grids, strides = _grids_and_strides()
    if len(output) != len(grids):
        raise ValueError(f"expected {len(grids)} YOLOX anchors, got {len(output)}")
    center = (output[:, :2] + grids) * strides
    size = np.exp(np.clip(output[:, 2:4], -20.0, 20.0)) * strides
    boxes = np.concatenate((center - size / 2, center + size / 2), axis=1)
    classes = output[:, 5:].argmax(axis=1)
    scores = output[:, 4] * output[:, 5:].max(axis=1)
    return boxes, scores, classes


def _nms(boxes: np.ndarray, scores: np.ndarray, iou_threshold: float = 0.45) -> np.ndarray:
    """Return kept indices using class-agnostic greedy IoU NMS."""
    if not len(boxes):
        return np.empty(0, dtype=np.int64)
    order = scores.argsort()[::-1]
    keep: list[int] = []
    while len(order):
        index = int(order[0])
        keep.append(index)
        rest = order[1:]
        if not len(rest):
            break
        xx1 = np.maximum(boxes[index, 0], boxes[rest, 0])
        yy1 = np.maximum(boxes[index, 1], boxes[rest, 1])
        xx2 = np.minimum(boxes[index, 2], boxes[rest, 2])
        yy2 = np.minimum(boxes[index, 3], boxes[rest, 3])
        intersection = np.maximum(0, xx2 - xx1) * np.maximum(0, yy2 - yy1)
        area_current = (boxes[index, 2] - boxes[index, 0]) * (boxes[index, 3] - boxes[index, 1])
        area_rest = (boxes[rest, 2] - boxes[rest, 0]) * (boxes[rest, 3] - boxes[rest, 1])
        iou = intersection / np.maximum(area_current + area_rest - intersection, 1e-12)
        order = rest[iou <= iou_threshold]
    return np.asarray(keep, dtype=np.int64)


class UltralyticsYoloBackend:
    """AGPL wrapper retained only for non-commercial-compatible deployments."""

    license = "AGPL-3.0"

    def __init__(self, model_path: str | Path | None = None) -> None:
        try:
            from ultralytics import YOLO
        except ImportError as error:
            raise ImportError(
                "UltralyticsYoloBackend needs ultralytics. Install it, or set "
                "CV_DETECTOR=yolox with an Apache-2.0 YOLOX ONNX model."
            ) from error
        self._model = YOLO(str(model_path or "yolov8n.pt"))

    def detect(self, frame_bgr: np.ndarray) -> list[Detection]:
        result = self._model(frame_bgr, verbose=False)[0]
        names = result.names
        detections = []
        for box in result.boxes:
            x1, y1, x2, y2 = box.xyxy[0].tolist()
            cls_id = int(box.cls[0])
            detections.append(Detection(x1, y1, x2, y2, float(box.conf[0]), str(names[cls_id])))
        return detections


class YoloxOnnxBackend:
    """Apache-2.0 ONNX YOLOX person detector with numpy decoding and NMS."""

    license = "Apache-2.0"

    def __init__(self, model_path: str | Path) -> None:
        if model_path is None:
            raise ValueError("YoloxOnnxBackend requires model_path to an ONNX model")
        try:
            import onnxruntime as ort
        except ImportError as error:
            raise ImportError("YoloxOnnxBackend needs onnxruntime; install onnxruntime to use YOLOX ONNX.") from error
        self._session = ort.InferenceSession(str(model_path), providers=["CPUExecutionProvider"])
        self._input_name = self._session.get_inputs()[0].name

    @staticmethod
    def _preprocess(frame_bgr: np.ndarray) -> tuple[np.ndarray, float]:
        try:
            import cv2
        except ImportError as error:
            raise ImportError("YoloxOnnxBackend needs opencv-python for YOLOX letterbox resizing.") from error
        height, width = frame_bgr.shape[:2]
        scale = min(_INPUT_SIZE / height, _INPUT_SIZE / width)
        resized = cv2.resize(frame_bgr, (round(width * scale), round(height * scale)), interpolation=cv2.INTER_LINEAR)
        canvas = np.full((_INPUT_SIZE, _INPUT_SIZE, 3), 114, dtype=np.uint8)
        canvas[: resized.shape[0], : resized.shape[1]] = resized
        return np.ascontiguousarray(canvas.transpose(2, 0, 1)[None], dtype=np.float32), scale

    def detect(self, frame_bgr: np.ndarray) -> list[Detection]:
        tensor, scale = self._preprocess(frame_bgr)
        output = self._session.run(None, {self._input_name: tensor})[0]
        boxes, scores, classes = _decode_yolox(output)
        person = (classes == _COCO_PERSON) & (scores >= 0.25)
        boxes, scores = boxes[person] / scale, scores[person]
        return [Detection(*boxes[i], float(scores[i]), "person") for i in _nms(boxes, scores)]


def get_detector(name: str | None = None, model_path: str | Path | None = None) -> DetectorBackend:
    """Build the configured detector; defaults to ``CV_DETECTOR=ultralytics``."""
    selected = (name or os.environ.get("CV_DETECTOR", "ultralytics")).lower()
    if selected == "ultralytics":
        return UltralyticsYoloBackend(model_path)
    if selected in {"yolox", "yolox_onnx"}:
        return YoloxOnnxBackend(model_path)
    raise ValueError(f"unknown detector backend {selected!r}; expected 'ultralytics' or 'yolox'")
