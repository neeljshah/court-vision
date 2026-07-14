"""Tests for scripts.platformkit.omni.box_store_refresh (BOX-REFRESH lane).

Per-file run only:
    cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/test_omni_box_store_refresh.py -q
"""
from __future__ import annotations

import json

import pandas as pd
import pytest

from scripts.platformkit.omni import box_store_refresh as bsr

_SNAP_COLS = [
    "game_id", "date", "season", "team", "opp", "is_home", "player_id",
    "player_name", "starter", "min", "pts", "reb", "oreb", "dreb", "ast",
    "stl", "blk", "tov", "fgm", "fga", "fg3m", "fg3a", "ftm", "fta", "pf",
    "plus_minus",
]


def _make_snapshot(tmp_path):
    df = pd.DataFrame([{
        "game_id": "0022500047", "date": pd.Timestamp("2026-04-12"),
        "season": "2025-26", "team": "BOS", "opp": "MIA", "is_home": 1.0,
        "player_id": 111, "player_name": "Reg Season Guy", "starter": True,
        "min": 30.0, "pts": 20.0, "reb": 5.0, "oreb": 1.0, "dreb": 4.0,
        "ast": 4.0, "stl": 1.0, "blk": 0.0, "tov": 2.0, "fgm": 8.0, "fga": 15.0,
        "fg3m": 2.0, "fg3a": 5.0, "ftm": 2.0, "fta": 2.0, "pf": 2.0,
        "plus_minus": 5.0,
    }], columns=_SNAP_COLS)
    path = tmp_path / "snapshot.parquet"
    df.to_parquet(path, index=False)
    return path


def _player(person_id, name, starter, minutes_iso, pts):
    return {
        "status": "ACTIVE", "personId": person_id, "name": name,
        "starter": "1" if starter else "0", "played": "1",
        "statistics": {
            "points": pts, "reboundsTotal": 5, "reboundsOffensive": 1,
            "reboundsDefensive": 4, "assists": 3, "steals": 1, "blocks": 0,
            "turnovers": 1, "fieldGoalsMade": 6, "fieldGoalsAttempted": 12,
            "threePointersMade": 1, "threePointersAttempted": 3,
            "freeThrowsMade": 2, "freeThrowsAttempted": 2, "foulsPersonal": 2,
            "plusMinusPoints": 7, "minutes": minutes_iso,
        },
    }


def _write_game(dirpath, game_id, game_et):
    payload = {
        "meta": {"code": 200},
        "game": {
            "gameId": game_id, "gameEt": game_et,
            "homeTeam": {"teamTricode": "SAS", "players": [
                _player(1, "Home Starter", True, "PT36M00.00S", 24),
            ]},
            "awayTeam": {"teamTricode": "NYK", "players": [
                _player(2, "Away Starter", True, "PT34M30.00S", 18),
            ]},
        },
    }
    (dirpath / f"{game_id}.json").write_text(json.dumps(payload), encoding="utf-8")


@pytest.fixture
def cache_dir(tmp_path):
    d = tmp_path / "box"
    d.mkdir()
    # Playoff game after cutoff (0042 prefix).
    _write_game(d, "0042500401", "2026-06-03T20:30:00-04:00")
    # Regular-season game BEFORE cutoff (0022 prefix) -- must be excluded.
    _write_game(d, "0022500047", "2026-01-05T19:00:00-04:00")
    return d


def test_extension_schema_matches_snapshot(tmp_path, cache_dir):
    snap = _make_snapshot(tmp_path)
    ext = bsr.build_extension(snapshot_path=snap, box_cache_glob=str(cache_dir / "*.json"))
    assert list(ext.columns) == _SNAP_COLS + ["is_playoffs"]


def test_no_overlap_with_snapshot_date_range(tmp_path, cache_dir):
    snap = _make_snapshot(tmp_path)
    ext = bsr.build_extension(snapshot_path=snap, box_cache_glob=str(cache_dir / "*.json"))
    cutoff = pd.Timestamp("2026-04-12")
    assert (ext["date"] > cutoff).all()
    assert "0022500047" not in set(ext["game_id"])  # pre-cutoff regular season excluded


def test_playoff_flag_correct_on_known_playoff_date(tmp_path, cache_dir):
    snap = _make_snapshot(tmp_path)
    ext = bsr.build_extension(snapshot_path=snap, box_cache_glob=str(cache_dir / "*.json"))
    row = ext.loc[ext["game_id"] == "0042500401"]
    assert not row.empty
    assert bool(row["is_playoffs"].iloc[0]) is True
    assert row["season"].iloc[0] == "2025-26"


def test_minutes_parsed_from_iso_duration(tmp_path, cache_dir):
    snap = _make_snapshot(tmp_path)
    ext = bsr.build_extension(snapshot_path=snap, box_cache_glob=str(cache_dir / "*.json"))
    home = ext.loc[ext["player_id"] == 1].iloc[0]
    assert home["min"] == pytest.approx(36.0)
    away = ext.loc[ext["player_id"] == 2].iloc[0]
    assert away["min"] == pytest.approx(34.5)


def test_idempotent_rerun(tmp_path, cache_dir):
    snap = _make_snapshot(tmp_path)
    out_path = tmp_path / "ext.parquet"
    r1 = bsr.run_refresh(snapshot_path=snap, box_cache_glob=str(cache_dir / "*.json"), out_path=out_path)
    r2 = bsr.run_refresh(snapshot_path=snap, box_cache_glob=str(cache_dir / "*.json"), out_path=out_path)
    assert r1 == r2
    df1 = pd.read_parquet(out_path)
    r3 = bsr.run_refresh(snapshot_path=snap, box_cache_glob=str(cache_dir / "*.json"), out_path=out_path)
    df2 = pd.read_parquet(out_path)
    assert r3["rows_written"] == r1["rows_written"]
    pd.testing.assert_frame_equal(df1.reset_index(drop=True), df2.reset_index(drop=True))


def test_load_box_full_concats_snapshot_and_extension(tmp_path, cache_dir):
    snap = _make_snapshot(tmp_path)
    ext_path = tmp_path / "ext.parquet"
    bsr.run_refresh(snapshot_path=snap, box_cache_glob=str(cache_dir / "*.json"), out_path=ext_path)
    full = bsr.load_box_full(snapshot_path=snap, extension_path=ext_path)
    assert len(full) == 1 + 2  # 1 snapshot row + 2 players from the one qualifying game
    assert full.loc[full["game_id"] == "0022500047", "is_playoffs"].iloc[0] == False  # noqa: E712
    assert full.loc[full["game_id"] == "0042500401", "is_playoffs"].all()


def test_is_playoff_game_id():
    assert bsr.is_playoff_game_id("0042500401") is True
    assert bsr.is_playoff_game_id("0052500001") is True
    assert bsr.is_playoff_game_id("0022500047") is False
