"""Sport-blind tracking-by-detection association with appearance recovery."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional

import numpy as np
from scipy.optimize import linear_sum_assignment


@dataclass
class Track:
    """One active object track, using an ``xyxy`` bounding box."""

    id: int
    box: np.ndarray
    age: int = 0
    misses: int = 0
    embedding: Optional[np.ndarray] = None
    hits: int = 1


def _boxes(boxes: Iterable[np.ndarray]) -> np.ndarray:
    array = np.asarray(list(boxes), dtype=float)
    if array.size == 0:
        return np.empty((0, 4), dtype=float)
    if array.ndim != 2 or array.shape[1] != 4:
        raise ValueError("boxes must have shape (n, 4) in xyxy order")
    return array


def _iou(boxes_a: np.ndarray, boxes_b: np.ndarray) -> np.ndarray:
    left_top = np.maximum(boxes_a[:, None, :2], boxes_b[None, :, :2])
    right_bottom = np.minimum(boxes_a[:, None, 2:], boxes_b[None, :, 2:])
    wh = np.maximum(0.0, right_bottom - left_top)
    intersection = wh[..., 0] * wh[..., 1]
    area_a = np.prod(np.maximum(0.0, boxes_a[:, 2:] - boxes_a[:, :2]), axis=1)
    area_b = np.prod(np.maximum(0.0, boxes_b[:, 2:] - boxes_b[:, :2]), axis=1)
    return intersection / np.maximum(area_a[:, None] + area_b - intersection, 1e-12)


def _expand(boxes: np.ndarray, factor: float) -> np.ndarray:
    centers = (boxes[:, :2] + boxes[:, 2:]) / 2.0
    half_sizes = (boxes[:, 2:] - boxes[:, :2]) * factor / 2.0
    return np.concatenate((centers - half_sizes, centers + half_sizes), axis=1)


def _cosine_distance(track_embedding: Optional[np.ndarray], det_embedding: np.ndarray) -> float:
    if track_embedding is None:
        return 0.0
    a, b = np.asarray(track_embedding, dtype=float), np.asarray(det_embedding, dtype=float)
    denom = np.linalg.norm(a) * np.linalg.norm(b)
    return 1.0 - float(np.dot(a, b) / denom) if denom else 1.0


def _match(
    tracks: list[Track], detections: np.ndarray, det_embeddings: Optional[np.ndarray],
    iou_gate: float, app_weight: float, scale: float = 1.0,
) -> list[tuple[int, int]]:
    if not tracks or not len(detections):
        return []
    track_boxes = _boxes(track.box for track in tracks)
    if scale != 1.0:
        track_boxes, detections = _expand(track_boxes, scale), _expand(detections, scale)
    overlaps = _iou(track_boxes, detections)
    cost = 1.0 - overlaps
    if det_embeddings is not None:
        appearance = np.array([
            [_cosine_distance(track.embedding, embedding) for embedding in det_embeddings]
            for track in tracks
        ])
        have_embeddings = np.array([track.embedding is not None for track in tracks])
        cost[have_embeddings] = ((1.0 - app_weight) * cost[have_embeddings]
                                 + app_weight * appearance[have_embeddings])
    valid = overlaps >= iou_gate
    rows, cols = linear_sum_assignment(np.where(valid, cost, 1e6))
    return [(int(row), int(col)) for row, col in zip(rows, cols) if valid[row, col]]


def associate(
    tracks: list[Track], detections: Iterable[np.ndarray], embeddings: Optional[np.ndarray] = None,
    iou_gate: float = 0.3, expand_steps: int = 2, expand_factor: float = 1.2,
    app_weight: float = 0.25,
) -> tuple[list[tuple[int, int]], list[int], list[int]]:
    """Associate tracks to detection boxes via Hungarian matching and EIoU recovery."""

    detections_array = _boxes(detections)
    if embeddings is not None:
        embeddings = np.asarray(embeddings, dtype=float)
        if embeddings.ndim != 2 or len(embeddings) != len(detections_array):
            raise ValueError("embeddings must have one row per detection")
    if not 0.0 <= app_weight <= 1.0 or iou_gate < 0.0:
        raise ValueError("iou_gate and app_weight must be between 0 and 1")
    matches = _match(tracks, detections_array, embeddings, iou_gate, app_weight)
    unmatched_tracks = set(range(len(tracks))) - {track for track, _ in matches}
    unmatched_dets = set(range(len(detections_array))) - {det for _, det in matches}

    for step in range(1, expand_steps + 1):
        if not unmatched_tracks or not unmatched_dets:
            break
        track_indices, det_indices = sorted(unmatched_tracks), sorted(unmatched_dets)
        subset_tracks = [tracks[index] for index in track_indices]
        subset_dets = detections_array[det_indices]
        subset_embeddings = None if embeddings is None else embeddings[det_indices]
        recovered = _match(
            subset_tracks, subset_dets, subset_embeddings, iou_gate, app_weight,
            expand_factor ** step,
        )
        for local_track, local_det in recovered:
            track_index, det_index = track_indices[local_track], det_indices[local_det]
            matches.append((track_index, det_index))
            unmatched_tracks.remove(track_index)
            unmatched_dets.remove(det_index)
    return sorted(matches), sorted(unmatched_tracks), sorted(unmatched_dets)


def apply_motion(tracks: list[Track], dxdy: Iterable[float]) -> None:
    """Shift active boxes by camera motion ``(dx, dy)`` before association."""

    delta = np.asarray(dxdy, dtype=float)
    if delta.shape != (2,):
        raise ValueError("dxdy must contain exactly two values")
    shift = np.tile(delta, 2)
    for track in tracks:
        track.box = np.asarray(track.box, dtype=float) + shift


class Tracker:
    """Small online tracker retaining tentative tracks until they are confirmed."""

    def __init__(
        self, max_misses: int = 30, min_hits: int = 3, iou_gate: float = 0.3,
        expand_steps: int = 2, expand_factor: float = 1.2, app_weight: float = 0.25,
    ) -> None:
        self.max_misses = max_misses
        self.min_hits = min_hits
        self.iou_gate = iou_gate
        self.expand_steps = expand_steps
        self.expand_factor = expand_factor
        self.app_weight = app_weight
        self.tracks: list[Track] = []
        self._next_id = 0

    def step(
        self, detections: Iterable[np.ndarray], embeddings: Optional[np.ndarray] = None,
    ) -> list[Track]:
        """Advance one frame and return currently confirmed active tracks."""

        boxes = _boxes(detections)
        det_embeddings = None if embeddings is None else np.asarray(embeddings, dtype=float)
        matches, unmatched_tracks, unmatched_dets = associate(
            self.tracks, boxes, det_embeddings, self.iou_gate, self.expand_steps,
            self.expand_factor, self.app_weight,
        )
        for track_index, det_index in matches:
            track = self.tracks[track_index]
            track.box, track.age, track.misses = boxes[det_index].copy(), track.age + 1, 0
            track.hits += 1
            if det_embeddings is not None:
                track.embedding = det_embeddings[det_index].copy()
        for track_index in unmatched_tracks:
            track = self.tracks[track_index]
            track.age, track.misses = track.age + 1, track.misses + 1
        for det_index in unmatched_dets:
            embedding = None if det_embeddings is None else det_embeddings[det_index].copy()
            self.tracks.append(Track(self._next_id, boxes[det_index].copy(), 1, 0, embedding))
            self._next_id += 1
        self.tracks = [track for track in self.tracks if track.misses <= self.max_misses]
        return [track for track in self.tracks if track.hits >= self.min_hits]
