"""Per-file test: zone offense diet math + n_games floor, on a synthetic
2-game PBP corpus + stints frame (no real data/ dependency).

Run: python -m pytest domains/basketball_nba/profiles/test_team_expansion.py -q
"""
from __future__ import annotations

import json

import pandas as pd
import pytest

import domains.basketball_nba.profiles.team_expansion as te
import domains.basketball_nba.profiles.profile_compute as profile_compute


def _write_corpus(tmp_path, n_games: int):
    lineups_dir = tmp_path / "lineups"
    pbp_dir = tmp_path / "pbp"
    lineups_dir.mkdir()
    pbp_dir.mkdir()

    stint_rows = []
    for i in range(n_games):
        gid = f"G{i}"
        stint_rows.append({"game_id": gid, "team_id": 1, "period": 1, "lineup_key": "1,2,3,4,5",
                            "n_on_court": 5, "elapsed_s": 720.0, "pts_for": 10, "pts_against": 8})
        # each game: 1 rim make (team 1) + 1 corner3 miss (team 1)
        game_json = {"game": {"gameId": gid, "actions": [
            {"actionType": "2pt", "teamId": 1, "personId": 101, "x": 5.585, "y": 50.0, "shotResult": "Made"},
            {"actionType": "3pt", "teamId": 1, "personId": 101, "x": 2.128, "y": 98.0, "shotResult": "Missed"},
        ]}}
        (pbp_dir / f"{gid}.json").write_text(json.dumps(game_json), encoding="utf-8")
    stints_df = pd.DataFrame(stint_rows)
    stints_df.to_parquet(lineups_dir / "stints_2099_00.parquet", index=False)
    return lineups_dir, pbp_dir


def test_zone_offense_diet_math_and_floor(tmp_path, monkeypatch):
    lineups_dir, pbp_dir = _write_corpus(tmp_path, n_games=10)  # meets n_games>=10 floor
    monkeypatch.setattr(te, "_LINEUPS", lineups_dir)
    monkeypatch.setattr(te, "_PBP_BY_SEASON", {"2099_00": pbp_dir})
    monkeypatch.setattr(profile_compute, "REPO_ROOT", tmp_path)

    rows = te.build_zone_offense_diet("2099_00")
    by_attr = {r["attribute"]: r for r in rows if r["entity_id"] == 1}

    assert by_attr["zone_offense_rim_share"]["raw_value"] == pytest.approx(0.5)   # 1 of 2 total fga
    assert by_attr["zone_offense_rim_efg"]["raw_value"] == pytest.approx(1.0)     # made, plain FG%
    assert by_attr["zone_offense_rim_fga_per_game"]["raw_value"] == pytest.approx(1.0)
    assert by_attr["zone_offense_corner3_share"]["raw_value"] == pytest.approx(0.5)
    assert by_attr["zone_offense_corner3_efg"]["raw_value"] == pytest.approx(0.0)  # missed


def test_zone_offense_diet_below_floor_dropped(tmp_path, monkeypatch):
    lineups_dir, pbp_dir = _write_corpus(tmp_path, n_games=3)  # below n_games>=10 floor
    monkeypatch.setattr(te, "_LINEUPS", lineups_dir)
    monkeypatch.setattr(te, "_PBP_BY_SEASON", {"2099_00": pbp_dir})
    monkeypatch.setattr(profile_compute, "REPO_ROOT", tmp_path)

    assert te.build_zone_offense_diet("2099_00") == []


def test_missing_stints_returns_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(te, "_LINEUPS", tmp_path / "nope")
    monkeypatch.setattr(te, "_PBP_BY_SEASON", {"2099_00": tmp_path / "nope_pbp"})
    assert te.build_zone_offense_diet("2099_00") == []


def test_home_away_net_rating_split(tmp_path, monkeypatch):
    lineups_dir = tmp_path / "lineups"
    lineups_dir.mkdir()
    stint_rows = []
    for i in range(10):
        gid = f"H{i}"  # team 1 at HOME, wins by 10 net/48 pace
        stint_rows.append({"game_id": gid, "team_id": 1, "elapsed_s": 2880.0, "pts_for": 110.0, "pts_against": 100.0})
    for i in range(10):
        gid = f"A{i}"  # team 1 AWAY, loses by 10
        stint_rows.append({"game_id": gid, "team_id": 1, "elapsed_s": 2880.0, "pts_for": 90.0, "pts_against": 100.0})
    pd.DataFrame(stint_rows).to_parquet(lineups_dir / "stints_2099_00.parquet", index=False)

    games_rows = [{"game_id": f"H{i}", "season": "2099-00", "home_team": "ATL"} for i in range(10)]
    games_rows += [{"game_id": f"A{i}", "season": "2099-00", "home_team": "BOS"} for i in range(10)]
    games_path = tmp_path / "games.parquet"
    pd.DataFrame(games_rows).to_parquet(games_path, index=False)

    monkeypatch.setattr(te, "_LINEUPS", lineups_dir)
    monkeypatch.setattr(te, "_GAMES", games_path)
    monkeypatch.setattr(te, "_tricode_to_team_id", lambda: {"ATL": 1, "BOS": 2})
    monkeypatch.setattr(profile_compute, "REPO_ROOT", tmp_path)

    rows = te.build_home_away_net_rating("2099_00")
    by_attr = {r["attribute"]: r for r in rows if r["entity_id"] == 1}
    assert by_attr["net_rating_home"]["raw_value"] > 0
    assert by_attr["net_rating_away"]["raw_value"] < 0
    assert by_attr["net_rating_home_away_diff"]["raw_value"] == pytest.approx(
        by_attr["net_rating_home"]["raw_value"] - by_attr["net_rating_away"]["raw_value"])
