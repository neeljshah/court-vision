"""Focused tests for bridge-only tracking infill."""
import pandas as pd

from scripts.platformkit.tracking.bridge_infill import bridge_dataframe
from scripts.platformkit.tracking_harness import evaluate


def _rows(frames: list[int], track_id: str = "p", x_step: float = 1.0) -> pd.DataFrame:
    return pd.DataFrame([
        {"frame": frame, "track_id": track_id, "cls": "player", "x": frame * x_step,
         "y": 0.0, "team": "home", "confidence": 0.9}
        for frame in frames
    ])


def test_trailing_observation_is_never_extrapolated():
    table = _rows([100])
    after, report = bridge_dataframe(table, "basketball", {"p99": 6.0})
    assert len(after) == 1
    assert report.rows_bridged == 0
    assert set(after["provenance"]) == {"observed"}


def test_infeasible_endpoint_motion_is_rejected():
    table = _rows([0, 5], x_step=0.0)
    table.loc[table["frame"].eq(5), "x"] = 40.0
    after, report = bridge_dataframe(table, "basketball", {"p99": 6.0})
    assert len(after) == 2
    assert report.gaps_rejected_infeasible == 1
    assert report.gaps_bridged == 0


def test_observed_coverage_matches_harness_and_bridge_rows_have_two_endpoints():
    rows = []
    for track_id in range(6):
        for frame in (0, 2):
            rows.append({"frame": frame, "track_id": track_id, "cls": "player",
                         "x": float(track_id), "y": 0.0, "team": "home"})
    table = pd.DataFrame(rows)
    after, report = bridge_dataframe(table, "basketball", {"basketball": {"p99": 6.0}})
    assert report.coverage_observed == evaluate(table, "basketball").coverage_pct
    assert report.coverage_with_bridge >= report.coverage_observed
    bridged = after.loc[after["provenance"].eq("inferred")]
    assert len(bridged) == 6
    assert set(bridged["frame"]) == {1}
    for track_id in bridged["track_id"].unique():
        observed = after.loc[(after["track_id"] == track_id) & after["provenance"].eq("observed")]
        assert observed["frame"].min() < 1 < observed["frame"].max()


def test_disabled_sports_reject_even_short_gaps():
    after, report = bridge_dataframe(_rows([0, 2]), "tennis", {"p99": 6.0})
    assert len(after) == 2
    assert report.gaps_rejected_gap_too_long == 1
