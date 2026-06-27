"""Per-file test: fusion_planted_nulls -- shuffled-label fused nulls REJECT; freeze fires."""
from __future__ import annotations

from scripts.platformkit.improve.fusion.fusion_planted_nulls import (
    all_family_names, frozen_families, ran_through_identical_gate,
    run_fusion_family_nulls,
)


def test_runs_through_the_identical_gate_object():
    """No parallel stub: the null lane's default gate IS the production combo gate."""
    assert ran_through_identical_gate() is True


def test_shuffled_label_fused_null_does_not_ship():
    """A shuffled-OUTCOME-label fused model must NOT ship (does not replicate)."""
    r = run_fusion_family_nulls("FAMILY_STACK_OOF", n=20, n_games=40, ticks=6, seed=11)
    assert r.n_run >= 20
    assert r.n_shipped == 0, r
    assert r.frozen is False
    assert r.fdr_hat <= r.budget


def test_forced_ship_freezes_the_family():
    """A deliberately-WEAKENED gate that ships a null FREEZES the family (tripwire fires)."""
    class _Verdict:
        verdict = "SHIP"

    def weak_gate(*_a, **_k):
        return _Verdict()

    r = run_fusion_family_nulls("FAMILY_REGIME_MOE", n=20, n_games=30, ticks=4,
                                seed=3, gate=weak_gate)
    assert r.n_shipped == r.n_run
    assert r.frozen is True
    assert frozen_families([r]) == ["FAMILY_REGIME_MOE"]


def test_all_families_covered():
    fams = all_family_names()
    assert set(fams) == {"FAMILY_STACK_OOF", "FAMILY_REGIME_MOE",
                         "FAMILY_RESID_BOOST", "FAMILY_REFUSE_CAL"}
