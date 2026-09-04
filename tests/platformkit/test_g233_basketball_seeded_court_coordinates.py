import numpy as np

from scripts.platformkit.tracking.g233_basketball_seeded_court_coordinates import outside_distance_ft, project_feet, summarize
from scripts.platformkit.tracking.g233_pod_measure import remote_script


def test_g233_projection_summary_and_pod_guard() -> None:
    assert outside_distance_ft(25.0, 47.0) == 0.0
    assert outside_distance_ft(-3.0, 96.0) == np.hypot(3.0, 2.0)
    rows = project_feet(np.eye(3, dtype=np.float32), [(25.0, 47.0), (-1.0, 100.0)])
    report = summarize([{"distance_frames": 0, "projected_player_feet": rows}])
    assert report["distance_bins"][0]["inside_94x50ft_court_rows"] == 1
    assert report["distance_bins"][0]["outside_distance_ft_positive_rows_only"]["n"] == 1
    command = remote_script(1)
    assert "conv=fsync" in command
    assert "run_clip.py" not in command
