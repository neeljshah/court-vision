"""Per-file test: the generic on/off event aggregator (_on_off_by_player) on
hand-built stint/event frames -- the shared math behind oreb_pct/dreb_pct's
opportunity denominators and team_dreb_pct_swing's is_dreb rate.

Run: python -m pytest domains/basketball_nba/profiles/test_player_rebounding.py -q
"""
from __future__ import annotations

import pandas as pd
import pytest

from domains.basketball_nba.profiles.player_rebounding import _dedup_trade, _on_off_by_player

_STINTS = pd.DataFrame([
    {"game_id": "G1", "team_id": 1, "period": 1, "lineup_key": "1,2,3,4,5",
     "n_on_court": 5, "elapsed_s": 240.0},
    {"game_id": "G1", "team_id": 1, "period": 1, "lineup_key": "2,3,4,5,6",
     "n_on_court": 5, "elapsed_s": 480.0},
])


def test_on_off_event_counts_and_value_sum():
    # 3 events during stint 1 (player 1 ON): 2 missed (fga=1,is_dreb=1 twice), 1 (is_dreb=0)
    # 1 event during stint 2 (player 1 OFF): is_dreb=1
    events = pd.DataFrame([
        {"game_id": "G1", "team_id": 1, "lineup_key": "1,2,3,4,5", "n_on_court": 5, "is_dreb": 1},
        {"game_id": "G1", "team_id": 1, "lineup_key": "1,2,3,4,5", "n_on_court": 5, "is_dreb": 1},
        {"game_id": "G1", "team_id": 1, "lineup_key": "1,2,3,4,5", "n_on_court": 5, "is_dreb": 0},
        {"game_id": "G1", "team_id": 1, "lineup_key": "2,3,4,5,6", "n_on_court": 5, "is_dreb": 1},
    ])
    out = _on_off_by_player(_STINTS, events, "is_dreb").set_index("player_id")

    p1 = out.loc[1]  # on for stint 1 only
    assert p1["min_on"] == pytest.approx(4.0) and p1["min_off"] == pytest.approx(8.0)
    assert p1["n_events_on"] == 3 and p1["n_events_off"] == 1
    assert p1["is_dreb_on"] == 2 and p1["is_dreb_off"] == 1

    p6 = out.loc[6]  # on for stint 2 only (opposite of player 1)
    assert p6["n_events_on"] == 1 and p6["n_events_off"] == 3
    assert p6["is_dreb_on"] == 1 and p6["is_dreb_off"] == 2

    p3 = out.loc[3]  # on for BOTH stints -- every event counts "on"
    assert p3["n_events_on"] == 4 and p3["n_events_off"] == 0


def test_dedup_trade_keeps_higher_minutes_team():
    df = pd.DataFrame([
        {"player_id": 7, "team_id": 100, "min_on": 300.0},
        {"player_id": 7, "team_id": 200, "min_on": 900.0},  # traded here, more minutes
    ])
    out = _dedup_trade(df)
    assert len(out) == 1 and out.iloc[0]["team_id"] == 200
