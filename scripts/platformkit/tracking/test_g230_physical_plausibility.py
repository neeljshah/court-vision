import csv
from pathlib import Path

from scripts.platformkit.tracking.g230_physical_plausibility import EXPECTED_HASHES, analyze


def test_analyze_uses_actual_frame_gap_and_player_class(tmp_path, monkeypatch):
    path = Path(tmp_path) / "tennis_01_tracking_data.csv"
    fields = ["frame", "track_id", "cls", "x", "y", "coordinate_space", "source_fps"]
    rows = [
        {"frame": "0", "track_id": "1", "cls": "player", "x": "0", "y": "0", "coordinate_space": "court_feet", "source_fps": "10"},
        {"frame": "5", "track_id": "1", "cls": "player", "x": "20", "y": "0", "coordinate_space": "court_feet", "source_fps": "10"},
        {"frame": "5", "track_id": "9", "cls": "ball", "x": "999", "y": "999", "coordinate_space": "court_feet", "source_fps": "10"},
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader(); writer.writerows(rows)
    digest = __import__("hashlib").sha256(path.read_bytes()).hexdigest()
    monkeypatch.setitem(EXPECTED_HASHES, "tennis_01", digest)
    result = analyze(path)
    assert result["eligible_player_rows"] == 2
    assert result["class_rows"] == {"ball": 1, "player": 2}
    assert result["speed_ft_per_second"]["distribution"]["max"] == 40.0
    assert result["speed_ft_per_second"]["actual_frame_gap_distribution"]["median"] == 5.0
