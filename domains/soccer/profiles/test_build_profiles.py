"""Per-file test: python -m pytest domains/soccer/profiles/test_build_profiles.py -q

Covers: registry integrity, percentile/rating math, floor filtering, and
counter_threat's masked-column composition against a synthetic possession
snapshot (hand-computed expected values).
"""
from __future__ import annotations

import math

import pandas as pd

from domains.soccer.profiles.attribute_registry import BLOCKED_ATTRIBUTES, REGISTRY
from domains.soccer.profiles.build_profiles import (
    _counter_threat,
    add_percentile_rating,
    build_profile_table,
)

_REQUIRED_KEYS = {
    "description", "entity", "corpus", "ingredients", "formula", "status",
    "floor", "floor_basis", "higher_is_better", "weight_ledger_family",
}
_VALID_STATUS = {"VALIDATED_MECHANISM", "VALIDATED_CLAIM", "DESCRIPTIVE"}
_VALID_CORPUS = {"statsbomb_event", "footballdata_season"}


def test_registry_integrity():
    assert len(REGISTRY) > 0
    for attr, spec in REGISTRY.items():
        missing = _REQUIRED_KEYS - spec.keys()
        assert not missing, f"{attr} missing keys: {missing}"
        assert spec["entity"] == "team"
        assert spec["corpus"] in _VALID_CORPUS
        assert spec["status"] in _VALID_STATUS
        assert isinstance(spec["floor"], int) and spec["floor"] > 0
        assert isinstance(spec["higher_is_better"], bool)
        assert isinstance(spec["ingredients"], list) and len(spec["ingredients"]) > 0
        assert isinstance(spec["weight_ledger_family"], str) and spec["weight_ledger_family"]

    # counter_threat is the one attribute the task requires be VALIDATED_MECHANISM
    # (the counter xG premium is a REPLICATED prereg result, not a fresh claim).
    assert REGISTRY["counter_threat"]["status"] == "VALIDATED_MECHANISM"

    # BLOCKED attributes never double as REGISTRY entries.
    assert set(BLOCKED_ATTRIBUTES) & set(REGISTRY) == set()
    assert "press_resistance" in BLOCKED_ATTRIBUTES
    assert BLOCKED_ATTRIBUTES["press_resistance"]["reason"]


def test_percentile_rating_math_higher_is_better():
    df = pd.DataFrame({
        "attribute": ["buildup_quality"] * 3, "window": ["w"] * 3,
        "entity_id": ["a", "b", "c"], "raw_value": [1.0, 2.0, 3.0],
    })
    out = add_percentile_rating(df)
    row_c = out[out.entity_id == "c"].iloc[0]  # highest raw_value
    row_a = out[out.entity_id == "a"].iloc[0]  # lowest raw_value
    assert row_c["percentile"] == 100.0
    assert math.isclose(row_c["rating_2k"], 25 + 100.0 * 0.74)
    assert row_a["percentile"] < row_c["percentile"]
    assert (out["percentile"] >= 0).all() and (out["percentile"] <= 100).all()


def test_percentile_rating_math_lower_is_better():
    # defensive_solidity: higher_is_better=False -> the LOWEST raw_value (fewest
    # xG conceded per possession) should get the highest percentile.
    df = pd.DataFrame({
        "attribute": ["defensive_solidity"] * 3, "window": ["w"] * 3,
        "entity_id": ["a", "b", "c"], "raw_value": [0.05, 0.20, 0.35],
    })
    out = add_percentile_rating(df)
    row_a = out[out.entity_id == "a"].iloc[0]  # lowest raw_value = best defense
    assert row_a["percentile"] == 100.0


def test_floor_filters_below_threshold_rows():
    floor = REGISTRY["counter_threat"]["floor"]
    rows = pd.DataFrame([
        {"entity_id": "pass", "entity_name": "Pass FC", "window": "statsbomb_2015_2021",
         "raw_value": 0.1, "n": floor + 5, "ingredients": {}},
        {"entity_id": "fail", "entity_name": "Fail FC", "window": "statsbomb_2015_2021",
         "raw_value": 0.1, "n": floor - 1, "ingredients": {}},
    ])
    raw_df, profile_df = build_profile_table({"counter_threat": rows})
    assert len(raw_df) == 2  # nothing dropped pre-floor
    assert list(profile_df["entity_id"]) == ["pass"]  # only the floor-passer survives


