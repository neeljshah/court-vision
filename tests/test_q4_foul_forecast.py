"""test_q4_foul_forecast.py -- cycle 96c (loop 5).

Validates the Q4 PF forecast head + its interaction with the cycle-89b
unified ``foul_trouble_factor``.
"""
from __future__ import annotations

import os
import sys

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from src.prediction.q4_foul_forecast import (  # noqa: E402
    forecast_q4_pf_addition,
    forecasted_endgame_pf,
)
from src.prediction.live_factors import foul_trouble_factor  # noqa: E402


def test_forecast_in_0_to_3_range():
    """Forecast must always be a float in [0.0, 3.0]."""
    cases = [
        (0, 0, None, None),
        (2, 1, "Guard", None),
        (3, 2, "Center", 0.5),
        (4, 2, "Forward", None),
        (5, 1, "Center", None),
        (6, 3, "Center", None),
        (-1, -1, "junk", None),
        (None, None, None, None),
    ]
    for pf, q3pf, pos, opp in cases:
        v = forecast_q4_pf_addition(pf, q3pf, pos, opp)
        assert isinstance(v, float), f"non-float for {pf,q3pf,pos,opp}"
        assert 0.0 <= v <= 3.0, f"out of range for {pf,q3pf,pos,opp}: {v}"


def test_q3_high_pf_raises_forecast():
    """Player carrying pf>=3 (with non-zero q3 pf) forecasts MORE Q4 PF
    than a clean player."""
    baseline = forecast_q4_pf_addition(0, 0, "Guard")
    trouble = forecast_q4_pf_addition(3, 1, "Guard")
    assert trouble > baseline, f"trouble={trouble} <= baseline={baseline}"


def test_pf5_sits_lower_forecast():
    """A pf>=5 player forecasts a REDUCED Q4 rate (player protects /
    coach pulls early)."""
    danger = forecast_q4_pf_addition(5, 1, "Guard")
    mid = forecast_q4_pf_addition(3, 1, "Guard")
    assert danger < mid, f"pf=5 forecast {danger} not < pf=3 forecast {mid}"


def test_forecasted_pf_applies_foul_trouble_band():
    """End-to-end: take a Q3-snapshot pf=3 player who's been picking up
    fouls, forecast the endgame pf, and confirm ``foul_trouble_factor``
    drops below 1.00 when the forecasted pf crosses into the 4-foul band.
    """
    # Snapshot at endQ3 (period=4 about to start, clock=12:00):
    snap_pf = 3
    forecasted = forecasted_endgame_pf(snap_pf, q3_pf=2, position_proxy="Center")
    # Snapshot pf alone -> no penalty at pf=3 in Q4.
    f_snap = foul_trouble_factor(snap_pf, period=4, clock_minutes_remaining=12.0)
    f_fore = foul_trouble_factor(forecasted, period=4, clock_minutes_remaining=12.0)
    assert f_snap == 1.0, f"snapshot pf=3 in Q4 should be neutral, got {f_snap}"
    assert forecasted >= 4, f"expected forecasted pf>=4, got {forecasted}"
    assert f_fore < 1.0, f"forecasted pf={forecasted} should trigger band, got {f_fore}"


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-q"]))
