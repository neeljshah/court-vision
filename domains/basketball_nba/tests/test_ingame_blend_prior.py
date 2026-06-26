"""Edge-case tests for domains/basketball_nba/ingame_blend_prior.py.

Run ONLY as:
    python -m pytest domains/basketball_nba/tests/test_ingame_blend_prior.py -q

NEVER run the full suite (it freezes the box).
"""
from __future__ import annotations

import numpy as np
import pytest

from domains.basketball_nba.ingame_blend_prior import (
    EDGE_CLAIMED,
    derive_p0,
    margins_from_sim,
    proj_margin,
)


# --------------------------------------------------------------------------- honesty flag
def test_edge_claimed_false():
    assert EDGE_CLAIMED is False


# --------------------------------------------------------------------------- margins_from_sim: shape mismatch
def test_margins_shape_mismatch_raises():
    with pytest.raises(ValueError, match="same shape"):
        margins_from_sim([1.0, 2.0, 3.0], [1.0, 2.0, 3.0, 4.0])


def test_margins_len3_vs_len4_raises():
    # Explicit len-3 vs len-4 scenario from the task spec
    h = np.array([100.0, 105.0, 110.0])
    a = np.array([99.0, 101.0, 103.0, 107.0])
    with pytest.raises(ValueError):
        margins_from_sim(h, a)


# --------------------------------------------------------------------------- margins_from_sim: empty
def test_margins_empty_raises():
    with pytest.raises(ValueError, match="empty"):
        margins_from_sim([], [])


def test_margins_both_empty_numpy_raises():
    with pytest.raises(ValueError, match="empty"):
        margins_from_sim(np.array([]), np.array([]))


# --------------------------------------------------------------------------- margins_from_sim: multidim ravel
def test_margins_ravel_2x3_and_3x2_match():
    # (2,3) and (3,2) both ravel to 6 -> shape matches -> no error
    h = np.ones((2, 3)) * 10.0
    a = np.ones((3, 2)) * 7.0
    result = margins_from_sim(h, a)
    assert result.shape == (6,)
    assert np.all(result == pytest.approx(3.0))


def test_margins_ravel_2x3_vs_2x4_raises():
    # (2,3)=6 elements vs (2,4)=8 elements -> shape mismatch after ravel
    h = np.ones((2, 3)) * 10.0
    a = np.ones((2, 4)) * 7.0
    with pytest.raises(ValueError):
        margins_from_sim(h, a)


def test_margins_ravel_preserves_difference():
    # (2,3) h vs (2,3) a -> should compute element-wise diff
    h = np.array([[100.0, 105.0, 110.0], [95.0, 100.0, 115.0]])
    a = np.array([[99.0, 99.0, 99.0], [100.0, 100.0, 100.0]])
    result = margins_from_sim(h, a)
    expected = (h - a).ravel()
    assert result == pytest.approx(expected)


# --------------------------------------------------------------------------- derive_p0: missing both inputs
def test_derive_p0_no_args_raises():
    with pytest.raises(ValueError, match="provide sim_result"):
        derive_p0(sim_result=None, home_total=None, away_total=None)


def test_derive_p0_only_home_total_raises():
    with pytest.raises(ValueError):
        derive_p0(home_total=np.array([100.0, 105.0]), away_total=None)


def test_derive_p0_only_away_total_raises():
    with pytest.raises(ValueError):
        derive_p0(home_total=None, away_total=np.array([99.0, 103.0]))


# --------------------------------------------------------------------------- derive_p0: all-ties
def test_derive_p0_all_ties_returns_half():
    # home_total == away_total elementwise -> all margins == 0 -> ties only
    arr = np.array([100.0, 105.0, 110.0, 115.0])
    p = derive_p0(home_total=arr, away_total=arr.copy())
    assert p == pytest.approx(0.5)


def test_derive_p0_ties_counted_as_half():
    # [10, -10, 0, 0] -> margins: home wins 1, losses 1, ties 2
    # p0 = (1 + 0.5*2) / 4 = 2.0/4 = 0.5
    h = np.array([110.0, 90.0, 100.0, 100.0])
    a = np.array([100.0, 100.0, 100.0, 100.0])
    p = derive_p0(home_total=h, away_total=a)
    assert p == pytest.approx(0.5)


def test_derive_p0_mixed_ties_asymmetric():
    # margins: [+5, +3, 0, 0] -> wins=2, ties=2
    # p0 = (2 + 1.0) / 4 = 0.75
    h = np.array([105.0, 103.0, 100.0, 100.0])
    a = np.array([100.0, 100.0, 100.0, 100.0])
    p = derive_p0(home_total=h, away_total=a)
    assert p == pytest.approx(0.75)


# --------------------------------------------------------------------------- derive_p0: duck-typed sim_result
def test_derive_p0_duck_typed_object():
    class _SimResult:
        home_total = np.array([105.0, 110.0, 115.0])
        away_total = np.array([100.0, 100.0, 100.0])

    p = derive_p0(_SimResult())
    assert p == pytest.approx(1.0)


def test_derive_p0_duck_typed_list_attrs():
    class _SimResult:
        home_total = [100.0, 105.0]
        away_total = [99.0, 103.0]

    p = derive_p0(_SimResult())
    assert p == pytest.approx(1.0)


def test_derive_p0_accepts_list_inputs():
    p = derive_p0(home_total=[110.0, 115.0], away_total=[99.0, 98.0])
    assert p == pytest.approx(1.0)


def test_derive_p0_accepts_numpy_inputs():
    p = derive_p0(home_total=np.array([110.0, 115.0]), away_total=np.array([99.0, 98.0]))
    assert p == pytest.approx(1.0)


# --------------------------------------------------------------------------- derive_p0: unanimous
def test_derive_p0_unanimous_wins_returns_one():
    h = np.full(500, 115.0)
    a = np.full(500, 100.0)
    p = derive_p0(home_total=h, away_total=a)
    assert p == pytest.approx(1.0)


def test_derive_p0_unanimous_losses_returns_zero():
    h = np.full(500, 95.0)
    a = np.full(500, 110.0)
    p = derive_p0(home_total=h, away_total=a)
    assert p == pytest.approx(0.0)


def test_derive_p0_returns_float():
    p = derive_p0(home_total=[110.0], away_total=[105.0])
    assert isinstance(p, float)
    assert 0.0 <= p <= 1.0


# --------------------------------------------------------------------------- proj_margin
def test_proj_margin_returns_median():
    # [+5, +3, -1] -> sorted [-1, 3, 5] -> median = 3
    h = np.array([105.0, 103.0, 99.0])
    a = np.array([100.0, 100.0, 100.0])
    m = proj_margin(h, a)
    assert m == pytest.approx(3.0)


def test_proj_margin_asymmetric_distribution():
    # margins [10, 2, -1, -2, -3] sorted -> [-3,-2,-1,2,10] -> median = -1
    h = np.array([110.0, 102.0, 99.0, 98.0, 97.0])
    a = np.full(5, 100.0)
    m = proj_margin(h, a)
    assert m == pytest.approx(-1.0)


def test_proj_margin_single_element():
    m = proj_margin([108.0], [100.0])
    assert m == pytest.approx(8.0)


def test_proj_margin_returns_float():
    m = proj_margin([110.0, 105.0], [100.0, 100.0])
    assert isinstance(m, float)
