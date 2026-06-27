"""Per-file test: honesty_mw units-rail exemption + real-$ still trips.

Regression: the bare "stake" forbidden token (added 2026-06-19) blocked every
bestbets/quant response carrying the canonical UNITS field stake_units, returning
a 500 fail-closed sentinel. stake_units / stake_a / stake_b are the units rail and
must NOT trip; stake_dollars / stake_usd / roi / pnl MUST still trip.
"""
from predict_service.honesty_mw import _money_key_violations


def _keys(viol):
    return {v["where"].rsplit(".", 1)[-1] for v in viol}


def test_units_rail_keys_do_not_trip():
    obj = {"bets": [{"stake_units": 1.5, "tier": "C", "units": 1.5},
                    {"stake_a": 1.0, "stake_b": 1.2}]}
    viol = _money_key_violations(obj, "/api/v1/bestbets/nba")
    assert viol == [], "units-rail keys must not trip the $ guard: %r" % viol


def test_real_dollar_keys_still_trip():
    obj = {"row": {"stake_dollars": 100.0, "stake_usd": 50.0,
                   "roi": 0.1, "total_pnl": 5.0, "bankroll": 1000}}
    viol = _money_key_violations(obj, "/x")
    hit = _keys(viol)
    for k in ("stake_dollars", "stake_usd", "roi", "total_pnl", "bankroll"):
        assert k in hit, "%s must still trip but did not: %r" % (k, hit)


def test_stake_units_with_roi_sibling_still_trips_roi_only():
    # A units key is forgiven, but a $/roi key in the same object still trips.
    obj = {"stake_units": 2.0, "paper_roi": 0.2}
    viol = _money_key_violations(obj, "/x")
    hit = _keys(viol)
    assert "stake_units" not in hit
    assert "paper_roi" in hit


def test_bare_stake_key_still_trips():
    # A bare ambiguous "stake" with no units token is still treated as $.
    obj = {"stake": 100.0}
    viol = _money_key_violations(obj, "/x")
    assert "stake" in _keys(viol)