def test_counter_threat_composition_synthetic():
    # Team A: 3 possessions in 2 matches, 1 counter (xg=0.5), 2 regular (xg=0.2,0.3)
    # Team B: 3 possessions in 2 matches, 1 counter (xg=0.6), 2 regular (xg=0.1,0.4)
    poss_snap = pd.DataFrame([
        {"entity_id": "A", "entity_name": "Team A", "match_id": 1, "xg": 0.5,
         "is_counter": 1.0, "counter_xg": 0.5, "regular_xg": None, "set_piece_xg": 0.0},
        {"entity_id": "A", "entity_name": "Team A", "match_id": 1, "xg": 0.2,
         "is_counter": 0.0, "counter_xg": None, "regular_xg": 0.2, "set_piece_xg": 0.0},
        {"entity_id": "A", "entity_name": "Team A", "match_id": 2, "xg": 0.3,
         "is_counter": 0.0, "counter_xg": None, "regular_xg": 0.3, "set_piece_xg": 0.0},
        {"entity_id": "B", "entity_name": "Team B", "match_id": 1, "xg": 0.1,
         "is_counter": 0.0, "counter_xg": None, "regular_xg": 0.1, "set_piece_xg": 0.0},
        {"entity_id": "B", "entity_name": "Team B", "match_id": 2, "xg": 0.4,
         "is_counter": 0.0, "counter_xg": None, "regular_xg": 0.4, "set_piece_xg": 0.0},
        {"entity_id": "B", "entity_name": "Team B", "match_id": 2, "xg": 0.6,
         "is_counter": 1.0, "counter_xg": 0.6, "regular_xg": None, "set_piece_xg": 0.0},
    ])
    float_cols = ["xg", "is_counter", "counter_xg", "regular_xg", "set_piece_xg"]
    poss_snap[float_cols] = poss_snap[float_cols].astype(float)  # None -> proper float NaN, not object dtype
    out = _counter_threat(poss_snap).set_index("entity_id")

    row_a = out.loc["A"]
    assert row_a["n"] == 2  # team_matches = nunique(match_id) = {1, 2}
    assert math.isclose(row_a["raw_value"], 0.5 / 3, rel_tol=1e-9)  # counter_xg_sum/total_n
    assert row_a["ingredients"]["counter_n"] == 1
    assert row_a["ingredients"]["total_n"] == 3
    assert math.isclose(row_a["ingredients"]["counter_share"], 1 / 3, abs_tol=1e-4)  # rounded to 4dp in ingredients
    assert math.isclose(row_a["ingredients"]["counter_xg_per_poss"], 0.5, abs_tol=1e-4)

    row_b = out.loc["B"]
    assert math.isclose(row_b["raw_value"], 0.6 / 3, rel_tol=1e-9)
    # counter_share * counter_xg_per_poss must equal the raw_value it simplifies from (within
    # the ingredients' 4dp rounding).
    implied = row_b["ingredients"]["counter_share"] * row_b["ingredients"]["counter_xg_per_poss"]
    assert math.isclose(implied, row_b["raw_value"], abs_tol=1e-3)


def test_counter_threat_zero_counters_no_nan():
    # A team that NEVER counters must get raw_value=0.0, not NaN (the 0*NaN
    # edge case the sum/count formula was written to avoid).
    poss_snap = pd.DataFrame([
        {"entity_id": "C", "entity_name": "Team C", "match_id": 1, "xg": 0.2,
         "is_counter": 0.0, "counter_xg": None, "regular_xg": 0.2, "set_piece_xg": 0.0},
        {"entity_id": "C", "entity_name": "Team C", "match_id": 2, "xg": 0.3,
         "is_counter": 0.0, "counter_xg": None, "regular_xg": 0.3, "set_piece_xg": 0.0},
    ])
    float_cols = ["xg", "is_counter", "counter_xg", "regular_xg", "set_piece_xg"]
    poss_snap[float_cols] = poss_snap[float_cols].astype(float)
    out = _counter_threat(poss_snap).set_index("entity_id")
    assert out.loc["C", "raw_value"] == 0.0
    assert not math.isnan(out.loc["C", "raw_value"])
