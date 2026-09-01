"""Tests for framing-conditioned coverage decomposition."""
import json

import pandas as pd

from scripts.platformkit.tracking.framing_coverage import analyze_csv, analyze_dataframe, sha256


def _fixture() -> pd.DataFrame:
    rows = []
    for frame in range(300):
        player_count = 6 if frame < 200 else 10
        span = 40.0 if frame < 200 else 70.0
        for player in range(player_count):
            rows.append({"frame": frame, "player_id": player, "cls": "player",
                         "x_position": player * span / (player_count - 1), "bbox_x1": 3,
                         "bbox_x2": 100})
    return pd.DataFrame(rows)


def test_synthetic_decomposition_and_read_only_csv(tmp_path):
    source = tmp_path / "game" / "tracking_data.csv"
    source.parent.mkdir()
    _fixture().to_csv(source, index=False)
    before = sha256(source)
    report = analyze_csv(source, "basketball", tmp_path / "reports")
    assert report.coverage_ge8_wide == 1.0
    assert abs(report.coverage_ge8_all - 100 / 300) < 1e-9
    assert abs(report.framing_share + report.detection_share - 1.0) < 1e-9
    assert sha256(source) == before
    assert json.loads((tmp_path / "reports" / "game.json").read_text())["n_frames"] == 300


def test_empty_denominator_uses_nan_share():
    rows = _fixture().query("frame >= 200")
    report = analyze_dataframe(rows, "basketball")
    assert report.coverage_ge8_all == 1.0
    assert report.framing_share != report.framing_share
