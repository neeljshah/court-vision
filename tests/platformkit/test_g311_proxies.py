"""G311 per-file test: proxy/matching arithmetic on SYNTHETIC boxes only.

Pins the IoU >= 0.5 match threshold, greedy ONE-TO-ONE matching, the both-way
agreement asymmetry, and that a zero-box frame stays in the denominator.
"""

import numpy as np

from scripts.platformkit.tracking.g311_apache_detector_arm import (
    IOU_MATCH,
    agreement,
    frame_indices,
    greedy_match,
    iou,
    link_tracks,
    summarize,
)


def test_iou_threshold_is_half():
    assert IOU_MATCH == 0.5


def test_iou_values_and_empty_shapes():
    a = np.array([[0.0, 0.0, 10.0, 10.0]])
    assert iou(a, a)[0, 0] == 1.0
    # 50 pct overlap in x -> inter 50, union 150 -> 1/3, below the 0.5 bar
    b = np.array([[5.0, 0.0, 15.0, 10.0]])
    assert abs(iou(a, b)[0, 0] - 1.0 / 3.0) < 1e-9
    assert iou(np.zeros((0, 4)), a).shape == (0, 1)
    assert iou(a, np.zeros((0, 4))).shape == (1, 0)


def test_greedy_match_is_one_to_one_and_respects_threshold():
    a = np.array([[0.0, 0.0, 10.0, 10.0]])
    # two candidates overlapping the same box; only one may be consumed
    b = np.array([[0.0, 0.0, 10.0, 10.0], [1.0, 1.0, 11.0, 11.0]])
    pairs = greedy_match(a, b)
    assert pairs == [(0, 0)]
    # 1/3 IoU is below 0.5 -> no pair at all
    far = np.array([[5.0, 0.0, 15.0, 10.0]])
    assert greedy_match(a, far) == []


def test_agreement_is_asymmetric_and_keeps_zero_box_frames():
    box = np.array([[0.0, 0.0, 10.0, 10.0]])
    two = np.array([[0.0, 0.0, 10.0, 10.0], [100.0, 100.0, 110.0, 110.0]])
    frames_a = [box, np.zeros((0, 4))]
    frames_b = [two, np.zeros((0, 4))]
    r = agreement(frames_a, frames_b)
    # the zero-box frame is counted, not dropped
    assert r["frames"] == 2
    assert r["zero_box_frames_a"] == 1 and r["zero_box_frames_b"] == 1
    assert r["boxes_a"] == 1 and r["boxes_b"] == 2 and r["matched"] == 1
    # both ways, and they differ because the box counts differ
    assert r["agree_a_in_b"] == 1.0
    assert r["agree_b_in_a"] == 0.5


def test_summarize_denominator_includes_zero_box_frames():
    frames = [np.array([[0.0, 0.0, 10.0, 10.0]]), np.zeros((0, 4))]
    s = summarize("t", frames, [10.0, 20.0], 1.0, "test")
    assert s["decoded_frames"] == 2
    assert s["boxes_total"] == 1
    assert s["boxes_per_frame"] == 0.5
    assert s["zero_box_frames"] == 1
    assert s["ms_per_frame"] == 15.0


def test_link_tracks_links_across_frames_and_splits_on_jump():
    still = np.array([[0.0, 0.0, 10.0, 10.0]])
    jumped = np.array([[500.0, 500.0, 510.0, 510.0]])
    assert link_tracks([still, still, still]) == {"distinct_ids": 1, "median_track_length": 3}
    assert link_tracks([still, jumped])["distinct_ids"] == 2


def test_agreement_refuses_frame_misaligned_arms():
    # a dropped frame in one arm would silently shift the pairing; it must raise
    import pytest
    with pytest.raises(ValueError):
        agreement([np.zeros((0, 4)), np.zeros((0, 4))], [np.zeros((0, 4))])


def test_decode_raises_rather_than_dropping_a_failed_frame(tmp_path):
    # a missing file makes every read fail; decode must raise, not return a short list
    import pytest

    from scripts.platformkit.tracking.g311_apache_detector_arm import decode
    with pytest.raises(RuntimeError, match="failed to decode"):
        decode(str(tmp_path / "no_such.mp4"), 3, 3)


def test_frame_indices_are_evenly_spaced_over_the_whole_clip():
    idxs = frame_indices(100, 5)
    assert idxs == [0, 25, 50, 74, 99]
    assert frame_indices(3, 5) == [0, 1, 2]
    assert frame_indices(0, 5) == []


def test_last_decodable_anchors_on_the_last_readable_frame():
    # ffprobe nb_frames overcounts the seekable range, so the top anchor is measured:
    # with reads failing above index 60, a 100-frame clip must anchor on 60, not 99.
    from scripts.platformkit.tracking.g311_apache_detector_arm import last_decodable

    class FakeCap:
        def __init__(self, last):
            self.last, self.pos = last, 0

        def set(self, prop, i):
            self.pos = i

        def read(self):
            return (self.pos <= self.last, None)

    assert last_decodable(FakeCap(60), 100) == 60
    assert last_decodable(FakeCap(99), 100) == 99  # a fully decodable tail is kept
