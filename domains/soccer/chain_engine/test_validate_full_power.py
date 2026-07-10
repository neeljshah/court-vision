"""Smallest runnable check for validate_full_power's aggregation math (the
only NEW logic in this module -- the panel functions themselves are reused
unchanged from validate.py / validate_extra_corpora.py and already covered
by test_validate.py). No data I/O: synthetic per-competition (delta, n)
pairs only.
"""
from __future__ import annotations

import numpy as np

from domains.soccer.chain_engine.validate_full_power import (
    assign_group, cluster_bootstrap_ci, GROUPS,
)


def test_assign_group_known_and_unknown():
    assert assign_group("Premier_League_2015_2016") == "mens_league"
    assert assign_group("NWSL_2023") == "womens_league"
    assert assign_group("UEFA_Euro_2024") == "international_tournament"
    assert assign_group("Some_Brand_New_League_2099") == "other"


def test_groups_are_disjoint():
    seen = set()
    for members in GROUPS.values():
        assert seen.isdisjoint(members), "a competition appears in two groups"
        seen.update(members)


def test_cluster_bootstrap_ci_reliable_positive_signal():
    # every "competition" shows the same clear positive delta -> CI should
    # sit entirely above 0 (reliable pooled win), not straddle it.
    deltas = [0.05, 0.06, 0.055, 0.048, 0.052]
    weights = [1000, 1000, 1000, 1000, 1000]
    lo, hi = cluster_bootstrap_ci(deltas, weights, n_boot=500, seed=0)
    assert lo > 0 and hi > 0
    assert lo <= hi


def test_cluster_bootstrap_ci_null_straddles_zero():
    # noisy near-zero deltas with mixed signs -> CI should straddle 0, the
    # signature of a NULL that holds at power.
    deltas = [0.001, -0.002, 0.0005, -0.0015, 0.0008]
    weights = [1000, 1000, 1000, 1000, 1000]
    lo, hi = cluster_bootstrap_ci(deltas, weights, n_boot=2000, seed=0)
    assert lo < 0 < hi


def test_cluster_bootstrap_ci_matches_weighted_mean_at_zero_variance():
    # identical deltas across "competitions" -> every bootstrap draw is the
    # same weighted mean, so CI collapses to a point equal to that mean.
    deltas = [0.03] * 6
    weights = [500, 700, 300, 900, 200, 600]
    lo, hi = cluster_bootstrap_ci(deltas, weights, n_boot=300, seed=1)
    assert abs(lo - 0.03) < 1e-9
    assert abs(hi - 0.03) < 1e-9
