"""Per-file test: combination planted nulls REJECT through the IDENTICAL gate.

The lane routes shuffled-label combos for every family through the production gate
object (same-object assertion); a shuffled-label combination null does NOT ship; if a
null shipped the family would be FROZEN.
"""
from __future__ import annotations

from scripts.platformkit.combo.combination_families import FAMILIES
from scripts.platformkit.combo.combination_planted_nulls import (
    all_nulls_reject, frozen_families, ran_through_identical_gate,
    run_all_family_nulls,
)


def test_ran_through_identical_gate():
    assert ran_through_identical_gate() is True


def test_all_family_nulls_reject():
    # small but >= the lane's power floor (20); a structureless shuffled label cannot
    # replicate cross-corpus, so every family's fdr_hat must be 0 and none frozen.
    res = run_all_family_nulls(n=20, n_games=40, ticks=6, K=1)
    assert set(res) == set(FAMILIES)
    for fam, r in res.items():
        assert r.n_shipped == 0, (fam, r)
        assert r.fdr_hat == 0.0, (fam, r)
    assert all_nulls_reject(res) is True
    assert frozen_families(res) == []
