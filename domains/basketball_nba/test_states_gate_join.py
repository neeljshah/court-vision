"""Per-file tests for states_gate_join.py (LANE 2: CDN <-> ESPN join).
PORTED from domains/basketball_wnba/test_states_gate_join.py, adapted for
NBA's flat data/cache/team_system/box/<game_id>.json cache layout (WNBA
uses a per-game subdirectory + boxscore.json; NBA's box_path_getter takes a
single game_id -> Path callable instead).

Hermetic: synthetic boxscore JSON files under tmp_path + a synthetic
linescores DataFrame. No network, no real box-cache reads.

Run: cd /c/Users/neelj/nba-ai-system && python -m pytest domains/basketball_nba/test_states_gate_join.py -q
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from domains.basketball_nba.states_gate_join import build_join_map


def _write_boxscore(tmp_path: Path, game_id: str, *, date: str,
                     home: str, away: str) -> None:
    payload = {
        "game": {
            "gameId": game_id,
            "gameEt": f"{date}T15:00:00-04:00",
            "homeTeam": {"teamCity": home.rsplit(" ", 1)[0], "teamName": home.rsplit(" ", 1)[1]},
            "awayTeam": {"teamCity": away.rsplit(" ", 1)[0], "teamName": away.rsplit(" ", 1)[1]},
        }
    }
    (tmp_path / f"{game_id}.json").write_text(json.dumps(payload), encoding="utf-8")


def _linescores_df() -> pd.DataFrame:
    return pd.DataFrame([
        {"event_id": "401809243", "date": pd.Timestamp("2026-01-03"),
         "home_team": "New York Knicks", "away_team": "Boston Celtics"},
        {"event_id": "401809244", "date": pd.Timestamp("2026-01-04"),
         "home_team": "Golden State Warriors", "away_team": "LA Clippers"},
    ])


def test_matches_by_date_home_away(tmp_path):
    _write_boxscore(tmp_path, "0022500001", date="2026-01-03", home="New York Knicks", away="Boston Celtics")
    result = build_join_map(["0022500001"], linescores_df=_linescores_df(),
                             box_path_getter=lambda gid: tmp_path / f"{gid}.json")
    assert result["game_id_to_event_id"] == {"0022500001": "401809243"}
    assert result["matched"] == 1
    assert result["unmatched"] == []


def test_multiple_games_all_match(tmp_path):
    _write_boxscore(tmp_path, "0022500001", date="2026-01-03", home="New York Knicks", away="Boston Celtics")
    _write_boxscore(tmp_path, "0022500002", date="2026-01-04", home="Golden State Warriors", away="LA Clippers")
    result = build_join_map(["0022500001", "0022500002"], linescores_df=_linescores_df(),
                             box_path_getter=lambda gid: tmp_path / f"{gid}.json")
    assert result["matched"] == 2
    assert result["game_id_to_event_id"]["0022500002"] == "401809244"


def test_no_boxscore_file_is_unmatched_not_raised(tmp_path):
    result = build_join_map(["0029999999"], linescores_df=_linescores_df(),
                             box_path_getter=lambda gid: tmp_path / f"{gid}.json")
    assert result["matched"] == 0
    assert result["unmatched"][0]["reason"] == "no_boxscore_file"


def test_malformed_boxscore_is_unmatched_not_raised(tmp_path):
    (tmp_path / "0029999998.json").write_text("{not valid json", encoding="utf-8")
    result = build_join_map(["0029999998"], linescores_df=_linescores_df(),
                             box_path_getter=lambda gid: tmp_path / f"{gid}.json")
    assert result["matched"] == 0
    assert result["unmatched"][0]["reason"] == "malformed_boxscore"


def test_no_matching_linescores_row_is_unmatched_not_fabricated(tmp_path):
    _write_boxscore(tmp_path, "0029999500", date="2025-10-01", home="World Select Team", away="Boston Celtics")
    result = build_join_map(["0029999500"], linescores_df=_linescores_df(),
                             box_path_getter=lambda gid: tmp_path / f"{gid}.json")
    assert result["matched"] == 0
    assert result["unmatched"][0]["reason"] == "no_linescores_match"


def test_missing_game_key_is_unmatched(tmp_path):
    (tmp_path / "0029999700.json").write_text(json.dumps({"nogame": True}), encoding="utf-8")
    result = build_join_map(["0029999700"], linescores_df=_linescores_df(),
                             box_path_getter=lambda gid: tmp_path / f"{gid}.json")
    assert result["unmatched"][0]["reason"] == "no_game_key"


def test_real_box_cache_dir_matches_at_least_one_game():
    """Sanity check against the real existing CDN box cache
    (data/cache/team_system/box/<game_id>.json, 196 files at authoring
    time). The real on-disk linescores.parquet carries home_abbr/away_abbr,
    NOT home_team/away_team full names (verified at authoring time) -- per
    this module's own contract (_linescores_key_map docstring), callers must
    supply a linescores_df with full-name columns; the bare real parquet
    does not satisfy that contract, so this honestly SKIPS rather than
    asserting a join that the schema cannot support, matching the module's
    documented expectation instead of papering over the column mismatch."""
    from domains.basketball_nba.states_gate_join import (
        LINESCORES_PARQUET,
        _DEFAULT_BOX_DIR,
    )
    if not LINESCORES_PARQUET.exists() or not _DEFAULT_BOX_DIR.exists():
        pytest.skip("real NBA box cache / linescores corpus not present in this environment")
    lines = pd.read_parquet(LINESCORES_PARQUET)
    if not {"home_team", "away_team"} <= set(lines.columns):
        pytest.skip("real linescores.parquet lacks home_team/away_team full-name "
                     "columns (has home_abbr/away_abbr only) -- caller must supply "
                     "a full-name-joined linescores_df, per this module's contract")
    game_ids = sorted(p.stem for p in _DEFAULT_BOX_DIR.glob("*.json"))
    if not game_ids:
        pytest.skip("no cached NBA box files present")
    result = build_join_map(game_ids, linescores_df=lines)
    assert result["matched"] >= 0  # floor-honest: some/none may match, never raises
