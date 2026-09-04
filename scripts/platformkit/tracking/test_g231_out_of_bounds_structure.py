import csv
import hashlib
from pathlib import Path

from scripts.platformkit.tracking.g231_out_of_bounds_structure import EXPECTED_COUNTS, EXPECTED_HASHES, analyze


def test_analyze_separates_player_edges_and_uses_smallest_scale_minimizer(tmp_path, monkeypatch):
    path = Path(tmp_path) / "tennis_01_tracking_data.csv"
    fields = ["frame", "track_id", "cls", "x", "y", "coordinate_space", "calibration_provenance", "projection_status", "source_fps", "source_height"]
    rows = [
        {"frame": "0", "track_id": "1", "cls": "player", "x": "-1", "y": "10", "coordinate_space": "court_feet", "calibration_provenance": "solved", "projection_status": "", "source_fps": "10", "source_height": "100"},
        {"frame": "1", "track_id": "1", "cls": "player", "x": "156", "y": "72", "coordinate_space": "court_feet", "calibration_provenance": "solved", "projection_status": "", "source_fps": "10", "source_height": "100"},
        {"frame": "2", "track_id": "2", "cls": "ball", "x": "999", "y": "999", "coordinate_space": "court_feet", "calibration_provenance": "solved", "projection_status": "accepted", "source_fps": "10", "source_height": "100"},
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    monkeypatch.setitem(EXPECTED_HASHES, "tennis_01", hashlib.sha256(path.read_bytes()).hexdigest())
    monkeypatch.setitem(EXPECTED_COUNTS, "tennis_01", len(rows))

    result = analyze(path)

    assert result["eligible_denominator"]["rows"] == 2
    assert result["out_of_bounds"]["edge_joint_distribution"] == {"x_gt_78 + y_gt_36": 1, "x_lt_0": 1}
    assert result["scale_fit"]["best_k"] == 2.0
    assert result["scale_fit"]["residual_out_of_bounds_rows"] == 1
    assert result["by_projection_status"] == {"(blank)": {"eligible_player_rows": 2, "out_of_bounds_rows": 2, "out_of_bounds_fraction": 1.0}}
