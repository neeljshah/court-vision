"""Negative control (b): >=20 shuffled nulls REJECT; fdr_hat<=budget; weak gate -> FROZEN.

The lane routes each null through the IDENTICAL combo gate object (same-object assert).
"""
from __future__ import annotations

from scripts.platformkit.combo.combo_gate import SHIP, ComboVerdict
from scripts.platformkit.combo.fwer_budget import fdr_budget
from scripts.platformkit.combo.planted_null_fdr import (
    ran_through_identical_gate, run_family_nulls,
)


def test_lane_uses_identical_gate_object():
    assert ran_through_identical_gate() is True


def test_twenty_nulls_reject_fdr_within_budget():
    """>=20 shuffled-label combos through the REAL gate: none ship, fdr_hat<=budget."""
    res = run_family_nulls("interaction", n=20, n_games=40, ticks=8, seed=1234,
                           eps=0.05, K=1)
    assert res.n_run == 20
    assert res.n_shipped == 0, res
    assert res.fdr_hat == 0.0
    assert res.fdr_hat <= res.budget == fdr_budget(0.05, 1)
    assert res.frozen is False


def test_n_below_floor_is_raised_to_20():
    res = run_family_nulls("interaction", n=5, n_games=30, ticks=6)
    assert res.n_run >= 20            # power floor enforced


def test_weakened_gate_ships_a_null_and_freezes_family():
    """A DELIBERATELY weakened gate (always SHIP) -> a null ships -> the family FREEZES.

    This proves the tripwire fires: if a future change makes the gate manufacture ships,
    the planted-null lane catches it (frozen True) before any real false positive serves.
    """
    def weak_gate(*a, **k):
        return ComboVerdict(SHIP, "weakened: always ships (test-injected)")

    res = run_family_nulls("interaction", n=20, n_games=30, ticks=6, gate=weak_gate)
    assert res.n_shipped == res.n_run
    assert res.fdr_hat == 1.0
    assert res.fdr_hat > res.budget
    assert res.frozen is True


def test_every_null_crashing_fails_closed():
    """20/20 crashed nulls measured NOTHING -> no rate, and the family FREEZES.

    Counting a crash as a conservative non-ship let the lane report
    fdr_hat=0.0 / n_shipped=0 / frozen=False -- "the gate is not manufacturing
    ships" having scored nothing at all.
    """
    def broken_gate(*a, **k):
        raise RuntimeError("gate blew up")

    res = run_family_nulls("interaction", n=20, n_games=20, ticks=4, gate=broken_gate)
    assert res.n_run == 20
    assert res.n_error == 20          # crashes are COUNTED, not silently absorbed
    assert res.n_shipped == 0
    assert res.fdr_hat is None        # no scorable null -> no rate (never 0.0)
    assert res.frozen is True         # fail CLOSED
