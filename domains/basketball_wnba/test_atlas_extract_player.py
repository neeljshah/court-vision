"""Per-file tests for domains.basketball_wnba.atlas_extract_player.

Fixture boxscores mirror the REAL cdn_backfill schema shape (verified this
wave against gameId 1012600001): homeTeam/awayTeam.players[].statistics with
minutesCalculated (ISO8601), fieldGoalsMade/Attempted, etc.

Run: cd /c/Users/neelj/nba-ai-system && python -m pytest domains/basketball_wnba/test_atlas_extract_player.py -q
"""
from __future__ import annotations

import json

import domains.basketball_wnba.atlas_extract_common as common
from domains.basketball_wnba.atlas_extract_player import (
    build_box_profile, build_player_game_frame, build_rotation_profile,
    build_shooting_profile, run_extract_player_atlas,
)

HOME_ID, AWAY_ID = 1611661313, 1611661325


def _player(pid, name, played="1", starter="1", minutes="PT20M00.00S",
            points=10, fga=8, fgm=4, fg3a=2, fg3m=1, fta=2, ftm=2,
            oreb=1, dreb=2, reb_total=3, turnovers=1, assists=2, steals=1,
            blocks=0, blocks_received=0, fouls_personal=2, fouls_offensive=0,
            fouls_technical=0, fouls_drawn=1, plus_minus=5.0):
    return {
        "personId": pid, "name": name, "starter": starter, "played": played,
        "statistics": {
            "minutesCalculated": minutes, "points": points,
            "fieldGoalsAttempted": fga, "fieldGoalsMade": fgm,
            "threePointersAttempted": fg3a, "threePointersMade": fg3m,
            "freeThrowsAttempted": fta, "freeThrowsMade": ftm,
            "freeThrowsPercentage": (ftm / fta) if fta else 0.0,
            "reboundsOffensive": oreb, "reboundsDefensive": dreb,
            "reboundsTotal": reb_total, "turnovers": turnovers,
            "assists": assists, "steals": steals, "blocks": blocks,
            "blocksReceived": blocks_received, "foulsPersonal": fouls_personal,
            "foulsOffensive": fouls_offensive, "foulsTechnical": fouls_technical,
            "foulsDrawn": fouls_drawn, "plusMinusPoints": plus_minus,
        },
    }


def _box_game(home_players, away_players):
    return {
        "homeTeam": {"teamId": HOME_ID, "teamTricode": "NYL", "players": home_players},
        "awayTeam": {"teamId": AWAY_ID, "teamTricode": "IND", "players": away_players},
    }


def _write_game(tmp_path, gid, box_game):
    d = tmp_path / gid
    d.mkdir()
    (d / "boxscore.json").write_text(json.dumps({"game": box_game}), encoding="utf-8")
    (d / "playbyplay.json").write_text(json.dumps({"game": {"actions": []}}), encoding="utf-8")


# ---------------------------------------------------------------------------
# build_player_game_frame -- disk walk
# ---------------------------------------------------------------------------

def test_build_player_game_frame_two_games(tmp_path, monkeypatch):
    monkeypatch.setattr(common, "BACKFILL_DIR", tmp_path)
    box1 = _box_game([_player(1, "A", points=10)], [_player(2, "B", points=8)])
    box2 = _box_game([_player(1, "A", points=14)], [_player(2, "B", points=6)])
    _write_game(tmp_path, "g1", box1)
    _write_game(tmp_path, "g2", box2)

    pg = build_player_game_frame()
    assert len(pg) == 4  # 2 players x 2 games
    a_rows = pg[pg["player_id"] == "1"]
    assert sorted(a_rows["points"].tolist()) == [10, 14]


def test_build_player_game_frame_empty_dir_returns_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(common, "BACKFILL_DIR", tmp_path)
    pg = build_player_game_frame()
    assert pg.empty


def test_dnp_player_included_but_minutes_zero(tmp_path, monkeypatch):
    monkeypatch.setattr(common, "BACKFILL_DIR", tmp_path)
    box = _box_game(
        [_player(1, "A"), _player(3, "DNP", played="0", starter="0", minutes="PT00M", points=0, fga=0, fgm=0)],
        [_player(2, "B")],
    )
    _write_game(tmp_path, "g1", box)
    pg = build_player_game_frame()
    dnp_row = pg[pg["player_id"] == "3"].iloc[0]
    assert bool(dnp_row["played"]) is False
    assert dnp_row["minutes"] == 0.0


# ---------------------------------------------------------------------------
# build_shooting_profile -- season aggregate, TS%/eFG%
# ---------------------------------------------------------------------------

