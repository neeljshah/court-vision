"""Per-file tests for scripts.platformkit.bestbets.floor_config (BB-Q5).

Run ONLY this file (full pytest freezes the box):
    python -m pytest tests/platformkit/bestbets/test_floor_config.py -q

Acceptance criteria (BB-Q5):
  * Unknown sport -> returns TIER_FLOORS fallback dict (not an error).
  * Known sport with override -> override dict returned (not the global default).
  * Floors are calibration thresholds, not $ (no dollar / roi / pnl key).
  * Import never mutates TIER_FLOORS (the global stays unchanged after import).
  * Returned dict is a copy -- mutating it does not affect the module state.
  * All three tiers (A, B, C) are present in every returned dict.
"""
from __future__ import annotations

import copy
import sys
import pathlib

# Ensure the repo root is importable when running from the repo root.
_REPO = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_REPO))

# Import baseline defaults BEFORE importing floor_config so we can check that
# the import itself did not mutate the global.
from frontend.exec_decision import TIER_FLOORS as _TIER_FLOORS

_TIER_FLOORS_SNAPSHOT: dict = copy.deepcopy(_TIER_FLOORS)

from scripts.platformkit.bestbets.floor_config import (
    KNOWN_SPORTS,
    get_floors,
    is_known_sport,
)


# ---------------------------------------------------------------------------
# Invariant: import must not mutate TIER_FLOORS
# ---------------------------------------------------------------------------

def test_import_does_not_mutate_tier_floors():
    """TIER_FLOORS global must be identical after importing floor_config."""
    assert dict(_TIER_FLOORS) == _TIER_FLOORS_SNAPSHOT, (
        "floor_config import mutated frontend.exec_decision.TIER_FLOORS: "
        f"before={_TIER_FLOORS_SNAPSHOT} after={dict(_TIER_FLOORS)}"
    )


# ---------------------------------------------------------------------------
# Unknown sport -> TIER_FLOORS fallback
# ---------------------------------------------------------------------------

def test_unknown_sport_returns_tier_floors_fallback():
    """An unknown sport slug falls back to TIER_FLOORS without raising."""
    result = get_floors("rugby")
    assert result == _TIER_FLOORS_SNAPSHOT, (
        "Unknown sport should return TIER_FLOORS fallback "
        f"(expected {_TIER_FLOORS_SNAPSHOT}, got {result})"
    )


def test_empty_string_returns_fallback():
    """Empty string is an unknown sport -> returns fallback."""
    result = get_floors("")
    assert result == _TIER_FLOORS_SNAPSHOT


def test_gibberish_sport_returns_fallback():
    """Totally unknown slug -> fallback dict, no exception."""
    result = get_floors("xxxxxx")
    assert set(result.keys()) == {"A", "B", "C"}
    assert result == _TIER_FLOORS_SNAPSHOT


# ---------------------------------------------------------------------------
# Known sport -> override returned
# ---------------------------------------------------------------------------

def test_nba_returns_explicit_entry():
    """NBA has an explicit entry; get_floors('nba') returns it."""
    result = get_floors("nba")
    assert is_known_sport("nba")
    assert set(result.keys()) == {"A", "B", "C"}


def test_tennis_floors_higher_than_default():
    """Tennis floors are raised vs the default (proxy-close adjustment)."""
    tennis = get_floors("tennis")
    default = _TIER_FLOORS_SNAPSHOT
    assert tennis["A"] > default["A"], "Tennis A floor must exceed default A"
    assert tennis["B"] > default["B"], "Tennis B floor must exceed default B"
    assert tennis["C"] > default["C"], "Tennis C floor must exceed default C"


def test_soccer_floors_higher_than_default():
    """Soccer floors are raised vs the default."""
    soccer = get_floors("soccer")
    default = _TIER_FLOORS_SNAPSHOT
    assert soccer["A"] > default["A"]
    assert soccer["B"] > default["B"]
    assert soccer["C"] > default["C"]


def test_mlb_floors_highest():
    """MLB floors are the most conservative (pitcher-blind model)."""
    mlb = get_floors("mlb")
    default = _TIER_FLOORS_SNAPSHOT
    tennis = get_floors("tennis")
    # MLB bump (+0.02) is larger than tennis/soccer bump (+0.01)
    assert mlb["A"] > tennis["A"], "MLB A floor should exceed tennis A floor"
    assert mlb["A"] > default["A"] + 0.015, (
        "MLB A should be at least +0.015 above default"
    )


