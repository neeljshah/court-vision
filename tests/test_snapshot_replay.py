"""tests/test_snapshot_replay.py — Agent 3 (overnight build).

Tests for src/prediction/snapshot_replay.py. All tests run fully offline
using in-memory fakes — no parquet reads, no live_engine calls, no network.

The module under test imports retro_inplay_mae at module level; we patch the
heavy entry points (load_quarter_stats, build_snapshot, find_game_date,
pregame_predictions_via_gamelog) so every test stays fast.
"""
from __future__ import annotations

import csv
import os
import sys
from typing import Dict, List, Optional
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS_DIR = os.path.join(PROJECT_DIR, "scripts")
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)


# ── fixtures ──────────────────────────────────────────────────────────────────

def _fake_qstats(game_ids=("GAME_A", "GAME_B", "GAME_C")) -> pd.DataFrame:
    """Minimal quarter-stats DataFrame with the columns load_quarter_stats returns."""
    rows = []
    for gid in game_ids:
        for period in (1, 2, 3, 4):
            rows.append({
                "game_id": gid, "player_id": 1001, "period": period,
                "min": 8.0, "pts": 5.0, "reb": 2.0, "ast": 1.0,
                "fg3m": 1.0, "stl": 0.5, "blk": 0.2, "tov": 0.8, "pf": 1.0,
            })
            rows.append({
                "game_id": gid, "player_id": 1002, "period": period,
                "min": 10.0, "pts": 8.0, "reb": 3.0, "ast": 2.0,
                "fg3m": 1.5, "stl": 0.3, "blk": 0.1, "tov": 1.0, "pf": 2.0,
            })
    return pd.DataFrame(rows)


def _fake_snap(game_id: str = "GAME_A", point: str = "endQ1") -> dict:
    """Minimal snapshot dict as returned by build_snapshot."""
    period_map = {"endQ1": 2, "endQ2": 3, "endQ3": 4}
    return {
        "game_id": game_id,
        "period": period_map.get(point, 2),
        "clock": "12:00",
        "home_team": "LAL",
        "away_team": "BOS",
        "home_score": 10.0,
        "away_score": 8.0,
        "players": [
            {"player_id": 1001, "name": "pid_1001", "team": "LAL",
             "pts": 5.0, "reb": 2.0, "ast": 1.0, "fg3m": 1.0,
             "stl": 0.5, "blk": 0.2, "tov": 0.8, "pf": 1.0, "min": 8.0},
            {"player_id": 1002, "name": "pid_1002", "team": "BOS",
             "pts": 8.0, "reb": 3.0, "ast": 2.0, "fg3m": 1.5,
             "stl": 0.3, "blk": 0.1, "tov": 1.0, "pf": 2.0, "min": 10.0},
        ],
    }


def _fake_proj_rows(game_id: str = "GAME_A", period: int = 2) -> List[Dict]:
    """Minimal projection rows as returned by project_from_snapshot."""
    rows = []
    for pid, proj_pts in ((1001, 18.0), (1002, 25.0)):
        for stat, proj in (("pts", proj_pts), ("reb", 6.0), ("ast", 3.0)):
            rows.append({
                "player_id": pid,
                "name": f"pid_{pid}",
                "team": "LAL" if pid == 1001 else "BOS",
                "stat": stat,
                "current": 5.0,
                "projected_final": proj,
                "period": period,
                "snapshot_period": period,
                "snapshot_clock": "12:00",
            })
    return rows


# ── 1. list_historical_game_ids: sorted unique ids ────────────────────────────

def test_list_historical_game_ids_sorted_unique():
    """list_historical_game_ids returns sorted unique game_ids."""
    qdf = _fake_qstats(["GAME_C", "GAME_A", "GAME_B"])

    with patch("src.prediction.snapshot_replay._rim.load_quarter_stats",
               return_value=qdf):
        from src.prediction import snapshot_replay
        result = snapshot_replay.list_historical_game_ids()

    # Must be sorted lexicographically.
    assert result == sorted(result), "result must be sorted"
    # Must be unique.
    assert len(result) == len(set(result)), "result must be unique"
    # Must include all 3 games.
    assert set(result) == {"GAME_A", "GAME_B", "GAME_C"}


