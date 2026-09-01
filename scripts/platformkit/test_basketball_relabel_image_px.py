"""Focused tests for the basketball image-pixel relabel migration."""
import pandas as pd

from scripts.platformkit.basketball_relabel_image_px import relabel_all


def _source_rows() -> pd.DataFrame:
    return pd.DataFrame({
        "frame": [0, 0, 1, 1], "timestamp": [0.0, 0.0, 0.1, 0.1],
        "player_id": [1, 2, 1, 2], "team": ["a", "b", "a", "b"],
        "x_position": [100, 200, 110, 210], "y_position": [300, 400, 310, 410],
        "ft_x": [1.0, 2.0, 1.1, 2.1], "ft_y": [3.0, 4.0, 3.1, 4.1],
    })


def test_relabel_all_preserves_pixels_and_fails_harness(tmp_path):
    tracking = tmp_path / "tracking"
    for index in range(5):
        game = tracking / "wnba_{:02d}".format(index + 1)
        game.mkdir(parents=True)
        _source_rows().to_csv(game / "tracking_data.csv", index=False)
    for index in range(6):
        game = tracking / "ncaa_{}".format(index + 1)
        game.mkdir(parents=True)
        _source_rows().to_csv(game / "tracking_data.csv", index=False)

    results = relabel_all(tracking)

    assert len(results) == 11
    assert all(result.verdict_before == "FAIL" for result in results)
    assert all(result.verdict_after == "FAIL" for result in results)
    result_path = tracking / "wnba_01" / "tracking_data.csv"
    relabeled = pd.read_csv(result_path)
    assert relabeled.columns.tolist() == [
        "frame", "track_id", "cls", "x", "y", "coordinate_calibration_reason",
        "coordinate_space", "observation", "calibration",
    ]
    assert relabeled[["x", "y"]].values.tolist() == [[100, 300], [200, 400], [110, 310], [210, 410]]
    assert set(relabeled["coordinate_space"]) == {"image_px"}
    assert set(relabeled["coordinate_calibration_reason"]) == {"no_court_calibration_sidecar"}
    assert (tracking / "wnba_01" / "tracking_data.csv.pre_relabel").exists()
