"""Per-file test: percentile/rating math, ingredients-json round-trip, negative-
id exclusion, floor behavior. Synthetic frames only -- no disk IO, fast.

Run: python -m pytest domains/basketball_nba/profiles/test_profile_compute.py -q
"""
from __future__ import annotations

import json

import pandas as pd

from domains.basketball_nba.profiles.profile_compute import (
    _ascii_name, exclude_negative_ids, finalize_rows, ingredients_json, percentile_rank, rating_2k,
)


def test_rating_2k_bounds():
    assert rating_2k(0.0) == 25.0
    assert rating_2k(100.0) == 25.0 + 100.0 * 0.74  # 99.0
    assert rating_2k(50.0) == 25.0 + 50.0 * 0.74


def test_percentile_rank_higher_is_better():
    s = pd.Series([10.0, 20.0, 30.0, 40.0])
    pct = percentile_rank(s, higher_is_better=True)
    assert pct.iloc[3] == 100.0  # the max gets the top percentile
    assert pct.iloc[0] == 25.0  # the min of 4 evenly-spaced values


def test_percentile_rank_lower_is_better_inverts():
    s = pd.Series([10.0, 20.0, 30.0, 40.0])
    pct_hi = percentile_rank(s, higher_is_better=True)
    pct_lo = percentile_rank(s, higher_is_better=False)
    # inverted: what was best (rank 4) is now worst (rank 1)
    assert pct_lo.iloc[3] == pct_hi.iloc[0]
    assert pct_lo.iloc[0] == pct_hi.iloc[3]


def test_exclude_negative_ids_drops_placeholder_rows():
    df = pd.DataFrame({"player_id": [1, -5, 2, -2988564523], "v": [1, 2, 3, 4]})
    out = exclude_negative_ids(df, "player_id")
    assert (out["player_id"] >= 0).all()
    assert len(out) == 2


def test_exclude_negative_ids_multi_column():
    df = pd.DataFrame({"a": [1, -1, 2], "b": [1, 2, -1]})
    out = exclude_negative_ids(df, "a", "b")
    assert len(out) == 1  # only row 0 (a=1,b=1) survives both


def test_ingredients_json_round_trip():
    payload = {"teammate_efg_on": 0.55123456, "min_on": 412, "name": "Test Player"}
    s = ingredients_json(payload)
    back = json.loads(s)
    assert back["teammate_efg_on"] == round(0.55123456, 4)
    assert back["min_on"] == 412
    assert back["name"] == "Test Player"


def test_finalize_rows_floor_and_schema():
    """The caller applies the floor BEFORE calling finalize_rows -- this
    checks the resulting rows carry every SHARED SCHEMA column and that a
    pre-floor-filtered-out entity never appears."""
    df = pd.DataFrame({
        "player_id": [101, 102, 103],
        "player_name": ["A", "B", "C"],
        "raw_value": [0.10, 0.20, 0.30],
        "n_min": [50.0, 500.0, 600.0],
    })
    floored = df[df["n_min"] >= 100.0]  # drops player 101
    rows = finalize_rows(
        floored, entity_col="player_id", name_col="player_name", raw_col="raw_value", n_col="n_min",
        window="season_2025_26", attribute="test_attr", status="DESCRIPTIVE", sources="x.parquet",
        ingredient_cols=["raw_value", "n_min"],
    )
    assert len(rows) == 2
    ids = {r["entity_id"] for r in rows}
    assert ids == {102, 103}
    for r in rows:
        for col in ("entity_id", "entity_name", "window", "attribute", "raw_value", "percentile",
                    "rating_2k", "n", "ingredients", "status", "sources"):
            assert col in r
        assert 0.0 <= r["percentile"] <= 100.0
        assert 25.0 <= r["rating_2k"] <= 99.0
        json.loads(r["ingredients"])  # must be valid json


def test_finalize_rows_canonicalizes_accented_name_variants():
    """Two source rows for the SAME entity_id carrying an accented and a
    plain spelling (e.g. a builder pulling from two upstream feeds) must
    stamp the IDENTICAL ascii-folded entity_name -- otherwise the parquet
    grows duplicate spellings that inflate resolver ambiguity candidates."""
    accented = "Luka Dončić"  # "Luka Doncic" with diacritics
    plain = "Luka Doncic"
    assert _ascii_name(accented) == plain  # sanity: folds to the plain form

    df_a = pd.DataFrame({
        "player_id": [1629029], "player_name": [accented],
        "raw_value": [0.42], "n_min": [500.0],
    })
    df_b = pd.DataFrame({
        "player_id": [1629029], "player_name": [plain],
        "raw_value": [0.55], "n_min": [600.0],
    })
    rows_a = finalize_rows(
        df_a, entity_col="player_id", name_col="player_name", raw_col="raw_value", n_col="n_min",
        window="season_2025_26", attribute="attr_a", status="DESCRIPTIVE", sources="a.parquet",
        ingredient_cols=["raw_value"],
    )
    rows_b = finalize_rows(
        df_b, entity_col="player_id", name_col="player_name", raw_col="raw_value", n_col="n_min",
        window="season_2025_26", attribute="attr_b", status="DESCRIPTIVE", sources="b.parquet",
        ingredient_cols=["raw_value"],
    )
    names = {rows_a[0]["entity_name"], rows_b[0]["entity_name"]}
    assert names == {plain}  # one canonical spelling per entity_id, not two


def test_finalize_rows_lineup_key_stays_string():
    df = pd.DataFrame({"lineup_key": ["1,2,3,4,5"], "raw_value": [1.5], "n": [200.0]})
    rows = finalize_rows(
        df, entity_col="lineup_key", name_col=None, raw_col="raw_value", n_col="n",
        window="season_2025_26", attribute="spacing", status="DESCRIPTIVE", sources="x.parquet",
        ingredient_cols=["raw_value"], entity_id_int=False,
    )
    assert rows[0]["entity_id"] == "1,2,3,4,5"
    assert isinstance(rows[0]["entity_id"], str)
