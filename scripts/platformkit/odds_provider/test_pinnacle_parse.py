"""tests for scripts.platformkit.odds_provider.pinnacle_parse -- hermetic, no network.

Coverage:
  (a) spread_node / total_node with a non-dict element mixed into prices -- no crash.
  (b) moneyline_sides with a non-dict leg mixed in -- no crash.
  (c) prices=None / prices="notalist" / prices={} -- return None / {} without crash.
  (d) fully valid two-leg market parses EXACTLY as before.
"""
from __future__ import annotations

import pytest

from scripts.platformkit.odds_provider.pinnacle_parse import (
    moneyline_sides,
    spread_node,
    total_node,
)

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

VALID_HOME = {"designation": "home", "points": -3.5, "price": -110}
VALID_AWAY = {"designation": "away", "points": 3.5, "price": -110}
VALID_OVER = {"points": 220.5, "price": -110}
VALID_UNDER = {"points": 220.5, "price": -110}

# american_to_decimal(-110) = 1 + 100/110 = 1.909090...
DEC_MINUS110 = 1.0 + 100.0 / 110.0


# ---------------------------------------------------------------------------
# (d) valid two-leg spread -- golden path, decimal output unchanged
# ---------------------------------------------------------------------------

def test_spread_node_valid():
    result = spread_node([VALID_HOME, VALID_AWAY])
    assert result is not None
    assert set(result.keys()) == {"home", "away"}
    assert result["home"]["line"] == pytest.approx(-3.5)
    assert result["home"]["odds"] == pytest.approx(DEC_MINUS110)
    assert result["away"]["line"] == pytest.approx(3.5)
    assert result["away"]["odds"] == pytest.approx(DEC_MINUS110)


def test_total_node_valid():
    result = total_node([VALID_OVER, VALID_UNDER])
    assert result is not None
    assert set(result.keys()) == {"over", "under"}
    assert result["over"]["line"] == pytest.approx(220.5)
    assert result["over"]["odds"] == pytest.approx(DEC_MINUS110)


def test_moneyline_sides_valid():
    ml_home = {"designation": "home", "price": -150}
    ml_away = {"designation": "away", "price": 130}
    result = moneyline_sides([ml_home, ml_away])
    assert set(result.keys()) == {"home", "away"}
    assert result["home"] == pytest.approx(1.0 + 100.0 / 150.0)
    assert result["away"] == pytest.approx(1.0 + 130.0 / 100.0)


# ---------------------------------------------------------------------------
# (a) non-dict element in spread / total prices -- no crash
# ---------------------------------------------------------------------------

def test_spread_node_nondict_at_start_still_returns_valid():
    # "junk" string at index 0 should be skipped; valid dicts at 1 and 2
    # index-fallback assigns: idx=0 skipped (not dict); idx=1 -> side_a=home; idx=2 -> side_b=away
    result = spread_node(["junk", VALID_HOME, VALID_AWAY])
    # VALID_HOME has designation="home" so it maps correctly regardless of index shift
    assert result is not None
    assert result["home"]["line"] == pytest.approx(-3.5)
    assert result["away"]["line"] == pytest.approx(3.5)


def test_spread_node_nondict_only_returns_none():
    result = spread_node(["bad", 42, None])
    assert result is None


def test_total_node_nondict_mixed_returns_valid():
    # one junk item before two valid legs; totals use index fallback (no designation)
    # idx=0 -> "junk" -> skipped; idx=1 -> dict but index=1 -> side_b=under; idx=2 -> idx>1 -> ""
    # So only one leg completes -> None (both required)
    result = total_node(["junk", VALID_OVER, VALID_UNDER])
    # idx 1 = under, idx 2 = "" (neither is over) -> both legs won't complete -> None
    assert result is None


def test_total_node_nondict_prefix_exact_two_dicts_complete():
    # non-dict at end -- valid [over, under] at idx 0 and 1 -> should complete
    result = total_node([VALID_OVER, VALID_UNDER, "trailing_junk"])
    assert result is not None
    assert set(result.keys()) == {"over", "under"}


def test_spread_node_nondict_only_element_returns_none():
    assert spread_node(["onlystring"]) is None


# ---------------------------------------------------------------------------
# (b) moneyline_sides with a non-dict leg mixed in -- no crash
# ---------------------------------------------------------------------------

def test_moneyline_sides_nondict_middle_skipped():
    ml_home = {"designation": "home", "price": -150}
    ml_away = {"designation": "away", "price": 130}
    result = moneyline_sides([ml_home, "garbage", ml_away])
    # designation path finds both home and away
    assert result.get("home") == pytest.approx(1.0 + 100.0 / 150.0)
    assert result.get("away") == pytest.approx(1.0 + 130.0 / 100.0)


def test_moneyline_sides_all_nondict_returns_empty():
    assert moneyline_sides(["a", "b", 99]) == {}


def test_moneyline_sides_nondict_fallback_branch():
    # no designation in either dict but mixed with non-dict at idx 0;
    # fallback fires: h_dec=None, a_dec=None, len>=2
    # prs[0] is "bad" (not dict) -> h_dec stays None; prs[1] is dict -> a_dec = its price
    nodesig_home = {"price": -150}
    result = moneyline_sides(["bad", nodesig_home])
    # prs[0] not dict -> h_dec=None; prs[1] is dict -> a_dec set from fallback
    assert result.get("home") is None
    assert result.get("away") == pytest.approx(1.0 + 100.0 / 150.0)


# ---------------------------------------------------------------------------
# (c) prices=None / prices="notalist" / prices={} -- no crash
# ---------------------------------------------------------------------------

def test_spread_node_prices_none():
    assert spread_node(None) is None  # type: ignore[arg-type]


def test_total_node_prices_none():
    assert total_node(None) is None  # type: ignore[arg-type]


def test_moneyline_sides_prices_none():
    assert moneyline_sides(None) == {}  # type: ignore[arg-type]


def test_spread_node_prices_string():
    # "notalist" is a str; `prices or []` evaluates to "notalist" (truthy);
    # enumerate("notalist") yields single chars -> not dicts -> all skipped -> None
    assert spread_node("notalist") is None  # type: ignore[arg-type]


def test_moneyline_sides_prices_string():
    result = moneyline_sides("notalist")  # type: ignore[arg-type]
    assert isinstance(result, dict)


def test_spread_node_prices_dict():
    # a dict whose enumerate yields (idx, key_string) pairs -> keys are strings, not dicts -> skipped
    assert spread_node({"home": {}, "away": {}}) is None  # type: ignore[arg-type]


def test_moneyline_sides_prices_dict():
    result = moneyline_sides({"home": {}, "away": {}})  # type: ignore[arg-type]
    assert isinstance(result, dict)


def test_spread_node_prices_empty_list():
    assert spread_node([]) is None


def test_moneyline_sides_prices_empty_list():
    assert moneyline_sides([]) == {}
