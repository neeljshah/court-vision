"""Per-file test: combination_enum dedup + K-cap + screen-slice disjointness + choke.

A tried id is never re-rolled; the K-cap is honored (and tightens with cumulative K);
the screen slice is asserted disjoint from the CV folds; the build path goes through the
choke only (sentinel-absent -> []); determinism.
"""
from __future__ import annotations

import numpy as np
import pytest

from scripts.platformkit.combo.combination_families import all_combination_specs
from scripts.platformkit.combo.combination_enum import (
    ScreenColumns, assert_screen_disjoint, build_combination_candidates,
    enumerate_combination_specs, fwer_budget_remaining, k_cap, screen_score,
)

_HANDLES = ("run_diff", "pace_so_far", "poss_since_lead_change", "possessions_elapsed")


def _specs():
    return all_combination_specs("nba", "home_win", _HANDLES)


def test_tried_never_rerolled():
    specs = _specs()
    first = enumerate_combination_specs(specs, prior_k=0)
    assert first
    tried = {first[0].combo_id}
    again = enumerate_combination_specs(specs, tried_ids=tried, prior_k=0)
    assert all(s.combo_id != first[0].combo_id for s in again)


def test_k_cap_honored_and_tightens():
    specs = _specs()
    out = enumerate_combination_specs(specs, prior_k=0)
    assert len(out) <= k_cap(0)
    # a large cumulative prior_k drives the budget toward zero (stricter as search widens)
    assert fwer_budget_remaining(100) == 0
    out2 = enumerate_combination_specs(specs, prior_k=100)
    assert out2 == []


def test_screen_disjointness_tripwire():
    with pytest.raises(AssertionError):
        assert_screen_disjoint([1, 2, 3], [3, 4, 5])
    assert_screen_disjoint([1, 2, 3], [4, 5, 6])  # disjoint -> no raise


def test_enum_asserts_screen_disjoint():
    specs = _specs()
    rng = np.random.default_rng(0)
    n = 100
    combo = rng.normal(size=n)
    target = rng.normal(size=n)
    screen_idx = np.arange(0, 50)
    cv_idx = np.arange(50, 100)

    def screen_of(_spec):
        return ScreenColumns(combo, target, screen_idx)

    # disjoint -> ok
    enumerate_combination_specs(specs, screen_of=screen_of, cv_fold_idx=cv_idx, prior_k=0)
    # overlapping -> tripwire
    with pytest.raises(AssertionError):
        enumerate_combination_specs(specs, screen_of=screen_of,
                                    cv_fold_idx=np.arange(40, 90), prior_k=0)


def test_collinear_combo_dropped_by_screen():
    rng = np.random.default_rng(1)
    n = 200
    base = rng.normal(size=n)
    combo = base * 1.0001  # ~perfectly collinear with the base column
    target = rng.normal(size=n)
    idx = np.arange(n)
    cols = ScreenColumns(combo, target, idx, base_cols=(base,))
    assert screen_score(cols) is None  # collinear-with-base -> dropped


def test_build_path_choke_only():
    specs = _specs()[:3]
    # the real choke returns None while the sentinel is absent -> [] (NO_CANDIDATE)
    out = build_combination_candidates(specs, build_fn=lambda _s: None)
    assert out == []
    # a stub choke that returns a dict is the ONLY path that yields candidates
    out2 = build_combination_candidates(specs, build_fn=lambda s: {"id": s.combo_id})
    assert len(out2) == len(specs)


def test_determinism():
    specs = _specs()
    a = enumerate_combination_specs(specs, prior_k=0, seed=7)
    b = enumerate_combination_specs(specs, prior_k=0, seed=7)
    assert [s.combo_id for s in a] == [s.combo_id for s in b]
