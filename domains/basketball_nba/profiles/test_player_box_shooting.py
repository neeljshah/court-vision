"""Per-file test: shooting-rate attributes (fg3_pct/ft_pct/fg_pct/efg/ts_pct/
pts_per36/ppg) -- synthetic boxscore parquet, no data/ dependency.

Run: python -m pytest domains/basketball_nba/profiles/test_player_box_shooting.py -q
"""
from __future__ import annotations

import pandas as pd
import pytest

import domains.basketball_nba.profiles.player_box_shooting as bs
import domains.basketball_nba.profiles.profile_compute as profile_compute


def _setup_box(tmp_path, monkeypatch, rows):
    box = pd.DataFrame(rows)
    box_path = tmp_path / "player_boxscores.parquet"
    box.to_parquet(box_path, index=False)
    monkeypatch.setattr(bs, "_BOX", box_path)
    monkeypatch.setattr(profile_compute, "REPO_ROOT", tmp_path)


def _row(player_id=1, name="Sharpshooter", season="2024-25", game_id="G1", pts=20.0,
         min_=30.0, fgm=8.0, fga=15.0, fg3m=3.0, fg3a=6.0, ftm=1.0, fta=1.0):
    return {"player_id": player_id, "player_name": name, "season": season, "game_id": game_id,
            "pts": pts, "min": min_, "fgm": fgm, "fga": fga, "fg3m": fg3m, "fg3a": fg3a,
            "ftm": ftm, "fta": fta}


def _many_games(n, **overrides):
    return [_row(game_id=f"G{i}", **overrides) for i in range(n)]


def test_fg3_pct_floor_and_math(tmp_path, monkeypatch):
    # 20 games x fg3a=6 = 120 >= FLOOR_FG3A(100); fg3m=3/game -> 60/120=0.5
    _setup_box(tmp_path, monkeypatch, _many_games(20, fg3m=3.0, fg3a=6.0))
    rows = bs.build_fg3_pct("2024_25")
    assert len(rows) == 1
    assert rows[0]["raw_value"] == pytest.approx(0.5)
    assert rows[0]["n"] == pytest.approx(120.0)


def test_fg3_pct_below_floor_excluded(tmp_path, monkeypatch):
    # 10 games x fg3a=6 = 60 < FLOOR_FG3A(100)
    _setup_box(tmp_path, monkeypatch, _many_games(10, fg3m=3.0, fg3a=6.0))
    assert bs.build_fg3_pct("2024_25") == []


def test_ft_pct_math(tmp_path, monkeypatch):
    # 20 games x fta=3 = 60 >= FLOOR_FTA(50); ftm=2.7/game -> 54/60=0.9
    _setup_box(tmp_path, monkeypatch, _many_games(20, ftm=2.7, fta=3.0))
    rows = bs.build_ft_pct("2024_25")
    assert rows[0]["raw_value"] == pytest.approx(0.9)


def test_fg_pct_and_efg_and_ts_pct(tmp_path, monkeypatch):
    # 20 games x fga=12 = 240 >= FLOOR_FGA(200)
    _setup_box(tmp_path, monkeypatch, _many_games(
        20, pts=22.0, fgm=8.0, fga=12.0, fg3m=2.0, fg3a=4.0, ftm=4.0, fta=5.0))
    fg_pct = {r["attribute"]: r for r in bs.build_fg_pct("2024_25")}
    efg = {r["attribute"]: r for r in bs.build_efg("2024_25")}
    ts_pct = {r["attribute"]: r for r in bs.build_ts_pct("2024_25")}
    assert fg_pct["fg_pct"]["raw_value"] == pytest.approx(8.0 / 12.0)
    assert efg["efg"]["raw_value"] == pytest.approx((8.0 + 0.5 * 2.0) / 12.0)
    assert ts_pct["ts_pct"]["raw_value"] == pytest.approx(22.0 / (2.0 * (12.0 + 0.44 * 5.0)))


def test_pts_per36_and_ppg(tmp_path, monkeypatch):
    # 20 games x min=30 = 600 >= FLOOR_MIN(200)
    _setup_box(tmp_path, monkeypatch, _many_games(20, pts=20.0, min_=30.0))
    per36 = bs.build_pts_per36("2024_25")
    ppg = bs.build_ppg("2024_25")
    assert per36[0]["raw_value"] == pytest.approx(20.0 * 20 / (30.0 * 20) * 36.0)
    assert ppg[0]["raw_value"] == pytest.approx(20.0)  # pts/game == pts (1 pts value repeated)


def test_below_min_floor_excluded_from_rate_attrs(tmp_path, monkeypatch):
    _setup_box(tmp_path, monkeypatch, _many_games(5, min_=30.0))  # 150 min < 200 floor
    assert bs.build_pts_per36("2024_25") == []
    assert bs.build_ppg("2024_25") == []


def test_skips_non_box_season():
    assert bs.build_fg3_pct("2023_24") == []
    assert bs.build_all_player_box_shooting_rows(["2023_24"]) == []


def test_build_all_returns_all_seven_attributes(tmp_path, monkeypatch):
    _setup_box(tmp_path, monkeypatch, _many_games(
        20, pts=22.0, min_=30.0, fgm=8.0, fga=12.0, fg3m=3.0, fg3a=6.0, ftm=3.0, fta=3.0))
    rows = bs.build_all_player_box_shooting_rows(["2024_25"])
    attrs = {r["attribute"] for r in rows}
    assert attrs == {"fg3_pct", "ft_pct", "fg_pct", "efg", "ts_pct", "pts_per36", "ppg"}
