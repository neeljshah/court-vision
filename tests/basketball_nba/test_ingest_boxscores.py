"""Tests for domains.basketball_nba.ingest_boxscores.

SMALL synthetic fixtures only — 2 fake games x ~2 quarters x 2 players written
as JSON + a tiny synthetic games.parquet in tmp_path.  Never loads the real
~1299-game cache.  Fast + low-RAM.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from domains.basketball_nba.ingest_boxscores import (
    OUTPUT_COLS,
    _parse_minutes,
    build_player_boxscores,
)

# game_ids: G1 matched in games fixture; G2 deliberately UNMATCHED.
G1 = "0022400001"
G2 = "0022499999"  # not present in games fixture
HOME, AWAY = "BOS", "ATL"


def _player(pid, name, team, pos, mm, **stats):
    rec = {
        "game_id": G1, "team_id": 1, "team_abbreviation": team,
        "player_id": pid, "player_name": name, "start_position": pos, "min": mm,
        "fgm": 0, "fga": 0, "fg3m": 0, "fg3a": 0, "ftm": 0, "fta": 0,
        "oreb": 0, "dreb": 0, "reb": 0, "ast": 0, "stl": 0, "blk": 0,
        "to": 0, "pf": 0, "pts": 0, "plus_minus": 0,
    }
    rec.update(stats)
    return rec


def _write_quarter(cache: Path, gid: str, period: int, players):
    for p in players:
        p["game_id"] = gid
    (cache / f"{gid}_q{period}.json").write_text(
        json.dumps({"game_id": gid, "period": period, "players": players}),
        encoding="utf-8",
    )


@pytest.fixture
def world(tmp_path):
    """Build synthetic cache + games.parquet; return (cache, games, out)."""
    cache = tmp_path / "quarter_box"
    cache.mkdir()

    # --- G1: 2 quarters, 2 players (one home BOS starter, one away ATL bench) ---
    # Player 100: BOS, q1 starter (pos "G"), q2 bench (pos "").  Stats sum.
    # Player 200: ATL, bench both quarters.
    _write_quarter(cache, G1, 1, [
        _player(100, "Star Guard", HOME, "G", "10:00", pts=8, ast=3, reb=2, to=1, fgm=3, fga=5),
        _player(200, "Bench Wing", AWAY, "", "6:30", pts=4, ast=1, reb=1, to=0, fgm=2, fga=4),
    ])
    _write_quarter(cache, G1, 2, [
        _player(100, "Star Guard", HOME, "", "12:00", pts=5, ast=2, reb=3, to=2, fgm=2, fga=3),
        _player(200, "Bench Wing", AWAY, "", "9:15", pts=2, ast=0, reb=2, to=1, fgm=1, fga=2),
    ])

    # --- G2: 1 quarter, 1 player; game_id NOT in games fixture (unmatched) ---
    _write_quarter(cache, G2, 1, [
        _player(300, "Lone Player", "MIA", "F", "8:00", pts=10, ast=4),
    ])

    games = pd.DataFrame({
        "game_id": [G1],
        "date": [pd.Timestamp("2024-10-22")],
        "season": ["2024-25"],
        "home_team": [HOME],
        "away_team": [AWAY],
    })
    gpath = tmp_path / "games.parquet"
    games.to_parquet(gpath, index=False)

    out = tmp_path / "player_boxscores.parquet"
    return cache, gpath, out


def _build(world):
    cache, gpath, out = world
    dest = build_player_boxscores(cache_dir=str(cache), games_path=str(gpath), out_path=str(out))
    return pd.read_parquet(dest)


# --------------------------------------------------------------------------- #

def test_parse_minutes_formats():
    assert _parse_minutes("12:00") == pytest.approx(12.0)
    assert _parse_minutes("6:30") == pytest.approx(6.5)
    assert _parse_minutes("0:45") == pytest.approx(0.75)
    assert _parse_minutes(7.5) == pytest.approx(7.5)
    assert _parse_minutes("") == 0.0
    assert _parse_minutes(None) == 0.0
    assert _parse_minutes("garbage") == 0.0


def test_aggregation_sums_counting_stats(world):
    df = _build(world)
    p100 = df[(df["game_id"] == G1) & (df["player_id"] == 100)].iloc[0]
    assert p100["pts"] == 13.0   # 8 + 5
    assert p100["ast"] == 5.0    # 3 + 2
    assert p100["reb"] == 5.0    # 2 + 3
    assert p100["tov"] == 3.0    # 1 + 2 (from "to" field)
    assert p100["fgm"] == 5.0    # 3 + 2
    assert p100["fga"] == 8.0    # 5 + 3


def test_minutes_parse_and_sum(world):
    df = _build(world)
    p100 = df[(df["game_id"] == G1) & (df["player_id"] == 100)].iloc[0]
    assert p100["min"] == pytest.approx(22.0)        # 10:00 + 12:00
    p200 = df[(df["game_id"] == G1) & (df["player_id"] == 200)].iloc[0]
    assert p200["min"] == pytest.approx(6.5 + 9.25)  # 6:30 + 9:15


def test_join_context_attached(world):
    df = _build(world)
    p100 = df[(df["game_id"] == G1) & (df["player_id"] == 100)].iloc[0]
    assert pd.Timestamp(p100["date"]) == pd.Timestamp("2024-10-22")
    assert p100["season"] == "2024-25"


def test_is_home_and_opp(world):
    df = _build(world)
    p100 = df[(df["game_id"] == G1) & (df["player_id"] == 100)].iloc[0]  # BOS = home
    p200 = df[(df["game_id"] == G1) & (df["player_id"] == 200)].iloc[0]  # ATL = away
    assert bool(p100["is_home"]) is True
    assert p100["opp"] == AWAY
    assert bool(p200["is_home"]) is False
    assert p200["opp"] == HOME


def test_starter_from_q1_start_position(world):
    df = _build(world)
    p100 = df[(df["game_id"] == G1) & (df["player_id"] == 100)].iloc[0]  # q1 pos "G"
    p200 = df[(df["game_id"] == G1) & (df["player_id"] == 200)].iloc[0]  # bench both
    assert bool(p100["starter"]) is True
    assert bool(p200["starter"]) is False


def test_schema_columns_present(world):
    df = _build(world)
    assert list(df.columns) == list(OUTPUT_COLS)
    for col in OUTPUT_COLS:
        assert col in df.columns


def test_unmatched_game_id_nan_context_no_crash(world):
    df = _build(world)
    p300 = df[df["game_id"] == G2].iloc[0]
    assert pd.isna(p300["date"])
    assert pd.isna(p300["season"]) or p300["season"] is None
    assert p300["pts"] == 10.0  # box stats still captured


def test_malformed_quarter_file_does_not_crash(world):
    cache, gpath, out = world
    # corrupt file + a quarter referencing a non-list players -> must not crash
    (cache / f"{G1}_q3.json").write_text("{ this is not valid json", encoding="utf-8")
    (cache / f"{G1}_q4.json").write_text(json.dumps({"game_id": G1, "period": 4, "players": "oops"}), encoding="utf-8")
    dest = build_player_boxscores(cache_dir=str(cache), games_path=str(gpath), out_path=str(out))
    df = pd.read_parquet(dest)
    # G1 player 100 still aggregated from q1+q2 only (corrupt q3/q4 skipped)
    p100 = df[(df["game_id"] == G1) & (df["player_id"] == 100)].iloc[0]
    assert p100["pts"] == 13.0


def test_one_row_per_game_player(world):
    df = _build(world)
    counts = df.groupby(["game_id", "player_id"]).size()
    assert (counts == 1).all()
    # G1: 2 players, G2: 1 player -> 3 rows total
    assert len(df) == 3


def test_missing_cache_dir_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        build_player_boxscores(cache_dir=str(tmp_path / "nope"),
                               games_path=str(tmp_path / "g.parquet"),
                               out_path=str(tmp_path / "o.parquet"))


def test_missing_games_parquet_nan_context(world):
    cache, _gpath, out = world
    dest = build_player_boxscores(cache_dir=str(cache),
                                  games_path=str(out.parent / "absent_games.parquet"),
                                  out_path=str(out))
    df = pd.read_parquet(dest)
    assert df["date"].isna().all()
    # box stats + schema still intact
    assert list(df.columns) == list(OUTPUT_COLS)
    assert df["pts"].sum() > 0
