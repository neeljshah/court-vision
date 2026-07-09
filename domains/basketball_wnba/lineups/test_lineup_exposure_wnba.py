"""Per-file tests for domains.basketball_wnba.lineups.lineup_exposure_wnba.

Run: cd /c/Users/neelj/nba-ai-system && python -m pytest domains/basketball_wnba/lineups/test_lineup_exposure_wnba.py -q
"""
from __future__ import annotations

import pandas as pd

from domains.basketball_wnba.lineups.lineup_exposure_wnba import (
    build_lineup_exposure_frame_from_stints,
)

_LU1 = "p1,p2,p3,p4,p5"
_LU2 = "p1,p2,p3,p4,p6"


def _stint(game_id, team_id, period, lineup_key, elapsed_s, pf, pa, n_on_court=5):
    return {
        "game_id": game_id, "team_id": team_id, "period": period, "lineup_key": lineup_key,
        "n_on_court": n_on_court, "start_s": 0.0, "end_s": elapsed_s, "elapsed_s": elapsed_s,
        "pts_for": pf, "pts_against": pa, "quality": "",
    }


def _box(game_id, date, player_id, name):
    return {"game_id": game_id, "game_date": date, "player_id": player_id, "player_name": name}


def test_empty_stints_gives_empty_frame():
    df = build_lineup_exposure_frame_from_stints(pd.DataFrame(
        columns=["game_id", "team_id", "period", "lineup_key", "n_on_court", "elapsed_s", "pts_for", "pts_against"]
    ), pd.DataFrame())
    assert df.empty


def test_dirty_stints_dropped_clean_ones_aggregated_with_dates():
    stints = pd.DataFrame([
        _stint("g1", 1, 1, _LU1, 1200.0, 15, 10),
        _stint("g2", 1, 1, _LU1, 900.0, 10, 12),
        _stint("g1", 1, 2, _LU2, 1200.0, 12, 14),
        _stint("g1", 1, 3, _LU1, 999.0, 1, 1, n_on_court=4),  # dirty -- must be dropped
    ])
    box = pd.DataFrame([
        _box("g1", "2026-05-01", "p1", "Alpha"),
        _box("g2", "2026-05-03", "p1", "Alpha"),
    ])
    df = build_lineup_exposure_frame_from_stints(stints, box)
    assert len(df) == 2  # dirty stint's lineup never contributes a new row alone here

    row = df[df["lineup_player_ids"] == _LU1].iloc[0]
    assert row["n_games"] == 2
    assert abs(row["minutes"] - 35.0) < 1e-6  # (1200+900)/60, dirty 999s excluded
    assert abs(row["minutes_share"] - 35.0 / 55.0) < 1e-3
    assert row["pts_for"] == 25 and row["pts_against"] == 22
    assert row["net_pts"] == 3
    assert row["lineup_player_names"].startswith("Alpha,")
    assert row["first_game_date"] == "2026-05-01" and row["last_game_date"] == "2026-05-03"
    assert row["team_id"] == 1
    assert df["team_id"].dtype == "int64"

    row2 = df[df["lineup_player_ids"] == _LU2].iloc[0]
    assert row2["n_games"] == 1
    assert abs(row2["minutes_share"] - 20.0 / 55.0) < 1e-3


def test_parquet_round_trip_via_tmp_path(tmp_path):
    stints_path = tmp_path / "stints.parquet"
    box_path = tmp_path / "box.parquet"
    pd.DataFrame([_stint("g1", 2, 1, _LU1, 600.0, 8, 4)]).to_parquet(stints_path, index=False)
    pd.DataFrame([_box("g1", "2026-05-10", "p1", "Beta")]).to_parquet(box_path, index=False)

    df = build_lineup_exposure_frame_from_stints(pd.read_parquet(stints_path), pd.read_parquet(box_path))
    assert len(df) == 1
    assert df.iloc[0]["minutes_share"] == 1.0
    assert df.iloc[0]["first_game_date"] == "2026-05-10"
