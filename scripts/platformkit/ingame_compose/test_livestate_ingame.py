"""Leak tests for livestate_ingame: two-way proof per feature --
(a) future-event mutation: mutating anything strictly after t must not change
    the value at t; (b) prefix-equality: computing on a truncated event stream
    (everything after t deleted) gives the identical result to computing on
    the full stream. Stint features additionally prove the CURRENT-stint
    end-time guard: a stint spanning t must be truncated at t, not use its
    real (possibly far-future) end.
"""
from __future__ import annotations

import copy

import pandas as pd
import pytest

from scripts.platformkit.ingame_compose.livestate_ingame import (
    add_global_times,
    compute_v2_features,
    distinct_players_at,
    floor_lineup_at,
    shot_tally_before,
    truncated_minutes_at,
)

TEAM_H, TEAM_A = 111, 222


def _stints() -> pd.DataFrame:
    # Home: two stints; the 2nd (P1) SPANS t=500 (start 400, end 700).
    # Away: one stint covering the whole period.
    rows = [
        dict(game_id="g1", team_id=TEAM_H, period=1, lineup_key="1,2,3,4,5",
             n_on_court=5, start_s=0.0, end_s=400.0, elapsed_s=400.0,
             pts_for=8, pts_against=6, quality=""),
        dict(game_id="g1", team_id=TEAM_H, period=1, lineup_key="1,2,3,4,6",
             n_on_court=5, start_s=400.0, end_s=700.0, elapsed_s=300.0,
             pts_for=6, pts_against=4, quality=""),
        dict(game_id="g1", team_id=TEAM_A, period=1, lineup_key="11,12,13,14,15",
             n_on_court=5, start_s=0.0, end_s=720.0, elapsed_s=720.0,
             pts_for=10, pts_against=9, quality=""),
    ]
    return add_global_times(pd.DataFrame(rows))


def _actions():
    return [
        {"actionNumber": 1, "actionType": "2pt", "shotResult": "Made", "teamId": TEAM_H,
         "period": 1, "clock": "PT10M0.00S", "scoreHome": 2, "scoreAway": 0},   # elapsed 120
        {"actionNumber": 2, "actionType": "3pt", "shotResult": "Missed", "teamId": TEAM_A,
         "period": 1, "clock": "PT9M0.00S", "scoreHome": 2, "scoreAway": 0},    # elapsed 180
        # after t=500 (elapsed 550) -- must never affect a t=500 checkpoint
        {"actionNumber": 3, "actionType": "3pt", "shotResult": "Made", "teamId": TEAM_A,
         "period": 1, "clock": "PT2M50.00S", "scoreHome": 2, "scoreAway": 3},   # elapsed 550
    ]


def test_floor_lineup_ignores_future_end_time():
    st = _stints()
    floor_before = floor_lineup_at(st, TEAM_H, 500.0)
    mutated = st.copy()
    mutated.loc[mutated["team_id"] == TEAM_H, "end_g"] = 999999.0  # blow up the future end
    floor_after = floor_lineup_at(mutated, TEAM_H, 500.0)
    assert floor_before == floor_after == [1, 2, 3, 4, 6]


def test_truncated_minutes_caps_at_t_not_real_end():
    st = _stints()
    tm = truncated_minutes_at(st, TEAM_H, 500.0)
    # spanning stint (start 400) contributes only 100s (500-400), not its full 300s
    assert tm[1] == pytest.approx(400.0 + 100.0)  # 400s from stint1 (full) + 100s from stint2 (capped)
    mutated = st.copy()
    spanning = (mutated["team_id"] == TEAM_H) & (mutated["start_g"] == 400.0)
    mutated.loc[spanning, "end_g"] = 999999.0  # blow up ONLY the stint that spans t
    tm_mut = truncated_minutes_at(mutated, TEAM_H, 500.0)
    assert tm_mut == tm, "mutating the real (future) end time must not change the truncated total"


def test_distinct_players_prefix_equality():
    st = _stints()
    full = distinct_players_at(st, TEAM_H, 500.0)
    truncated_stream = st[st["start_g"] < 500.0]  # drop rows that couldn't matter
    trunc = distinct_players_at(truncated_stream, TEAM_H, 500.0)
    # both home stints started before 500 -> union of both lineups (5 was subbed for 6)
    assert full == trunc == {1, 2, 3, 4, 5, 6}


def test_shot_tally_future_mutation_and_prefix_equality():
    acts = _actions()
    before = shot_tally_before(acts, 500.0)
    assert before[TEAM_H] == [1, 1, 0, 0, 0, 0]     # 1 made 2pt
    assert before[TEAM_A] == [0, 0, 0, 1, 0, 0]     # 1 missed 3pt

    mutated = copy.deepcopy(acts)
    mutated[2]["shotResult"] = "Made"      # flip the post-t action's result
    mutated[2]["scoreAway"] = 999
    after = shot_tally_before(mutated, 500.0)
    assert after == before, "an action strictly after t must not affect the tally at t"

    prefix_only = [a for a in acts if a["actionNumber"] != 3]
    assert shot_tally_before(prefix_only, 500.0) == before


def test_compute_v2_features_none_when_no_top3_history():
    st = _stints()
    gj = {"game": {"actions": _actions()}}
    net48 = {i: 5.0 for i in (1, 2, 3, 4, 6)}
    net48.update({i: -5.0 for i in (11, 12, 13, 14, 15)})
    out = compute_v2_features(gj, st, 500.0, TEAM_H, TEAM_A, net48,
                              top3_home=[], top3_away=[1], shot_rates=(0.5, 0.35, 0.75))
    assert out is None  # empty top3 roster history -> whole checkpoint skipped, not imputed


def test_compute_v2_features_full_row():
    st = _stints()
    gj = {"game": {"actions": _actions()}}
    net48 = {i: 5.0 for i in (1, 2, 3, 4, 6)}
    net48.update({i: -5.0 for i in (11, 12, 13, 14, 15)})
    out = compute_v2_features(gj, st, 500.0, TEAM_H, TEAM_A, net48,
                              top3_home=[1, 2, 3], top3_away=[11, 12, 13],
                              shot_rates=(0.5, 0.35, 0.75))
    assert out is not None
    floor_q, star_min, luck, bench = out
    assert floor_q == pytest.approx(10.0)              # 5.0 - (-5.0)
    assert bench == pytest.approx(1.0)                  # home used 6 distinct (1 sub), away used 5
    assert star_min == pytest.approx(0.0)               # both top3s played uninterrupted -> no absence signal


def test_star_minutes_load_penalizes_absent_top3_player():
    st = _stints()
    gj = {"game": {"actions": _actions()}}
    net48 = {i: 0.0 for i in list(range(1, 7)) + list(range(11, 16))}
    # away top3 includes player 99, who never plays this game -> 0 minutes for him
    out = compute_v2_features(gj, st, 500.0, TEAM_H, TEAM_A, net48,
                              top3_home=[1, 2, 3], top3_away=[11, 12, 99],
                              shot_rates=(0.5, 0.35, 0.75))
    assert out is not None
    _, star_min, _, _ = out
    assert star_min > 0, "away's absent top-3 player should drag its share below home's"
