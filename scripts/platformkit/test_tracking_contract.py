"""Focused tests for the normalized tracking contract."""
import json

import numpy as np
import pandas as pd

from scripts.platformkit.tracking_contract import normalize_tracking_table


def _aliased_rows():
    return pd.DataFrame({
        "frame": [1, 1, 2],
        "player_id": [10, 11, 10],
        "cls": ["player", "player", "ball"],
        "ft_x": [10.0, 12.0, 11.0],
        "ft_y": [5.0, 5.0, 6.0],
    })


def test_aliases_normalize_and_report_required_fields():
    normalized, report = normalize_tracking_table(_aliased_rows(), "WNBA", "feet")
    assert list(normalized.columns) == ["frame", "track_id", "cls", "x", "y"]
    assert report.canonical_sport == "wnba"
    assert report.coordinate_units == "feet"
    assert report.row_count == 3 and report.frame_count == 2
    assert report.duplicate_key_count == 0 and report.status == "PASS"
    assert json.loads(report.to_json())["required_columns"] == list(normalized.columns)


def test_csv_input_and_duplicate_keys_are_reported(tmp_path):
    source = tmp_path / "rows.csv"
    rows = _aliased_rows()
    rows.loc[2, "player_id"] = 10
    rows.loc[2, "frame"] = 1
    rows.to_csv(source, index=False)
    normalized, report = normalize_tracking_table(source, "basketball")
    assert len(normalized) == 3
    assert report.duplicate_key_count == 1
    assert report.status == "PASS"


def test_unknown_sport_missing_columns_and_unknown_alias_reject():
    _, unknown_sport = normalize_tracking_table(_aliased_rows(), "cricket")
    _, unknown_alias = normalize_tracking_table(
        pd.DataFrame({"frame_id": [1], "player_id": [1], "cls": ["player"],
                      "ft_x": [1.0], "ft_y": [2.0]}), "soccer"
    )
    assert unknown_sport.status == "REJECT"
    assert unknown_alias.status == "REJECT"
    assert "missing required columns: frame" in unknown_alias.errors


def test_nonfinite_player_coordinates_reject_but_ball_rows_do_not():
    player = _aliased_rows()
    player.loc[0, "ft_x"] = np.inf
    _, player_report = normalize_tracking_table(player, "football")
    ball = _aliased_rows()
    ball.loc[2, "ft_x"] = np.nan
    _, ball_report = normalize_tracking_table(ball, "football")
    assert player_report.status == "REJECT"
    assert "non-finite player coordinates" in player_report.errors
    assert ball_report.status == "PASS"


def test_empty_or_absent_input_is_data_pending(tmp_path):
    empty = pd.DataFrame(columns=["frame", "track_id", "cls", "x", "y"])
    _, empty_report = normalize_tracking_table(empty, "tennis")
    _, missing_report = normalize_tracking_table(tmp_path / "missing.parquet", "tennis")
    assert empty_report.status == "DATA_PENDING"
    assert missing_report.status == "DATA_PENDING"
