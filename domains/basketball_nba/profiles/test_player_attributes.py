"""Per-file test: rim_pressure_def's z-score-sum composite math, on
hand-built frames (no disk I/O -- pure arithmetic check).

Run: python -m pytest domains/basketball_nba/profiles/test_player_attributes.py -q
"""
from __future__ import annotations

import pandas as pd

from domains.basketball_nba.profiles.player_attributes import _compose_rim_pressure, _zscore


def test_zscore_zero_variance_returns_zero():
    s = pd.Series([5.0, 5.0, 5.0])
    assert (_zscore(s) == 0.0).all()


def test_zscore_standardizes_to_mean_zero():
    s = pd.Series([1.0, 2.0, 3.0, 4.0])
    z = _zscore(s)
    assert abs(z.mean()) < 1e-9


def test_composite_orders_better_defender_higher():
    # player 0: allows LESS rim share/eFG and FEWER pts when on -- a real
    # rim-deterrence swing. player 1: no swing at all (on == off everywhere).
    d = pd.DataFrame({
        "rim_share_allowed_on": [0.20, 0.35],
        "rim_share_allowed_off": [0.35, 0.35],
        "rim_efg_allowed_on": [0.55, 0.60],
        "rim_efg_allowed_off": [0.65, 0.60],
        "pts_against_per48_on": [100.0, 110.0],
        "pts_against_per48_off": [112.0, 110.0],
    })
    composite = _compose_rim_pressure(d)
    assert composite.iloc[0] > composite.iloc[1]


def test_composite_sign_flips_for_a_negative_defender():
    # player 0 suppresses (good defense), player 1 is WORSE on than off
    # (allows MORE rim share/eFG/points when on) -- composite must rank
    # player 0 above player 1, and player 1's own composite should be < 0.
    d = pd.DataFrame({
        "rim_share_allowed_on": [0.20, 0.45],
        "rim_share_allowed_off": [0.35, 0.35],
        "rim_efg_allowed_on": [0.50, 0.65],
        "rim_efg_allowed_off": [0.60, 0.55],
        "pts_against_per48_on": [95.0, 118.0],
        "pts_against_per48_off": [110.0, 108.0],
    })
    composite = _compose_rim_pressure(d)
    assert composite.iloc[0] > 0 > composite.iloc[1]
