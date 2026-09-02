"""Focused tests for the soccer decimal-close join."""
from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd

from scripts.platformkit.eval_gate.close_join import JoinSpec, close_column
from scripts.platformkit.eval_gate.walkforward import walk_forward

_SPEC = JoinSpec("soccer", "event_id", "date", "over", "under", "fallback_over", "fallback_under", "over25", "under25")


def test_even_decimal_pair_is_exactly_half():
    result = close_column(pd.DataFrame({"over": [2.0], "under": [2.0]}), _SPEC)
    assert result.iloc[0] == 0.5
    assert result.attrs["bad_price_drop_count"] == 0
    assert result.attrs["null_close_count"] == 0


def test_lopsided_decimal_pair_has_correct_side_probability():
    result = close_column(pd.DataFrame({"over": [2.0], "under": [4.0]}), _SPEC)
    assert result.iloc[0] == 2.0 / 3.0


def test_bad_decimal_prices_are_dropped_and_counted():
    frame = pd.DataFrame({"over": [2.0, 0.0, np.nan, 1.0], "under": [2.0, 2.0, 2.0, 2.0]})
    result = close_column(frame, _SPEC)
    assert result.notna().sum() == 1
    assert result.attrs["bad_price_drop_count"] == 2
    assert result.attrs["null_close_count"] == 1


def test_walk_forward_smoke_on_forty_synthetic_states():
    start = date(2024, 1, 1)
    states = []
    for i in range(40):
        day = start + timedelta(days=4 * i)
        iso = day.isoformat()
        states.append({
            "game_id": f"g{i}", "state_ts": f"{iso}T12:00:00", "home": f"H{i}", "away": f"A{i}",
            "features": {"p_base": 0.5}, "feature_avail": {"p_base": f"{iso}T00:00:00"},
            "devig_close_prob": 0.5, "outcome": i % 2,
        })
    result = walk_forward(states, lambda train, test, inside: 0.5, select_inside=True)
    assert len(result.records) == 40
    assert result.select_inside is True
