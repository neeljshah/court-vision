"""Per-file tests for states_gate_join.py (LANE 5 step 1: CDN <-> ESPN join).

Hermetic: synthetic boxscore.json files under tmp_path + a synthetic
linescores DataFrame. No network, no real cdn_backfill/ reads.

Run: cd /c/Users/neelj/nba-ai-system && python -m pytest domains/basketball_wnba/test_states_gate_join.py -q
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from domains.basketball_wnba.states_gate_join import build_join_map


def _write_boxscore(tmp_path: Path, game_id: str, *, date: str,
                     home: str, away: str) -> None:
    d = tmp_path / game_id
    d.mkdir(parents=True, exist_ok=True)
    payload = {
        "game": {
            "gameId": game_id,
            "gameEt": f"{date}T15:00:00-04:00",
            "homeTeam": {"teamCity": home.rsplit(" ", 1)[0], "teamName": home.rsplit(" ", 1)[1]},
            "awayTeam": {"teamCity": away.rsplit(" ", 1)[0], "teamName": away.rsplit(" ", 1)[1]},
        }
    }
    (d / "boxscore.json").write_text(json.dumps(payload), encoding="utf-8")


def _linescores_df() -> pd.DataFrame:
    return pd.DataFrame([
        {"event_id": "1001", "date": pd.Timestamp("2026-05-03"),
         "home_team": "New York Liberty", "away_team": "Indiana Fever"},
        {"event_id": "1002", "date": pd.Timestamp("2026-05-04"),
         "home_team": "Seattle Storm", "away_team": "Dallas Wings"},
    ])


def test_matches_by_date_home_away(tmp_path):
    _write_boxscore(tmp_path, "9001", date="2026-05-03", home="New York Liberty", away="Indiana Fever")
    result = build_join_map(["9001"], linescores_df=_linescores_df(),
                             backfill_dir_getter=lambda gid: tmp_path / gid)
    assert result["game_id_to_event_id"] == {"9001": "1001"}
    assert result["matched"] == 1
    assert result["unmatched"] == []


def test_multiple_games_all_match(tmp_path):
    _write_boxscore(tmp_path, "9001", date="2026-05-03", home="New York Liberty", away="Indiana Fever")
    _write_boxscore(tmp_path, "9002", date="2026-05-04", home="Seattle Storm", away="Dallas Wings")
    result = build_join_map(["9001", "9002"], linescores_df=_linescores_df(),
                             backfill_dir_getter=lambda gid: tmp_path / gid)
    assert result["matched"] == 2
    assert result["game_id_to_event_id"]["9002"] == "1002"


def test_no_boxscore_file_is_unmatched_not_raised(tmp_path):
    result = build_join_map(["9999"], linescores_df=_linescores_df(),
                             backfill_dir_getter=lambda gid: tmp_path / gid)
    assert result["matched"] == 0
    assert result["unmatched"][0]["reason"] == "no_boxscore_file"


def test_malformed_boxscore_is_unmatched_not_raised(tmp_path):
    d = tmp_path / "9998"
    d.mkdir(parents=True)
    (d / "boxscore.json").write_text("{not valid json", encoding="utf-8")
    result = build_join_map(["9998"], linescores_df=_linescores_df(),
                             backfill_dir_getter=lambda gid: tmp_path / gid)
    assert result["matched"] == 0
    assert result["unmatched"][0]["reason"] == "malformed_boxscore"


def test_no_matching_linescores_row_is_unmatched_not_fabricated(tmp_path):
    _write_boxscore(tmp_path, "9500", date="2026-04-01", home="Nigeria National Team", away="Indiana Fever")
    result = build_join_map(["9500"], linescores_df=_linescores_df(),
                             backfill_dir_getter=lambda gid: tmp_path / gid)
    assert result["matched"] == 0
    assert result["unmatched"][0]["reason"] == "no_linescores_match"


def test_missing_game_key_is_unmatched(tmp_path):
    d = tmp_path / "9700"
    d.mkdir(parents=True)
    (d / "boxscore.json").write_text(json.dumps({"nogame": True}), encoding="utf-8")
    result = build_join_map(["9700"], linescores_df=_linescores_df(),
                             backfill_dir_getter=lambda gid: tmp_path / gid)
    assert result["unmatched"][0]["reason"] == "no_game_key"


def test_real_backfill_dir_matches_161_of_168():
    """Sanity check against the real wave-14 corpus: 161/168 CDN games join
    cleanly to linescores.parquet (7 unmatched = preseason exhibitions vs
    national teams + 2 games newer than the linescores corpus, per LANE 5
    exploration). This is a floor-honest regression guard, not a leak risk."""
    from domains.basketball_wnba.states_gate_join import (
        all_backfilled_game_ids,
        STATES_PARQUET,
        LINESCORES_PARQUET,
    )
    if not STATES_PARQUET.exists() or not LINESCORES_PARQUET.exists():
        pytest.skip("real wave-14 corpus not present in this environment")
    gids = all_backfilled_game_ids()
    result = build_join_map(gids)
    assert result["matched"] >= 150  # floor, not an exact pin -- corpus may grow
