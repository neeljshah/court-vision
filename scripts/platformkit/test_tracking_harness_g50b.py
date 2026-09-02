"""G50B regression: thin reports withhold only sample-derived metrics."""
import pandas as pd

from scripts.platformkit.tracking_harness import MIN_FRAMES_FOR_METRICS, evaluate


_N_DEPENDENT_FIELDS = (
    "coverage_pct", "det_per_frame", "median_track_len", "ball_valid_pct",
    "ball_in_bounds_pct", "jump_p95", "oob_pct", "zero_step_share",
    "median_step_distance", "distinct_position_ratio", "stationary_track_share",
    "liveness_verdict", "jump_p95_ft_per_s",
)


def _fixture(n_frames: int) -> pd.DataFrame:
    rows = []
    for frame in range(n_frames):
        for track_id in range(6):
            rows.append({"frame": frame, "track_id": track_id, "cls": "player",
                         "x": 10.0 + track_id + frame * 0.02, "y": 25.0,
                         "coordinate_space": "court_feet"})
        rows.append({"frame": frame, "track_id": 99, "cls": "ball", "x": 47.0,
                     "y": 25.0, "coordinate_space": "court_feet"})
    return pd.DataFrame(rows)


def test_g50b_nulls_thin_metrics_without_changing_fixture_verdicts() -> None:
    """Exercise below, at, and above the frame floor plus the two-frame case."""
    expected_passed = {2: False, MIN_FRAMES_FOR_METRICS - 1: True,
                       MIN_FRAMES_FOR_METRICS: True, MIN_FRAMES_FOR_METRICS + 1: True}
    for n_frames, passed_before_g50b in expected_passed.items():
        report = evaluate(_fixture(n_frames), "basketball",
                          source_metadata={"frame_rate": 30, "frame_stride": 3})

        assert report.passed is passed_before_g50b
        assert report.n_frames == n_frames
        assert report.ball_rows == n_frames
        assert report.n_unique_games == 1
        assert report.source_frame_rate == 30.0
        assert report.sampling_interval_s == 0.1
        assert report.verdict == ("PASS" if passed_before_g50b else "FAIL")
        if n_frames < MIN_FRAMES_FOR_METRICS:
            assert report.insufficient_data is True
            assert all(getattr(report, field) is None for field in _N_DEPENDENT_FIELDS)
            assert report.failures == (["median_track_len 2.00 < 3.00",
                                        "stationary_track_share 1.0000 > 0.1490"]
                                       if n_frames == 2 else [])
        else:
            assert report.insufficient_data is False
            assert all(getattr(report, field) is not None for field in _N_DEPENDENT_FIELDS)
