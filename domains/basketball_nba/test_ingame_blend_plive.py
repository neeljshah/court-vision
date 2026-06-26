"""Per-file tests for domains/basketball_nba/ingame_blend_plive.py.

Covers: sec_remaining, build_state_features, fit_plive, predict_plive.
Hermetic -- no network, no data files. Calls the REAL functions only.
"""
import math
import pytest
import numpy as np

from domains.basketball_nba.ingame_blend_plive import (
    PLIVE_FEATS,
    _ConstModel,
    build_state_features,
    fit_plive,
    predict_plive,
    sec_remaining,
)


# ---------------------------------------------------------------------------
# sec_remaining
# ---------------------------------------------------------------------------

def test_sec_remaining_q1_full_clock():
    # Q1 with 12:00 on clock -> 3 full remaining periods + 720 = 2880
    assert sec_remaining(1, 720) == 2880.0


def test_sec_remaining_q4_with_time():
    # Q4 with 5:00 left -- only those 300 s remain in regulation
    assert sec_remaining(4, 300) == 300.0


def test_sec_remaining_ot_period5():
    # OT (period 5) returns clock_s directly
    assert sec_remaining(5, 180) == 180.0


def test_sec_remaining_final_buzzer():
    # Q4 clock at 0 -> 0
    assert sec_remaining(4, 0) == 0.0


def test_sec_remaining_never_negative_q4_negative_clock():
    # Negative clock in period >= 4 branch is clamped to 0
    assert sec_remaining(4, -5) == 0.0


def test_sec_remaining_never_negative_ot_negative_clock():
    # Same clamp for OT
    assert sec_remaining(5, -1) == 0.0


def test_sec_remaining_q2_midclock():
    # Q2 with 6:00 left: 2 full remaining periods (Q3+Q4 = 1440) + 360 = 1800
    assert sec_remaining(2, 360) == 1800.0


# ---------------------------------------------------------------------------
# build_state_features
# ---------------------------------------------------------------------------

def _make_st(period=2, clock_s=360,
             home_score=55, away_score=50,
             players=None,
             home_bonus=False, away_bonus=False):
    st = {
        "period": period,
        "clock_s": clock_s,
        "home_score": home_score,
        "away_score": away_score,
    }
    if players is not None:
        st["players"] = players
    if home_bonus:
        st["home_bonus"] = True
    if away_bonus:
        st["away_bonus"] = True
    return st


def test_score_diff_home_perspective():
    st = _make_st(home_score=60, away_score=55)
    feats = build_state_features(st, "HOM", "AWY")
    assert feats["score_diff"] == 5.0


def test_score_diff_negative_when_trailing():
    st = _make_st(home_score=40, away_score=50)
    feats = build_state_features(st, "HOM", "AWY")
    assert feats["score_diff"] == -10.0


def test_foul_diff_favors_home_when_away_in_trouble():
    # 2 away players with pf=4, 0 home players with pf>=4
    players = {
        "p1": {"team": "AWY", "pf": 4},
        "p2": {"team": "AWY", "pf": 5},
        "p3": {"team": "HOM", "pf": 2},
    }
    st = _make_st(players=players)
    feats = build_state_features(st, "HOM", "AWY")
    # away_trouble=2, home_trouble=0 -> foul_diff = +2
    assert feats["foul_diff"] == 2.0


def test_foul_diff_negative_when_home_in_trouble():
    players = {
        "p1": {"team": "HOM", "pf": 4},
        "p2": {"team": "AWY", "pf": 2},
    }
    st = _make_st(players=players)
    feats = build_state_features(st, "HOM", "AWY")
    # away_trouble=0, home_trouble=1 -> foul_diff = -1
    assert feats["foul_diff"] == -1.0


def test_bonus_positive_when_only_home_bonus():
    st = _make_st(home_bonus=True, away_bonus=False)
    feats = build_state_features(st, "HOM", "AWY")
    assert feats["bonus"] == 1.0


def test_bonus_negative_when_only_away_bonus():
    st = _make_st(home_bonus=False, away_bonus=True)
    feats = build_state_features(st, "HOM", "AWY")
    assert feats["bonus"] == -1.0


def test_bonus_zero_when_both_or_neither():
    st_neither = _make_st()
    feats_neither = build_state_features(st_neither, "HOM", "AWY")
    assert feats_neither["bonus"] == 0.0

    st_both = _make_st(home_bonus=True, away_bonus=True)
    feats_both = build_state_features(st_both, "HOM", "AWY")
    assert feats_both["bonus"] == 0.0


def test_margin_abs_equals_abs_score_diff():
    for home, away in [(60, 50), (40, 55), (50, 50)]:
        st = _make_st(home_score=home, away_score=away)
        feats = build_state_features(st, "HOM", "AWY")
        assert feats["margin_abs"] == abs(feats["score_diff"])


