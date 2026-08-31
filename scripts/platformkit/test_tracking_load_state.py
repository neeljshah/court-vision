"""Leak-safety tests for ``tracking_load_state``.

Run: python -m pytest scripts/platformkit/test_tracking_load_state.py -q
"""
from __future__ import annotations

import pandas as pd
import pytest
from pandas.testing import assert_frame_equal

from scripts.platformkit.tracking_load_state import build_tracking_load_state


def _tracking_rows() -> pd.DataFrame:
    rows = []
    game_dates = ["2024-01-01", "2024-01-03", "2024-01-08", "2024-01-10", "2024-01-11"]
    for player in (11, 22):
        for game_no, game_date in enumerate(game_dates, start=1):
            rows.append(
                {
                    "gameId": "00224000%02d" % game_no,
                    "personId": player,
                    "minutes": "24:00",
                    "distance": float(10 * game_no),
                    "speed": [10.0, 8.0, 6.0, 4.0, 2.0][game_no - 1],
                    "fixtureDate": game_date,
                }
            )
    result = pd.DataFrame(rows)
    result["fixtureDate"] = pd.to_datetime(result["fixtureDate"])
    return result


def test_truncation_invariance() -> None:
    """Rows before T are identical whether or not games after T exist."""
    tracking = _tracking_rows()
    dates = dict(zip(tracking["gameId"], tracking["fixtureDate"]))
    full = build_tracking_load_state(tracking.drop(columns="fixtureDate"), dates)
    cutoff = pd.Timestamp("2024-01-10")
    truncated = build_tracking_load_state(
        tracking.loc[tracking["fixtureDate"] < cutoff].drop(columns="fixtureDate"), dates
    )
    full_before_t = full.loc[full["gameDate"] < cutoff].reset_index(drop=True)
    assert_frame_equal(full_before_t, truncated.reset_index(drop=True), check_dtype=True)


def test_calendar_windows_and_rest_days() -> None:
    """Calendar windows, rest days, and shifted speed state have exact values."""
    tracking = _tracking_rows().query("personId == 11")
    dates = dict(zip(tracking["gameId"], tracking["fixtureDate"]))
    state = build_tracking_load_state(tracking.drop(columns="fixtureDate"), dates)

    assert state.loc[2, "cum_distance_7d"] == 30.0
    assert state.loc[3, "cum_distance_7d"] == 50.0
    assert state.loc[4, "cum_distance_7d"] == 70.0
    assert state.loc[3, "cum_distance_14d"] == 60.0
    assert state.loc[3, "minutes_7d"] == 48.0
    assert state["days_rest"].tolist()[1:] == [2.0, 5.0, 2.0, 1.0]
    assert state["b2b"].tolist() == [False, False, False, False, True]
    assert state.loc[4, "speed_decline_ratio"] == pytest.approx(6.0 / 7.0)
