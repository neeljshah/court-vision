from __future__ import annotations

import pandas as pd

from scripts.platformkit.ingame.wnba_wallclock_join import join_game_states, states_from_payload


def test_states_from_payload_and_asof_rail() -> None:
    payload = {"game": {"actions": [
        {"timeActual": "2026-06-01T12:00:00.0Z", "clock": "PT10M00.00S", "period": 1,
         "scoreHome": "2", "scoreAway": "0"},
        {"timeActual": "bad", "clock": "PT09M50.00S", "period": 1,
         "scoreHome": "2", "scoreAway": "0"},
    ]}}
    states = states_from_payload(payload)
    ticks = pd.DataFrame({"ts": [1780315210, 1780315601], "market_prob": [0.5, 0.6],
                          "traded": [True, False]})
    joined = join_game_states(states, ticks)
    assert len(states) == 1
    assert len(joined) == 1
    assert joined.iloc[0]["margin"] == 2
    assert joined.iloc[0]["state_age_s"] == 10
