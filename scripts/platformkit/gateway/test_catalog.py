"""Tests for scripts.platformkit.gateway.catalog -- the all_honest runtime tripwire.

catalog.all_honest() is the single honesty bit the whole gateway is judged on
(see no-edge-claims rule). It had ZERO tests before this file. Covers:
  (a) a retracted number in a probed body flips the verdict False
  (b) money-key detection matches the ACTUAL code (units-rail exemption is
      narrow: stake_units/stake_a/stake_b pass, bare stake/roi/pnl/$ keys fail)
  (c) all_honest() is green on the real FACES catalog (no faces, no probe)
  (d) a poisoned probe row (retracted number) makes all_honest() fail

Stdlib + pytest only. Per-file run:
  python -m pytest scripts/platformkit/gateway/test_catalog.py -q
"""
from __future__ import annotations

from scripts.platformkit.gateway.catalog import (
    all_honest,
    catalog,
    _has_money_key,
    _has_retracted_number,
)


# --------------------------------------------------------------------------- #
# (a) retracted numbers
# --------------------------------------------------------------------------- #
def test_retracted_number_flags_top_level():
    assert _has_retracted_number({"vs_close": 18.38}) is True


def test_retracted_number_flags_nested():
    assert _has_retracted_number({"a": {"b": [1, 2, {"c": 0.119}]}}) is True


def test_retracted_number_all_six_flagged():
    for r in (18.38, 0.119, 54.0, 78.11, 8.94, 54.57):
        assert _has_retracted_number({"x": r}) is True, r


def test_retracted_number_clean_body_not_flagged():
    assert _has_retracted_number({"win_prob": 0.539, "edge_claimed": False}) is False


def test_retracted_number_bool_not_misread_as_number():
    # bool is a subclass of int -- must not accidentally match a retracted value.
    assert _has_retracted_number({"serveable": True}) is False


# --------------------------------------------------------------------------- #
# (b) money-key detection -- assert what the code DOES, not a guess
# --------------------------------------------------------------------------- #
def test_money_key_bare_stake_flags():
    # bare "stake" is a forbidden token; not on the units-exempt list.
    assert _has_money_key({"stake": 5}) is True


def test_money_key_stake_units_is_exempt():
    # canonical units-rail field -- must NOT trip the honesty bit.
    assert _has_money_key({"stake_units": 5}) is False


def test_money_key_stake_a_stake_b_exempt():
    # two-leg arb unit stakes -- units rail, not $.
    assert _has_money_key({"stake_a": 5, "stake_b": 3}) is False


def test_money_key_stake_dollars_and_usd_still_flag():
    # explicit $ keys are NOT exempt even though they share the "stake" token.
    assert _has_money_key({"stake_dollars": 5}) is True
    assert _has_money_key({"stake_usd": 5}) is True


def test_money_key_roi_pnl_bankroll_flag():
    assert _has_money_key({"roi": 1.2}) is True
    assert _has_money_key({"pnl": 100}) is True
    assert _has_money_key({"bankroll": 1000}) is True


def test_money_key_clean_body_not_flagged():
    assert _has_money_key({"win_prob": 0.55, "units": "probability"}) is False


def test_money_key_nested_and_in_list():
    assert _has_money_key({"a": {"b": {"roi": 1}}}) is True
    assert _has_money_key({"a": [1, {"pnl": 1}]}) is True


# --------------------------------------------------------------------------- #
# (c) all_honest() is green on the real, current catalog
# --------------------------------------------------------------------------- #
def test_all_honest_green_on_real_catalog():
    verdict = all_honest()
    assert verdict["ok"] is True
    assert verdict["violations"] == []
    assert verdict["n_faces"] > 0


def test_catalog_payload_carries_no_number_and_no_edge():
    payload = catalog()
    assert payload["edge_claimed"] is False
    assert payload["real_money_enabled"] is False
    assert payload["units"] == "probability"
    assert payload["count"] == all_honest()["n_faces"]


# --------------------------------------------------------------------------- #
# (d) a poisoned row fails the verdict
# --------------------------------------------------------------------------- #
def test_all_honest_poisoned_probe_retracted_number_fails():
    verdict = all_honest(probe=[{"win_prob": 0.5, "note": 18.38}])
    assert verdict["ok"] is False
    assert any("retracted" in v["reason"] for v in verdict["violations"])


def test_all_honest_poisoned_probe_money_key_fails():
    verdict = all_honest(probe=[{"roi": 12.0}])
    assert verdict["ok"] is False
    assert any("$/P&L/ROI" in v["reason"] for v in verdict["violations"])


def test_all_honest_poisoned_probe_edge_claimed_fails():
    verdict = all_honest(probe=[{"edge_claimed": True}])
    assert verdict["ok"] is False


def test_all_honest_poisoned_probe_stale_green_fails():
    verdict = all_honest(probe=[
        {"serveable": True, "freshness": {"serveable": False}},
    ])
    assert verdict["ok"] is False
    assert any("stale" in v["reason"] for v in verdict["violations"])


def test_all_honest_clean_probe_stays_green():
    verdict = all_honest(probe=[{"win_prob": 0.55, "serveable": True}])
    assert verdict["ok"] is True
    assert verdict["violations"] == []
