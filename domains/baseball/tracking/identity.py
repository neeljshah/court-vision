"""Continuity-first association for sparse baseball broadcast people tracks."""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Sequence

import numpy as np
from scipy.optimize import linear_sum_assignment


@dataclass
class _Track:
    track_id: int
    box: np.ndarray
    history: deque[np.ndarray] = field(default_factory=lambda: deque(maxlen=6))
    misses: int = 0

    def __post_init__(self) -> None:
        if not self.history:
            self.history.append(_center(self.box))

    def predicted_center(self) -> np.ndarray:
        """Predict the next observed centroid from recent observed motion."""
        latest = self.history[-1]
        if len(self.history) < 2:
            return latest
        velocity = self.history[-1] - self.history[-2]
        return latest + velocity * min(self.misses + 1, 3)

    def update(self, box: np.ndarray) -> None:
        self.box = box.copy()
        self.history.append(_center(box))
        self.misses = 0


def _center(box: np.ndarray) -> np.ndarray:
    return (box[:2] + box[2:]) / 2.0


def _boxes(raw_boxes: Sequence[Sequence[float]]) -> np.ndarray:
    boxes = np.asarray([list(box[:4]) for box in raw_boxes], dtype=float)
    if boxes.size == 0:
        return np.empty((0, 4), dtype=float)
    if boxes.ndim != 2 or boxes.shape[1] != 4:
        raise ValueError("detections must contain xyxy boxes")
    valid = (boxes[:, 2] > boxes[:, 0]) & (boxes[:, 3] > boxes[:, 1])
    return boxes[valid]


class BaseballIdentityTracker:
    """Associate observed people by recent centroid continuity, never box size."""

    def __init__(self, max_misses: int = 90, min_gate_px: float = 42.0) -> None:
        if max_misses < 0 or min_gate_px <= 0.0:
            raise ValueError("max_misses must be non-negative and min_gate_px positive")
        self.max_misses = max_misses
        self.min_gate_px = min_gate_px
        self._tracks: list[_Track] = []
        self._next_track_id = 1

    def reset_for_cut(self) -> None:
        """End all active identities at a verified broadcast cut."""
        self._tracks.clear()

    def step(self, raw_boxes: Sequence[Sequence[float]]) -> list[tuple[int, np.ndarray]]:
        """Return IDs and bottom-centre observations for this decoded frame.

        Active tracks compete globally by distance to their velocity-predicted
        centroids. Box area only orders truly unmatched cold starts, and never
        affects association between an existing identity and a detection.
        """
        boxes = _boxes(raw_boxes)
        matches, unmatched_tracks, unmatched_boxes = self._associate(boxes)
        output: list[tuple[int, np.ndarray]] = []
        for track_index, box_index in matches:
            track = self._tracks[track_index]
            track.update(boxes[box_index])
            output.append((track.track_id, _bottom_center(boxes[box_index])))
        for track_index in unmatched_tracks:
            self._tracks[track_index].misses += 1
        self._tracks = [track for track in self._tracks if track.misses <= self.max_misses]
        # Area is deliberately a cold-start tie-breaker only; association above
        # has already considered every existing identity.
        for box_index in sorted(unmatched_boxes, key=lambda i: _area(boxes[i]), reverse=True):
            track = _Track(self._next_track_id, boxes[box_index].copy())
            self._next_track_id += 1
            self._tracks.append(track)
            output.append((track.track_id, _bottom_center(boxes[box_index])))
        return sorted(output, key=lambda row: row[0])

    def _associate(self, boxes: np.ndarray) -> tuple[list[tuple[int, int]], list[int], list[int]]:
        if not len(self._tracks) or not len(boxes):
            return [], list(range(len(self._tracks))), list(range(len(boxes)))
        predicted = np.vstack([track.predicted_center() for track in self._tracks])
        centers = (boxes[:, :2] + boxes[:, 2:]) / 2.0
        distances = np.linalg.norm(predicted[:, None, :] - centers[None, :, :], axis=2)
        diagonals = np.linalg.norm(boxes[:, 2:] - boxes[:, :2], axis=1)
        gates = np.maximum(self.min_gate_px, diagonals[None, :] * 1.5)
        valid = distances <= gates
        rows, cols = linear_sum_assignment(np.where(valid, distances, 1e9))
        matches = [(int(row), int(col)) for row, col in zip(rows, cols) if valid[row, col]]
        used_tracks = {row for row, _ in matches}
        used_boxes = {col for _, col in matches}
        return matches, [i for i in range(len(self._tracks)) if i not in used_tracks], [
            i for i in range(len(boxes)) if i not in used_boxes
        ]


def _area(box: np.ndarray) -> float:
    return float((box[2] - box[0]) * (box[3] - box[1]))


def _bottom_center(box: np.ndarray) -> np.ndarray:
    return np.array(((box[0] + box[2]) / 2.0, box[3]), dtype=float)
