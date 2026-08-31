"""Conservative v1 ball-detection seam for fixed-camera tennis broadcasts."""
from __future__ import annotations

from pathlib import Path
from typing import Optional, Protocol, Sequence, Tuple, Union

import cv2
import numpy as np
import pandas as pd


BallPoint = Tuple[float, float, float]
RectifiedTrack = list[Optional[BallPoint]]
BALL_COLUMNS = ("frame", "track_id", "cls", "x", "y")
_MIN_CONFIDENCE = 0.5


class BallDetector(Protocol):
    """Stateful detector interface for one ball candidate per video frame."""

    def detect(self, frame: np.ndarray) -> Optional[BallPoint]:
        """Return pixel x, y, confidence, or None when detection is uncertain."""


class MotionDiffDetector:
    """Detect a small moving blob, rejecting ambiguous motion explicitly."""

    def __init__(self, threshold: int = 40) -> None:
        self.threshold = threshold
        self._previous_gray: Optional[np.ndarray] = None

    def detect(self, frame: np.ndarray) -> Optional[BallPoint]:
        """Return the highest-scoring upper-court motion blob when unambiguous."""
        gray = frame if frame.ndim == 2 else cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray = np.asarray(gray, dtype=np.uint8)
        previous = self._previous_gray
        self._previous_gray = gray.copy()
        if previous is None or previous.shape != gray.shape:
            return None
        difference = cv2.absdiff(previous, gray)
        _, mask = cv2.threshold(difference, self.threshold, 255, cv2.THRESH_BINARY)
        blobs: list[BallPoint] = []
        upper_limit = gray.shape[0] * (2.0 / 3.0)
        count, labels, stats, centroids = cv2.connectedComponentsWithStats(mask, connectivity=8)
        for label in range(1, count):
            area = float(stats[label, cv2.CC_STAT_AREA])
            if not 4.0 <= area <= 120.0:
                continue
            x, y = map(float, centroids[label])
            if y >= upper_limit:
                continue
            component = np.where(labels == label, 255, 0).astype(np.uint8)
            intensity = float(cv2.mean(difference, mask=component)[0])
            blobs.append((x, y, area * intensity))
        if not blobs:
            return None
        candidates: list[BallPoint] = []
        for blob in blobs:
            for index, candidate in enumerate(candidates):
                if np.hypot(blob[0] - candidate[0], blob[1] - candidate[1]) <= 12.0:
                    score = blob[2] + candidate[2]
                    candidates[index] = (
                        (blob[0] * blob[2] + candidate[0] * candidate[2]) / score,
                        (blob[1] * blob[2] + candidate[1] * candidate[2]) / score,
                        score,
                    )
                    break
            else:
                candidates.append(blob)
        candidates.sort(key=lambda item: item[2], reverse=True)
        best = candidates[0]
        if len(candidates) > 1 and candidates[1][2] >= best[2] * 0.85:
            return None
        confidence = 0.5 + 0.5 * min(1.0, best[2] / (120.0 * 255.0))
        return (best[0], best[1], confidence)


def rectify_track(points: Sequence[Optional[BallPoint]]) -> RectifiedTrack:
    """Reject impossible jumps, fill short gaps, and remove isolated sightings."""
    cleaned: RectifiedTrack = [None] * len(points)
    accepted: list[int] = []
    last_index: Optional[int] = None
    for index, point in enumerate(points):
        if point is None or point[2] < _MIN_CONFIDENCE:
            continue
        x, y, confidence = map(float, point)
        if last_index is not None:
            previous = cleaned[last_index]
            assert previous is not None
            distance = float(np.hypot(x - previous[0], y - previous[1]))
            if distance / (index - last_index) > 80.0:
                continue
        cleaned[index] = (x, y, confidence)
        accepted.append(index)
        last_index = index

    groups: list[list[int]] = []
    for index in accepted:
        if not groups or index - groups[-1][-1] > 6:
            groups.append([index])
        else:
            groups[-1].append(index)
    for group in groups:
        if len(group) == 1:
            cleaned[group[0]] = None
            continue
        for start, end in zip(group, group[1:]):
            if end - start <= 1:
                continue
            first, last = cleaned[start], cleaned[end]
            assert first is not None and last is not None
            for index in range(start + 1, end):
                fraction = (index - start) / (end - start)
                cleaned[index] = (
                    first[0] + fraction * (last[0] - first[0]),
                    first[1] + fraction * (last[1] - first[1]),
                    0.0,
                )
    return cleaned


def ball_rows(rectified: Sequence[Optional[BallPoint]], homography: np.ndarray) -> pd.DataFrame:
    """Project confident pixel detections into canonical tennis tracking rows."""
    rows: list[dict[str, object]] = []
    for frame, point in enumerate(rectified):
        if point is None or point[2] < _MIN_CONFIDENCE:
            continue
        court = cv2.perspectiveTransform(np.float32([[[point[0], point[1]]]]), homography)[0, 0]
        rows.append({"frame": frame, "track_id": 99, "cls": "ball",
                     "x": float(court[0]), "y": float(court[1])})
    return pd.DataFrame(rows, columns=BALL_COLUMNS)


def attach_ball(
    adapter_df: pd.DataFrame,
    video_path: Union[str, Path],
    homography: np.ndarray,
    detector: BallDetector,
) -> pd.DataFrame:
    """Return existing tracking rows augmented with conservative ball detections."""
    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        raise FileNotFoundError("Could not open video: %s" % video_path)
    points: list[Optional[BallPoint]] = []
    try:
        while True:
            ok, frame = capture.read()
            if not ok:
                break
            points.append(detector.detect(frame))
    finally:
        capture.release()
    balls = ball_rows(rectify_track(points), homography)
    return pd.concat((adapter_df.copy(), balls), ignore_index=True)
