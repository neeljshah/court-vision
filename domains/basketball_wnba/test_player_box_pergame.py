"""Per-file test for domains.basketball_wnba.player_box_pergame.
Run: cd /c/Users/neelj/nba-ai-system && python -m pytest domains/basketball_wnba/test_player_box_pergame.py -q
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from domains.basketball_wnba.player_box_pergame import (
    _player_rows_for_game, _team_point_check, build_player_box_frame,
)


def _synthetic_game() -> dict:
    return {
        "gameId": "9990000001",
        "gameEt": "2026-05-01T19:00:00-04:00",
        "homeTeam": {
            "teamId": 111,
            "score": 20,
            "players": [
                {"personId": 1, "name": "A One", "starter": "1", "played": "1",
                 "statistics": {"points": 10, "reboundsTotal": 3, "assists": 2,
                                "steals": 1, "blocks": 0, "turnovers": 1,
                                "fieldGoalsAttempted": 8, "fieldGoalsMade": 4,
                                "threePointersAttempted": 2, "threePointersMade": 1,
                                "freeThrowsAttempted": 2, "freeThrowsMade": 1,
                                "minutesCalculated": "PT20M", "plusMinusPoints": 5.0}},
                {"personId": 2, "name": "B Two", "starter": "0", "played": "1",
                 "statistics": {"points": 10, "reboundsTotal": 5, "assists": 1,
                                "minutesCalculated": "PT15M"}},  # most fields absent
            ],
        },
        "awayTeam": {
            "teamId": 222,
            "score": 18,
            "players": [
                {"personId": 3, "name": "C Three", "starter": "1", "played": "1",
                 "statistics": {"points": 18, "reboundsTotal": 4, "assists": 3,
                                "minutesCalculated": "PT25M"}},
            ],
        },
    }


def test_row_per_player_correct_game_and_date():
    rows = _player_rows_for_game("9990000001", _synthetic_game())
    assert len(rows) == 3
    for r in rows:
        assert r["game_id"] == "9990000001"
        assert r["game_date"] == "2026-05-01"
    home_ids = {r["player_id"] for r in rows if r["team_id"] == "111"}
    assert home_ids == {"1", "2"}
    row1 = next(r for r in rows if r["player_id"] == "1")
    assert row1["opponent_id"] == "222"
    assert row1["is_home"] is True


def test_team_total_invariant():
    game = _synthetic_game()
    rows = _player_rows_for_game("9990000001", game)
    home_sum = sum(r["pts"] for r in rows if r["team_id"] == "111")
    away_sum = sum(r["pts"] for r in rows if r["team_id"] == "222")
    assert home_sum == game["homeTeam"]["score"] == 20
    assert away_sum == game["awayTeam"]["score"] == 18


def test_missing_field_tolerance_no_crash():
    rows = _player_rows_for_game("9990000001", _synthetic_game())
    row2 = next(r for r in rows if r["player_id"] == "2")
    assert row2["stl"] is None
    assert row2["fga"] is None
    df = pd.DataFrame(rows)
    assert df["stl"].isna().any()


def test_build_player_box_frame_from_disk(tmp_path: Path):
    gdir = tmp_path / "9990000001"
    gdir.mkdir()
    (gdir / "boxscore.json").write_text(json.dumps({"game": _synthetic_game()}), encoding="utf-8")
    df, failed, n_parsed = build_player_box_frame(root=tmp_path)
    assert n_parsed == 1
    assert failed == []
    assert len(df) == 3


def test_malformed_game_flagged_not_crashed(tmp_path: Path):
    gdir = tmp_path / "bad_game"
    gdir.mkdir()
    (gdir / "boxscore.json").write_text("{not json", encoding="utf-8")
    df, failed, n_parsed = build_player_box_frame(root=tmp_path)
    assert n_parsed == 0
    assert failed == ["bad_game"]
    assert df.empty


def test_team_point_check_matches(tmp_path: Path):
    gdir = tmp_path / "9990000001"
    gdir.mkdir()
    (gdir / "boxscore.json").write_text(json.dumps({"game": _synthetic_game()}), encoding="utf-8")
    report = _team_point_check(root=tmp_path, n_samples=5)
    assert len(report) == 1
    assert report[0]["homeTeam_match"] is True
    assert report[0]["awayTeam_match"] is True
