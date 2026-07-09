"""Per-file test for domains.mlb.profiles.ingredients_leaderboard: builder/
registry parity for the leaderboard family + one hand-computed builder on a
synthetic frame (no real CSV reads, no network).
Run: cd /c/Users/neelj/nba-ai-system && python -m pytest domains/mlb/profiles/test_ingredients_leaderboard.py -q
"""
from __future__ import annotations

import pandas as pd
import pytest

from domains.mlb.profiles import ingredients_leaderboard as lb
from domains.mlb.profiles.attribute_registry import ATTRIBUTES


def test_leaderboard_attrs_registered():
    for attr in lb.BUILDERS:
        assert attr in ATTRIBUTES, f"{attr} missing from attribute_registry.ATTRIBUTES"
        assert ATTRIBUTES[attr]["entity"] in ("batter", "fielder")


def test_builder_family_parity():
    assert set(lb.BUILDERS) == set(lb.ATTR_TO_FAMILY)


def test_build_swing_speed_hand_computed(tmp_path, monkeypatch):
    monkeypatch.setattr(lb, "_DIR", tmp_path)
    pd.DataFrame({
        "id": [1, 2], "avg_bat_speed": [75.0, 70.0], "swings_competitive": [500, 10],
    }).to_csv(tmp_path / "bat_tracking_2025.csv", index=False)
    out = lb.build_swing_speed("2025").set_index("entity_id")
    assert out.loc[1, "raw_value"] == pytest.approx(75.0)
    assert out.loc[1, "n"] == 500
    assert out.loc[2, "n"] == 10


def test_build_sword_rate_zero_swings_dropped(tmp_path, monkeypatch):
    monkeypatch.setattr(lb, "_DIR", tmp_path)
    pd.DataFrame({
        "id": [1, 2], "avg_bat_speed": [75.0, 70.0], "swings_competitive": [100, 0],
        "swords": [5, 0],
    }).to_csv(tmp_path / "bat_tracking_2025.csv", index=False)
    out = lb.build_sword_rate("2025")
    assert set(out["entity_id"]) == {1}
    assert out.set_index("entity_id").loc[1, "raw_value"] == pytest.approx(0.05)


def test_build_range_oaa_cross_join(tmp_path, monkeypatch):
    monkeypatch.setattr(lb, "_DIR", tmp_path)
    pd.DataFrame({
        "player_id": [1, 2], "outs_above_average": [10, -5],
    }).to_csv(tmp_path / "outs_above_average_2025.csv", index=False)
    pd.DataFrame({
        "player_id": [1], "n_opp_5stars": [10], "n_opp_4stars": [10],
        "n_opp_3stars": [10], "n_opp_2stars": [10], "n_opp_1stars": [10],
    }).to_csv(tmp_path / "catch_probability_2025.csv", index=False)
    out = lb.build_range_oaa("2025")
    # player 2 has no catch_probability row -> inner join drops it (n unknowable)
    assert set(out["entity_id"]) == {1}
    assert out.set_index("entity_id").loc[1, "n"] == 50
    assert out.set_index("entity_id").loc[1, "raw_value"] == pytest.approx(10.0)


def test_build_difficult_play_conversion(tmp_path, monkeypatch):
    monkeypatch.setattr(lb, "_DIR", tmp_path)
    pd.DataFrame({
        "player_id": [1, 2], "n_opp_1stars": [20, 0], "n_fieldout_1stars": [8, 0],
    }).to_csv(tmp_path / "catch_probability_2025.csv", index=False)
    out = lb.build_difficult_play_conversion("2025")
    assert set(out["entity_id"]) == {1}  # player 2 has n_opp_1stars=0, excluded
    assert out.set_index("entity_id").loc[1, "raw_value"] == pytest.approx(0.4)


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-q"]))
