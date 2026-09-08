"""G304 attempt 2: the proposal generator recovers drawn court-line intersections.

Per-file test only -- never run the full suite.  This test asserts geometry and the sealed
constants; it rates nothing and asserts no registration, calibration or tracking quality.
"""
import collections

import cv2
import numpy as np

from scripts.platformkit.tracking.g304_proposals import (
    CAP, DEDUPE_PX, MIN_CROSS_ANGLE_DEG, Proposal, VOCABULARY, frame_proposals,
    lsd_proposals, name_for, select,
)

# Four drawn lines: two shallow (sideline-like), two steep (lane-boundary-like).
SHALLOW = (((120, 780), (1800, 700)), ((160, 430), (1780, 400)))
STEEP = (((520, 240), (400, 1000)), ((1340, 250), (1500, 1010)))


def _synthetic_court():
    frame = np.full((1080, 1920, 3), 55, np.uint8)
    for start, end in SHALLOW + STEEP:
        cv2.line(frame, start, end, (245, 245, 245), 1, cv2.LINE_AA)
    return frame


def _true_intersections():
    points = []
    for shallow in SHALLOW:
        for steep in STEEP:
            (x1, y1), (x2, y2) = shallow
            (x3, y3), (x4, y4) = steep
            first = np.cross((x1, y1, 1.0), (x2, y2, 1.0))
            second = np.cross((x3, y3, 1.0), (x4, y4, 1.0))
            point = np.cross(first, second)
            points.append((point[0] / point[2], point[1] / point[2]))
    return points


def test_lsd_proposals_recover_every_drawn_intersection_within_3px():
    proposals = lsd_proposals(_synthetic_court(), allow_center=False)
    assert proposals, "generator produced no intersection on a four-line synthetic court"
    for true_x, true_y in _true_intersections():
        nearest = min(np.hypot(p.x - true_x, p.y - true_y) for p in proposals)
        assert nearest <= 3.0, "drawn intersection (%.1f, %.1f) missed by %.2f px" % (
            true_x, true_y, nearest)


def test_cap_bounds_the_frame_and_spends_itself_on_distinct_names_first():
    kept = frame_proposals(_synthetic_court(), allow_center=False)
    assert 0 < len(kept) <= CAP
    # Within a family, no name repeats before every available name has been used once.
    for source in set(item.source for item in kept):
        names = [item.name for item in kept if item.source == source]
        assert names[:len(set(names))] == list(dict.fromkeys(names))
    # The cap never destroys precision: whatever survives is still on a drawn intersection.
    truth = _true_intersections()
    assert min(min(np.hypot(p.x - tx, p.y - ty) for tx, ty in truth) for p in kept) <= 3.0


def test_sealed_constants_match_the_preregistration():
    assert CAP == 12
    assert DEDUPE_PX == 5.0
    assert MIN_CROSS_ANGLE_DEG == 25.0
    assert len(VOCABULARY) == 15
    assert len(set(VOCABULARY.values())) == 6
    assert name_for(100.0, 1000.0, False) == "CORNER_NEAR_L"
    assert name_for(960.0, 100.0, False) == "KEY_TOP"
    assert name_for(960.0, 100.0, True) == "CENTER_SIDELINE_FAR"


def test_select_dedupes_by_name_then_spends_the_cap_on_distinct_names():
    crowd = [Proposal("KEY_TOP", "lsd_intersect", 100.0 + i * 0.5, 100.0, 0.9 - i * 0.01)
             for i in range(8)]
    crowd += [Proposal("CORNER_NEAR_L", "shitomasi", 300.0, 900.0, 0.2)]
    kept = select(crowd, cap=4)
    assert [p.name for p in kept] == ["KEY_TOP", "CORNER_NEAR_L"]


def test_amendment_1_interleaves_families_so_none_monopolises_the_cap():
    # Both families hold ample stock and the coarser one scores far higher; the amended
    # rule must still split the cap rather than let the high scores take every slot.
    crowd = [Proposal("CORNER_NEAR_L" if index % 2 else "KEY_TOP", "shitomasi",
                      100.0 + index * 40.0, 900.0, 0.99 - index * 0.001) for index in range(20)]
    crowd += [Proposal("FT_LINE_L" if index % 2 else "CORNER_FAR_R", "lsd_intersect",
                       200.0 + index * 40.0, 400.0, 0.20 - index * 0.001) for index in range(20)]
    counts = collections.Counter(item.source for item in select(crowd, cap=12))
    assert counts == {"shitomasi": 6, "lsd_intersect": 6}