def test_time_pressure_at_buzzer_uses_30s_clamp():
    # Q4 clock=0 -> sec_remaining=0 -> max(0, 30)=30 -> time_pressure = diff/30
    st = _make_st(period=4, clock_s=0, home_score=65, away_score=60)
    feats = build_state_features(st, "HOM", "AWY")
    expected = 5.0 / 30.0
    assert math.isclose(feats["time_pressure"], expected, rel_tol=1e-9)


def test_time_pressure_above_30s_uses_actual_sec():
    # With plenty of time, divides by the actual sec_remaining
    st = _make_st(period=2, clock_s=360,
                  home_score=60, away_score=50)
    feats = build_state_features(st, "HOM", "AWY")
    sr = feats["sec_remaining"]
    assert sr >= 30.0
    expected = feats["score_diff"] / sr
    assert math.isclose(feats["time_pressure"], expected, rel_tol=1e-9)


def test_all_plive_feats_present_and_finite():
    st = _make_st()
    feats = build_state_features(st, "HOM", "AWY")
    for k in PLIVE_FEATS:
        assert k in feats, "Missing PLIVE_FEAT key: {}".format(k)
        assert math.isfinite(feats[k]), "Non-finite value for key: {}".format(k)


# ---------------------------------------------------------------------------
# fit_plive / predict_plive
# ---------------------------------------------------------------------------

def _base_row(score_diff=0.0, sec_remaining=1440.0,
              foul_diff=0.0, bonus=0.0, time_pressure=0.0):
    return {
        "score_diff": score_diff,
        "sec_remaining": sec_remaining,
        "foul_diff": foul_diff,
        "bonus": bonus,
        "time_pressure": time_pressure,
    }


def test_empty_rows_gives_const05():
    model = fit_plive([], [])
    assert isinstance(model, _ConstModel)
    assert predict_plive(model, _base_row()) == pytest.approx(0.5, abs=1e-9)


def test_single_class_all_wins_gives_const_near1():
    rows = [_base_row(score_diff=float(i)) for i in range(5)]
    labels = [1.0] * 5
    model = fit_plive(rows, labels)
    assert isinstance(model, _ConstModel)
    p = predict_plive(model, _base_row())
    assert p == pytest.approx(1.0, abs=1e-9)


def test_single_class_all_losses_gives_const_near0():
    rows = [_base_row(score_diff=float(i)) for i in range(5)]
    labels = [0.0] * 5
    model = fit_plive(rows, labels)
    assert isinstance(model, _ConstModel)
    p = predict_plive(model, _base_row())
    assert p == pytest.approx(0.0, abs=1e-9)


def test_separable_fit_ranks_leading_above_trailing():
    # Home up 20 with plenty of time -> win=1
    win_rows = [_base_row(score_diff=20.0 + i, sec_remaining=1400.0,
                          time_pressure=(20.0 + i) / 1400.0)
                for i in range(10)]
    # Home down 20 with plenty of time -> win=0
    lose_rows = [_base_row(score_diff=-20.0 - i, sec_remaining=1400.0,
                           time_pressure=(-20.0 - i) / 1400.0)
                 for i in range(10)]
    rows = win_rows + lose_rows
    labels = [1.0] * 10 + [0.0] * 10

    model = fit_plive(rows, labels)

    # Predict for leading state
    p_lead = predict_plive(model, _base_row(score_diff=18.0, sec_remaining=1400.0,
                                            time_pressure=18.0 / 1400.0))
    # Predict for trailing state
    p_trail = predict_plive(model, _base_row(score_diff=-18.0, sec_remaining=1400.0,
                                             time_pressure=-18.0 / 1400.0))

    assert 0.0 <= p_lead <= 1.0
    assert 0.0 <= p_trail <= 1.0
    assert p_lead > p_trail


def test_predict_plive_output_in_unit_interval():
    rows = ([_base_row(score_diff=15.0, time_pressure=0.01)] * 10 +
            [_base_row(score_diff=-15.0, time_pressure=-0.01)] * 10)
    labels = [1.0] * 10 + [0.0] * 10
    model = fit_plive(rows, labels)
    for sd in [30.0, 0.0, -30.0, 100.0, -100.0]:
        p = predict_plive(model, _base_row(score_diff=sd,
                                           time_pressure=sd / 1440.0))
        assert 0.0 <= p <= 1.0


def test_const_model_clamps_over1():
    # _ConstModel init clamps p to [0,1], so p=1.5 -> stored as 1.0
    m = _ConstModel(1.5)
    assert m.p == pytest.approx(1.0, abs=1e-9)
    p = predict_plive(m, _base_row())
    assert p <= 1.0


def test_const_model_clamps_under0():
    m = _ConstModel(-0.5)
    assert m.p == pytest.approx(0.0, abs=1e-9)
    p = predict_plive(m, _base_row())
    assert p >= 0.0
