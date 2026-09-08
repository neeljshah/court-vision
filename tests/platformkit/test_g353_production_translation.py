"""G353 production-schema translation coverage."""
from __future__ import annotations

import pandas as pd

from scripts.platformkit.tracking.g353_production_translation import translate_production_window


def test_three_production_rows_round_trip_with_embedded_ball_and_absent_size() -> None:
    source = pd.DataFrame([
        {"frame": 1, "player_id": 7, "team": "home", "x_position": 11.0, "y_position": 12.0,
         "x_norm": None, "y_norm": None, "ball_x2d": 30.0, "ball_y2d": 31.0,
         "coordinate_space": "image_px"},
        {"frame": 1, "player_id": 8, "team": "away", "x_position": 21.0, "y_position": 22.0,
         "x_norm": None, "y_norm": None, "ball_x2d": None, "ball_y2d": None,
         "coordinate_space": "image_px"},
        {"frame": 2, "player_id": 7, "team": "home", "x_position": 13.0, "y_position": 14.0,
         "x_norm": None, "y_norm": None, "ball_x2d": None, "ball_y2d": None,
         "coordinate_space": "image_px"},
    ])

    translated = translate_production_window(source)

    players = translated.table.loc[translated.table["cls"].eq("player")]
    ball = translated.table.loc[translated.table["cls"].eq("ball")].iloc[0]
    assert players[["frame", "track_id", "x", "y"]].to_dict("records") == [
        {"frame": 1, "track_id": 7, "x": 11.0, "y": 12.0},
        {"frame": 1, "track_id": 8, "x": 21.0, "y": 22.0},
        {"frame": 2, "track_id": 7, "x": 13.0, "y": 14.0},
    ]
    assert ball["ball_source"] == "embedded"
    assert translated.frame_size_source == "absent"
    assert translated.frame_width is None and translated.frame_height is None
