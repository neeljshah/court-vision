"""Leak-safety tests for ``tracking_features``.

Run: python -m pytest scripts/platformkit/test_tracking_features.py -q
"""
from __future__ import annotations

import pandas as pd
from pandas.testing import assert_frame_equal

from scripts.platformkit.tracking_features import build_tracking_features


def _tracking_rows() -> pd.DataFrame:
    rows = []
    game_dates = ["2024-01-01", "2024-01-03", "2024-01-05", "2024-01-07"]
    for player in (11, 22, 33):
        for game_no, game_date in enumerate(game_dates, start=1):
            rows.append(
                {
                    "gameId": "00224000%02d" % game_no,
                    "personId": player,
                    "teamId": player + 100,
                    "minutes": "24:00",
                    "speed": 4.0 + player / 100.0 + game_no / 10.0,
                    "distance": 2.0 * game_no,
                    "touches": 10 * game_no,
                    "passes": 5 * game_no,
                    "reboundChancesTotal": 2 * game_no,
                    "secondaryAssists": game_no,
                    "freeThrowAssists": 0,
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
    full = build_tracking_features(tracking.drop(columns="fixtureDate"), dates)
    cutoff = pd.Timestamp("2024-01-05")
    truncated = build_tracking_features(
        tracking.loc[tracking["fixtureDate"] < cutoff].drop(columns="fixtureDate"), dates
    )
    full_before_t = full.loc[full["gameDate"] < cutoff].reset_index(drop=True)
    assert_frame_equal(full_before_t, truncated.reset_index(drop=True), check_dtype=True)
