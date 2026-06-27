"""Negative control (d): eps_eff strictly decreasing in K; K cumulative across cycles."""
from __future__ import annotations

import pytest

from scripts.platformkit.combo.fwer_budget import (
    cumulative_k, eps_eff, fdr_budget, min_corpora_eff,
)


def test_eps_eff_monotone_decreasing():
    ks = [1, 2, 4, 8, 16, 64, 256]
    vals = [eps_eff(0.05, k) for k in ks]
    assert vals[0] == pytest.approx(0.05)
    # strictly decreasing as K grows
    for a, b in zip(vals, vals[1:]):
        assert b < a
    # matches the doc curve
    assert eps_eff(0.05, 4) == pytest.approx(0.0125)
    assert eps_eff(0.05, 256) == pytest.approx(0.05 / 256)


def test_eps_eff_clamps_k_and_validates_eps():
    assert eps_eff(0.05, 0) == pytest.approx(0.05)   # K<1 does not loosen
    assert eps_eff(0.05, -3) == pytest.approx(0.05)
    with pytest.raises(ValueError):
        eps_eff(0.0, 4)
    with pytest.raises(ValueError):
        eps_eff(1.5, 4)


def test_min_corpora_rises_then_caps():
    # 2 at K=1, 3 at K=2..3, 4 at K=4.., capped at 4 -- but never above n_available
    assert min_corpora_eff(10, 1) == 2
    assert min_corpora_eff(10, 2) == 3
    assert min_corpora_eff(10, 3) == 3
    assert min_corpora_eff(10, 4) == 4
    assert min_corpora_eff(10, 256) == 4          # capped
    # never demands more corpora than exist (R14 over-tightening guard)
    assert min_corpora_eff(2, 256) == 2
    # SAFETY (pre-flag-flip): the replication floor can NEVER collapse to 1, even when a
    # candidate claims a single corpus (n_corpora=1). A flipped sentinel must not ship a
    # one-corpus fusion via min_corpora_eff dropping to 1 -- the floor stays >=2 at every K.
    assert min_corpora_eff(1, 1) == 2
    assert min_corpora_eff(1, 256) == 2
    assert min_corpora_eff(0, 1) == 2
    assert all(min_corpora_eff(1, k) >= 2 for k in (1, 2, 4, 16, 256))


def test_curve_bites_a_borderline_combo():
    """A DM p that clears the bar at K=1 FAILS at K=256 with the same p (the curve bites)."""
    dm_p = 0.04
    assert dm_p < eps_eff(0.05, 1)        # ships at K=1
    assert dm_p > eps_eff(0.05, 256)      # rejected at K=256, same p


def test_fdr_budget_tracks_eps_eff():
    for k in (1, 4, 16, 256):
        assert fdr_budget(0.05, k) == eps_eff(0.05, k)


def test_k_cumulative_across_cycles():
    """Splitting a search across cycles cannot reset the budget (R13)."""
    # cycle 1 enumerates 100 deduped, cycle 2 enumerates 156 deduped
    k1 = cumulative_k(0, 100)
    k2 = cumulative_k(k1, 156)
    assert k1 == 100 and k2 == 256
    # the cumulative bar is STRICTER than either single cycle's bar
    assert eps_eff(0.05, k2) < eps_eff(0.05, 100)
    assert eps_eff(0.05, k2) < eps_eff(0.05, 156)
    # negatives clamp to 0
    assert cumulative_k(-5, -7) == 0
