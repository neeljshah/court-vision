"""Per-file test for domains.basketball_nba.states_corpus_ondisk.

Run: cd /c/Users/neelj/nba-ai-system && python -m pytest domains/basketball_nba/test_states_corpus_ondisk.py -q
"""
from __future__ import annotations

import pandas as pd

from domains.basketball_nba.states_corpus_ondisk import (
    FEATURES_AVAILABLE,
    build_rows_from_ondisk,
    run_last_3min_ondisk,
)


def _traj() -> dict:
    # Regulation-second grid, 120s step, decreasing sr (matches ingest_pbp_states).
    return {2760.0: 1.0, 2640.0: -1.0, 2520.0: -2.0, 2400.0: 0.0, 2280.0: -1.0,
            2160.0: -3.0, 2040.0: -1.0, 1920.0: -2.0, 1800.0: -4.0, 1680.0: -1.0,
            1560.0: -5.0, 1440.0: -6.0, 1320.0: -12.0, 1200.0: -6.0, 1080.0: -6.0,
            960.0: -6.0, 840.0: 0.0, 720.0: -4.0, 600.0: -5.0}


def test_features_available_is_run_last_3min_only():
    assert FEATURES_AVAILABLE == ("run_last_3min",)


def test_run_last_3min_ondisk_end_q1_checkpoint():
    traj = _traj()
    # sr=2160 (end_q1), 2 grid steps back = sr+240=2400 -> margin -3.0 - 0.0 = -3.0
    assert run_last_3min_ondisk(traj, 2160.0) == -3.0


def test_run_last_3min_ondisk_missing_point_returns_none():
    traj = {2160.0: -3.0}  # no 2400.0 prior point
    assert run_last_3min_ondisk(traj, 2160.0) is None


def test_run_last_3min_ondisk_half_checkpoint():
    traj = _traj()
    # sr=1440 (half), prior = 1440+240=1680 -> -6.0 - (-1.0) = -5.0
    assert run_last_3min_ondisk(traj, 1440.0) == -5.0


def _pbp_df() -> pd.DataFrame:
    traj = _traj()
    rows = [{"event_id": "e1", "seconds_remaining": sr, "home_margin": m}
            for sr, m in traj.items()]
    # second game with identical trajectory, different event_id
    rows += [{"event_id": "e2", "seconds_remaining": sr, "home_margin": m}
             for sr, m in traj.items()]
    return pd.DataFrame(rows)


def _linescores_df() -> pd.DataFrame:
    return pd.DataFrame([
        {"event_id": "e1", "home_q1": 25.0, "home_q2": 25.0, "home_q3": 25.0, "home_q4": 25.0,
         "away_q1": 25.0, "away_q2": 25.0, "away_q3": 25.0, "away_q4": 21.0},
        {"event_id": "e2", "home_q1": 25.0, "home_q2": 25.0, "home_q3": 25.0, "home_q4": 25.0,
         "away_q1": 25.0, "away_q2": 25.0, "away_q3": 25.0, "away_q4": 21.0},
    ])


def _games_with_p0_df() -> pd.DataFrame:
    return pd.DataFrame([
        {"event_id": "e1", "p_anchored": 0.55, "home_win": 1.0},
        {"event_id": "e2", "p_anchored": 0.60, "home_win": 1.0},
    ])


def test_build_rows_from_ondisk_produces_rows_per_checkpoint():
    rows = build_rows_from_ondisk(_games_with_p0_df(), _linescores_df(), _pbp_df())
    # 2 games x 3 checkpoints = 6 rows (all checkpoints have valid window data)
    assert len(rows) == 6
    checkpoints = {r.checkpoint for r in rows}
    assert checkpoints == {"end_q1", "half", "end_q3"}
    for r in rows:
        assert r.in_bonus_diff == 0.0  # honestly absent from this source


def test_build_rows_from_ondisk_skips_unmatched_event():
    games_with_p0 = pd.DataFrame([{"event_id": "unknown", "p_anchored": 0.5, "home_win": 1.0}])
    rows = build_rows_from_ondisk(games_with_p0, _linescores_df(), _pbp_df())
    assert rows == []
