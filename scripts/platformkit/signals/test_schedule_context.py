"""Focused N11 tests. Run this file only with pytest."""
from __future__ import annotations

import pandas as pd
from pandas.testing import assert_frame_equal

from scripts.platformkit.signals.schedule_context import (
    OUTPUT_COLUMNS, build_schedule_context, fill_rate_report,
)


VENUES = {
    "A": {"venue_id": "va", "lat": 39.739, "lon": -104.99, "elevation_m": 1609,
          "tz_name": "America/Denver"},
    "B": {"venue_id": "vb", "lat": 25.761, "lon": -80.191, "elevation_m": 2,
          "tz_name": "America/New_York"},
    "C": {"venue_id": "vc", "lat": 34.052, "lon": -118.244, "elevation_m": 71,
          "tz_name": "America/Los_Angeles"},
    "D": {"venue_id": "vd", "lat": 41.878, "lon": -87.630, "elevation_m": 181,
          "tz_name": "America/Chicago"},
}


def _schedule(n: int = 30) -> pd.DataFrame:
    rows = []
    for i in range(n):
        rows.append({"event_id": f"g{i:02d}", "date": pd.Timestamp("2024-01-01") + pd.Timedelta(days=i),
                     "start_time": "19:30", "home_team": "A" if i % 2 == 0 else "B",
                     "away_team": "B" if i % 2 == 0 else "A",
                     "venue": "A" if i % 2 == 0 else "B"})
    return pd.DataFrame(rows)


def test_truncation_invariance_all_six_columns():
    schedule = _schedule()
    full = build_schedule_context(schedule, VENUES)
    for i, row in schedule.iterrows():
        truncated = build_schedule_context(schedule.iloc[: i + 1], VENUES)
        expected = full.loc[full["event_id"] == row["event_id"], ["event_id", *OUTPUT_COLUMNS]].reset_index(drop=True)
        actual = truncated.tail(1).reset_index(drop=True)
        assert_frame_equal(actual, expected, check_exact=True)


def test_debut_rows_are_nan_not_zero():
    out = build_schedule_context(_schedule(3), VENUES)
    first = out.iloc[0]
    assert first[list(OUTPUT_COLUMNS)].isna().all()
    assert not (first[list(OUTPUT_COLUMNS)] == 0.0).any()


def test_fill_rate_is_reported_per_column_and_long_input_is_supported():
    game = _schedule(30)
    long_rows = []
    for _, row in game.iterrows():
        for home in (True, False):
            team = row["home_team"] if home else row["away_team"]
            opponent = row["away_team"] if home else row["home_team"]
            long_rows.append({"game_id": row["event_id"], "date": row["date"],
                              "start_time": row["start_time"], "team": team,
                              "opponent": opponent, "is_home": home,
                              "venue": row["venue"]})
    out = build_schedule_context(pd.DataFrame(long_rows), VENUES)
    report = fill_rate_report(out)
    assert set(report) == set(OUTPUT_COLUMNS)
    assert all(0.0 <= value <= 1.0 for value in report.values())
    assert all(value >= 0.95 for value in report.values())
    assert out.attrs["fill_rate"] == report


def test_known_schedule_values_use_prior_venue_only():
    out = build_schedule_context(_schedule(3), VENUES)
    # g2: away B last played at B in g1. The current game venue is A and must
    # not be confused with the prior venue.
    assert out.loc[2, "travel_km_since_last_game"] > 0.0
    assert out.loc[2, "altitude_delta_m"] == 803.5
    assert out.loc[2, "timezone_shift_signed"] == -1.0
