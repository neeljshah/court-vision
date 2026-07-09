"""Per-file test for domains.tennis.profiles.

Covers: registry integrity (every entry shape-valid, status enum, concrete
vs BLOCKED partition), percentile/rating_2k math on a small synthetic
frame, floor enforcement in the point-corpus rollups, and a break-point
smoke test on synthetic points (the REUSED prereg_point_mechanisms
machinery pressure_serve is built on) -- no writes to any production path.

Run: python -m pytest domains/tennis/profiles/test_build_profiles.py -q
"""
from __future__ import annotations

import pandas as pd

from domains.tennis.profiles.attribute_registry import (
    ATTRIBUTES, BLOCKED, blocked_attributes, concrete_attributes,
)
from domains.tennis.profiles.ingredients import _window_rollup
from domains.tennis.prereg_point_mechanisms import charting_point_state

_STATUS_ENUM = {"VALIDATED_MECHANISM", "VALIDATED_CLAIM", "DESCRIPTIVE", "BLOCKED"}
_REQUIRED_KEYS = {"description", "entity", "ingredients", "formula", "status", "floor", "weight_ledger_family"}


def test_registry_entries_shape_valid():
    for name, spec in ATTRIBUTES.items():
        missing = _REQUIRED_KEYS - spec.keys()
        assert not missing, f"{name} missing keys: {missing}"
        assert spec["status"] in _STATUS_ENUM, f"{name} has unknown status {spec['status']!r}"
        if spec["status"] == BLOCKED:
            assert "reason" in spec and spec["reason"], f"{name} is BLOCKED with no reason"
            assert spec["formula"] is None


def test_concrete_and_blocked_partition_is_exhaustive_and_disjoint():
    concrete = set(concrete_attributes())
    blocked = set(blocked_attributes())
    assert concrete & blocked == set()
    assert concrete | blocked == set(ATTRIBUTES)
    assert blocked == {"rally_tolerance"}
    # original 10 (2 point-corpus + 1 pressure + 1 second-serve + 6 surface_splits) +
    # EXPANDED 39 (11 court-side/set/momentum/tiebreak/aggression/game-point +
    # 28 match_agg 7-metrics x 4-buckets) + WINDOWS 23 (7 window_<metric> + 14
    # opp_tier_<metric>_<tier> + 2 form_*) registered in attribute_registry.py's
    # _EXPANDED / _WINDOWS blocks -- see ingredients_expanded.py/ingredients_windows.py.
    assert len(concrete) == 72


def test_pressure_serve_is_validated_mechanism():
    assert ATTRIBUTES["pressure_serve"]["status"] == "VALIDATED_MECHANISM"
    assert ATTRIBUTES["pressure_serve"]["floor"]["n_bp_faced"] == 200


def test_percentile_and_rating_math_matches_formula():
    raw = pd.DataFrame({
        "attribute": ["x"] * 4, "window": ["2024"] * 4,
        "raw_value": [0.1, 0.4, 0.7, 1.0],
    })
    raw["percentile"] = raw.groupby(["attribute", "window"])["raw_value"].rank(pct=True) * 100.0
    raw["rating_2k"] = 25.0 + raw["percentile"] * 0.74
    # 4 tied-free values -> ranks 1..4 -> percentiles 25/50/75/100
    assert list(raw["percentile"]) == [25.0, 50.0, 75.0, 100.0]
    assert raw["rating_2k"].max() == 25.0 + 100.0 * 0.74 == 99.0
    assert raw["rating_2k"].min() == 25.0 + 25.0 * 0.74
    assert raw["rating_2k"].between(25.0, 99.0).all()


def test_window_rollup_enforces_floor_per_year_and_career():
    # player A: 2 years, each clears floor=10 alone; player B: 2 years of 4
    # each (below floor alone) but 8 combined -- still below floor=10 career.
    match_lvl = pd.DataFrame([
        {"entity_id": "a", "entity_name": "A", "year": 2020, "serve_won": 8, "serve_n": 12},
        {"entity_id": "a", "entity_name": "A", "year": 2021, "serve_won": 9, "serve_n": 11},
        {"entity_id": "b", "entity_name": "B", "year": 2020, "serve_won": 2, "serve_n": 4},
        {"entity_id": "b", "entity_name": "B", "year": 2021, "serve_won": 2, "serve_n": 4},
    ])
    out = _window_rollup(match_lvl, "serve_won", "serve_n", floor=10)
    windows_a = set(out[out["entity_id"] == "a"]["window"])
    assert windows_a == {"2020", "2021", "career_to_2026"}
    # B never clears the floor in any year OR career -> absent entirely
    assert (out["entity_id"] == "b").sum() == 0


def test_second_serve_ingredient_requires_both_sides_to_clear_floor():
    from domains.tennis.profiles.ingredients import charting_serve_split

    pts = pd.DataFrame({
        "date_source": ["match_date"] * 20,
        "server": [1] * 20,
        "point_winner": [1] * 15 + [2] * 5,
        "match_id": ["20200101-m-evt-R1-Player_One-Player_Two"] * 20,
        "date": ["2020-01-01"] * 20,
        "is_second_serve": [False] * 12 + [True] * 8,  # first_n=12, second_n=8
    })
    d = charting_serve_split(pts)
    assert set(d["entity_id"]) == {"one_p"}  # Player One served every point

    # first_n=12 second_n=8: floor=8 includes both sides, floor=10 excludes second
    assert len(_merge_for_floor(d, floor=8)) == 1
    assert len(_merge_for_floor(d, floor=10)) == 0


def _merge_for_floor(d: pd.DataFrame, floor: int) -> pd.DataFrame:
    from domains.tennis.profiles.ingredients import CAREER_WINDOW

    def _side(is_second: bool, label: str) -> pd.DataFrame:
        sub = d[d["is_second_serve"] == is_second]
        career = sub.assign(window=CAREER_WINDOW)
        g = career.groupby(["entity_id", "entity_name", "window"], as_index=False).agg(
            won=("won", "sum"), n=("won", "count"))
        return g.rename(columns={"won": f"{label}_won", "n": f"{label}_n"})

    merged = _side(False, "first").merge(_side(True, "second"), on=["entity_id", "entity_name", "window"], how="inner")
    return merged[(merged["first_n"] >= floor) & (merged["second_n"] >= floor)]


def test_break_point_reuse_smoke_on_synthetic_points():
    """Server down 30-40 IS a break point; 15-0 is not -- the exact rule
    prereg_point_mechanisms.charting_point_state/_break_point applies, which
    pressure_serve's mechanism status is built on. No file writes."""
    synthetic = pd.DataFrame({
        "match_id": ["20240101-m-evt-R1-Player_One-Player_Two"] * 2,
        "date": ["2024-01-01"] * 2,
        "date_source": ["match_date"] * 2,
        "tour": ["m"] * 2,
        "server": [1, 1],
        "is_second_serve": [False, False],
        "point_winner": [2, 1],
        "rally_length": [pd.NA, pd.NA],
        "set1": [0, 0], "set2": [0, 0], "gm1": [0, 0], "gm2": [0, 0],
        "score_state": ["30-40", "15-0"],
    })
    state = charting_point_state(synthetic)
    assert len(state) == 2
    bp_row = state[state["match_id"] == synthetic["match_id"].iloc[0]].sort_values("break_point", ascending=False)
    assert bool(bp_row["break_point"].iloc[0]) is True
    assert bool(bp_row["break_point"].iloc[1]) is False
