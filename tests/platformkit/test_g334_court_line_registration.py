"""G334: the template fit on a synthetic court, the held-out scorer, and the inside-court test.

Nothing here reads footage or a label. Following G217's decomposition -- exact lines through the
same solver gave 0.000000 px, so the solver and the court model are not the error source -- the
solver and the enumeration are pinned on EXACT lines, and the detected-group path on the rendered
court is measured separately rather than asserted.
"""
from __future__ import annotations

import cv2
import numpy as np
import pytest

from scripts.platformkit.tracking import g334_court_template as gt
from scripts.platformkit.tracking.g334_court_line_calibration import (
    ARM_A, ARM_B, detect_segments, enumerate_hypotheses, family_groups, fit_frame, gate,
    heldout_split, score_image_matrix, shot_median, split_families,
)
from scripts.platformkit.tracking.g334_metrics import (
    Cell, court_points, forward_error, inside_count, invert, nearest_neighbour_ft, reverse_error,
    route_court_matrix,
)
from scripts.platformkit.tracking.g334_seal import body_of, scan_text, seal_hex

SHAPE = (680, 1280)
# A side-on broadcast pose: baseline at the left, half-court at the right, near sideline at the foot.
COURT_QUAD = np.float32([(0.0, 0.0), (0.0, gt.HALF_Y_FT),
                         (gt.COURT_WIDTH_FT, 0.0), (gt.COURT_WIDTH_FT, gt.HALF_Y_FT)])
IMAGE_QUAD = np.float32([(120.0, 620.0), (1160.0, 600.0), (300.0, 220.0), (1000.0, 240.0)])


class _Stub:
    """The only attribute `enumerate_hypotheses` reads from a candidate group."""

    def __init__(self, line):
        self.line = line


def true_image_matrix() -> np.ndarray:
    return cv2.getPerspectiveTransform(COURT_QUAD, IMAGE_QUAD)


def synthetic_court(matrix, thickness: int = 3) -> np.ndarray:
    """The template rendered as white lines on a flat floor -- the only image these tests use."""
    canvas = np.full((SHAPE[0], SHAPE[1], 3), 70, dtype=np.uint8)
    for polyline in gt.template_polylines():
        projected = gt.project(matrix, polyline)
        cv2.polylines(canvas, [np.round(projected).astype(np.int32)], False,
                      (245, 245, 245), thickness, cv2.LINE_AA)
    return canvas


def exact_line(matrix, court_line) -> np.ndarray:
    """The image line a court line maps to: l_image = H^-T l_court, normalised like an observation."""
    line = np.linalg.inv(np.asarray(matrix, float)).T @ np.asarray(court_line, float)
    return line / float(np.hypot(line[0], line[1]))


def projection_gap(first, second) -> float:
    """Max separation in pixels between two matrices over the template points inside the image."""
    a, b = gt.project(first, gt.TEMPLATE_POINTS), gt.project(second, gt.TEMPLATE_POINTS)
    inside = (a[:, 0] >= 0) & (a[:, 0] < SHAPE[1]) & (a[:, 1] >= 0) & (a[:, 1] < SHAPE[0])
    return float(np.linalg.norm(a[inside] - b[inside], axis=1).max())


def test_template_geometry_matches_the_sealed_court():
    lines = gt.template_polylines()
    assert len(lines) == 12
    assert gt.corner_three_end() == pytest.approx(14.1978, abs=1e-3)
    assert gt.FAMILY_W_VALUES == (0.0, 19.0, 47.0)
    assert gt.FAMILY_L_VALUES == (0.0, 3.0, 17.0, 33.0, 47.0, 50.0)
    points = gt.TEMPLATE_POINTS
    assert len(points) > 300
    assert points[:, 0].min() >= 0.0 and points[:, 0].max() <= gt.COURT_WIDTH_FT
    assert points[:, 1].min() >= 0.0 and points[:, 1].max() <= gt.HALF_Y_FT + 1e-6


def test_measurement_image_and_matrix_agree():
    image = gt.measurement_image(np.zeros((1080, 1920, 3), np.uint8))
    assert image.shape[1] == gt.MEASURE_WIDTH and image.shape[0] == 680
    mapped = gt.project(gt.measurement_matrix(1080, 1920),
                        np.float32([(0.0, gt.TOPCUT), (1920.0, 1080.0)]))
    assert mapped[0] == pytest.approx([0.0, 0.0], abs=1e-6)
    assert mapped[1] == pytest.approx([1280.0, 680.0], abs=1e-6)
    # A 720p frame is not resampled at all, which is why the bar is one flat pixel count.
    assert gt.measurement_image(np.zeros((720, 1280, 3), np.uint8)).shape[:2] == (660, 1280)


