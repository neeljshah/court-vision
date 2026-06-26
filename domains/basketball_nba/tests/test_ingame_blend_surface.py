"""Edge-case tests for domains/basketball_nba/ingame_blend_surface.py.

Run ONLY as:
    python -m pytest domains/basketball_nba/tests/test_ingame_blend_surface.py -q

NEVER run the full suite (it freezes the box).
"""
from __future__ import annotations

import numpy as np
import pytest

from scripts.platformkit.eval_gate.ingame_blend import WeightSurface
from domains.basketball_nba.ingame_blend_surface import (
    EDGE_CLAIMED,
    GT_MARGIN,
    GT_SECONDS,
    GT_LO,
    GT_HI,
    MARGIN_EDGES,
    TIME_EDGES,
    __all__,
    fit_surface_on_season,
    garbage_clamp,
    grid_monotone_score,
)


# --------------------------------------------------------------------------- honesty flag
def test_edge_claimed_false():
    assert EDGE_CLAIMED is False


# --------------------------------------------------------------------------- __all__ exports
def test_all_exports_include_public_names():
    required = {"garbage_clamp", "fit_surface_on_season", "TIME_EDGES", "MARGIN_EDGES", "EDGE_CLAIMED"}
    assert required.issubset(set(__all__))


# --------------------------------------------------------------------------- TIME_EDGES invariant
def test_time_edges_strictly_descending():
    for i in range(len(TIME_EDGES) - 1):
        assert TIME_EDGES[i] > TIME_EDGES[i + 1], (
            f"TIME_EDGES not descending at index {i}: {TIME_EDGES[i]} vs {TIME_EDGES[i+1]}"
        )


# --------------------------------------------------------------------------- MARGIN_EDGES invariant
def test_margin_edges_strictly_ascending():
    for i in range(len(MARGIN_EDGES) - 1):
        assert MARGIN_EDGES[i] < MARGIN_EDGES[i + 1], (
            f"MARGIN_EDGES not ascending at index {i}: {MARGIN_EDGES[i]} vs {MARGIN_EDGES[i+1]}"
        )


# --------------------------------------------------------------------------- garbage_clamp: boundary on margin
def test_garbage_clamp_margin_eq_gt_margin_triggers():
    # margin_abs == GT_MARGIN (18.0) AND sec_remaining < GT_SECONDS (120.0) -> triggers
    p = garbage_clamp(0.5, margin_abs=GT_MARGIN, sec_remaining=GT_SECONDS - 1.0, leader_is_home=True)
    assert p == GT_HI


def test_garbage_clamp_margin_just_below_gt_margin_no_trigger():
    # margin_abs = 17.999 < GT_MARGIN -> no trigger -> p clamped to [0,1]
    p = garbage_clamp(0.5, margin_abs=GT_MARGIN - 0.001, sec_remaining=GT_SECONDS - 1.0)
    assert p == pytest.approx(0.5)


# --------------------------------------------------------------------------- garbage_clamp: boundary on seconds
def test_garbage_clamp_sec_eq_gt_seconds_no_trigger():
    # sec_remaining == GT_SECONDS (120.0) -> condition is strict < -> no trigger
    p = garbage_clamp(0.5, margin_abs=GT_MARGIN + 5.0, sec_remaining=GT_SECONDS)
    assert p == pytest.approx(0.5)


def test_garbage_clamp_sec_just_below_gt_seconds_triggers():
    # sec_remaining = 119.999 < GT_SECONDS -> triggers (margin also >= GT_MARGIN)
    p = garbage_clamp(0.5, margin_abs=GT_MARGIN, sec_remaining=GT_SECONDS - 0.001, leader_is_home=False)
    assert p == GT_LO


# --------------------------------------------------------------------------- garbage_clamp: no-trigger path clamping
def test_garbage_clamp_no_trigger_p_above_one_clamps():
    p = garbage_clamp(1.5, margin_abs=2.0, sec_remaining=900.0)
    assert p == pytest.approx(1.0)


def test_garbage_clamp_no_trigger_p_below_zero_clamps():
    p = garbage_clamp(-0.3, margin_abs=2.0, sec_remaining=900.0)
    assert p == pytest.approx(0.0)


def test_garbage_clamp_no_trigger_p_in_range_unchanged():
    for val in [0.0, 0.3, 0.5, 0.7, 1.0]:
        p = garbage_clamp(val, margin_abs=2.0, sec_remaining=900.0)
        assert p == pytest.approx(val)


