"""Fail-closed American-football screening for queue candidates.

This gate is intentionally stricter than the generic playing-surface gate.  A
green field is not sport identity: an accepted candidate needs repeated,
full-width yard-line evidence.  Ambiguous video is rejected from the football
queue and may be reviewed manually outside this producer.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import cv2
import numpy as np


_GREEN_LOW = np.array((35, 50, 35), dtype=np.uint8)
_GREEN_HIGH = np.array((95, 255, 255), dtype=np.uint8)
_MIN_GREEN_FRACTION = 0.10
_MIN_YARD_LINES = 7
_MIN_PASSING_FRAMES = 2


@dataclass(frozen=True)
class FootballFrameEvidence:
    green_fraction: float
    yard_line_count: int


@dataclass(frozen=True)
class FootballVerdict:
    decision: str
    reason: str
    frames: tuple[FootballFrameEvidence, ...]


def _green_fraction(frame: np.ndarray) -> float:
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    return float(np.mean(cv2.inRange(hsv, _GREEN_LOW, _GREEN_HIGH) > 0))


def _yard_line_count(frame: np.ndarray) -> int:
    """Count distinct long, nearly horizontal field markings in one frame."""
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    height, width = gray.shape
    edges = cv2.Canny(gray, 60, 160)
    lines = cv2.HoughLinesP(edges, 1, np.pi / 180, threshold=35,
                            minLineLength=int(width * 0.30), maxLineGap=18)
    if lines is None:
        return 0
    rows: list[int] = []
    for x1, y1, x2, y2 in lines.reshape(-1, lines.shape[-1]):
        if abs(int(y2) - int(y1)) > max(8, int(height * 0.05)):
            continue
        rows.append(int((int(y1) + int(y2)) / 2))
    rows.sort()
    separated: list[int] = []
    for row in rows:
        if not separated or row - separated[-1] >= 7:
            separated.append(row)
    return len(separated)


def inspect_frame(frame: np.ndarray) -> FootballFrameEvidence:
    """Return structural field evidence for a decoded broadcast frame."""
    resized = cv2.resize(frame, (320, 180), interpolation=cv2.INTER_AREA)
    return FootballFrameEvidence(_green_fraction(resized), _yard_line_count(resized))


def decide(evidence: Iterable[FootballFrameEvidence]) -> FootballVerdict:
    """Accept only repeated yard-line structure; all uncertainty stays out."""
    frames = tuple(evidence)
    passing = sum(
        frame.green_fraction >= _MIN_GREEN_FRACTION
        and frame.yard_line_count >= _MIN_YARD_LINES
        for frame in frames
    )
    if passing >= _MIN_PASSING_FRAMES:
        return FootballVerdict("accept", "repeated_yard_line_structure", frames)
    if not frames:
        return FootballVerdict("reject", "no_readable_sample_fail_closed", frames)
    if max(frame.green_fraction for frame in frames) < _MIN_GREEN_FRACTION:
        return FootballVerdict("reject", "no_field_surface_fail_closed", frames)
    return FootballVerdict("reject", "yard_line_structure_absent_fail_closed", frames)


def screen(video: Path, sample_count: int = 5) -> FootballVerdict:
    """Seek a small number of frames from a cheap candidate download."""
    capture = cv2.VideoCapture(str(video))
    if not capture.isOpened():
        return FootballVerdict("reject", "unreadable_sample_fail_closed", ())
    total = max(capture.get(cv2.CAP_PROP_FRAME_COUNT), 1.0)
    evidence: list[FootballFrameEvidence] = []
    for portion in np.linspace(0.10, 0.90, sample_count):
        capture.set(cv2.CAP_PROP_POS_FRAMES, float(total * portion))
        ok, frame = capture.read()
        if ok:
            evidence.append(inspect_frame(frame))
    capture.release()
    return decide(evidence)
