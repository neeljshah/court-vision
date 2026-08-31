"""Tests for observed tracking-depth capability reporting."""
import json

import pandas as pd

from scripts.platformkit.tracking_depth_inventory import (
    family_for_column,
    inventory_dataframe,
    write_inventory,
)


def test_family_grouping_and_coverage_math(tmp_path):
    df = pd.DataFrame({
        "track_id": [1, 2, None, 4],
        "court_x": [10.0, 95.0, 40.0, None],
        "ball_detected": [1, 0, None, 1],
        "event_type": ["pass", "shot", "", None],
        "camera_id": [None, None, None, None],
    })
    inventory = {item.name: item for item in inventory_dataframe(df)}
    assert family_for_column("track_id") == "IDENTITY"
    assert family_for_column("court_x") == "POSITION"
    assert family_for_column("ball_detected") == "BALL"
    assert inventory["track_id"].non_null_pct == 75.0
    assert inventory["court_x"].non_null_pct == 75.0
    assert inventory["court_x"].validity_pct == 66.67
    assert inventory["ball_detected"].validity == "set flag rate"
    assert inventory["ball_detected"].validity_pct == 66.67

    source = tmp_path / "tracking_data.csv"
    df.to_csv(source, index=False)
    json_path, markdown_path, ascii_report = write_inventory(source, "nba", tmp_path / "evidence")
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["rows"] == 4
    assert "IDENTITY" in ascii_report and "POSITION" in ascii_report
    assert "NOT YET RELIABLE" in markdown_path.read_text(encoding="utf-8")
