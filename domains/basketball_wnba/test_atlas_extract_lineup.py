"""Per-file tests for domains.basketball_wnba.atlas_extract_lineup.

Run: cd /c/Users/neelj/nba-ai-system && python -m pytest domains/basketball_wnba/test_atlas_extract_lineup.py -q
"""
from __future__ import annotations

from domains.basketball_wnba.atlas_extract_lineup import build_lineup_exposure_frame
from domains.basketball_wnba.lineup_stints import Stint


def _stint(game_id, team_id, lineup, minutes, pf, pa):
    return Stint(game_id=game_id, team_id=team_id, side="home", lineup=lineup,
                 elapsed_start_sec=0.0, elapsed_end_sec=minutes * 60.0, pts_for=pf, pts_against=pa)


def test_empty_stints_gives_empty_frame():
    df = build_lineup_exposure_frame([])
    assert df.empty


def test_minutes_share_and_pts_aggregate_across_games():
    lu = ("p1", "p2", "p3", "p4", "p5")
    lu2 = ("p1", "p2", "p3", "p4", "p6")
    stints = [
        _stint("g1", "T1", lu, 20.0, 15, 10),
        _stint("g2", "T1", lu, 15.0, 10, 12),
        _stint("g1", "T1", lu2, 20.0, 12, 14),
    ]
    df = build_lineup_exposure_frame(stints)
    assert len(df) == 2

    row = df[df["lineup_player_ids"] == ",".join(lu)].iloc[0]
    assert row["n_games"] == 2
    assert abs(row["minutes"] - 35.0) < 1e-6
    assert abs(row["minutes_share"] - 35.0 / 55.0) < 1e-3
    assert row["pts_for"] == 25 and row["pts_against"] == 22
    assert row["net_pts"] == 3
    assert row["confidence"] == "low"  # n_games=2 < 5

    row2 = df[df["lineup_player_ids"] == ",".join(lu2)].iloc[0]
    assert row2["n_games"] == 1
    assert abs(row2["minutes_share"] - 20.0 / 55.0) < 1e-3
