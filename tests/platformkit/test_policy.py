"""Per-file unit tests for pm_trading.policy (PURE -- no IO, no network).

Run ONLY this file (a bare pytest freezes the box):
    python -m pytest tests/platformkit/test_policy.py -q

Asserts: tier() is monotonic in EV and returns A/B/C/None at the pre-registered
floors; below-floor -> None; clv_is_proxy raises every floor; stake_units returns
BOTH keys; flat_unit is 1.0 for a tiered bet and 0.0 for None; quarter_kelly
matches risk.py's Kelly applied to the implied price.
"""
import math

from scripts.platformkit.pm_trading import policy
from scripts.platformkit.pm_trading.risk import (
    KELLY_FRACTION, kelly_fraction_binary)
from scripts.platformkit.pm_trading.venues.base import Side


def test_tier_at_each_floor():
    assert policy.tier(ev=policy.EV_FLOOR_A) == "A"
    assert policy.tier(ev=policy.EV_FLOOR_B) == "B"
    assert policy.tier(ev=policy.EV_FLOOR_C) == "C"
    # Strongest EV still A; well above all floors.
    assert policy.tier(ev=0.50) == "A"


def test_below_floor_is_none():
    assert policy.tier(ev=policy.EV_FLOOR_C - 1e-6) is None
    assert policy.tier(ev=0.0) is None
    assert policy.tier(ev=-0.10) is None


def test_tier_monotonic_in_ev():
    grid = [round(-0.05 + 0.005 * i, 4) for i in range(30)]
    rank = {None: 0, "C": 1, "B": 2, "A": 3}
    prev = -1
    for ev in grid:
        r = rank[policy.tier(ev=ev)]
        assert r >= prev, "tier dropped as EV rose at ev=%r" % ev
        prev = r


def test_clv_proxy_raises_floors():
    # An EV that is exactly tier-C on a true close must DROP below floor when the
    # close is only a proxy (floors bumped by EV_PROXY_PENALTY).
    ev = policy.EV_FLOOR_C
    assert policy.tier(ev=ev, clv_is_proxy=False) == "C"
    assert policy.tier(ev=ev, clv_is_proxy=True) is None
    # And the bumped floor is exactly clearable.
    assert policy.tier(ev=ev + policy.EV_PROXY_PENALTY, clv_is_proxy=True) == "C"


def test_bad_probabilities_block_bet():
    assert policy.tier(ev=0.20, model_prob=1.5) is None
    assert policy.tier(ev=0.20, market_prob=-0.1) is None
    assert policy.tier(ev=0.20, model_prob=float("nan")) is None
    assert policy.tier(ev=float("nan")) is None
    # Valid probabilities pass through.
    assert policy.tier(ev=0.20, model_prob=0.6, market_prob=0.5) == "A"


def test_stake_units_returns_both_keys():
    out = policy.stake_units(ev=0.20, model_prob=0.6, taken_decimal=2.0,
                             tier="A")
    assert set(out.keys()) == {"flat_unit", "quarter_kelly"}


def test_flat_unit_one_for_tiered_zero_for_none():
    tiered = policy.stake_units(ev=0.10, model_prob=0.6, taken_decimal=2.0,
                                tier="A")
    assert tiered["flat_unit"] == 1.0
    none = policy.stake_units(ev=0.0, model_prob=0.6, taken_decimal=2.0,
                              tier=None)
    assert none["flat_unit"] == 0.0
    assert none["quarter_kelly"] == 0.0


def test_quarter_kelly_matches_risk():
    p, dec = 0.60, 2.0          # fair 0.60 vs implied price 0.50
    out = policy.stake_units(ev=p * dec - 1.0, model_prob=p,
                             taken_decimal=dec, tier="A")
    expected = kelly_fraction_binary(p, 1.0 / dec, Side.BUY, corr=0.0,
                                     kelly_fraction=KELLY_FRACTION)
    assert math.isclose(out["quarter_kelly"], expected, rel_tol=1e-12)
    assert expected > 0.0       # this case has a positive Kelly fraction


def test_quarter_kelly_zero_when_no_edge():
    # Implied price (0.50) above fair prob (0.40) -> no positive Kelly.
    out = policy.stake_units(ev=0.40 * 2.0 - 1.0, model_prob=0.40,
                             taken_decimal=2.0, tier="C")
    assert out["quarter_kelly"] == 0.0
    # Flat unit still 1 because the row WAS tiered.
    assert out["flat_unit"] == 1.0


def test_floors_for_helper():
    base = policy.floors_for(clv_is_proxy=False)
    proxy = policy.floors_for(clv_is_proxy=True)
    assert base == {"A": policy.EV_FLOOR_A, "B": policy.EV_FLOOR_B,
                    "C": policy.EV_FLOOR_C}
    for k in ("A", "B", "C"):
        assert math.isclose(proxy[k], base[k] + policy.EV_PROXY_PENALTY)
