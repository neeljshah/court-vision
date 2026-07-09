"""Per-file test: opponent-missed-FGA self-join math (dreb_pct_team) + floor
enforcement, on a synthetic 2-team boxscore frame.

Run: python -m pytest domains/basketball_nba/profiles/test_team_box_splits.py -q
"""
from __future__ import annotations

import pandas as pd
import pytest

import domains.basketball_nba.profiles.profile_compute as profile_compute
import domains.basketball_nba.profiles.team_box_splits as tbs


def _synthetic_box(n_games: int) -> pd.DataFrame:
    rows = []
    for i in range(n_games):
        gid = f"G{i}"
        # team ATL: 1 starter (40min) + 1 bench (10min), 10 fga/6 fgm, 5 oreb, 5 dreb, 4 fta, 2 pf
        rows.append({"game_id": gid, "season": "2024-25", "team": "ATL", "opp": "BOS",
                     "player_id": 1, "starter": True, "min": 40.0,
                     "fga": 6.0, "fgm": 4.0, "oreb": 3.0, "dreb": 3.0, "fta": 2.0, "pf": 1.0})
        rows.append({"game_id": gid, "season": "2024-25", "team": "ATL", "opp": "BOS",
                     "player_id": 2, "starter": False, "min": 10.0,
                     "fga": 4.0, "fgm": 2.0, "oreb": 2.0, "dreb": 2.0, "fta": 2.0, "pf": 1.0})
        # team BOS: mirrors, 10 fga/5 fgm -> 5 missed (opponent-missed-fga for ATL's dreb_pct)
        rows.append({"game_id": gid, "season": "2024-25", "team": "BOS", "opp": "ATL",
                     "player_id": 3, "starter": True, "min": 48.0,
                     "fga": 10.0, "fgm": 5.0, "oreb": 4.0, "dreb": 4.0, "fta": 4.0, "pf": 2.0})
    return pd.DataFrame(rows)


def test_opponent_missed_fga_self_join():
    box = _synthetic_box(n_games=1)
    opp_missed = tbs._opponent_missed_fga(box)
    # ATL's opponent (BOS) missed 10-5=5 FGA in the shared game
    assert opp_missed["ATL"] == pytest.approx(5.0)
    # BOS's opponent (ATL) missed (6-4)+(4-2) = 4 FGA
    assert opp_missed["BOS"] == pytest.approx(4.0)


def test_team_reb_ft_floor_and_dreb_pct(tmp_path, monkeypatch):
    box = _synthetic_box(n_games=10)
    box_path = tmp_path / "player_boxscores.parquet"
    box.to_parquet(box_path, index=False)
    monkeypatch.setattr(tbs, "_BOX", box_path)
    monkeypatch.setattr(tbs, "_tricode_to_team_id", lambda: {"ATL": 111, "BOS": 222})
    monkeypatch.setattr(profile_compute, "REPO_ROOT", tmp_path)

    rows = tbs.build_team_reb_ft("2024_25")
    by_attr_entity = {(r["attribute"], r["entity_id"]) for r in rows}
    assert ("dreb_pct_team", 111) in by_attr_entity
    assert ("oreb_pct_team", 111) in by_attr_entity

    dreb_row = next(r for r in rows if r["attribute"] == "dreb_pct_team" and r["entity_id"] == 111)
    # ATL dreb=5/game * 10 games=50, opp_missed=5/game*10games=50 -> 1.0
    assert dreb_row["raw_value"] == pytest.approx(1.0)


def test_below_n_games_floor_dropped(tmp_path, monkeypatch):
    box = _synthetic_box(n_games=3)  # below n_games>=10
    box_path = tmp_path / "player_boxscores.parquet"
    box.to_parquet(box_path, index=False)
    monkeypatch.setattr(tbs, "_BOX", box_path)
    monkeypatch.setattr(tbs, "_tricode_to_team_id", lambda: {"ATL": 111, "BOS": 222})
    monkeypatch.setattr(profile_compute, "REPO_ROOT", tmp_path)

    assert tbs.build_team_reb_ft("2024_25") == []
