"""Catcher glove-target versus actual pitch crossing location (command meter).

This is the CV-unique baseball signal: no public feed publishes the catcher
PRE-PITCH glove target, so the miss distance between where the catcher set up
and where the pitch actually crossed can only come from pixels.

HONESTY NOTE (v1): ``MotionStableDetector`` is a heuristic blob detector.  It has
NOT been validated against any glove-position ground truth -- no labelled set of
catcher targets exists in this repo, so its accuracy, bias, and false-positive
rate are all UNKNOWN.  It is deliberately fail-quiet: when the pre-pitch window
is too short, no small stable blob is present, or two blobs are equally stable,
it emits nothing rather than guessing.  Downstream, ``command_series`` simply
drops pitches with no target.  Treat every number here as a calibration-stage
measurement, never as a validated command metric.

Coordinate convention follows ``adapter.py``: image pixels in, feet out, with
horizontal positive toward increasing image x and vertical positive UPWARD
(image y decreasing), matching ``BaseballAdapter._project``.
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
SERIES_SCHEMA = (
    "pitch", "inning", "miss_ft", "horizontal_ft", "vertical_ft", "inning_median_ft",
)
# Lower-center quadrant (left, top, right, bottom), normalized: where the
# catcher glove sits in a center-field pitch view. ponytail: fixed box, not a
# catcher detection -- upgrade to a person-box ROI when a validated one exists.
CATCHER_REGION = (0.30, 0.55, 0.70, 0.95)


class GloveDetector(Protocol):
    """Anything that can locate a glove target in one frame."""

    def detect(self, frame: np.ndarray) -> Optional[Detection]:
        """Return ``(px, py, confidence)`` or None when not confidently found."""


@dataclass(frozen=True)
class CommandMiss:
    """Signed miss of a pitch relative to the catcher set-up target, in feet."""

    horizontal_ft: float
    vertical_ft: float
    miss_ft: float


def _gray(frame: np.ndarray) -> np.ndarray:
    return frame if frame.ndim == 2 else cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)


def frame_motion(frames: Sequence[np.ndarray]) -> list[float]:
    """Mean absolute inter-frame gray-level change; the first entry is 0."""
    grays = [_gray(frame).astype(np.int16) for frame in frames]
    return [0.0] + [
        float(np.mean(np.abs(grays[index] - grays[index - 1])))
        for index in range(1, len(grays))
    ]


def pre_pitch_window(
    frames: Sequence[np.ndarray], motion_threshold: float = 3.0
) -> list[int]:
    """Indices of the leading low-motion frames, i.e. before the pitcher releases.

    Low overall motion is a PROXY for "not yet released" -- it also stays true
    during a timeout, a mound visit, or a still broadcast graphic.  The window
    ends at the first frame whose mean gray-level change exceeds the threshold.
    ponytail: absolute threshold, tuned per broadcast; swap for a pitcher-arm
    motion gate if a validated pose detector lands.
    """
    window: list[int] = []
    for index, motion in enumerate(frame_motion(frames)):
        if motion > motion_threshold:
            break
        window.append(index)
    return window


class MotionStableDetector:
    """v1 heuristic: the most positionally stable small high-contrast blob.

    Keeps a rolling buffer of per-frame blob candidates from the catcher region
    and scores each candidate in the newest frame by its mean distance to the
    nearest candidate in each buffered frame.  Returns None when the buffer is
    too short, when nothing scores stably enough, or when two candidates are
    near-equally stable (an ambiguous frame).  UNVALIDATED against ground truth.
    """

    def __init__(
        self,
        region: tuple[float, float, float, float] = CATCHER_REGION,
        buffer_frames: int = 5,
        min_frames: int = 3,
        contrast: float = 40.0,
        min_area_fraction: float = 0.0005,
        max_area_fraction: float = 0.05,
        stable_px: float = 4.0,
        separation_px: float = 3.0,
        min_confidence: float = 0.5,
    ) -> None:
        self.region = region
        self.min_frames = max(2, min_frames)
        self.contrast = contrast
        self.min_area_fraction = min_area_fraction
        self.max_area_fraction = max_area_fraction
        self.stable_px = stable_px
        self.separation_px = separation_px
        self.min_confidence = min_confidence
        self._buffer: deque[list[np.ndarray]] = deque(
            maxlen=max(buffer_frames, self.min_frames)
        )

    def reset(self) -> None:
        """Drop buffered frames; call between pitches."""
        self._buffer.clear()

    def candidates(self, frame: np.ndarray) -> list[np.ndarray]:
        """Centroids of small high-contrast blobs inside the catcher region."""
        height, width = frame.shape[:2]
        left, top, right, bottom = self.region
        x0, x1 = int(left * width), int(right * width)
        y0, y1 = int(top * height), int(bottom * height)
        if x1 - x0 < 3 or y1 - y0 < 3:
            return []
        roi = _gray(frame)[y0:y1, x0:x1].astype(np.int16)
        median = float(np.median(roi))
        mask = (np.abs(roi - median) > self.contrast).astype(np.uint8) * 255
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
        count, _, stats, centers = cv2.connectedComponentsWithStats(mask)
        area = float(roi.size)
        return [
            centers[index].astype(np.float32) + np.array((x0, y0), dtype=np.float32)
            for index in range(1, count)
            if self.min_area_fraction * area
            <= float(stats[index, cv2.CC_STAT_AREA])
            <= self.max_area_fraction * area
        ]

    def detect(self, frame: np.ndarray) -> Optional[Detection]:
        """Return the stable glove-target candidate, or None when unconfident."""
        latest = self.candidates(frame)
        prior = [frames for frames in self._buffer if frames]
        seen = len(self._buffer) + 1
        self._buffer.append(latest)
        if not latest or seen < self.min_frames or not prior:
            return None
        scored = sorted(
            (self._drift(point, prior), index, point)
            for index, point in enumerate(latest)
        )
        best_score, _, best_point = scored[0]
        if len(scored) > 1 and scored[1][0] - best_score < self.separation_px:
            return None
        confidence = max(0.0, 1.0 - best_score / self.stable_px)
        if confidence < self.min_confidence:
            return None
        return float(best_point[0]), float(best_point[1]), float(confidence)

    @staticmethod
    def _drift(point: np.ndarray, prior: Sequence[Sequence[np.ndarray]]) -> float:
        """Mean distance from a point to the nearest candidate in each past frame."""
        return float(np.mean([
            min(float(np.linalg.norm(point - other)) for other in frames)
            for frames in prior
        ]))


def glove_target(
    frames: Sequence[np.ndarray],
    detector: GloveDetector,
    motion_threshold: float = 3.0,
) -> Optional[Detection]:
    """Best glove target from the pre-pitch window of a single pitch clip.

    Feeds only the low-motion leading frames to the detector and keeps the last
    confident detection (the one closest to release).  Returns None when the
    window is too short or the detector never fires.
    """
    window = pre_pitch_window(frames, motion_threshold)
    reset = getattr(detector, "reset", None)
    if callable(reset):
        reset()
    found: Optional[Detection] = None
    for index in window:
        detection = detector.detect(frames[index])
        if detection is not None:
            found = detection
    return found


def target_vs_actual(
    target_px: Sequence[float],
    crossing_px: Sequence[float],
    scale_px_per_ft: float,
) -> CommandMiss:
    """Miss of the actual crossing point from the glove target, in feet.

    ``horizontal_ft`` is positive when the pitch crossed to the image-right of
    the target; ``vertical_ft`` is positive when it crossed ABOVE the target.
    """
    if not scale_px_per_ft > 0.0:
        raise ValueError("scale_px_per_ft must be positive")
    horizontal = (float(crossing_px[0]) - float(target_px[0])) / scale_px_per_ft
    vertical = (float(target_px[1]) - float(crossing_px[1])) / scale_px_per_ft
    return CommandMiss(horizontal, vertical, float(np.hypot(horizontal, vertical)))


def command_series(events: Sequence[Mapping[str, object]]) -> pd.DataFrame:
    """Per-pitch miss distances plus a running per-inning median (command decay).

    Each event needs ``inning``, ``target_px``, ``crossing_px`` and
    ``scale_px_per_ft``.  Events with a missing target or crossing are dropped,
    so a pitch whose glove was never confidently found contributes nothing.
    ``inning_median_ft`` is the median of every emitted miss so far in that
    inning; it resets each inning, so a rising trace within an inning is the
    command-decay read.  Pitches are ordered as supplied -- callers must pass
    them in pitch order, and only pitches already thrown (never a same-pitch
    outcome) may condition a downstream forecast.
    """
    running: dict[object, list[float]] = {}
    rows: list[dict[str, object]] = []
    for pitch, event in enumerate(events):
        target = event.get("target_px")
        crossing = event.get("crossing_px")
        scale = event.get("scale_px_per_ft")
        if target is None or crossing is None or not isinstance(scale, (int, float)):
            continue
        if not float(scale) > 0.0:
            continue
        miss = target_vs_actual(target, crossing, float(scale))  # type: ignore[arg-type]
        inning = event.get("inning")
        running.setdefault(inning, []).append(miss.miss_ft)
        rows.append({
            "pitch": pitch,
            "inning": inning,
            "miss_ft": miss.miss_ft,
            "horizontal_ft": miss.horizontal_ft,
            "vertical_ft": miss.vertical_ft,
            "inning_median_ft": statistics.median(running[inning]),
        })
    return pd.DataFrame(rows, columns=list(SERIES_SCHEMA))
