"""Per-file test for knowledge.validate_research_wave5. Run:
  cd /c/Users/neelj/nba-ai-system && python -m pytest domains/tennis/knowledge/test_validate_research_wave5.py -q
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from domains.tennis.knowledge import validate_research_wave5 as vrw5


def test_self_check():
    vrw5._self_check()


def test_persistence_not_testable_below_player_floor():
    r = vrw5.return_depth_aggressiveness_persistence(pd.DataFrame({
        "player": ["P0"] * 6, "date": pd.date_range("2020-01-01", periods=6), "deep_rate": [0.1] * 6}))
    assert r["verdict"] == "NOT_TESTABLE"  # only 1 player, below MIN_PLAYERS


def test_persistence_confirms_a_real_split_half_correlation():
    rng = np.random.RandomState(0)
    players = ["P%d" % i for i in range(20)]
    true_rate = {p: rng.uniform(0.1, 0.6) for p in players}
    rows = []
    for p in players:
        for half, base_date in (("A", pd.Timestamp("2020-01-01")), ("B", pd.Timestamp("2021-01-01"))):
            for m in range(6):
                rows.append({"player": p, "date": base_date + pd.Timedelta(days=m),
                             "deep_rate": true_rate[p] + rng.normal(0, 0.02)})
    tot = pd.DataFrame(rows)
    r = vrw5.return_depth_aggressiveness_persistence(tot)
    assert r["verdict"] == "CONFIRMED_LOCAL"
    assert r["effect"] > 0.15
