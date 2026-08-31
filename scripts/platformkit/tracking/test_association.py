"""Tests for sport-blind tracking association."""
import numpy as np

from scripts.platformkit.tracking.association import Track, Tracker, associate


def _box(center_x: float, width: float = 50.0) -> np.ndarray:
    return np.array([center_x - width / 2, 0.0, center_x + width / 2, 20.0])


def _naive_greedy_history(frames: list[list[tuple[str, np.ndarray]]]) -> dict[str, list[int]]:
    """Deliberately appearance-free greedy IoU baseline used for comparison."""
    tracks, next_id, history = [], 0, {"a": [], "b": []}
    for detections in frames:
        assigned = set()
        labels = {}
        for track in tracks:
            best = max(
                ((index, _iou(track["box"], box)) for index, (_, box) in enumerate(detections)
                 if index not in assigned), default=(None, 0.0), key=lambda item: item[1],
            )
            if best[0] is not None and best[1] >= 0.3:
                index = best[0]
                track["box"] = detections[index][1]
                assigned.add(index)
                labels[detections[index][0]] = track["id"]
        for index, (label, box) in enumerate(detections):
            if index not in assigned:
                tracks.append({"id": next_id, "box": box})
                labels[label], next_id = next_id, next_id + 1
        for label, track_id in labels.items():
            history[label].append(track_id)
    return history


def _iou(a: np.ndarray, b: np.ndarray) -> float:
    inter = max(0.0, min(a[2], b[2]) - max(a[0], b[0])) * max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    return inter / (50.0 * 20.0 * 2 - inter)


def test_embeddings_keep_ids_through_crossing_and_gap():
    tracker = Tracker(min_hits=1)
    embeddings = {"a": np.array([1.0, 0.0]), "b": np.array([0.0, 1.0])}
    frames = []
    tracker_history = {"a": [], "b": []}
    for frame in range(14):
        a, b = _box(-10 + 2 * frame), _box(10 - 2 * frame)
        detections = [("a", a), ("b", b)] if frame < 3 else [("b", b)]
        if frame == 13:
            detections = [("b", b), ("a", a)]
        frames.append(detections)
        visible = tracker.step([box for _, box in detections], np.array([embeddings[label] for label, _ in detections]))
        ids_by_box = {tuple(track.box): track.id for track in visible}
        for label, box in detections:
            tracker_history[label].append(ids_by_box[tuple(box)])

    naive_history = _naive_greedy_history(frames)
    assert len(set(tracker_history["a"])) == 1
    assert len(set(tracker_history["b"])) == 1
    assert len(set(naive_history["a"])) > 1 or len(set(naive_history["b"])) > 1


def test_expansion_recovers_displaced_box_only_after_scaling():
    track = Track(7, _box(0.0, 10.0))
    detection = _box(7.5, 10.0)
    matches, unmatched_tracks, unmatched_dets = associate([track], [detection])
    assert matches == [(0, 0)]
    assert unmatched_tracks == [] and unmatched_dets == []
