"""Synthetic-fixture tests for domains.mlb.sp_quality_asof. No real data/ needed."""
from __future__ import annotations

import math

import pandas as pd
import pytest

from domains.mlb.sp_quality_asof import (
    _ew_asof_sequence,
    _identify_starters,
    build_sp_quality_asof_from_frame,
)


def _pitch_row(game_pk, date, inning, topbot, pitcher, home_team, away_team,
               batter, woba, terminal=True):
    return {
        "game_pk": game_pk, "game_date": date, "inning": inning,
        "inning_topbot": topbot, "pitcher": pitcher, "batter": batter,
        "home_team": home_team, "away_team": away_team,
        "estimated_woba_using_speedangle": woba if terminal else None,
    }


def test_identify_starters_two_games_known_inning1_pitchers():
    rows = [
        _pitch_row(1, "2023-04-01", 1, "Top", 100, "HOU", "SEA", 1, 0.30),
        _pitch_row(1, "2023-04-01", 1, "Bot", 200, "HOU", "SEA", 2, 0.35),
        _pitch_row(2, "2023-04-02", 1, "Top", 300, "TEX", "OAK", 3, 0.28),
        _pitch_row(2, "2023-04-02", 1, "Bot", 400, "TEX", "OAK", 4, 0.31),
    ]
    df = pd.DataFrame(rows)
    starters = _identify_starters(df)
    assert len(starters) == 4
    g1 = starters[starters["game_pk"] == 1]
    assert set(g1["pitcher"]) == {100, 200}
    home_row = g1[g1["side"] == "Top"].iloc[0]
    away_row = g1[g1["side"] == "Bot"].iloc[0]
    assert home_row["pitcher"] == 100 and home_row["team"] == "HOU"
    assert away_row["pitcher"] == 200 and away_row["team"] == "SEA"


def test_per_start_aggregate_ignores_reliever_and_spans_multiple_innings():
    rows = [
        _pitch_row(1, "2023-04-01", 1, "Top", 100, "HOU", "SEA", 1, 0.40),
        _pitch_row(1, "2023-04-01", 2, "Top", 100, "HOU", "SEA", 2, 0.20),
        # reliever takes over inning 3 -- must NOT be counted as the starter's outing
        _pitch_row(1, "2023-04-01", 3, "Top", 999, "HOU", "SEA", 3, 0.90),
        _pitch_row(1, "2023-04-01", 1, "Bot", 200, "HOU", "SEA", 4, 0.10),
    ]
    df = pd.DataFrame(rows)
    out = build_sp_quality_asof_from_frame(df)
    # only one prior-less appearance per pitcher here; check the raw aggregate
    # indirectly via a second start for pitcher 100 with a known prior value
    rows2 = rows + [
        _pitch_row(2, "2023-04-08", 1, "Top", 100, "HOU", "SEA", 5, 0.50),
    ]
    out2 = build_sp_quality_asof_from_frame(pd.DataFrame(rows2))
    second_start = out2[(out2["pitcher"] == 100) & (out2["game_pk"] == 2)].iloc[0]
    # prior start's mean xwoba was (0.40+0.20)/2 = 0.30 (reliever's 0.90 excluded)
    assert second_start["n_prior_starts"] == 1
    assert second_start["sp_xwoba_against_asof"] == pytest.approx(0.30)


def test_ew_asof_hand_computed_3_start_sequence():
    values = [0.300, 0.350, 0.280]
    asof, nprior = _ew_asof_sequence(values, alpha=0.35, window=6)
    assert nprior == [0, 1, 2]
    assert math.isnan(asof[0])
    assert asof[1] == pytest.approx(0.300)
    expected3 = (0.65 * 0.300 + 1.0 * 0.350) / (0.65 + 1.0)
    assert asof[2] == pytest.approx(expected3)


def test_leak_freedom_current_start_never_affects_own_asof():
    # start2's asof must equal ewm(prior=[start1]) regardless of start2's own value
    values_a = [0.300, 0.900]
    values_b = [0.300, 0.100]
    asof_a, _ = _ew_asof_sequence(values_a)
    asof_b, _ = _ew_asof_sequence(values_b)
    assert asof_a[1] == asof_b[1] == pytest.approx(0.300)


def test_leak_freedom_later_start_never_affects_earlier_one():
    baseline, _ = _ew_asof_sequence([0.300, 0.350])
    with_future_extreme, _ = _ew_asof_sequence([0.300, 0.350, 999.0])
    assert math.isnan(with_future_extreme[0]) and math.isnan(baseline[0])
    assert with_future_extreme[1] == pytest.approx(baseline[1])


def test_n_prior_starts_floor_zero_on_debut():
    rows = [
        _pitch_row(1, "2023-04-01", 1, "Top", 100, "HOU", "SEA", 1, 0.30),
        _pitch_row(1, "2023-04-01", 1, "Bot", 200, "HOU", "SEA", 2, 0.35),
    ]
    out = build_sp_quality_asof_from_frame(pd.DataFrame(rows))
    assert (out["n_prior_starts"] == 0).all()
    assert out["sp_xwoba_against_asof"].isna().all()


def test_empty_frame_returns_empty_with_expected_columns():
    out = build_sp_quality_asof_from_frame(pd.DataFrame())
    assert list(out.columns) == [
        "pitcher", "game_pk", "game_date", "team", "sp_xwoba_against_asof", "n_prior_starts"]
    assert out.empty