def test_nfl_floors_equal_to_default():
    """NFL uses default floors (liquid market, no extra bump)."""
    nfl = get_floors("nfl")
    assert nfl == _TIER_FLOORS_SNAPSHOT, (
        "NFL override should equal the global default"
    )


def test_case_insensitive_lookup():
    """Sport lookup is case-insensitive: NBA/nba/Nba all match."""
    lower = get_floors("nba")
    upper = get_floors("NBA")
    mixed = get_floors("NbA")
    assert lower == upper == mixed


# ---------------------------------------------------------------------------
# All-tiers present in every result
# ---------------------------------------------------------------------------

def test_all_tiers_present_for_known_sports():
    """Every known sport's floors dict has all three tier keys."""
    for sport in KNOWN_SPORTS:
        floors = get_floors(sport)
        assert set(floors.keys()) == {"A", "B", "C"}, (
            f"Sport {sport!r} missing tier keys: {set(floors.keys())}"
        )


def test_all_tiers_present_for_unknown_sport():
    """Fallback dict also has all three tier keys."""
    floors = get_floors("unknown_sport_xyz")
    assert set(floors.keys()) == {"A", "B", "C"}


# ---------------------------------------------------------------------------
# Calibration thresholds not $ -- no banned keys, no negative floors
# ---------------------------------------------------------------------------

def test_no_dollar_or_roi_key_in_floors():
    """Returned dict must not contain any $ / roi / pnl key."""
    banned = {"dollar", "roi", "pnl", "profit", "return", "revenue", "usd", "$"}
    for sport in list(KNOWN_SPORTS) + ["unknown"]:
        floors = get_floors(sport)
        for key in floors:
            assert key.lower() not in banned, (
                f"Banned key '{key}' in get_floors('{sport}')"
            )


def test_floor_values_are_positive_floats():
    """All floor values must be positive EV thresholds (> 0)."""
    for sport in list(KNOWN_SPORTS) + ["unknown_sport"]:
        floors = get_floors(sport)
        for tier, value in floors.items():
            assert isinstance(value, float), (
                f"Floor value for tier '{tier}' sport '{sport}' is not float: {value!r}"
            )
            assert value > 0.0, (
                f"Floor for tier '{tier}' sport '{sport}' must be > 0, got {value}"
            )


# ---------------------------------------------------------------------------
# Returned dict is a defensive copy -- mutating it must not affect state
# ---------------------------------------------------------------------------

def test_returned_dict_is_copy_for_known_sport():
    """Mutating the returned dict must not change a subsequent call's result."""
    first = get_floors("nba")
    first_original_A = first["A"]
    first["A"] = 999.0  # mutate the returned dict
    second = get_floors("nba")
    assert second["A"] == first_original_A, (
        "get_floors must return a copy; mutating it changed the module state"
    )


def test_returned_dict_is_copy_for_unknown_sport():
    """Mutating the fallback-returned dict must not affect TIER_FLOORS."""
    result = get_floors("rugby")
    result["A"] = 999.0  # mutate
    assert _TIER_FLOORS["A"] != 999.0, (
        "Mutating get_floors fallback result must not mutate TIER_FLOORS"
    )
    assert _TIER_FLOORS["A"] == _TIER_FLOORS_SNAPSHOT["A"], (
        "TIER_FLOORS['A'] was changed by mutating get_floors result"
    )


# ---------------------------------------------------------------------------
# is_known_sport helper
# ---------------------------------------------------------------------------

def test_is_known_sport_true_for_all_known():
    """is_known_sport returns True for every sport in KNOWN_SPORTS."""
    for sport in KNOWN_SPORTS:
        assert is_known_sport(sport), f"Expected is_known_sport('{sport}') True"


def test_is_known_sport_false_for_unknown():
    """is_known_sport returns False for unknown slugs."""
    for slug in ("rugby", "cricket", "curling", "", "xyz"):
        assert not is_known_sport(slug), (
            f"Expected is_known_sport('{slug}') False"
        )


def test_is_known_sport_case_insensitive():
    """Case-insensitive: 'NBA', 'nba', 'Nba' all recognised."""
    assert is_known_sport("NBA")
    assert is_known_sport("Nba")
    assert is_known_sport("nba")
