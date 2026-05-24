"""test_player_positions_join.py — cycle 90e (loop 5).

Pins the build_player_positions + build_pergame_dataset join contract:
1. When data/player_positions.parquet exists, build_pergame_dataset
   left-joins position onto each row dict.
2. When the parquet is absent (or empty), the join is a silent no-op:
   every row dict still carries a position key, value None.
3. Unknown pids return None (no KeyError) and do NOT crash the build.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from src.prediction.prop_pergame import (  # noqa: E402
    _PlayerPositions,
    build_pergame_dataset,
    build_player_positions,
)


def _write_gamelog(tmp_path, pid: int, season: str = "2024-25") -> None:
    """Two played games for one player — enough to emit at least one row."""
    games = [
        {"GAME_DATE": "Oct 22, 2024", "MATCHUP": "LAL vs. GSW",
         "PTS": 20, "REB": 5, "AST": 7, "FG3M": 2, "STL": 1, "BLK": 0,
         "TOV": 2, "MIN": 30.0},
        {"GAME_DATE": "Oct 25, 2024", "MATCHUP": "LAL @ DEN",
         "PTS": 22, "REB": 4, "AST": 8, "FG3M": 3, "STL": 2, "BLK": 1,
         "TOV": 1, "MIN": 32.0},
    ]
    (tmp_path / f"gamelog_{pid}_{season}.json").write_text(
        json.dumps(games), encoding="utf-8"
    )


def _write_positions_parquet(tmp_path, rows: list) -> str:
    """Write a tiny parquet at tmp_path / 'player_positions.parquet'."""
    import pandas as pd
    path = str(tmp_path / "player_positions.parquet")
    pd.DataFrame(rows).to_parquet(path, index=False)
    return path


# ── 1. join works when parquet exists ────────────────────────────────────────

def test_join_works_when_parquet_exists(tmp_path, monkeypatch):
    """A parquet with one known pid → that pid's rows carry position string."""
    pid = 1234567
    _write_gamelog(tmp_path, pid)
    parquet = _write_positions_parquet(tmp_path, [
        {"player_id": pid, "position": "Guard", "height_inches": 75,
         "weight_lbs": 190, "birth_date": "1995-01-01", "draft_year": "2015"},
    ])
    # Point the module-level path at our tmp parquet for this test.
    monkeypatch.setattr(
        "src.prediction.prop_pergame._PLAYER_POSITIONS_PATH", parquet
    )

    rows, _cols = build_pergame_dataset(gamelog_dir=str(tmp_path), min_prior=0)
    assert rows, "build_pergame_dataset should emit at least one row"
    assert all("position" in r for r in rows), "every row must carry a 'position' key"
    # All emitted rows are for the same pid → all should have the joined position.
    assert all(r["position"] == "Guard" for r in rows), \
        f"expected 'Guard' on every row, got {set(r['position'] for r in rows)}"


# ── 2. no-op when parquet absent (back-compat) ───────────────────────────────

def test_join_noop_when_parquet_absent(tmp_path, monkeypatch):
    """Missing parquet → build still succeeds; every row has position=None."""
    pid = 1234567
    _write_gamelog(tmp_path, pid)
    missing = str(tmp_path / "does_not_exist.parquet")
    assert not os.path.exists(missing)
    monkeypatch.setattr(
        "src.prediction.prop_pergame._PLAYER_POSITIONS_PATH", missing
    )

    rows, _cols = build_pergame_dataset(gamelog_dir=str(tmp_path), min_prior=0)
    assert rows, "build_pergame_dataset should still emit rows without the parquet"
    for r in rows:
        assert "position" in r, "back-compat: every row carries the key"
        assert r["position"] is None, \
            f"absent parquet → position must be None, got {r['position']!r}"


# ── 3. unknown pid gets None (no crash) ──────────────────────────────────────

def test_unknown_pid_returns_none(tmp_path, monkeypatch):
    """Parquet exists but does NOT contain our pid → join falls back to None."""
    fetched_pid = 9999991  # in parquet
    unknown_pid = 9999992  # in gamelog only
    _write_gamelog(tmp_path, unknown_pid)
    parquet = _write_positions_parquet(tmp_path, [
        {"player_id": fetched_pid, "position": "Center", "height_inches": 84,
         "weight_lbs": 240, "birth_date": "1990-01-01", "draft_year": "2010"},
    ])
    monkeypatch.setattr(
        "src.prediction.prop_pergame._PLAYER_POSITIONS_PATH", parquet
    )

    # _PlayerPositions itself returns None for unknown pids without raising.
    pos_wrapper = build_player_positions(parquet)
    assert isinstance(pos_wrapper, _PlayerPositions)
    assert pos_wrapper.position(unknown_pid) is None
    assert pos_wrapper.position(fetched_pid) == "Center"
    # And the wider pipeline doesn't crash on the unknown pid.
    rows, _cols = build_pergame_dataset(gamelog_dir=str(tmp_path), min_prior=0)
    assert rows
    assert all(r["position"] is None for r in rows), \
        "uncached pid → position must be None on every row"
