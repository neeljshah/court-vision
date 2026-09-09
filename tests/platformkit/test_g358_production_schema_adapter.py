"""Synthetic G358 coverage for the additive production-schema adapter."""
from __future__ import annotations

import hashlib
from pathlib import Path

import pandas as pd

from scripts.platformkit.tracking.image_space_gates import evaluate_image_space
from scripts.platformkit.tracking.production_schema_adapter import adapt_production_section


def _court_source() -> pd.DataFrame:
    return pd.DataFrame([
        {"frame": 4, "player_id": 17, "team": "home", "x_position": 0.0,
         "y_position": 0.0, "ball_x2d": 0.0, "ball_y2d": 0.0,
         "coordinate_space": "image_px"},
        {"frame": 4, "player_id": 18, "team": "away", "x_position": 20.0,
         "y_position": 30.0, "ball_x2d": None, "ball_y2d": None,
         "coordinate_space": "image_px"},
        {"frame": 5, "player_id": 17, "team": "home", "x_position": 2.0,
         "y_position": 3.0, "ball_x2d": 9.0, "ball_y2d": 8.0,
         "coordinate_space": "image_px"},
    ])


def test_synthetic_round_trip_preserves_columns_and_valid_zero() -> None:
    source = _court_source()
    before = source.copy(deep=True)

    adapted = adapt_production_section(source, {"frame_width": 640, "frame_height": 360})

    pd.testing.assert_frame_equal(source, before)
    assert {"x_position", "y_position", "ball_x2d", "ball_y2d", "team"} <= set(adapted.table.columns)
    players = adapted.table.loc[adapted.table["cls"].eq("player")]
    balls = adapted.table.loc[adapted.table["cls"].eq("ball")]
    assert players[["frame", "track_id", "x", "y"]].to_dict("records") == [
        {"frame": 4, "track_id": 17, "x": 0.0, "y": 0.0},
        {"frame": 4, "track_id": 18, "x": 20.0, "y": 30.0},
        {"frame": 5, "track_id": 17, "x": 2.0, "y": 3.0},
    ]
    assert balls[["frame", "x", "y", "ball_source"]].to_dict("records") == [
        {"frame": 4, "x": 0.0, "y": 0.0, "ball_source": "embedded_court"},
        {"frame": 5, "x": 9.0, "y": 8.0, "ball_source": "embedded_court"},
    ]
    assert adapted.frame_size_source == "sidecar"
    assert all(value is False for value in adapted.table["scorable"])


def test_absent_x_norm_is_absent_and_size_gate_is_not_applicable() -> None:
    adapted = adapt_production_section(_court_source())
    rows = {row["gate"]: row for row in evaluate_image_space(
        adapted.table, "basketball", adapted.frame_width, adapted.frame_height,
        adapted.frame_size_source)}

    assert adapted.frame_size_source == "absent"
    assert rows["g325_wholly_off_frame"]["status"] == "NOT_APPLICABLE"
    assert rows["g325_wholly_off_frame"]["reason"] == "frame_size_absent"


def test_px_fields_control_ball_coordinates_and_source_stamp() -> None:
    source = _court_source().assign(ball_x2d_px=[100.0, None, 101.0],
                                    ball_y2d_px=[200.0, None, 201.0])
    adapted = adapt_production_section(source)
    balls = adapted.table.loc[adapted.table["cls"].eq("ball")]

    assert balls[["x", "y", "ball_source"]].to_dict("records") == [
        {"x": 100.0, "y": 200.0, "ball_source": "embedded_px"},
        {"x": 101.0, "y": 201.0, "ball_source": "embedded_px"},
    ]


def test_estimated_size_stays_non_authoritative_for_containment() -> None:
    source = _court_source().assign(x_norm=[0.0, 0.5, 0.25], y_norm=[0.0, 0.5, 0.25])
    adapted = adapt_production_section(source)
    rows = {row["gate"]: row for row in evaluate_image_space(
        adapted.table, "basketball", adapted.frame_width, adapted.frame_height,
        adapted.frame_size_source)}

    assert (adapted.frame_width, adapted.frame_height, adapted.frame_size_source) == (24.0, 36.0, "estimated")
    assert rows["g325_wholly_off_frame"]["status"] == "NOT_APPLICABLE"


def test_prereg_seal_normalizes_crlf_without_git_show() -> None:
    prereg = Path(__file__).resolve().parents[2] / "docs/evidence/tracking/g358_prereg_2026-09-08.md"
    normalized = prereg.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    prefix, seal = normalized.rsplit(b"SEAL sha256 ", 1)
    assert hashlib.sha256(prefix).hexdigest() == seal.strip().decode("ascii")
