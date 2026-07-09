"""Per-file test: clutch window filter (period/remaining/margin) + the
team-vs-opponent pairing grid, on a synthetic 2-team game.

Run: python -m pytest domains/basketball_nba/profiles/test_team_clutch.py -q
"""
from __future__ import annotations

import json

import pandas as pd
import pytest

import domains.basketball_nba.profiles.profile_compute as profile_compute
import domains.basketball_nba.profiles.team_clutch as tc


def _write_corpus(tmp_path, n_games: int):
    lineups_dir, pbp_dir = tmp_path / "lineups", tmp_path / "pbp"
    lineups_dir.mkdir()
    pbp_dir.mkdir()
    stint_rows = []
    for i in range(n_games):
        gid = f"G{i}"
        stint_rows.append({"game_id": gid, "team_id": 1, "period": 4, "lineup_key": "1,2,3,4,5", "n_on_court": 5})
        actions = [
            # clutch: period 4, PT4M00S remaining (240s <= 300s), margin=3 <=10 -- team1 scores 2
            {"actionType": "2pt", "teamId": 1, "period": 4, "clock": "PT4M00S",
             "shotResult": "Made", "scoreHome": 100, "scoreAway": 97},
            # team 2 scores 3 in the same clutch window
            {"actionType": "3pt", "teamId": 2, "period": 4, "clock": "PT3M30S",
             "shotResult": "Made", "scoreHome": 100, "scoreAway": 100},
            # NOT clutch: period 2 -- must be excluded regardless of margin
            {"actionType": "2pt", "teamId": 1, "period": 2, "clock": "PT6M00S",
             "shotResult": "Made", "scoreHome": 50, "scoreAway": 48},
        ]
        (pbp_dir / f"{gid}.json").write_text(json.dumps({"game": {"gameId": gid, "actions": actions}}), encoding="utf-8")
    pd.DataFrame(stint_rows).to_parquet(lineups_dir / "stints_2099_00.parquet", index=False)
    return lineups_dir, pbp_dir


def test_clutch_window_filter_and_pairing(tmp_path, monkeypatch):
    lineups_dir, pbp_dir = _write_corpus(tmp_path, n_games=10)
    monkeypatch.setattr(tc, "_LINEUPS", lineups_dir)
    monkeypatch.setattr(tc, "_PBP_BY_SEASON", {"2099_00": pbp_dir})
    monkeypatch.setattr(profile_compute, "REPO_ROOT", tmp_path)

    rows = tc.build_clutch("2099_00")
    by_attr = {(r["attribute"], r["entity_id"]): r for r in rows}
    # team 1: 2 clutch pts for, 3 against (the period-2 make must NOT count)
    assert by_attr[("clutch_off_pts_per_game", 1)]["raw_value"] == pytest.approx(2.0)
    assert by_attr[("clutch_def_pts_per_game", 1)]["raw_value"] == pytest.approx(3.0)
    assert by_attr[("clutch_net_pts_per_game", 1)]["raw_value"] == pytest.approx(-1.0)


def test_below_floor_dropped(tmp_path, monkeypatch):
    lineups_dir, pbp_dir = _write_corpus(tmp_path, n_games=3)
    monkeypatch.setattr(tc, "_LINEUPS", lineups_dir)
    monkeypatch.setattr(tc, "_PBP_BY_SEASON", {"2099_00": pbp_dir})
    monkeypatch.setattr(profile_compute, "REPO_ROOT", tmp_path)
    assert tc.build_clutch("2099_00") == []
