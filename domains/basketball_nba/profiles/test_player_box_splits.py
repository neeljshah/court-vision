"""Per-file test: venue split (ppg_home/away/diff) + rest split (ppg_short/
long_rest/diff) -- synthetic boxscore parquet, no data/ dependency.

Run: python -m pytest domains/basketball_nba/profiles/test_player_box_splits.py -q
"""
from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import pytest

import domains.basketball_nba.profiles.player_box_splits as sp
import domains.basketball_nba.profiles.profile_compute as profile_compute


def _setup_box(tmp_path, monkeypatch, rows):
    box = pd.DataFrame(rows)
    box_path = tmp_path / "player_boxscores.parquet"
    box.to_parquet(box_path, index=False)
    monkeypatch.setattr(sp, "_BOX", box_path)
    monkeypatch.setattr(profile_compute, "REPO_ROOT", tmp_path)


def _venue_rows(player_id, name, n_home, home_pts, n_away, away_pts, season="2024-25"):
    rows = []
    for i in range(n_home):
        rows.append({"player_id": player_id, "player_name": name, "season": season,
                      "game_id": f"H{player_id}_{i}", "date": f"2024-11-{(i % 28) + 1:02d}",
                      "is_home": 1, "pts": home_pts})
    for i in range(n_away):
        rows.append({"player_id": player_id, "player_name": name, "season": season,
                      "game_id": f"A{player_id}_{i}", "date": f"2024-12-{(i % 28) + 1:02d}",
                      "is_home": 0, "pts": away_pts})
    return rows


def test_venue_split_math_and_floor(tmp_path, monkeypatch):
    # 20 home games @ 25ppg, 20 away games @ 20ppg -- both clear VENUE_FLOOR=15
    _setup_box(tmp_path, monkeypatch, _venue_rows(1, "Home Cooking", 20, 25.0, 20, 20.0))
    rows = sp.build_venue_split("2024_25")
    by_attr = {r["attribute"]: r for r in rows if r["entity_id"] == 1}
    assert by_attr["ppg_home"]["raw_value"] == pytest.approx(25.0)
    assert by_attr["ppg_away"]["raw_value"] == pytest.approx(20.0)
    assert by_attr["ppg_home_minus_away"]["raw_value"] == pytest.approx(5.0)


def test_venue_split_below_floor_one_side_excludes_diff(tmp_path, monkeypatch):
    # only 10 away games -- below VENUE_FLOOR=15, so ppg_away AND the diff drop
    _setup_box(tmp_path, monkeypatch, _venue_rows(1, "Home Only", 20, 25.0, 10, 20.0))
    rows = sp.build_venue_split("2024_25")
    attrs = {r["attribute"] for r in rows if r["entity_id"] == 1}
    assert attrs == {"ppg_home"}
    assert "ppg_home_minus_away" not in attrs


def test_skips_non_box_season():
    assert sp.build_venue_split("2023_24") == []
    assert sp.build_rest_split("2023_24") == []
    assert sp.build_all_player_box_split_rows(["2023_24"]) == []


def _rest_rows(player_id, name, n_short, short_pts, n_long, long_pts, season="2024-25"):
    """n_short games each on a 1-day gap from the prior game; n_long games
    each on a 4-day gap -- interleaved with a leading anchor game so every
    row has a real prior date."""
    rows = []
    d = date(2024, 10, 1)
    rows.append({"player_id": player_id, "player_name": name, "season": season,
                 "game_id": "anchor", "date": d.isoformat(), "pts": 15.0})
    for i in range(n_short):
        d += timedelta(days=1)  # 1-day gap -> rest_days == 1 (short)
        rows.append({"player_id": player_id, "player_name": name, "season": season,
                     "game_id": f"S{player_id}_{i}", "date": d.isoformat(), "pts": short_pts})
    for i in range(n_long):
        d += timedelta(days=4)  # 4-day gap -> rest_days == 4 (long)
        rows.append({"player_id": player_id, "player_name": name, "season": season,
                     "game_id": f"L{player_id}_{i}", "date": d.isoformat(), "pts": long_pts})
    return rows


def test_rest_split_math_and_floor(tmp_path, monkeypatch):
    # 10 short-rest games @ 18ppg, 10 long-rest games @ 22ppg -- both clear REST_FLOOR=8
    _setup_box(tmp_path, monkeypatch, _rest_rows(1, "Rested", 10, 18.0, 10, 22.0))
    rows = sp.build_rest_split("2024_25")
    by_attr = {r["attribute"]: r for r in rows if r["entity_id"] == 1}
    assert by_attr["ppg_short_rest"]["raw_value"] == pytest.approx(18.0)
    assert by_attr["ppg_long_rest"]["raw_value"] == pytest.approx(22.0)
    assert by_attr["ppg_short_minus_long_rest"]["raw_value"] == pytest.approx(-4.0)


def test_rest_split_below_floor_excluded(tmp_path, monkeypatch):
    # only 3 short-rest games -- below REST_FLOOR=8
    _setup_box(tmp_path, monkeypatch, _rest_rows(1, "Rarely B2B", 3, 18.0, 10, 22.0))
    rows = sp.build_rest_split("2024_25")
    attrs = {r["attribute"] for r in rows if r["entity_id"] == 1}
    assert attrs == {"ppg_long_rest"}
