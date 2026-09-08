"""Read-only translation of G353 production rows to image-gate rows.

Production tables have player coordinates and embed ball coordinates on player
rows.  This preserves the finisher's row conversion: player_id/x_position/
y_position become player rows and one non-null ball observation per frame becomes
a ball row.  Only decoded width and height count as frame dimensions; x_norm and
y_norm are not a substitute for the containment gate.
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class Translation:
    """Translated rows plus decoded-frame provenance for image gate calls."""

    table: pd.DataFrame
    frame_width: float | None
    frame_height: float | None
    frame_size_source: str


def _decoded_size(window: pd.DataFrame) -> tuple[float | None, float | None, str]:
    if not {"frame_width", "frame_height"}.issubset(window.columns):
        return None, None, "absent"
    dims = window[["frame_width", "frame_height"]].apply(pd.to_numeric, errors="coerce").dropna()
    if dims.empty or (dims <= 0).any().any():
        return None, None, "absent"
    return float(dims["frame_width"].iloc[0]), float(dims["frame_height"].iloc[0]), "decoded"


def translate_production_window(window: pd.DataFrame) -> Translation:
    """Translate one production window without changing its supplied rows."""
    required = {"frame", "player_id", "team", "x_position", "y_position", "ball_x2d",
                "ball_y2d", "coordinate_space"}
    missing = sorted(required.difference(window.columns))
    if missing:
        raise ValueError("production window missing columns: {}".format(", ".join(missing)))
    width, height, source = _decoded_size(window)
    players = window[["frame", "player_id", "team", "x_position", "y_position", "coordinate_space"]].rename(
        columns={"player_id": "track_id", "x_position": "x", "y_position": "y"})
    players["cls"] = "player"
    players["ball_source"] = "not_ball"
    balls = window.dropna(subset=["ball_x2d", "ball_y2d"]).groupby("frame", as_index=False).first()
    if not balls.empty:
        ball_rows = balls[["frame", "ball_x2d", "ball_y2d", "coordinate_space"]].rename(
            columns={"ball_x2d": "x", "ball_y2d": "y"})
        ball_rows["track_id"] = -1
        ball_rows["team"] = None
        ball_rows["cls"] = "ball"
        ball_rows["ball_source"] = "embedded"
        table = pd.concat([players, ball_rows], ignore_index=True, sort=False)
    else:
        table = players
    table["frame_size_source"] = source
    columns = ["frame", "track_id", "x", "y", "cls", "coordinate_space", "team", "ball_source",
               "frame_size_source"]
    return Translation(table=table[columns], frame_width=width, frame_height=height,
                       frame_size_source=source)