def test_shooting_profile_aggregates_across_games(tmp_path, monkeypatch):
    monkeypatch.setattr(common, "BACKFILL_DIR", tmp_path)
    box1 = _box_game([_player(1, "A", points=10, fga=8, fgm=4, fg3a=2, fg3m=1, fta=2, ftm=2)],
                      [_player(2, "B")])
    box2 = _box_game([_player(1, "A", points=14, fga=10, fgm=5, fg3a=3, fg3m=2, fta=2, ftm=2)],
                      [_player(2, "B")])
    _write_game(tmp_path, "g1", box1)
    _write_game(tmp_path, "g2", box2)

    pg = build_player_game_frame()
    prof = build_shooting_profile(pg)
    row = prof[prof["player_id"] == "1"].iloc[0]
    assert row["n_games_played"] == 2
    assert row["points_per_game"] == 12.0
    assert row["ts_pct"] is not None
    assert row["confidence"] == "low"  # n=2 games < 5


def test_shooting_profile_excludes_dnp(tmp_path, monkeypatch):
    monkeypatch.setattr(common, "BACKFILL_DIR", tmp_path)
    box = _box_game(
        [_player(1, "A"), _player(3, "DNP", played="0", minutes="PT00M", points=0, fga=0, fgm=0, fta=0, ftm=0)],
        [_player(2, "B")],
    )
    _write_game(tmp_path, "g1", box)
    pg = build_player_game_frame()
    prof = build_shooting_profile(pg)
    assert "3" not in prof["player_id"].tolist()


def test_shooting_profile_empty_input_returns_empty():
    import pandas as pd
    assert build_shooting_profile(pd.DataFrame()).empty


# ---------------------------------------------------------------------------
# build_box_profile
# ---------------------------------------------------------------------------

def test_box_profile_rebounding_turnover_foul_fields(tmp_path, monkeypatch):
    monkeypatch.setattr(common, "BACKFILL_DIR", tmp_path)
    box = _box_game([_player(1, "A", oreb=2, dreb=5, reb_total=7, turnovers=3,
                              fouls_personal=4, fouls_drawn=2)],
                     [_player(2, "B")])
    _write_game(tmp_path, "g1", box)
    pg = build_player_game_frame()
    prof = build_box_profile(pg)
    row = prof[prof["player_id"] == "1"].iloc[0]
    assert row["oreb_per_game"] == 2.0
    assert row["dreb_per_game"] == 5.0
    assert row["reb_per_game"] == 7.0
    assert row["turnovers_per_game"] == 3.0
    assert row["fouls_drawn_per_game"] == 2.0


# ---------------------------------------------------------------------------
# build_rotation_profile
# ---------------------------------------------------------------------------

def test_rotation_profile_minutes_and_starter_rate(tmp_path, monkeypatch):
    monkeypatch.setattr(common, "BACKFILL_DIR", tmp_path)
    box1 = _box_game([_player(1, "A", minutes="PT30M00.00S", starter="1")], [_player(2, "B")])
    box2 = _box_game([_player(1, "A", minutes="PT20M00.00S", starter="0")], [_player(2, "B")])
    _write_game(tmp_path, "g1", box1)
    _write_game(tmp_path, "g2", box2)
    pg = build_player_game_frame()
    rot = build_rotation_profile(pg)
    row = rot[rot["player_id"] == "1"].iloc[0]
    assert row["minutes_per_game"] == 25.0
    assert row["starter_rate"] == 0.5


# ---------------------------------------------------------------------------
# run_extract_player_atlas -- disk round-trip
# ---------------------------------------------------------------------------

def test_run_extract_player_atlas_writes_parquets(tmp_path, monkeypatch):
    monkeypatch.setattr(common, "BACKFILL_DIR", tmp_path)
    out_dir = tmp_path / "out"
    monkeypatch.setattr(common, "ATLAS_OUT_DIR", out_dir)
    box = _box_game([_player(1, "A")], [_player(2, "B")])
    _write_game(tmp_path, "g1", box)

    summary = run_extract_player_atlas()
    assert summary["player_shooting_profile"] == 2
    assert (out_dir / "atlas_wnba_player_shooting_profile.parquet").exists()
    assert (out_dir / "atlas_wnba_player_box_profile.parquet").exists()
    assert (out_dir / "atlas_wnba_player_rotation.parquet").exists()


def test_run_extract_player_atlas_empty_corpus_writes_nothing(tmp_path, monkeypatch):
    monkeypatch.setattr(common, "BACKFILL_DIR", tmp_path)
    out_dir = tmp_path / "out"
    monkeypatch.setattr(common, "ATLAS_OUT_DIR", out_dir)
    summary = run_extract_player_atlas()
    assert summary == {"player_shooting_profile": 0, "player_box_profile": 0, "player_rotation": 0}
    assert not out_dir.exists() or list(out_dir.iterdir()) == []
