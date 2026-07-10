"""Tests for domains.mlb.asof_bat_tracking -- the leak guard is the point:
same-day/future snapshots must never join, and out-of-order input rows must
come back aligned to their original position."""
from __future__ import annotations

import pandas as pd

from domains.mlb.asof_bat_tracking import SNAPSHOT_PATH, join_asof_trailing, load_snapshots


def _snapshots() -> pd.DataFrame:
    return pd.DataFrame({
        "id": [1, 1, 2],
        "as_of": pd.to_datetime(["2026-06-01", "2026-06-15", "2026-06-01"]),
        "avg_bat_speed": [70.0, 75.0, 80.0],
        "swing_length": [7.0, 7.5, 8.0],
    })


def test_same_day_snapshot_does_not_leak():
    pa = pd.DataFrame({"batter": [1], "game_date": pd.to_datetime(["2026-06-01"])})
    out = join_asof_trailing(pa, _snapshots())
    assert pd.isna(out.loc[0, "avg_bat_speed"])


def test_day_after_matches_most_recent_strictly_prior():
    pa = pd.DataFrame({"batter": [1, 1], "game_date": pd.to_datetime(["2026-06-02", "2026-06-16"])})
    out = join_asof_trailing(pa, _snapshots())
    assert out.loc[0, "avg_bat_speed"] == 70.0  # only the 06-01 snapshot is strictly prior
    assert out.loc[1, "avg_bat_speed"] == 75.0  # both prior -- picks the most recent (06-15)


def test_no_prior_snapshot_is_nan_not_zero():
    pa = pd.DataFrame({"batter": [2], "game_date": pd.to_datetime(["2026-05-31"])})
    out = join_asof_trailing(pa, _snapshots())
    assert pd.isna(out.loc[0, "avg_bat_speed"])


def test_output_row_order_matches_input_regardless_of_date_order():
    pa = pd.DataFrame({
        "batter": [1, 2, 1],
        "game_date": pd.to_datetime(["2026-06-16", "2026-05-31", "2026-06-02"]),
    })
    out = join_asof_trailing(pa, _snapshots())
    assert len(out) == 3
    assert out.loc[0, "avg_bat_speed"] == 75.0
    assert pd.isna(out.loc[1, "avg_bat_speed"])
    assert out.loc[2, "avg_bat_speed"] == 70.0


def test_load_snapshots_real_file_schema():
    if not SNAPSHOT_PATH.exists():
        return  # data/ is a local-only cache; skip on a clean clone
    df = load_snapshots()
    assert {"id", "as_of", "avg_bat_speed", "swing_length"}.issubset(df.columns)
    assert pd.api.types.is_datetime64_any_dtype(df["as_of"])


def demo() -> None:
    test_same_day_snapshot_does_not_leak()
    test_day_after_matches_most_recent_strictly_prior()
    test_no_prior_snapshot_is_nan_not_zero()
    test_output_row_order_matches_input_regardless_of_date_order()
    test_load_snapshots_real_file_schema()
    print("asof_bat_tracking demo: all checks passed")


if __name__ == "__main__":
    demo()
