"""Per-file test: defending-team FT tagging (synthetic PBP) + pf_per36 floor
math (synthetic boxscore parquet).

Run: python -m pytest domains/basketball_nba/profiles/test_player_fouls.py -q
"""
from __future__ import annotations

import pandas as pd
import pytest

import domains.basketball_nba.profiles.player_fouls as pf_mod
import domains.basketball_nba.profiles.profile_compute as profile_compute

_GAME_JSON = {
    "game": {
        "gameId": "0022500099",
        "actions": [
            {"actionType": "freethrow", "teamId": 2, "personId": 201, "period": 1,
             "clock": "PT11M00S", "shotResult": "Made"},
            {"actionType": "2pt", "teamId": 1, "personId": 101, "period": 1,
             "clock": "PT10M20S", "shotResult": "Missed"},  # not a freethrow -- must be ignored
        ],
    }
}


def test_ft_tagged_to_defending_team():
    out = pf_mod.load_defense_tagged_freethrows(_GAME_JSON)
    assert len(out) == 1
    assert out.iloc[0]["team_id"] == 1  # team 2 shot the FT -> tagged to team 1's defense
    assert out.iloc[0]["fta"] == 1


def test_pf_per36_floor_and_formula(tmp_path, monkeypatch):
    box = pd.DataFrame([
        {"player_id": 1, "player_name": "Fouls A Lot", "season": "2024-25", "pf": 72.0, "min": 720.0},
        {"player_id": 2, "player_name": "Bench Guy", "season": "2024-25", "pf": 5.0, "min": 50.0},  # below floor
    ])
    box_path = tmp_path / "player_boxscores.parquet"
    box.to_parquet(box_path, index=False)
    monkeypatch.setattr(pf_mod, "_BOX", box_path)
    monkeypatch.setattr(profile_compute, "REPO_ROOT", tmp_path)

    rows = pf_mod.build_player_fouls_per36("2024_25")
    assert len(rows) == 1
    assert rows[0]["entity_id"] == 1
    assert rows[0]["raw_value"] == pytest.approx(72.0 / 720.0 * 36.0)


def test_pf_per36_skips_non_box_season():
    assert pf_mod.build_player_fouls_per36("2023_24") == []