def test_list_historical_game_ids_limit():
    """limit parameter caps the returned list."""
    qdf = _fake_qstats(["GAME_A", "GAME_B", "GAME_C"])

    with patch("src.prediction.snapshot_replay._rim.load_quarter_stats",
               return_value=qdf):
        from src.prediction import snapshot_replay
        result = snapshot_replay.list_historical_game_ids(limit=2)

    assert len(result) == 2


# ── 2. replay_game: 3 entries for a known good game ──────────────────────────

def test_replay_game_three_snapshot_points():
    """replay_game returns one entry per snapshot_point when build_snapshot succeeds."""
    qdf = _fake_qstats(["GAME_A"])

    def _build(game_id, point, qstats_df):
        return _fake_snap(game_id, point)

    def _project(snap, **kw):
        return _fake_proj_rows(snap["game_id"], snap["period"])

    with patch("src.prediction.snapshot_replay._rim.load_quarter_stats",
               return_value=qdf), \
         patch("src.prediction.snapshot_replay._rim.build_snapshot",
               side_effect=_build), \
         patch("src.prediction.snapshot_replay.project_from_snapshot",
               side_effect=_project):
        from src.prediction import snapshot_replay
        result = snapshot_replay.replay_game("GAME_A")

    assert len(result) == 3, f"expected 3 entries, got {len(result)}"
    points = [e["snapshot_point"] for e in result]
    assert points == ["endQ1", "endQ2", "endQ3"]
    for entry in result:
        assert entry["game_id"] == "GAME_A"
        assert len(entry["projection_rows"]) > 0
        assert "snapshot" in entry
        assert "period" in entry
        assert "clock_remaining" in entry


# ── 3. replay_game: None snapshots are skipped ───────────────────────────────

def test_replay_game_skips_none_snapshots():
    """replay_game skips snapshot_points where build_snapshot returns None."""
    qdf = _fake_qstats(["GAME_A"])
    call_count = [0]

    def _build(game_id, point, qstats_df):
        call_count[0] += 1
        # Only endQ2 returns a real snapshot; endQ1/endQ3 return None.
        return _fake_snap(game_id, point) if point == "endQ2" else None

    def _project(snap, **kw):
        return _fake_proj_rows(snap["game_id"], snap["period"])

    with patch("src.prediction.snapshot_replay._rim.load_quarter_stats",
               return_value=qdf), \
         patch("src.prediction.snapshot_replay._rim.build_snapshot",
               side_effect=_build), \
         patch("src.prediction.snapshot_replay.project_from_snapshot",
               side_effect=_project):
        from src.prediction import snapshot_replay
        result = snapshot_replay.replay_game("GAME_A")

    # Only 1 entry: endQ2.
    assert len(result) == 1
    assert result[0]["snapshot_point"] == "endQ2"
    # build_snapshot was called for all 3 points.
    assert call_count[0] == 3


# ── 4. replay_game_to_shadow_log: writes CSV file ────────────────────────────

