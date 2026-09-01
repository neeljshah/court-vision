"""Depth checks for canonical tennis tracking CSVs.

The grade is a tracker-observation quality label, not a prediction or betting
claim. A needs two players on 85% of the observed frame span, ball rows on
50%, median rally length of 20 frames, and 25 square feet of coverage for each
tracked player. B uses 60%, 20%, 10 frames, and 10 square feet respectively.
Anything below B is C. The frame span is min-to-max frame because a CSV cannot
represent frames where no object was detected.
"""
from __future__ import annotations

import math
from pathlib import Path
from typing import Union

import pandas as pd

from domains.tennis.tracking.rally_features import SCHEMA, rally_segments


def _require(rows: pd.DataFrame) -> None:
    missing = [column for column in SCHEMA if column not in rows.columns]
    if missing:
        raise ValueError("Tracking rows missing columns: %s" % ", ".join(missing))


def _coverage(players: pd.DataFrame) -> dict[int, float]:
    output: dict[int, float] = {}
    for track_id, track in players.groupby("track_id"):
        output[int(track_id)] = float(
            (track["x"].max() - track["x"].min())
            * (track["y"].max() - track["y"].min())
        )
    return output


def _grade(two_players: float, ball: float, rally: float, coverage: dict[int, float]) -> str:
    values = list(coverage.values())
    if (two_players >= 85.0 and ball >= 50.0 and rally >= 20.0
            and len(values) >= 2 and min(values) >= 25.0):
        return "A"
    if (two_players >= 60.0 and ball >= 20.0 and rally >= 10.0
            and len(values) >= 2 and min(values) >= 10.0):
        return "B"
    return "C"


def quality_report(rows: pd.DataFrame) -> dict[str, object]:
    """Return tennis tracking depth metrics for canonical tracking rows."""
    _require(rows)
    if rows.empty:
        return {
            "pct_frames_two_players": 0.0,
            "pct_frames_ball": 0.0,
            "median_rally_length_frames": math.nan,
            "court_coverage_sqft_by_player": {},
            "depth_grade": "C",
        }
    frames = range(int(rows["frame"].min()), int(rows["frame"].max()) + 1)
    players = rows.loc[rows["cls"] == "player"]
    two_player_frames = sum(
        players.loc[players["frame"] == frame, "track_id"].nunique() >= 2
        for frame in frames
    )
    ball_frames = set(rows.loc[rows["cls"] == "ball", "frame"].astype(int))
    coverage = _coverage(players)
    lengths = [end - start + 1 for start, end in rally_segments(rows)]
    median = float(pd.Series(lengths, dtype=float).median()) if lengths else math.nan
    two_player_pct = 100.0 * two_player_frames / len(frames)
    ball_pct = 100.0 * len(ball_frames) / len(frames)
    return {
        "pct_frames_two_players": two_player_pct,
        "pct_frames_ball": ball_pct,
        "median_rally_length_frames": median,
        "court_coverage_sqft_by_player": coverage,
        "depth_grade": _grade(two_player_pct, ball_pct, median, coverage),
    }


def quality_report_csv(path: Union[str, Path]) -> dict[str, object]:
    """Read a tracking CSV and return its tennis depth report."""
    return quality_report(pd.read_csv(path))
