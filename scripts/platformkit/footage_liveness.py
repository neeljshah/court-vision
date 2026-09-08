"""Temporal liveness measurements for an already-downloaded video section."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np


SAMPLE_COUNT = 60
NEAR_IDENTICAL_DELTA = 1.0
FROZEN_SHARE = 0.90
LOW_BYTES_PER_FRAME = 2000.0
HIGH_RES_HEIGHT = 720


@dataclass(frozen=True)
class LivenessMetrics:
    """Reported temporal and container cues; verdict is informational by default."""

    sample_indices: list[int]
    valid_frames: int
    frame_count: int
    width: int
    height: int
    bytes_per_frame: float
    mean_abs_delta: float
    near_identical_share: float
    verdict: str


def measure_liveness(video: Path, sample_count: int = SAMPLE_COUNT) -> LivenessMetrics:
    """Sample evenly over a clip and report independent frozen-video cues."""
    capture = cv2.VideoCapture(str(video))
    if not capture.isOpened():
        raise ValueError("unreadable video: %s" % video)
    frame_count = max(0, int(capture.get(cv2.CAP_PROP_FRAME_COUNT)))
    width = max(0, int(capture.get(cv2.CAP_PROP_FRAME_WIDTH)))
    height = max(0, int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT)))
    if frame_count < 2:
        capture.release()
        raise ValueError("insufficient frames for liveness: %s" % video)
    indices = np.linspace(0, frame_count - 1, sample_count, dtype=int).tolist()
    frames: list[np.ndarray] = []
    valid_indices: list[int] = []
    for index in indices:
        capture.set(cv2.CAP_PROP_POS_FRAMES, index)
        ok, frame = capture.read()
        if not ok:
            continue
        resized = cv2.resize(frame, (320, 180), interpolation=cv2.INTER_AREA)
        frames.append(cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY))
        valid_indices.append(index)
    capture.release()
    if len(frames) < 2:
        raise ValueError("insufficient decoded frames for liveness: %s" % video)
    deltas = [float(cv2.absdiff(left, right).mean())
              for left, right in zip(frames, frames[1:])]
    mean_delta = float(np.mean(deltas))
    near_share = float(np.mean(np.asarray(deltas) < NEAR_IDENTICAL_DELTA))
    bytes_per_frame = video.stat().st_size / frame_count
    frozen_by_delta = near_share >= FROZEN_SHARE
    frozen_by_bytes = bytes_per_frame < LOW_BYTES_PER_FRAME and height >= HIGH_RES_HEIGHT
    return LivenessMetrics(
        sample_indices=valid_indices,
        valid_frames=len(frames),
        frame_count=frame_count,
        width=width,
        height=height,
        bytes_per_frame=bytes_per_frame,
        mean_abs_delta=mean_delta,
        near_identical_share=near_share,
        verdict="FROZEN" if frozen_by_delta or frozen_by_bytes else "LIVE",
    )
