"""Focused tests for NBA/WNBA tracking depth measurement."""
from __future__ import annotations

import pandas as pd

from domains.basketball_nba.tracking.quality_probe import (
    DEPTH_GRADE_THRESHOLDS,
    compare_games,
    measure_dataframe,
)
from scripts.platformkit.tracking_harness import SPORTS


def _game(frames: int = 60, players: int = 10) -> pd.DataFrame:
    rows = []
    for frame in range(frames):
        for player in range(players):
            rows.append({
                "frame": frame, "player_id": str(player),
                "ft_x": 40.0 if player == 0 else (43.0 if player == 1 else 60.0 + player),
                "ft_y": 25.0 + (player % 2), "ball_x2d": 40.0, "ball_y2d": 25.0,
                "homography_valid": 1, "team": "A" if player < 5 else "B",
                "jersey_number": player + 1, "has_possession": player == 0,
            })
    return pd.DataFrame(rows)


def test_production_aliases_and_depth_metrics() -> None:
    report = measure_dataframe(_game(), sport="wnba")
    assert report.sport == "wnba"
    assert report.pct_frames_ge_8_players == 1.0
    assert report.pct_frames_homography_valid == 1.0
    assert report.ball_row_coverage == 1.0
    assert report.jersey_number_fill_rate == 1.0
    assert report.team_assignment_fill_rate == 1.0
    assert report.median_track_length == 60.0
    assert report.screen_candidate_count == 1
    assert report.screen_candidates_per_minute == 30.0
    assert report.depth_grade == "A"


def test_grade_b_floor_is_tied_to_harness_and_compare_is_ascii(tmp_path, capsys) -> None:
    frame = _game(frames=10, players=7)
    frame.loc[frame.index % 3 == 0, "homography_valid"] = 0
    frame.loc[frame.index % 2 == 0, "jersey_number"] = -1
    frame.loc[frame.index % 4 == 0, "team"] = ""
    report = measure_dataframe(frame)
    assert report.depth_grade == "C"
    assert DEPTH_GRADE_THRESHOLDS["B"]["players_ge_8"] == SPORTS["basketball"]["coverage_min"]
    nba = tmp_path / "nba_game.csv"
    wnba = tmp_path / "wnba_game.csv"
    _game(frames=3).to_csv(nba, index=False)
    _game(frames=3).to_csv(wnba, index=False)
    compare_games([nba, wnba])
    output = capsys.readouterr().out
    assert "NBA" in output and "WNBA" in output and "DEPTH" in output
    output.encode("ascii")