def test_enumeration_recovers_the_known_homography_within_one_pixel():
    """Exact lines: the enumerated set contains the truth, so template and solver are not the error."""
    truth = true_image_matrix()
    groups_w = [_Stub(exact_line(truth, (0.0, 1.0, -value))) for value in (0.0, 47.0)]
    groups_l = [_Stub(exact_line(truth, (1.0, 0.0, -value))) for value in (0.0, 50.0)]
    gaps = []
    for first, second in ((groups_w, groups_l), (groups_l, groups_w)):
        for image_quad, court_quad in enumerate_hypotheses(first, second, ARM_A, 1e6):
            gaps.append(projection_gap(cv2.getPerspectiveTransform(court_quad, image_quad), truth))
    assert len(gaps) >= 180
    assert min(gaps) <= 1.0
    assert min(gaps) < 1e-6, "an exact-line hypothesis must reproduce the truth exactly"


def test_sealed_objective_does_not_select_the_closest_reachable_fit():
    """The measured defect of ARM A, pinned on the synthetic court where the truth is known.

    The sealed score is the mean over the SURVIVING template points, so a hypothesis that projects
    most of the template out of the image is scored only on the few points it keeps -- and those
    can all sit on line pixels. This is G254's warning made concrete: the objective is maximised
    away from the correct court. This test FAILS if that defect is ever repaired, which is the
    point of it.
    """
    truth = true_image_matrix()
    image = synthetic_court(truth)
    segments = detect_segments(image, ARM_A)
    field = gt.distance_transform(image.shape, segments)
    family_a, family_b = split_families(segments, ARM_A)
    groups_a, groups_b = family_groups(family_a, ARM_A), family_groups(family_b, ARM_A)
    reference = gt.project(truth, gt.TEMPLATE_POINTS)
    visible = ((reference[:, 0] >= 0) & (reference[:, 0] < SHAPE[1])
               & (reference[:, 1] >= 0) & (reference[:, 1] < SHAPE[0]))
    top_score, top_gap = None, None
    for first, second in ((groups_a, groups_b), (groups_b, groups_a)):
        for image_quad, court_quad in enumerate_hypotheses(first, second, ARM_A,
                                                           8.0 * max(image.shape[:2])):
            matrix = cv2.getPerspectiveTransform(court_quad, image_quad)
            score, n_scored = score_image_matrix(matrix, field, ARM_A)
            if score < 0.0:
                continue
            points = gt.project(matrix, gt.TEMPLATE_POINTS)
            if not np.isfinite(points).all():
                continue
            gap = float(np.linalg.norm(points[visible] - reference[visible], axis=1).max())
            if top_score is None or score > top_score[0]:
                top_score = (score, gap, n_scored)
            if top_gap is None or gap < top_gap[1]:
                top_gap = (score, gap, n_scored)
    assert top_score is not None and top_gap is not None
    # The truth itself scores well and passes the sealed gate, so the gate is not what loses it.
    true_score, true_n = score_image_matrix(truth, field, ARM_A)
    assert true_n == len(gt.TEMPLATE_POINTS)
    assert gate(truth, true_score, true_n, image.shape, ARM_A) == "valid"
    # The winner keeps fewer points than the truth, scores higher, and sits further from it.
    assert top_score[2] < true_n
    assert top_score[0] > true_score
    assert top_score[1] > top_gap[1]
    # Group truncation, not the solver: with exact lines the enumeration reaches 0 px above.
    assert top_gap[1] > 1.0


def test_detected_group_path_reaches_the_search_but_not_one_pixel():
    """The rendered court measured end to end. Recovery is limited by which groups make TOP_K."""
    truth = true_image_matrix()
    image = synthetic_court(truth)
    segments = detect_segments(image, ARM_A)
    assert len(segments) >= 8
    family_a, family_b = split_families(segments, ARM_A)
    assert len(family_a) >= 2 and len(family_b) >= 2
    assert len(family_groups(family_a, ARM_A)) == ARM_A.top_k
    fit = fit_frame(image, segments, ARM_A)
    assert fit.n_hypotheses > 10_000
    assert fit.reason in ("valid", "no_valid_h", "implausible_scale")
    if fit.reason == "valid":
        back = gt.project(fit.court, gt.project(fit.image, np.float32([(25.0, 19.0)])))
        assert back[0] == pytest.approx([25.0, 19.0], abs=0.05)


