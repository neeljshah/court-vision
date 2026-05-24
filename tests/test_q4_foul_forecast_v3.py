"""test_q4_foul_forecast_v3.py -- cycle 98a (loop 5).

Validates the fractional-band-blend v3 Q4 PF forecast applicator.
v3 keeps v2's NNLS forecast head; it replaces the round-down
integerization with a fractional weighted blend between adjacent
foul_trouble_factor bands.
"""
from __future__ import annotations

import os
import sys

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from src.prediction.live_factors import foul_trouble_factor  # noqa: E402
from src.prediction.q4_foul_forecast_v3 import (  # noqa: E402
    fractional_band_factor,
    fractional_factor_for_snapshot,
)


# ── core blend properties ─────────────────────────────────────────────────────

def test_frac_zero_returns_band_spf_exactly():
    """frac == 0 -> factor must equal band(spf) exactly (true no-op)."""
    # spf=3, Q3 endgame (clock=0): band(3)=1.0 per canonical table.
    f = fractional_band_factor(spf=3, forecast_pf_add=0.0, period=3,
                                clock_min=0.0)
    assert f == foul_trouble_factor(3, 3, 0.0), (
        f"expected exact band(3) match, got {f}")
    # spf=4, Q3: band(4) = 0.55. Whole=0, frac=0.0 -> exact band(4).
    f2 = fractional_band_factor(spf=4, forecast_pf_add=0.0, period=3,
                                 clock_min=0.0)
    assert f2 == foul_trouble_factor(4, 3, 0.0)


def test_frac_one_returns_band_spf_plus_1_exactly():
    """frac == 1 (i.e. forecast=1.0 exact) -> whole=1, frac=0 -> band(spf+1)."""
    # spf=3, forecast=1.0: whole=1, frac=0 -> band(4)
    f = fractional_band_factor(spf=3, forecast_pf_add=1.0, period=3,
                                clock_min=0.0)
    assert f == foul_trouble_factor(4, 3, 0.0), (
        f"expected band(4) = {foul_trouble_factor(4, 3, 0.0)}, got {f}")
    # spf=2, forecast=1.0: whole=1, frac=0 -> band(3) (= 1.0 for non-Q2)
    f2 = fractional_band_factor(spf=2, forecast_pf_add=1.0, period=4,
                                 clock_min=8.0)
    assert f2 == foul_trouble_factor(3, 4, 8.0)


def test_frac_half_returns_midpoint():
    """frac == 0.5 -> factor = 0.5 * (band(spf+whole) + band(spf+whole+1))."""
    # spf=3, forecast=0.5: whole=0, frac=0.5 -> 0.5*band(3) + 0.5*band(4)
    lo = foul_trouble_factor(3, 3, 0.0)   # 1.0 (no foul trouble at pf=3 Q3)
    hi = foul_trouble_factor(4, 3, 0.0)   # 0.55
    expected = 0.5 * lo + 0.5 * hi
    f = fractional_band_factor(spf=3, forecast_pf_add=0.5, period=3,
                                clock_min=0.0)
    assert abs(f - expected) < 1e-9, (
        f"expected {expected:.6f}, got {f:.6f}")


def test_spf_at_max_no_blend_past_foulout():
    """spf=5 hits band(5)=0.40; spf+1=6 also returns 0.40 (>=5 rule)."""
    # spf=5: any frac -> 0.40 (band(5)==band(6) in the canonical table).
    f_zero = fractional_band_factor(spf=5, forecast_pf_add=0.0, period=4,
                                     clock_min=5.0)
    f_half = fractional_band_factor(spf=5, forecast_pf_add=0.5, period=4,
                                     clock_min=5.0)
    f_one = fractional_band_factor(spf=5, forecast_pf_add=1.0, period=4,
                                    clock_min=5.0)
    assert f_zero == 0.40
    assert f_half == 0.40
    assert f_one == 0.40
    # spf=6 (already fouled out): identical floor.
    assert fractional_band_factor(6, 0.7, 4, 3.0) == 0.40


def test_gate_off_falls_back_to_baseline():
    """Below either gate floor, the snapshot helper must return the plain
    band lookup -- no forecast applied. This guarantees v3 is a true
    no-op for low-foul / low-minutes players (same projections as
    cycle 88b baseline)."""
    # pf=1: below GATE_MIN_PF=2. Should return plain band(1) = 1.0.
    f = fractional_factor_for_snapshot(
        pf_through_q3=1, q3_pf=0, min_q3=24.0, position_proxy="Guard",
        period=4, clock_min=10.0)
    assert f == foul_trouble_factor(1, 4, 10.0)
    assert f == 1.0  # band(1) anywhere is 1.0

    # min_q3=4.0: below GATE_MIN_Q3=6.0. Should return plain band(3) = 1.0.
    f2 = fractional_factor_for_snapshot(
        pf_through_q3=3, q3_pf=1, min_q3=4.0, position_proxy="Forward",
        period=4, clock_min=10.0)
    assert f2 == foul_trouble_factor(3, 4, 10.0)


def test_smoke_fixture_player_factor_in_range():
    """Smoke: apply v3 to one realistic fixture; factor must land in a
    sensible (0.40, 1.00] range -- never below band(5)=0.40 (foul-out
    floor) and never above 1.0 (no boost from being foul-troubled)."""
    # Realistic Q3-endgame foul-trouble case: pf=3, min_q3=8 (passes gate),
    # forward, opponent foul rate at league average.
    f = fractional_factor_for_snapshot(
        pf_through_q3=3, q3_pf=1, min_q3=8.0, position_proxy="Forward",
        period=4, clock_min=12.0, opp_foul_rate_l5=20.0)
    assert 0.40 < f <= 1.00, (
        f"factor {f} outside expected (0.40, 1.00] for pf=3 Q3-endgame")

    # Center @ pf=3 with high opp foul rate -- should pull factor LOWER
    # than the equivalent forward case (centers get the is_center lift).
    f_center = fractional_factor_for_snapshot(
        pf_through_q3=3, q3_pf=1, min_q3=8.0, position_proxy="Center",
        period=4, clock_min=12.0, opp_foul_rate_l5=22.0)
    assert f_center <= f, (
        f"center factor {f_center:.4f} should be <= forward factor "
        f"{f:.4f} (centers forecast more PF -> bigger band shift)")


# ── regression guard ──────────────────────────────────────────────────────────

def test_non_foul_player_unchanged():
    """Player below the gate (pf=0, min_q3=10) projects with the EXACT
    same foul_factor as the cycle-88b baseline -- not a fractional blend.
    This is the non-foul stratum no-regression guarantee at unit-test
    granularity."""
    baseline = foul_trouble_factor(0, 4, 10.0)  # 1.0
    v3 = fractional_factor_for_snapshot(
        pf_through_q3=0, q3_pf=0, min_q3=10.0, position_proxy="Guard",
        period=4, clock_min=10.0)
    assert v3 == baseline


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-q"]))
