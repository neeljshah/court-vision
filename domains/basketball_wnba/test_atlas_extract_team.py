"""Per-file tests for domains.basketball_wnba.atlas_extract_team.

Run: cd /c/Users/neelj/nba-ai-system && python -m pytest domains/basketball_wnba/test_atlas_extract_team.py -q
"""
from __future__ import annotations

import json

import domains.basketball_wnba.atlas_extract_common as common
from domains.basketball_wnba.atlas_extract_team import (
    build_bench_hustle, build_officials_venue, build_pace_shooting,
    build_rotation_concentration, build_team_game_frame, run_extract_team_atlas,
)

HOME_ID, AWAY_ID = 1611661313, 1611661325


def _team_stats(fga=70, fta=15, oreb=10, tov=12, bench_points=20,
                 pts_from_tov=8, fouls_personal=18, fouls_team=18,
                 opp_fg3a=25, opp_fg3m=8, opp_paint_pts=30, opp_paint_att=45):
    return {
        "fieldGoalsAttempted": fga, "freeThrowsAttempted": fta,
        "reboundsOffensive": oreb, "turnoversTotal": tov,
        "benchPoints": bench_points, "pointsFromTurnovers": pts_from_tov,
        "foulsPersonal": fouls_personal, "foulsTeam": fouls_team,
        "threePointersAttempted": opp_fg3a, "threePointersMade": opp_fg3m,
        "pointsInThePaint": opp_paint_pts, "pointsInThePaintAttempted": opp_paint_att,
    }


def _box_game(home_stats=None, away_stats=None, officials=None, attendance=10000, sellout=0):
    return {
        "homeTeam": {"teamId": HOME_ID, "teamTricode": "NYL", "statistics": home_stats or _team_stats()},
        "awayTeam": {"teamId": AWAY_ID, "teamTricode": "IND", "statistics": away_stats or _team_stats()},
        "officials": officials if officials is not None else [
            {"personId": 111}, {"personId": 222}, {"personId": 333}],
        "attendance": attendance,
        "arena": {"arenaCity": "Brooklyn"},
        "sellout": sellout,
    }


def _write_game(tmp_path, gid, box_game):
    d = tmp_path / gid
    d.mkdir()
    (d / "boxscore.json").write_text(json.dumps({"game": box_game}), encoding="utf-8")
    (d / "playbyplay.json").write_text(json.dumps({"game": {"actions": []}}), encoding="utf-8")


# ---------------------------------------------------------------------------
# build_team_game_frame
# ---------------------------------------------------------------------------

def test_build_team_game_frame_both_sides(tmp_path, monkeypatch):
    monkeypatch.setattr(common, "BACKFILL_DIR", tmp_path)
    _write_game(tmp_path, "g1", _box_game())
    tg = build_team_game_frame()
    assert len(tg) == 2  # home + away rows
    assert set(tg["team_id"]) == {str(HOME_ID), str(AWAY_ID)}


def test_opponent_allowed_stats_are_cross_wired(tmp_path, monkeypatch):
    """home row's opp_* fields must come from the AWAY team's stats block."""
    monkeypatch.setattr(common, "BACKFILL_DIR", tmp_path)
    away = _team_stats(opp_fg3a=99, opp_fg3m=50)  # distinctive marker values
    _write_game(tmp_path, "g1", _box_game(away_stats=away))
    tg = build_team_game_frame()
    home_row = tg[tg["team_id"] == str(HOME_ID)].iloc[0]
    assert home_row["opp_fg3a"] == 99
    assert home_row["opp_fg3m"] == 50


# ---------------------------------------------------------------------------
# build_pace_shooting -- pace proxy + opponent-allowed 3pt%
# ---------------------------------------------------------------------------

def test_pace_shooting_computes_pace_and_opp_fg3_pct(tmp_path, monkeypatch):
    monkeypatch.setattr(common, "BACKFILL_DIR", tmp_path)
    _write_game(tmp_path, "g1", _box_game())
    tg = build_team_game_frame()
    ps = build_pace_shooting(tg)
    row = ps[ps["team_id"] == str(HOME_ID)].iloc[0]
    # default _team_stats(): fga=70, fta=15, oreb=10, tov=12 (now turnoversTotal,
    # the TRUE total -- not turnoversTeam, which is only the ~0-2/game team-
    # charged sliver) -> 70 + 0.44*15 - 10 + 12 = 78.6, a realistic WNBA pace.
    assert row["pace_proxy_per_game"] == 78.6
    assert row["opp_fg3_pct_allowed"] == round(8 / 25, 4)
    assert row["confidence"] == "low"  # n=1


def test_pace_shooting_empty_input():
    import pandas as pd
    assert build_pace_shooting(pd.DataFrame()).empty


# ---------------------------------------------------------------------------
# build_bench_hustle
# ---------------------------------------------------------------------------

