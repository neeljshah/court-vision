"""Per-file test for domains.mlb.acquire_statcast_sample (OFFLINE; no network).

Validates starter isolation, leak-free per-start K LABEL (charged to the starter only),
and fatigue-feature derivation on a hand-built per-pitch frame -- no savant call.
"""
from __future__ import annotations

import math

import pandas as pd

from domains.mlb import acquire_statcast_sample as A


def _synth() -> pd.DataFrame:
    """One game: HOME starter id=100 (Top halves), AWAY starter id=200 (Bot halves),
    plus a HOME reliever id=999 entering inning 8 (must NOT be the starter)."""
    rows = []
    abn = 0

    def add(inning, tb, pitcher, velo, ptype, ev):
        nonlocal abn
        abn += 1
        rows.append({"game_pk": 1, "game_date": "2023-05-02", "inning": inning,
                     "inning_topbot": tb, "at_bat_number": abn, "pitch_number": 1,
                     "pitcher": pitcher, "batter": 5, "events": ev,
                     "release_speed": velo, "release_spin_rate": 2200.0,
                     "estimated_woba_using_speedangle": 0.31, "pitch_type": ptype,
                     "balls": 0, "strikes": 0, "outs_when_up": 0,
                     "home_team": "AAA", "away_team": "BBB"})

    # HOME starter (100) pitches the TOP halves, velo declines 95->91, 2 K
    add(1, "Top", 100, 95.0, "FF", "strikeout")
    add(2, "Top", 100, 94.0, "SL", "field_out")
    add(3, "Top", 100, 93.0, "FF", "strikeout")
    add(7, "Top", 100, 91.0, "CU", "walk")
    add(8, "Top", 999, 97.0, "FF", "strikeout")  # reliever -- not starter
    # AWAY starter (200) pitches the BOT halves, 1 K
    add(1, "Bot", 200, 90.0, "FF", "field_out")
    add(2, "Bot", 200, 89.5, "CH", "strikeout")
    add(3, "Bot", 200, 89.0, "FF", "field_out")
    return pd.DataFrame(rows)


def test_starter_isolation_and_label():
    df = _synth()
    st = A.build_starter_table(df, 2023)
    assert len(st) == 2, st
    home = st[st["pitch_side"] == "home"].iloc[0]
    away = st[st["pitch_side"] == "away"].iloc[0]
    # starter ids correct; reliever 999 excluded
    assert home["pitcher"] == 100
    assert away["pitcher"] == 200
    # K LABEL charged to STARTER ONLY: home starter has 2 K (reliever's K excluded)
    assert home["label_k"] == 2, home["label_k"]
    assert away["label_k"] == 1, away["label_k"]
    # home starter n_pitches excludes the reliever pitch (4 not 5)
    assert home["n_pitches"] == 4, home["n_pitches"]
    # velo decline slope negative for the home starter (95->91)
    assert home["velo_decline_slope"] < 0, home["velo_decline_slope"]
    assert home["pitch_team"] == "AAA"
    assert away["pitch_team"] == "BBB"


def test_ols_slope_and_entropy():
    assert A._ols_slope([5.0, 4.0, 3.0]) < 0
    assert math.isnan(A._ols_slope([1.0]))
    # entropy of a single type = 0, of two equal types = ln 2
    assert abs(A._entropy(["FF", "FF"]) - 0.0) < 1e-9
    assert abs(A._entropy(["FF", "SL"]) - math.log(2)) < 1e-9


def test_starter_for_side_picks_inning1_first():
    df = _synth()
    home_side = df[df["inning_topbot"] == "Top"]
    assert A._starter_for_side(home_side) == 100
