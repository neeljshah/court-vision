"""Catcher glove-target versus pitch-crossing command measurements.

This remains a calibration-stage heuristic: it emits nothing when a target or
crossing cannot be established confidently.
"""
from __future__ import annotations

import statistics
from collections import deque
from dataclasses import dataclass
from typing import Mapping, Optional, Protocol, Sequence

import cv2
import numpy as np
import pandas as pd


Detection = tuple[float, float, float]
SERIES_SCHEMA = ("pitch", "inning", "miss_ft", "horizontal_ft", "vertical_ft", "inning_median_ft")
CATCHER_REGION = (0.30, 0.55, 0.70, 0.95)


class GloveDetector(Protocol):
    """Locate a catcher glove target in a frame."""

    def detect(self, frame: np.ndarray) -> Optional[Detection]:
        """Return ``(px, py, confidence)`` or None."""


@dataclass(frozen=True)
class CommandMiss:
    """Signed pitch miss relative to the catcher target, measured in feet."""

    horizontal_ft: float
    vertical_ft: float
    miss_ft: float


def _gray(frame: np.ndarray) -> np.ndarray:
    return frame if frame.ndim == 2 else cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)


def pre_pitch_window(frames: Sequence[np.ndarray], motion_threshold: float = 3.0) -> list[int]:
    """Return leading low-motion frame indices for a pitch segment."""
    if not frames:
        return []
    grays = [_gray(frame).astype(np.int16) for frame in frames]
    window = [0]
    for index in range(1, len(grays)):
        if float(np.mean(np.abs(grays[index] - grays[index - 1]))) > motion_threshold:
            break
        window.append(index)
    return window


class MotionStableDetector:
    """Fail-quiet detector for a small, stable, high-contrast catcher blob."""

    def __init__(self, region: tuple[float, float, float, float] = CATCHER_REGION,
                 buffer_frames: int = 5, min_frames: int = 3, contrast: float = 40.0,
                 min_area_fraction: float = 0.0005, max_area_fraction: float = 0.05,
                 stable_px: float = 4.0, separation_px: float = 3.0,
                 min_confidence: float = 0.5) -> None:
        self.region, self.min_frames, self.contrast = region, max(2, min_frames), contrast
        self.min_area_fraction, self.max_area_fraction = min_area_fraction, max_area_fraction
        self.stable_px, self.separation_px, self.min_confidence = stable_px, separation_px, min_confidence
        self._buffer: deque[list[np.ndarray]] = deque(maxlen=max(buffer_frames, self.min_frames))

    def reset(self) -> None:
        self._buffer.clear()

    def candidates(self, frame: np.ndarray) -> list[np.ndarray]:
        height, width = frame.shape[:2]
        left, top, right, bottom = self.region
        x0, x1, y0, y1 = int(left * width), int(right * width), int(top * height), int(bottom * height)
        roi = _gray(frame)[y0:y1, x0:x1].astype(np.int16)
        if roi.size == 0:
            return []
        mask = (np.abs(roi - float(np.median(roi))) > self.contrast).astype(np.uint8) * 255
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
        count, _, stats, centers = cv2.connectedComponentsWithStats(mask)
        area = float(roi.size)
        return [centers[index].astype(np.float32) + np.array((x0, y0), dtype=np.float32)
                for index in range(1, count)
                if self.min_area_fraction * area <= float(stats[index, cv2.CC_STAT_AREA]) <= self.max_area_fraction * area]

    def detect(self, frame: np.ndarray) -> Optional[Detection]:
        latest, prior = self.candidates(frame), [items for items in self._buffer if items]
        seen = len(self._buffer) + 1
        self._buffer.append(latest)
        if not latest or seen < self.min_frames or not prior:
            return None
        scored = sorted((self._drift(point, prior), index, point)
                        for index, point in enumerate(latest))
        score, _, point = scored[0]
        if len(scored) > 1 and scored[1][0] - score < self.separation_px:
            return None
        confidence = max(0.0, 1.0 - score / self.stable_px)
        return None if confidence < self.min_confidence else (float(point[0]), float(point[1]), confidence)

    @staticmethod
    def _drift(point: np.ndarray, prior: Sequence[Sequence[np.ndarray]]) -> float:
        return float(np.mean([min(float(np.linalg.norm(point - other)) for other in items) for items in prior]))


def glove_target(frames: Sequence[np.ndarray], detector: GloveDetector,
                 motion_threshold: float = 3.0) -> Optional[Detection]:
    """Return the last confident pre-pitch glove target, if any."""
    reset = getattr(detector, "reset", None)
    if callable(reset):
        reset()
    found: Optional[Detection] = None
    for index in pre_pitch_window(frames, motion_threshold):
        detection = detector.detect(frames[index])
        if detection is not None:
            found = detection
    return found


def target_vs_actual(target_px: Sequence[float], crossing_px: Sequence[float],
                     scale_px_per_ft: float) -> CommandMiss:
    """Return the signed target-to-crossing miss in plate-relative feet."""
    if scale_px_per_ft <= 0.0:
        raise ValueError("scale_px_per_ft must be positive")
    horizontal = (float(crossing_px[0]) - float(target_px[0])) / scale_px_per_ft
    vertical = (float(target_px[1]) - float(crossing_px[1])) / scale_px_per_ft
    return CommandMiss(horizontal, vertical, float(np.hypot(horizontal, vertical)))


def command_series(events: Sequence[Mapping[str, object]]) -> pd.DataFrame:
    """Return per-pitch misses and a running per-inning median."""
    running: dict[object, list[float]] = {}
    rows: list[dict[str, object]] = []
    for pitch, event in enumerate(events):
        target, crossing, scale = event.get("target_px"), event.get("crossing_px"), event.get("scale_px_per_ft")
        if target is None or crossing is None or not isinstance(scale, (int, float)) or scale <= 0.0:
            continue
        miss = target_vs_actual(target, crossing, float(scale))  # type: ignore[arg-type]
        inning = event.get("inning")
        running.setdefault(inning, []).append(miss.miss_ft)
        rows.append({"pitch": pitch, "inning": inning, "miss_ft": miss.miss_ft,
                     "horizontal_ft": miss.horizontal_ft, "vertical_ft": miss.vertical_ft,
                     "inning_median_ft": statistics.median(running[inning])})
    return pd.DataFrame(rows, columns=list(SERIES_SCHEMA))