def test_bench_hustle_bench_points_per_game(tmp_path, monkeypatch):
    monkeypatch.setattr(common, "BACKFILL_DIR", tmp_path)
    home1 = _team_stats(bench_points=20)
    home2 = _team_stats(bench_points=30)
    _write_game(tmp_path, "g1", _box_game(home_stats=home1))
    _write_game(tmp_path, "g2", _box_game(home_stats=home2))
    tg = build_team_game_frame()
    bh = build_bench_hustle(tg)
    row = bh[bh["team_id"] == str(HOME_ID)].iloc[0]
    assert row["bench_points_per_game"] == 25.0
    assert row["n_games"] == 2


# ---------------------------------------------------------------------------
# build_rotation_concentration -- top-5 minutes share, cross-module reuse
# ---------------------------------------------------------------------------

def test_rotation_concentration_top5_share(tmp_path, monkeypatch):
    monkeypatch.setattr(common, "BACKFILL_DIR", tmp_path)
    players = []
    # 5 players @ 30min (150 total top-5), 2 more @ 15min each (30 more) => share = 150/180
    for i in range(5):
        players.append({"personId": i, "name": f"P{i}", "starter": "1", "played": "1",
                         "statistics": {"minutesCalculated": "PT30M00.00S", "points": 10,
                                        "fieldGoalsAttempted": 5, "fieldGoalsMade": 2,
                                        "threePointersAttempted": 1, "threePointersMade": 0,
                                        "freeThrowsAttempted": 1, "freeThrowsMade": 1,
                                        "freeThrowsPercentage": 1.0, "reboundsOffensive": 1,
                                        "reboundsDefensive": 1, "reboundsTotal": 2, "turnovers": 1,
                                        "assists": 1, "steals": 0, "blocks": 0, "blocksReceived": 0,
                                        "foulsPersonal": 1, "foulsOffensive": 0, "foulsTechnical": 0,
                                        "foulsDrawn": 0, "plusMinusPoints": 0.0}})
    for i in range(5, 7):
        players.append({"personId": i, "name": f"P{i}", "starter": "0", "played": "1",
                         "statistics": {"minutesCalculated": "PT15M00.00S", "points": 4,
                                        "fieldGoalsAttempted": 2, "fieldGoalsMade": 1,
                                        "threePointersAttempted": 0, "threePointersMade": 0,
                                        "freeThrowsAttempted": 0, "freeThrowsMade": 0,
                                        "freeThrowsPercentage": 0.0, "reboundsOffensive": 0,
                                        "reboundsDefensive": 0, "reboundsTotal": 0, "turnovers": 0,
                                        "assists": 0, "steals": 0, "blocks": 0, "blocksReceived": 0,
                                        "foulsPersonal": 0, "foulsOffensive": 0, "foulsTechnical": 0,
                                        "foulsDrawn": 0, "plusMinusPoints": 0.0}})
    box = _box_game()
    box["homeTeam"]["players"] = players
    box["awayTeam"]["players"] = []
    _write_game(tmp_path, "g1", box)

    from domains.basketball_wnba.atlas_extract_player import build_player_game_frame
    pg = build_player_game_frame()
    rc = build_rotation_concentration(pg)
    row = rc[rc["team_id"] == str(HOME_ID)].iloc[0]
    assert row["top5_minutes_share_mean"] == round(150 / 180, 4)


def test_rotation_concentration_empty_input():
    import pandas as pd
    assert build_rotation_concentration(pd.DataFrame()).empty


# ---------------------------------------------------------------------------
# build_officials_venue -- crew foul-rate + attendance
# ---------------------------------------------------------------------------

def test_officials_venue_crew_and_attendance(tmp_path, monkeypatch):
    monkeypatch.setattr(common, "BACKFILL_DIR", tmp_path)
    home = _team_stats(fouls_personal=10)
    away = _team_stats(fouls_personal=8)
    _write_game(tmp_path, "g1", _box_game(home_stats=home, away_stats=away, attendance=5000))
    tg = build_team_game_frame()
    ov = build_officials_venue(tg)
    crew_rows = ov[ov["grain"] == "officials_crew"]
    assert len(crew_rows) == 1
    assert crew_rows.iloc[0]["total_fouls_per_game_mean"] == 18.0  # 10+8 combined game fouls
    venue_rows = ov[ov["grain"] == "team_venue"]
    home_venue = venue_rows[venue_rows["team_id"] == str(HOME_ID)].iloc[0]
    assert home_venue["attendance_mean"] == 5000.0


def test_officials_venue_empty_input():
    import pandas as pd
    assert build_officials_venue(pd.DataFrame()).empty


# ---------------------------------------------------------------------------
# run_extract_team_atlas -- disk round-trip
# ---------------------------------------------------------------------------

def test_run_extract_team_atlas_writes_parquets(tmp_path, monkeypatch):
    monkeypatch.setattr(common, "BACKFILL_DIR", tmp_path)
    out_dir = tmp_path / "out"
    monkeypatch.setattr(common, "ATLAS_OUT_DIR", out_dir)
    _write_game(tmp_path, "g1", _box_game())

    summary = run_extract_team_atlas()
    assert summary["team_pace_shooting"] == 2
    assert summary["team_bench_hustle"] == 2
    assert (out_dir / "atlas_wnba_team_pace_shooting.parquet").exists()
    assert (out_dir / "atlas_wnba_team_officials_venue.parquet").exists()
