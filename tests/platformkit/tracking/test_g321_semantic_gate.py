"""G321 -- pin the sealed grid, the fidelity rule, the matching rule and the bars."""
import csv
from collections import Counter
from dataclasses import fields
from pathlib import Path

import cv2
import numpy as np
import pytest

from domains.basketball.tracking.keypoints import BasketballKeypointProvider
from scripts.platformkit.tracking.g304_proposals import SEMANTIC_MAP, VOCABULARY
from scripts.platformkit.tracking.g321_semantic_gate import (
    GRID, MATCH_RADIUS_PX, MAX_FALSE, MIN_NAMES, MIN_STRUCTURES, READY_FRAMES_BAR, STAGES,
    frame_ready, mapped, on_player, run_gate,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
CELLS_CSV = REPO_ROOT / "docs/evidence/tracking/g321_artifact/cells.csv"


def _synthetic(with_lane: bool) -> np.ndarray:
    """A dark 1080p field, optionally carrying one large light lane-sized quadrilateral."""
    frame = np.full((1080, 1920, 3), 30, np.uint8)
    if with_lane:
        cv2.fillConvexPoly(frame, np.array([[600, 300], [1300, 300], [1360, 900], [540, 900]]),
                           (210, 210, 210))
    return frame


@pytest.mark.parametrize("with_lane", [True, False])
def test_r0_shadow_equals_shipped_provider(with_lane):
    """R0 IS the shipped provider; a mismatch means the shadow may not be quoted at all."""
    frame = _synthetic(with_lane)
    shipped = BasketballKeypointProvider().detect(frame)
    shadow, _ = run_gate(frame, GRID[0])
    assert sorted(shipped) == sorted(shadow)
    for key in shipped:
        assert all(abs(a - b) <= 1e-6 for a, b in zip(shipped[key], shadow[key]))


def test_grid_is_the_ten_sealed_cells_each_moving_exactly_one_constant():
    assert [params.cell for params in GRID] == ["R%d" % i for i in range(10)]
    base = GRID[0]
    assert (base.min_edge_support, base.area_frac, base.side_frac, base.approx_eps,
            base.vertex_max, base.perimeter_floor, base.quad_area_floor,
            base.require_convex, base.contour_source) == (
        0.16, 0.006, 0.15, 0.025, 4, 120.0, 400.0, True, "canny")
    moved = {"R1": ("min_edge_support", 0.08), "R2": ("min_edge_support", 0.02),
             "R3": ("area_frac", 0.002), "R4": ("side_frac", 0.05),
             "R5": ("approx_eps", 0.050), "R6": ("vertex_max", 6),
             "R7": ("perimeter_floor", 60.0), "R8": ("require_convex", False),
             "R9": ("contour_source", "mask")}
    for params in GRID[1:]:
        field, value = moved[params.cell]
        assert getattr(params, field) == value
        differing = [item.name for item in fields(base) if item.name != "cell"
                     and getattr(params, item.name) != getattr(base, item.name)]
        assert differing == [field], (params.cell, differing)


def test_match_is_one_to_one_within_eight_px_and_never_reuses_a_truth_point():
    assert MATCH_RADIUS_PX == 8.0
    truth = [(100.0, 100.0)]
    points = [("LANE_BASE_L", 100.0, 100.0), ("LANE_BASE_R", 102.0, 100.0)]
    assert on_player(points, truth) == 1                       # one truth point, one match only
    assert on_player([("KEY_TOP", 100.0, 108.5)], truth) == 0   # 8.5 px is outside the radius
    assert on_player([("KEY_TOP", 100.0, 108.0)], truth) == 1   # 8.0 px is inside it
    assert on_player([], truth) == 0 and on_player(points, []) == 0


def test_frame_rule_and_bars_are_the_sealed_ones():
    assert (MIN_NAMES, MIN_STRUCTURES, MAX_FALSE, READY_FRAMES_BAR) == (6, 3, 12, 12)
    assert frame_ready({"n_named_landmarks": 6, "n_structures": 3, "n_false_proposals": 12})
    assert not frame_ready({"n_named_landmarks": 5, "n_structures": 3, "n_false_proposals": 12})
    assert not frame_ready({"n_named_landmarks": 6, "n_structures": 2, "n_false_proposals": 12})
    assert not frame_ready({"n_named_landmarks": 6, "n_structures": 3, "n_false_proposals": 13})


def test_semantic_map_ceiling_is_five_names_over_two_structures():
    """Premise P3: the map alone puts the >= 6-names / >= 3-structures rule out of reach."""
    names = sorted(set(SEMANTIC_MAP.values()))
    structures = sorted({VOCABULARY[name] for name in names})
    assert len(SEMANTIC_MAP) == 6 and names == [
        "FT_LINE_L", "FT_LINE_R", "KEY_TOP", "LANE_BASE_L", "LANE_BASE_R"]
    assert structures == ["free_throw_line", "lane_boundary"]
    assert len(names) < MIN_NAMES and len(structures) < MIN_STRUCTURES
    assert mapped({"center_circle": (1.0, 2.0, 0.5)}) == []    # unmapped keys are dropped


def test_first_zero_distribution_is_not_unique_and_no_stage_reaches_the_cause_bar():
    """Fix 1b (verifier CORRECTION): the killing stage per frame is whichever hits zero FIRST,
    not whichever is zero cumulatively downstream. CAUSE NOT UNIQUE -- 3/24 quad_ok, 10/24 area,
    11/24 side, and no single stage reaches the spec's 20/24 cause bar, even though cumulative
    side==0 is 24/24 (`G321_spec.md:85-90`; `keypoints.py:36`, `:41`, `:87`)."""
    with open(CELLS_CSV, newline="") as handle:
        rows = [row for row in csv.DictReader(handle) if row["cell"] == "R0"]
    assert len(rows) == 24
    first_zero = Counter()
    for row in rows:
        for stage in STAGES:
            if int(row["stage_" + stage]) == 0:
                first_zero[stage] += 1
                break
        else:
            first_zero["none"] += 1
    assert (first_zero["quad_ok"], first_zero["area"], first_zero["side"]) == (3, 10, 11)
    assert first_zero.get("none", 0) == 0
    assert max(first_zero.values()) < 20                                  # no stage reaches the bar
    assert sum(1 for row in rows if int(row["stage_side"]) == 0) == 24    # cumulative, not first-zero
