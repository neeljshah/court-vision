"""Pitch-view broadcast segmentation for soccer tracking."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, Union

import cv2
import numpy as np

from domains.tennis.tracking.segmenter import detect_cut, small_gray


PITCH_FRACTION_THRESHOLD = 0.35
MIN_PITCH_SEGMENT_FRAMES = 60


@dataclass(frozen=True)
class PitchSegment:
    """Inclusive source-frame interval judged safe for pitch calibration."""

    start_frame: int
    end_frame: int


def pitch_fraction(frame: np.ndarray) -> float:
    """Return the fraction covered by the adapter's largest green pitch mask."""
    from domains.soccer.tracking.adapter import SoccerAdapter

    return float(np.count_nonzero(SoccerAdapter._pitch_mask(frame)) / np.prod(frame.shape[:2]))


def is_pitch_view(frame: np.ndarray) -> bool:
    """Return whether green-pitch coverage is sufficient for homography work."""
    return pitch_fraction(frame) > PITCH_FRACTION_THRESHOLD


def segment_frames(
    frames: Iterable[np.ndarray], stride: int = 1, min_frames: int = MIN_PITCH_SEGMENT_FRAMES,
) -> list[PitchSegment]:
    """Return durable pitch-view intervals, splitting at cuts or view changes."""
    if stride < 1 or min_frames < 1:
        raise ValueError("stride and min_frames must be at least 1")
    segments: list[PitchSegment] = []
    previous_gray: np.ndarray | None = None
    start = 0
    previous_index = -1
    previous_view: bool | None = None
    for index, frame in enumerate(frames):
        frame_index = index * stride
        view = is_pitch_view(frame)
        gray = small_gray(frame)
        cut = previous_gray is not None and detect_cut(previous_gray, gray)
        if previous_view is not None and (cut or view != previous_view):
            if previous_view and previous_index - start + stride >= min_frames:
                segments.append(PitchSegment(start, previous_index))
            start = frame_index
        previous_gray, previous_index, previous_view = gray, frame_index, view
    if previous_view and previous_index - start + stride >= min_frames:
        segments.append(PitchSegment(start, previous_index))
    return segments


def segment_video(path: Union[str, Path], stride: int = 1, min_frames: int = MIN_PITCH_SEGMENT_FRAMES) -> list[PitchSegment]:
    """Read a video headlessly and return its durable pitch-view intervals."""
    capture = cv2.VideoCapture(str(path))
    if not capture.isOpened():
        raise FileNotFoundError("Could not open video: %s" % path)
    frames: list[np.ndarray] = []
    try:
        while True:
            ok, frame = capture.read()
            if not ok:
                break
            frames.append(frame)
    finally:
        capture.release()
    return segment_frames(frames[::stride], stride=stride, min_frames=min_frames)


def segments_to_json(segments: Iterable[PitchSegment], path: Union[str, Path]) -> None:
    """Write pitch-view intervals as a portable JSON list."""
    Path(path).write_text(json.dumps([asdict(segment) for segment in segments], indent=2), encoding="utf-8")
