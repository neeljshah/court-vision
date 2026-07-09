"""Per-file test for domains.tennis.pressure_situations + pressure_point_claims.

Covers: situation detection from hand-built score-state toys (break/game
point from both perspectives, tiebreak detection, deuce-battle running
count, set-point clinch rule), and the claim builder's delta math + min-n
floor exclusion.

Run: python -m pytest domains/tennis/test_pressure_point_claims.py -q
"""
from __future__ import annotations

import pandas as pd

from domains.tennis.pressure_point_claims import _build_claim
from domains.tennis.pressure_situations import charting_situation_state


def _row(match_id="m1", date="2020-01-01", server=1, is_2nd=False, winner=1,
         set1=0, set2=0, gm1=0, gm2=0, score="0-0"):
    return {"match_id": match_id, "date": date, "date_source": "match_date", "tour": "m",
            "server": server, "is_second_serve": is_2nd, "point_winner": winner,
            "rally_length": pd.NA, "set1": set1, "set2": set2, "gm1": gm1, "gm2": gm2,
            "score_state": score}


def test_break_point_and_game_point_mirror():
    # server=1 throughout. "30-40" (srv-ret) = returner at 40 -> break point.
    # "40-30" = server at 40 -> game point (mirror), not a break point.
    df = pd.DataFrame([
        _row(gm1=2, gm2=2, score="30-40"),
        _row(gm1=2, gm2=2, score="40-30"),
        _row(gm1=2, gm2=2, score="30-30"),  # neither
    ])
    out = charting_situation_state(df)
    assert out["break_point"].tolist() == [True, False, False]
    assert out["game_point"].tolist() == [False, True, False]


def test_tiebreak_point_detected_at_6_6_with_numeric_score():
    df = pd.DataFrame([
        _row(gm1=6, gm2=6, score="3-2"),
        _row(gm1=5, gm2=6, score="40-30"),  # not 6-6 -> not a tiebreak
    ])
    out = charting_situation_state(df)
    assert out["tiebreak_point"].tolist() == [True, False]
    # tiebreak rows never also flag the ad-scoring situations
    assert out.loc[0, "break_point"] is False or out.loc[0, "break_point"] == False  # noqa: E712


def test_deuce_battle_needs_three_prior_deuces_same_game():
    # 4 deuce (40-40) points then a 5th point in the SAME game (set1/set2/gm1/gm2 constant).
    rows = [_row(gm1=3, gm2=3, score="40-40") for _ in range(4)]
    rows.append(_row(gm1=3, gm2=3, score="40-30"))
    df = pd.DataFrame(rows)
    out = charting_situation_state(df)
    # points 1-3 (0,1,2 prior deuces) are False; point 4 (3 prior) True; point 5 (4 prior) True
    assert out["deuce_battle"].tolist() == [False, False, False, True, True]


def test_set_point_requires_game_point_and_clinch():
    df = pd.DataFrame([
        _row(gm1=5, gm2=3, score="40-15"),  # server game point, 6-3 would clinch -> set point
        _row(gm1=3, gm2=3, score="40-15"),  # server game point, 4-3 would NOT clinch -> not set point
    ])
    out = charting_situation_state(df)
    assert out["set_point"].tolist() == [True, False]
    assert out["game_point"].tolist() == [True, True]


def _toy_long_df(situation: str, n_qualify: int, n_exclude: int) -> pd.DataFrame:
    """player A: n_qualify situational points all won + baseline points all lost (clean +delta).
    player B: n_exclude (< floor) situational points -- must be excluded from the ranking."""
    rows = []
    for _ in range(20):  # baseline (non-situational) points, both players lose them all
        rows.append({"player_name": "A", "role": "serve", "won": 0, "first_serve_in": 0,
                     "date": "2020-01-01", situation: False})
        rows.append({"player_name": "B", "role": "serve", "won": 0, "first_serve_in": 0,
                     "date": "2020-01-01", situation: False})
    for _ in range(n_qualify):
        rows.append({"player_name": "A", "role": "serve", "won": 1, "first_serve_in": 1,
                     "date": "2020-01-01", situation: True})
    for _ in range(n_exclude):
        rows.append({"player_name": "B", "role": "serve", "won": 1, "first_serve_in": 1,
                     "date": "2020-01-01", situation: True})
    for s in ("break_point", "game_point", "set_point", "tiebreak_point", "deuce_battle"):
        if s != situation:
            for r in rows:
                r.setdefault(s, False)
    return pd.DataFrame(rows)


def test_build_claim_delta_math_and_min_n_floor(tmp_path):
    long_df = _toy_long_df("deuce_battle", n_qualify=40, n_exclude=10)  # floor=30
    claim = _build_claim(long_df, "deuce_battle", "serve", "won", "points_won_rate_delta",
                          snapshot_dir=tmp_path)
    assert claim["n_considered"] == 2          # both A and B have >=1 situational point
    assert claim["n_excluded_below_floor"] == 1  # only B (10 < 30) is excluded
    assert len(claim["ranking"]) == 1
    top = claim["ranking"][0]
    assert top["player_name"] == "A"
    # baseline (over ALL scoped points, situational included -- same convention as
    # pressure_claims.py's bp_save baseline) = 40 won / 60 total = 0.6667; situ rate = 1.0.
    assert abs(top["delta"] - (1.0 - 40 / 60)) < 1e-4
    assert top["n"] == 40
    assert claim["edge_claimed"] is False
