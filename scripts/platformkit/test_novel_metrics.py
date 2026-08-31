"""Tests for candidate tracking metrics.

Run: python -m pytest scripts/platformkit/test_novel_metrics.py -q
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from scripts.platformkit.novel_metrics import compute_novel_metrics
from scripts.platformkit.tracking_features import _minutes_as_float


def _engineered_games() -> tuple[pd.DataFrame, pd.DataFrame]:
    rows = []
    state_rows = []
    for number in range(30):
        load = float(number)
        rows.append({"gameId": number, "personId": 7, "minutes": "24:30", "speed": 5 + 2 * load,
                     "touches": (10 - 3 * load) * 24.5 / 36, "contestedFieldGoalsAttempted": number + 1,
                     "uncontestedFieldGoalsAttempted": 30 - number})
        state_rows.append({"gameId": number, "personId": 7, "cum_distance_7d": load,
                           "days_rest": 2 + number % 3, "b2b": number % 4 == 0})
    return pd.DataFrame(rows), pd.DataFrame(state_rows)


def test_engineered_elasticities_are_recovered() -> None:
    """Standardized-load slopes match engineered speed and touch responses."""
    tracking, state = _engineered_games()
    result = compute_novel_metrics(tracking, state).set_index("metric")
    expected_scale = np.arange(30, dtype=float).std(ddof=0)
    assert result.loc["load_speed_elasticity", "value"] == pytest.approx(2 * expected_scale)
    assert result.loc["load_touch_elasticity", "value"] == pytest.approx(-3 * expected_scale)
    assert result.loc["load_speed_elasticity", "r2"] == pytest.approx(1.0)
    assert result.loc["load_speed_elasticity", "n"] == 30


def test_minutes_mm_ss_parse() -> None:
    """MM:SS strings become fractional minutes before per-36 calculation."""
    parsed = _minutes_as_float(pd.Series(["24:30", "00:15"]))
    assert parsed.tolist() == pytest.approx([24.5, 0.25])
