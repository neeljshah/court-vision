"""Focused regression coverage for the G82 measurement artifact."""
from pathlib import Path

from scripts.platformkit.g82_jump_statistic_measure import measure_table, reproduce_sweep


def test_reproduced_sweep_and_real_retained_table() -> None:
    sweep = reproduce_sweep()
    assert [row["verdict_at_8ft"] for row in sweep] == ["PASS", "PASS", "PASS", "FAIL", "FAIL", "FAIL", "FAIL"]
    result, _, _ = measure_table(
        "tennis_09_retained", "tennis", Path("data/tracking/G83_tennis_09/tracking_data.csv"),
        track="track_id", x="x", y="y", player_filter=True,
    )
    assert result["steps"] == 74
    assert result["oversized_10_29_count"] == 0