def test_heldout_split_is_a_sealed_deterministic_partition():
    segments = detect_segments(synthetic_court(true_image_matrix()), ARM_A)
    first = heldout_split(segments, "S9", 123)
    assert heldout_split(segments, "S9", 123)[0] == first[0]
    assert heldout_split(segments, "S9", 124)[0] != first[0]
    assert heldout_split(segments, "S8", 123)[0] != first[0]
    assert len(first[0]) + len(first[1]) == len(segments)
    assert len(first[0]) == (len(segments) + 1) // 2
    assert not (set(map(id, first[0])) & set(map(id, first[1])))


def test_heldout_scorer_separates_the_true_fit_from_a_displaced_one():
    truth = true_image_matrix()
    image = synthetic_court(truth)
    _fit, held = heldout_split(detect_segments(image, ARM_A), "S9", 7)
    field = gt.distance_transform(image.shape, held)
    good, n_good = forward_error(truth, field)
    shifted = np.array([[1.0, 0.0, 40.0], [0.0, 1.0, 40.0], [0.0, 0.0, 1.0]]) @ truth
    bad, n_bad = forward_error(shifted, field)
    assert n_good > ARM_A.min_scored and n_bad > 0
    assert good < 8.0 < bad
    rev_good, n_rev = reverse_error(truth, held, image.shape)
    rev_bad, _ = reverse_error(shifted, held, image.shape)
    assert n_rev > 0 and rev_good < rev_bad
    assert np.isnan(forward_error(None, field)[0])


def test_inside_court_and_neighbour_distances():
    truth = true_image_matrix()
    feet = gt.project(truth, np.float32([(25.0, 10.0), (30.0, 12.0), (5.0, 40.0)]))
    points = court_points(invert(truth), [tuple(p) for p in feet])
    assert len(points) == 3 and inside_count(points) == 3
    assert points[0] == pytest.approx([25.0, 10.0], abs=0.05)
    assert inside_count(np.array([(-5.0, 10.0), (25.0, 120.0), (25.0, 25.0)])) == 1
    assert inside_count(np.zeros((0, 2))) == 0
    gaps = nearest_neighbour_ft(points)
    assert len(gaps) == 3 and gaps.min() == pytest.approx(np.hypot(5.0, 2.0), abs=0.05)
    assert len(nearest_neighbour_ft(points[:1])) == 0


def test_route_composition_and_shot_median():
    identity = np.eye(3)
    court = route_court_matrix(identity, identity, 940, 500, identity)
    # map_2d pixels scale to 94 x 50 ft and the axes swap: (940, 500) px is the far court corner.
    assert gt.project(court, np.float32([(940.0, 500.0)]))[0] == pytest.approx([50.0, 94.0])
    assert route_court_matrix(None, identity, 940, 500, identity) is None
    assert route_court_matrix(identity, identity, 940, 500, np.zeros((3, 3))) is None
    assert invert(np.zeros((3, 3))) is None and invert(None) is None
    truth = true_image_matrix()
    assert shot_median([truth, truth, None]) == pytest.approx(truth / truth[2, 2])
    assert shot_median([None]) is None


def test_arm_b_is_the_one_sealed_sensitivity_set():
    changed = {field for field in ARM_A.__dataclass_fields__
               if getattr(ARM_A, field) != getattr(ARM_B, field)}
    assert changed == {"name", "lsd_min_len", "family_tol_deg", "top_k"}
    assert (ARM_B.lsd_min_len, ARM_B.family_tol_deg, ARM_B.top_k) == (18.0, 50.0, 9)


def test_cell_denominators_and_the_vocabulary_scan():
    cell = Cell("S1", "G334A")
    cell.add("too_few_groups", float("nan"), 0, float("nan"), 0, 0, 4, 0, np.zeros(0), 0)
    cell.add("valid", 3.5, 200, 4.5, 300, 40, 10, 7, np.array([6.0, 8.0]), 500)
    summary = cell.summary()
    assert summary["n_frames"] == 2 and summary["valid_frames"] == 1
    assert (summary["feet_total"], summary["feet_evaluated"], summary["feet_inside"]) == (14, 10, 7)
    assert summary["heldout_forward_px"] == 3.5 and summary["n_forward_points"] == 200
    assert summary["nn_median_ft"] == 7.0 and summary["n_nn_pairs"] == 2
    assert summary["bucket_valid"] + summary["bucket_too_few_groups"] == 2
    assert seal_hex("a\r\nb\r\n") == seal_hex("a\nb\n")
    assert body_of("x\nSEAL sha256 dead\n") == "x\n"
    assert scan_text("ledger 000054 82.18 pct\n") == []
