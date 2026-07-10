"""Per-file test for domains.mlb.profiles: registry integrity, percentile/
rating math, floor application, and one hand-computed attribute (BB_rate,
single-group) plus one split attribute (platoon_resilience) on synthetic
frames -- no parquet reads, no network.
Run: cd /c/Users/neelj/nba-ai-system && python -m pytest domains/mlb/profiles/test_build_profiles.py -q
"""
from __future__ import annotations

import pandas as pd
import pytest

from domains.mlb.profiles.attribute_registry import ATTRIBUTES, ENTITIES, STATUSES, rating_2k
from domains.mlb.profiles.build_profiles import (
    LEADERBOARD_BUILDERS, SEASONS, _BAT_TRACKING_ATTRS, _BUILDERS,
    _percentile_and_rating, build_attribute_window,
)
from domains.mlb.profiles.ingredients_batter import build_BB_rate, build_platoon_resilience


def test_registry_builder_parity():
    """Registry attrs split across two builder dicts: pitch-frame _BUILDERS
    (season-frame-keyed) and LEADERBOARD_BUILDERS (year-csv-keyed, see
    ingredients_leaderboard.py). Every BUILDER must have a registry entry
    (an orphan builder is a real bug, build_profiles.py hard-fails this
    direction). A registry entry with no builder YET is normal WIP for a
    multi-lane factory (build_profiles.py skips + warns, never crashes) --
    see UNBACKED_ATTRS, not asserted empty here on purpose."""
    assert set(_BUILDERS) | set(LEADERBOARD_BUILDERS) <= set(ATTRIBUTES)
    assert not (set(_BUILDERS) & set(LEADERBOARD_BUILDERS))


@pytest.mark.parametrize("attr,spec", list(ATTRIBUTES.items()))
def test_registry_entry_shape(attr, spec):
    for key in ("description", "entity", "ingredients", "formula", "status", "floor", "weight_ledger_family"):
        assert key in spec, f"{attr} missing {key!r}"
    assert spec["entity"] in ENTITIES
    assert spec["status"] in STATUSES
    assert isinstance(spec["floor"], int) and spec["floor"] > 0
    assert isinstance(spec["ingredients"], list) and len(spec["ingredients"]) >= 2


def test_rating_2k_bounds_and_monotonic():
    assert rating_2k(0.0) == 25.0
    assert rating_2k(100.0) == pytest.approx(99.0)
    assert rating_2k(50.0) < rating_2k(75.0)


def test_percentile_and_rating_math():
    df = pd.DataFrame({
        "entity_id": [1, 2, 3, 4],
        "raw_value": [0.10, 0.30, 0.20, 0.40],
        "n": [500, 500, 500, 500],
        "ingredients": [{}] * 4,
    })
    out = _percentile_and_rating(df)
    # rank-pct ascending: 0.10->25%, 0.20->50%, 0.30->75%, 0.40->100%
    row = out.set_index("entity_id")
    assert row.loc[1, "percentile"] == pytest.approx(25.0)
    assert row.loc[4, "percentile"] == pytest.approx(100.0)
    assert row.loc[4, "rating_2k"] == pytest.approx(rating_2k(100.0))


def test_percentile_drops_nan_raw_value():
    df = pd.DataFrame({"entity_id": [1, 2], "raw_value": [0.5, float("nan")],
                        "n": [500, 500], "ingredients": [{}, {}]})
    out = _percentile_and_rating(df)
    assert len(out) == 1
    assert out.iloc[0]["entity_id"] == 1


def test_build_attribute_window_applies_floor():
    """BB_rate floor=200 PA. One batter clears it, one does not -- the
    below-floor batter must be excluded, and n_excluded_below_floor counted
    honestly, never silently dropped uncounted."""
    rows = []
    for pa in range(250):  # batter 1: 250 PA, clears floor=200
        rows.append({"batter": 1, "events": "walk" if pa % 5 == 0 else "field_out"})
    for pa in range(50):  # batter 2: 50 PA, below floor=200
        rows.append({"batter": 2, "events": "walk" if pa % 5 == 0 else "field_out"})
    frame = pd.DataFrame(rows)
    scored, coverage = build_attribute_window("BB_rate", "2023", frame, {})
    assert coverage["n_considered"] == 2
    assert coverage["n_excluded_below_floor"] == 1
    assert coverage["n_qualifying"] == 1
    assert set(scored["entity_id"]) == {1}
    assert scored.iloc[0]["window"] == "season_2023"
    assert scored.iloc[0]["status"] == ATTRIBUTES["BB_rate"]["status"]


def test_hand_computed_BB_rate():
    # batter 1: 10 PA, 3 walks -> bb_rate = 0.3; batter 2: 4 PA, 0 walks -> 0.0
    frame = pd.DataFrame({
        "batter": [1] * 10 + [2] * 4,
        "events": (["walk"] * 3 + ["field_out"] * 7) + ["strikeout"] * 4,
    })
    out = build_BB_rate(frame).set_index("entity_id")
    assert out.loc[1, "raw_value"] == pytest.approx(0.3)
    assert out.loc[1, "n"] == 10
    assert out.loc[2, "raw_value"] == pytest.approx(0.0)


def test_hand_computed_platoon_resilience():
    # batter 1: same-hand (p_throws==stand) 4 PA/1 reach-base=0.25;
    # opp-hand 4 PA/3 reach-base=0.75 -> delta = 0.25 - 0.75 = -0.5
    frame = pd.DataFrame({
        "batter": [1] * 8,
        "p_throws": ["R"] * 4 + ["L"] * 4,
        "stand": ["R"] * 4 + ["R"] * 4,  # first 4: same-hand (R/R); last 4: opp-hand (L/R)
        "events": ["single", "field_out", "field_out", "field_out",  # same-hand: 1/4 reach base
                    "single", "single", "single", "field_out"],       # opp-hand: 3/4 reach base
    })
    out = build_platoon_resilience(frame).set_index("entity_id")
    assert out.loc[1, "raw_value"] == pytest.approx(0.25 - 0.75)
    assert out.loc[1, "n"] == 4  # min(n_same_hand=4, n_opp_hand=4)


def test_seasons_includes_2025():
    """hitcoords_2025 landed 2026-07-09 (712,192 rows, column superset of 2024
    -- verified live); the pitch-frame season loop must pick it up."""
    assert "2025" in SEASONS


def test_bat_tracking_attrs_excluded_from_fake_season_windows():
    """bat_tracking's Savant endpoint ignores the year param (all 'years'
    byte-identical) -- these 4 attrs must NEVER be built via the season_YYYY
    per-year loop (that would fabricate season granularity); they route
    through build_bat_tracking_asof_window instead (see build_all)."""
    assert _BAT_TRACKING_ATTRS == {"swing_speed", "squared_up_rate", "blast_rate", "sword_rate"}
    assert _BAT_TRACKING_ATTRS <= set(LEADERBOARD_BUILDERS)


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-q"]))