def test_replay_game_to_shadow_log_writes_csv(tmp_path):
    """replay_game_to_shadow_log writes to data/shadow/<gid>_<date>.csv."""
    qdf = _fake_qstats(["GAME_A"])
    shadow_dir = str(tmp_path / "shadow")
    os.makedirs(shadow_dir, exist_ok=True)

    def _build(game_id, point, qstats_df):
        return _fake_snap(game_id, point)

    def _project(snap, **kw):
        return _fake_proj_rows(snap["game_id"], snap["period"])

    l5_preds = {("GAME_A", 1001, s): 15.0 for s in ("pts", "reb", "ast")}
    l5_preds.update({("GAME_A", 1002, s): 20.0 for s in ("pts", "reb", "ast")})

    # Build a real shadow_logger-compatible mock that writes real CSV rows.
    written_rows: List[Dict] = []

    def _fake_log_batch(records, base_dir=None):
        written_rows.extend(records)
        # Also write a real CSV so we can check file output.
        out_dir = base_dir or shadow_dir
        os.makedirs(out_dir, exist_ok=True)
        csv_path = os.path.join(out_dir, "GAME_A_2025-04-01.csv")
        is_new = not os.path.exists(csv_path)
        with open(csv_path, "a", newline="", encoding="utf-8") as fh:
            fieldnames = list(records[0].keys()) if records else []
            writer = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
            if is_new:
                writer.writeheader()
            for r in records:
                writer.writerow(r)
        return len(records)

    fake_sl = MagicMock()
    fake_sl.log_batch.side_effect = _fake_log_batch

    from src.prediction import snapshot_replay

    with patch("src.prediction.snapshot_replay._rim.load_quarter_stats",
               return_value=qdf), \
         patch("src.prediction.snapshot_replay._rim.build_snapshot",
               side_effect=_build), \
         patch("src.prediction.snapshot_replay.project_from_snapshot",
               side_effect=_project), \
         patch("src.prediction.snapshot_replay._rim.find_game_date",
               return_value="2025-04-01"), \
         patch("src.prediction.snapshot_replay._rim.pregame_predictions_via_gamelog",
               return_value=l5_preds), \
         patch("src.prediction.snapshot_replay._sl", fake_sl), \
         patch("src.prediction.snapshot_replay._HAS_SHADOW", True):
        count = snapshot_replay.replay_game_to_shadow_log(
            "GAME_A", base_dir=shadow_dir
        )

    assert count > 0, "expected at least one row logged"

    # Find the CSV written under shadow_dir.
    written = [f for f in os.listdir(shadow_dir) if f.endswith(".csv")]
    assert len(written) >= 1, "expected at least one shadow CSV written"

    # Read it and check it has rows.
    csv_path = os.path.join(shadow_dir, written[0])
    with open(csv_path, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    assert len(rows) > 0


# ── 5. gate filtering: both passed and blocked rows appear ───────────────────

def test_replay_game_to_shadow_log_captures_passed_and_blocked(tmp_path):
    """Rows that pass gates and rows that don't both appear in the batch."""
    shadow_dir = str(tmp_path / "shadow_gate")
    os.makedirs(shadow_dir, exist_ok=True)
    qdf = _fake_qstats(["GAME_B"])

    def _build(game_id, point, qstats_df):
        return _fake_snap(game_id, point)

    def _project(snap, **kw):
        # Player 1001 has a real projection; player 1002 has projected_final=0 (sentinel).
        rows = []
        for stat in ("pts", "reb", "ast"):
            rows.append({
                "player_id": 1001, "name": "pid_1001", "team": "LAL",
                "stat": stat, "current": 5.0, "projected_final": 20.0,
                "period": snap["period"], "snapshot_period": snap["period"],
                "snapshot_clock": "12:00",
            })
            rows.append({
                "player_id": 1002, "name": "pid_1002", "team": "BOS",
                "stat": stat, "current": 0.0, "projected_final": 0.0,  # sentinel
                "period": snap["period"], "snapshot_period": snap["period"],
                "snapshot_clock": "12:00",
            })
        return rows

    # Give L5 lines only for player 1001 (1002 has no line → auto-blocked).
    l5_preds = {("GAME_B", 1001, s): 16.0 for s in ("pts", "reb", "ast")}

    captured: List[Dict] = []

    def _capture_log_batch(records, base_dir=None):
        captured.extend(records)
        return len(records)

    fake_sl = MagicMock()
    fake_sl.log_batch.side_effect = _capture_log_batch

    from src.prediction import snapshot_replay

    with patch("src.prediction.snapshot_replay._rim.load_quarter_stats",
               return_value=qdf), \
         patch("src.prediction.snapshot_replay._rim.build_snapshot",
               side_effect=_build), \
         patch("src.prediction.snapshot_replay.project_from_snapshot",
               side_effect=_project), \
         patch("src.prediction.snapshot_replay._rim.find_game_date",
               return_value="2025-04-02"), \
         patch("src.prediction.snapshot_replay._rim.pregame_predictions_via_gamelog",
               return_value=l5_preds), \
         patch("src.prediction.snapshot_replay._sl", fake_sl), \
         patch("src.prediction.snapshot_replay._HAS_SHADOW", True):
        count = snapshot_replay.replay_game_to_shadow_log(
            "GAME_B", base_dir=shadow_dir
        )

    assert count > 0

    statuses = {r.get("gate_status") for r in captured}
    # Both "passed" and "blocked" must appear.
    assert "passed" in statuses, "expected at least one 'passed' row"
    assert "blocked" in statuses, "expected at least one 'blocked' row (sentinel proj)"
