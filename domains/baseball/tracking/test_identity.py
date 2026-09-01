import numpy as np

from domains.baseball.tracking.identity import BaseballIdentityTracker


def _box(x: float, y: float = 100.0) -> list[float]:
    return [x, y, x + 20.0, y + 50.0]


def test_continuity_survives_a_missed_detection_without_inventing_a_row():
    tracker = BaseballIdentityTracker(max_misses=3)
    assert [track_id for track_id, _ in tracker.step([_box(100)])] == [1]
    assert tracker.step([]) == []
    assert [track_id for track_id, _ in tracker.step([_box(106)])] == [1]


def test_global_continuity_assignment_beats_detection_order_and_area():
    tracker = BaseballIdentityTracker()
    tracker.step([_box(100), _box(200, 90)])
    rows = tracker.step([_box(204, 90), _box(104)])
    assert [(track_id, point[0]) for track_id, point in rows] == [(1, 114.0), (2, 214.0)]


def test_cut_ends_identity_instead_of_reusing_it_across_camera_views():
    tracker = BaseballIdentityTracker()
    tracker.step([_box(100)])
    assert [track_id for track_id, point in tracker.step([_box(100)], cut=True)] == [2]
