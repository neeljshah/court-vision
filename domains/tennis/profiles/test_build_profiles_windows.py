"""Per-file test for domains.tennis.profiles.ingredients_windows /
build_profiles_windows. Covers: year-window slicing (a 2019 match never
lands in year_2020), opponent-tier classification (missing rank excluded,
not guessed), and floor enforcement for windows/tiers/form -- all on
synthetic frames, no reads of any production parquet.

Run: python -m pytest domains/tennis/profiles/test_build_profiles_windows.py -q
"""
from __future__ import annotations

import pandas as pd

from domains.tennis.profiles.attribute_registry import ATTRIBUTES, concrete_attributes
from domains.tennis.profiles.ingredients_windows import (
    form_last10, opponent_tier_rollup, year_window_rollup,
)


def _long(rows: list[dict]) -> pd.DataFrame:
    base = {"entity_id": "p", "entity_name": "P", "opp_rank": 10, "ace_rate": 0.1, "date": "2020-01-01"}
    return pd.DataFrame([{**base, **r} for r in rows])


def test_registry_grew_to_72_and_new_families_present():
    assert len(concrete_attributes()) == 72
    for attr in ("window_ace_rate", "opp_tier_ace_rate_top20", "opp_tier_ace_rate_outside_top50",
                 "form_serve_dominance", "form_return_strength"):
        assert attr in ATTRIBUTES and ATTRIBUTES[attr]["status"] == "DESCRIPTIVE"


def test_year_window_slicing_never_mixes_years():
    """A 2019 match must land ONLY in window='year_2019', never year_2020."""
    d = _long([{"year": 2019, "ace_rate": v} for v in [0.1] * 20] +
              [{"year": 2020, "ace_rate": v} for v in [0.9] * 20])
    g = year_window_rollup(d, "ace_rate", floor=20)
    windows = set(g["window"])
    assert windows == {"year_2019", "year_2020"}
    row_2019 = g[g["window"] == "year_2019"].iloc[0]
    row_2020 = g[g["window"] == "year_2020"].iloc[0]
    assert row_2019["value"] == 0.1 and row_2019["n"] == 20
    assert row_2020["value"] == 0.9 and row_2020["n"] == 20


def test_year_window_floor_drops_thin_years():
    d = _long([{"year": 2021, "ace_rate": 0.1} for _ in range(19)])  # 19 < floor 20
    g = year_window_rollup(d, "ace_rate", floor=20)
    assert g.empty


def test_year_window_excludes_years_outside_declared_range():
    """WINDOW_YEARS is 2015-2025 -- a 2026-dated match is dropped, not coerced."""
    d = _long([{"year": 2026, "ace_rate": 0.1} for _ in range(30)])
    g = year_window_rollup(d, "ace_rate", floor=20)
    assert g.empty


def test_opponent_tier_missing_rank_excluded_not_guessed():
    rows = [{"opp_rank": 5, "ace_rate": 0.9} for _ in range(15)]     # top20
    rows += [{"opp_rank": 80, "ace_rate": 0.1} for _ in range(15)]   # outside_top50
    rows += [{"opp_rank": None, "ace_rate": 0.5} for _ in range(15)]  # missing -- excluded
    d = _long(rows)
    g = opponent_tier_rollup(d, "ace_rate", floor=15)
    assert set(g["tier"]) == {"top20", "outside_top50"}
    total_n = g["n"].sum()
    assert total_n == 30  # the 15 missing-rank rows never entered either tier
    top = g[g["tier"] == "top20"].iloc[0]
    assert top["value"] == 0.9 and top["n"] == 15


def test_opponent_tier_boundary_35_to_50_excluded_from_both_tiers():
    """opp_rank in (20, 50] is neither top20 nor outside_top50 -- excluded by design."""
    d = _long([{"opp_rank": 35, "ace_rate": 0.5} for _ in range(20)])
    g = opponent_tier_rollup(d, "ace_rate", floor=15)
    assert g.empty


def test_opponent_tier_floor_applies_per_tier_independently():
    rows = [{"opp_rank": 5, "ace_rate": 0.9} for _ in range(20)]  # clears floor
    rows += [{"opp_rank": 80, "ace_rate": 0.1} for _ in range(5)]  # below floor 15
    d = _long(rows)
    g = opponent_tier_rollup(d, "ace_rate", floor=15)
    assert set(g["tier"]) == {"top20"}


def test_form_last10_takes_only_most_recent_matches():
    dates = pd.date_range("2020-01-01", periods=15, freq="D").astype(str)
    d = _long([{"date": dates[i], "ace_rate": 0.0 if i < 5 else 1.0} for i in range(15)])
    g = form_last10(d, "ace_rate", floor=10)
    assert len(g) == 1
    row = g.iloc[0]
    assert row["n"] == 10
    assert row["value"] == 1.0  # last 10 rows are all the ace_rate=1.0 tail


def test_form_last10_floor_excludes_players_below_threshold():
    d = _long([{"date": f"2020-01-{i+1:02d}", "ace_rate": 0.5} for i in range(9)])  # 9 < floor 10
    g = form_last10(d, "ace_rate", floor=10)
    assert g.empty
