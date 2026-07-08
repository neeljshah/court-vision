"""Synthetic-frame tests for lineup_matchups.py -- no parquet/network I/O."""
from __future__ import annotations

import pandas as pd

from domains.basketball_nba.lineups.lineup_matchups import (
    aggregate_matchups,
    build_game_matchups,
    intersect_stints,
)


def _stint(team_id, period, start_s, end_s, lineup_key, pts_for, n_on_court=5):
    return {
        "game_id": "G1", "team_id": team_id, "period": period,
        "lineup_key": lineup_key, "n_on_court": n_on_court,
        "start_s": float(start_s), "end_s": float(end_s), "elapsed_s": float(end_s - start_s),
        "pts_for": pts_for, "pts_against": 0, "quality": "",
    }


def test_exact_interval_intersection():
    # team A: one stint 0-100s (10 pts). team B: two stints, 0-50s (5 pts) and 50-100s (5 pts).
    stints_a = [_stint(1, 1, 0, 100, "a1", 10)]
    stints_b = [_stint(2, 1, 0, 50, "b1", 5), _stint(2, 1, 50, 100, "b2", 5)]
    segs = intersect_stints(stints_a, stints_b)
    assert len(segs) == 2
    assert segs[0]["overlap_s"] == 50.0 and segs[0]["lineup_key_b"] == "b1"
    assert segs[1]["overlap_s"] == 50.0 and segs[1]["lineup_key_b"] == "b2"
    # hand-computed: A's 10 pts over 100s apportions to 5 pts per 50s half; B's stints are
    # already exactly 50s each so their full pts_for carries straight through.
    assert segs[0]["pts_a"] == 5.0 and segs[0]["pts_b"] == 5.0
    assert segs[1]["pts_a"] == 5.0 and segs[1]["pts_b"] == 5.0


def test_apportionment_sums_preserved():
    # team A's single 12-pt stint spans 3 unevenly-sized B stints -> segment pts_a must
    # sum back to A's stint total (within float rounding), same for each B stint's pts_b.
    stints_a = [_stint(1, 1, 0, 120, "a1", 12)]
    stints_b = [
        _stint(2, 1, 0, 30, "b1", 3),
        _stint(2, 1, 30, 90, "b2", 9),
        _stint(2, 1, 90, 120, "b3", 3),
    ]
    segs = intersect_stints(stints_a, stints_b)
    assert len(segs) == 3
    assert sum(s["pts_a"] for s in segs) == 12.0
    for seg, b in zip(segs, stints_b):
        assert seg["pts_b"] == b["pts_for"]  # each B stint fully covered by A -> full pts_for carries


def test_non_overlapping_stints_produce_no_segment():
    stints_a = [_stint(1, 1, 0, 50, "a1", 5)]
    stints_b = [_stint(2, 1, 50, 100, "b1", 5)]
    assert intersect_stints(stints_a, stints_b) == []


def test_game_date_join_present_on_every_row():
    stints_df = pd.DataFrame([
        _stint(1, 1, 0, 60, "a1", 6),
        _stint(2, 1, 0, 60, "b1", 4),
        _stint(1, 1, 0, 60, "a1", 6),  # second game, reused literal team/period/lineup ids
        _stint(2, 1, 0, 60, "b1", 4),
    ])
    stints_df.loc[2:, "game_id"] = "G2"
    games_df = pd.DataFrame({"game_id": ["G1", "G2"], "date": pd.to_datetime(["2025-11-01", "2025-11-02"])})

    seg_df = build_game_matchups(stints_df)
    result = aggregate_matchups(seg_df, games_df)

    assert len(result) == 2
    assert result["game_date"].notna().all()
    assert set(result["game_date"].dt.strftime("%Y-%m-%d")) == {"2025-11-01", "2025-11-02"}
