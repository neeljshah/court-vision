"""Regression coverage for nullable tracking-harness coverage reports."""
import pandas as pd

from scripts.platformkit.tracking.bridge_infill import bridge_dataframe
from scripts.platformkit.tracking.tracklet_merge import merge_tracklets
from scripts.platformkit.tracking_harness import evaluate


def _court_rows(n_frames: int) -> pd.DataFrame:
    return pd.DataFrame([
        {"frame": frame, "track_id": "p1", "x": float(frame), "y": 1.0,
         "cls": "player", "coordinate_space": "court_feet"}
        for frame in range(n_frames)
    ])


def test_readers_preserve_unmeasurable_coverage_and_keep_measurable_values():
    degenerate = _court_rows(5)
    _, bridge_degenerate = bridge_dataframe(degenerate, "basketball", 10.0)
    _, merge_degenerate = merge_tracklets(degenerate, "basketball", 10.0)

    assert bridge_degenerate.coverage_observed is None
    assert bridge_degenerate.coverage_with_bridge is None
    assert merge_degenerate.coverage_before is None
    assert merge_degenerate.coverage_after is None

    adequate = _court_rows(30)
    expected = evaluate(adequate, "basketball").coverage_pct
    _, bridge_adequate = bridge_dataframe(adequate, "basketball", 10.0)
    _, merge_adequate = merge_tracklets(adequate, "basketball", 10.0)

    assert expected is not None
    assert bridge_adequate.coverage_observed == expected
    assert bridge_adequate.coverage_with_bridge == expected
    assert merge_adequate.coverage_before == expected
    assert merge_adequate.coverage_after == expected