# --------------------------------------------------------------------------- garbage_clamp: leader_is_home
def test_garbage_clamp_leader_home_returns_hi():
    p = garbage_clamp(0.4, margin_abs=GT_MARGIN, sec_remaining=60.0, leader_is_home=True)
    assert p == GT_HI


def test_garbage_clamp_leader_away_returns_lo():
    p = garbage_clamp(0.4, margin_abs=GT_MARGIN, sec_remaining=60.0, leader_is_home=False)
    assert p == GT_LO


# --------------------------------------------------------------------------- garbage_clamp: custom thresholds
def test_garbage_clamp_custom_thresholds_fire_with_overrides():
    # Default thresholds would NOT trigger (margin=8 < 18, sec=200 > 120)
    # Custom: t_gt=5, s_gt=300 -> 8 >= 5 AND 200 < 300 -> triggers
    p = garbage_clamp(0.5, margin_abs=8.0, sec_remaining=200.0,
                      t_gt=5.0, s_gt=300.0, lo=0.05, hi=0.95, leader_is_home=True)
    assert p == pytest.approx(0.95)


def test_garbage_clamp_custom_thresholds_away():
    p = garbage_clamp(0.5, margin_abs=8.0, sec_remaining=200.0,
                      t_gt=5.0, s_gt=300.0, lo=0.05, hi=0.95, leader_is_home=False)
    assert p == pytest.approx(0.05)


def test_garbage_clamp_custom_thresholds_default_no_fire():
    # With defaults, margin=8, sec=200 should NOT trigger
    p = garbage_clamp(0.6, margin_abs=8.0, sec_remaining=200.0)
    assert p == pytest.approx(0.6)


# --------------------------------------------------------------------------- grid_monotone_score: empty surface
def test_grid_monotone_score_empty_surface():
    surf = WeightSurface()
    assert surf.grid == {}
    score = grid_monotone_score(surf)
    assert score == pytest.approx(1.0)


# --------------------------------------------------------------------------- grid_monotone_score: 1-cell surface
def test_grid_monotone_score_single_cell():
    surf = WeightSurface()
    surf.grid = {(0, 0): 0.5}
    score = grid_monotone_score(surf)
    assert score == pytest.approx(1.0)


# --------------------------------------------------------------------------- grid_monotone_score: fully non-decreasing 2x2
def test_grid_monotone_score_nondecreasing_2x2():
    surf = WeightSurface()
    # Grid: (0,0)->0.2, (0,1)->0.4, (1,0)->0.3, (1,1)->0.6
    # (0,0) neighbors: (1,0)=0.3>=0.2 ok, (0,1)=0.4>=0.2 ok
    # (0,1) neighbors: (1,1)=0.6>=0.4 ok
    # (1,0) neighbors: (1,1)=0.6>=0.3 ok
    surf.grid = {(0, 0): 0.2, (0, 1): 0.4, (1, 0): 0.3, (1, 1): 0.6}
    score = grid_monotone_score(surf)
    assert score == pytest.approx(1.0)


# --------------------------------------------------------------------------- grid_monotone_score: violating grid
def test_grid_monotone_score_violation_less_than_one():
    surf = WeightSurface()
    # (0,0)->0.8, (1,0)->0.2 -> (1,0) < (0,0): violation (neighbor at t+1 should be >= t)
    surf.grid = {(0, 0): 0.8, (1, 0): 0.2}
    score = grid_monotone_score(surf)
    assert score < 1.0


def test_grid_monotone_score_violation_count():
    surf = WeightSurface()
    # Two pairs: (0,0)->(1,0) is 0.9->0.1 (violation), (0,1)->(1,1) is 0.3->0.7 (ok)
    surf.grid = {(0, 0): 0.9, (1, 0): 0.1, (0, 1): 0.3, (1, 1): 0.7}
    score = grid_monotone_score(surf)
    # Pairs: (0,0)->(1,0) FAIL, (0,0)->(0,1) 0.3>=0.9? NO FAIL,
    # (1,0)->(1,1) 0.7>=0.1 OK, (0,1)->(1,1) 0.7>=0.3 OK
    # total=4, ok=2 -> score=0.5
    assert 0.0 <= score < 1.0


# --------------------------------------------------------------------------- fit_surface_on_season: no qualifying cells
def test_fit_surface_on_season_no_qualifying_cells():
    # min_cell=9999 means no cell with < 9999 samples qualifies -> empty grid
    states = [
        {"p0": 0.5, "p_live": 0.6, "seconds_remaining": 600.0,
         "score_diff": 5.0, "outcome": 1.0}
        for _ in range(10)
    ]
    surf = fit_surface_on_season(states, min_cell=9999)
    assert isinstance(surf, WeightSurface)
    assert surf.grid == {}
