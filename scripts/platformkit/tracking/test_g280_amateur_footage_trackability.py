"""Focused unit checks for G280's schema and G277-normalized profile."""
import csv

import pytest

from scripts.platformkit.tracking.g280_amateur_footage_trackability import analyze, profile
from scripts.platformkit.tracking.g280_amateur_blind_precision import two_proportion


def _write(path, frames=(0, 1, 2)):
    fields = ("frame", "track_id", "cls", "x", "y", "coordinate_space", "observation",
              "calibration", "source_fps", "source_height", "source_duration")
    with path.open("w", newline="", encoding="ascii") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for frame in frames:
            writer.writerow({"frame": frame, "track_id": 1, "cls": "player", "x": 10 * frame,
                             "y": 0, "coordinate_space": "image_px", "observation": "observed",
                             "calibration": "none", "source_fps": 30, "source_height": 720,
                             "source_duration": 3})


def test_profile_uses_only_consecutive_source_frames_and_frame_height_speed(tmp_path):
    path = tmp_path / "tracking_data.csv"
    _write(path)

    result = profile(path)

    assert result["step_count"] == 2
    assert result["speed"]["median"] == pytest.approx(10 / 720 * 30)
    assert result["track_length_frames"]["median"] == 3
    assert result["track_length_seconds"]["median"] == pytest.approx(0.1)


def test_nonconsecutive_rows_have_no_speed_quantile_and_analyze_writes_csv(tmp_path):
    path = tmp_path / "tracking_data.csv"
    _write(path, frames=(0, 3, 6))
    output = tmp_path / "summary.json"

    result = analyze([path], output)

    assert result[0]["step_count"] == 0
    assert result[0]["speed"]["p90"] is None
    assert output.is_file()
    assert output.with_suffix(".csv").is_file()


def test_two_proportion_matches_equal_g273_player_rate():
    result = two_proportion(43, 72, 43)

    assert result["pooled_p"] == pytest.approx(43 / 72)
    assert result["z"] == pytest.approx(0.0)
    assert result["nominal_two_sided_p"] == pytest.approx(1.0)
