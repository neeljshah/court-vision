"""Tolerance contract for the NBA wall-clock state join."""
from __future__ import annotations

import pandas as pd

from scripts.platformkit.eval_gate.asof_join import asof_join_state
from scripts.platformkit.venue_history.nba_wallclock_join import join_game_states


def _states() -> list[dict]:
    return [{"ts": 1000, "period": 1, "game_clock_s": 700.0,
             "score_home": 4, "score_away": 2, "margin": 2}]


def _candles() -> list[dict]:
    return [
        {"ts": 1100, "prob": 0.55, "traded": True},
        {"ts": 1301, "prob": 0.60, "traded": True},
    ]


def test_wallclock_join_applies_the_300_second_staleness_rail() -> None:
    """A fresh state survives; stale state columns are nulled before drop."""
    ticks = pd.DataFrame({"ts": [1100, 1301], "market_prob": [0.55, 0.60],
                          "traded": [True, True]})
    states = pd.DataFrame(_states())
    raw, stale_share = asof_join_state(ticks, states, "ts", 300)
    assert raw["margin"].tolist()[0] == 2
    assert pd.isna(raw["margin"].tolist()[1])
    assert stale_share == 0.5

    joined = join_game_states(_states(), _candles())
    assert list(joined["ts"]) == [1100]
    assert joined.attrs["stale_share"] == 0.5
    assert joined.attrs["max_staleness_s"] == 300.0
