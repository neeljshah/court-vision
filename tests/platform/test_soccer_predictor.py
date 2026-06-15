"""Per-file test for domains/soccer/predictor.py — the usable soccer predictor.

Mirrors tests/platform/test_nba_predictor.py: asserts a coherent calibrated
surface (1X2 + O/U-2.5), that to_jd() agrees with sim_framework.market_surface,
and that predict_live() reprices off the pregame number and sharpens with elapsed
minutes. Calibration/accuracy only; soccer pregame markets are efficient, no edge.

Run: python -m pytest tests/platform/test_soccer_predictor.py -q
"""
from __future__ import annotations

import pytest

from domains.soccer.predictor import SoccerPredictor


@pytest.fixture(scope="module")
def predictor():
    try:
        return SoccerPredictor()
    except FileNotFoundError:
        pytest.skip("soccer corpus not present")


@pytest.fixture(scope="module")
def teams(predictor):
    if len(predictor.teams) < 2:
        pytest.skip("need >=2 teams in the corpus")
    return predictor.teams[0], predictor.teams[1]


def test_surface_sane(predictor, teams):
    """predict() returns probs in [0,1], 1X2 sums to 1, O/U sums to 1, lambdas/total>0."""
    h, a = teams
    s = predictor.predict(h, a)
    assert s["sport"] == "soccer"
    # every probability is a valid probability
    for k in ("p_home_win", "p_draw", "p_away_win", "over_2.5", "under_2.5",
              "btts_yes", "btts_no", "over_2.5_raw"):
        assert 0.0 <= s[k] <= 1.0, (k, s[k])
    # 1X2 is a coherent distribution (sums to 1 within rounding)
    assert s["p_home_win"] + s["p_draw"] + s["p_away_win"] == pytest.approx(1.0, abs=2e-4)
    # O/U-2.5 complementary
    assert s["over_2.5"] + s["under_2.5"] == pytest.approx(1.0, abs=1e-6)
    assert s["btts_yes"] + s["btts_no"] == pytest.approx(1.0, abs=2e-4)
    # expected goals (the model's "total") are strictly positive
    assert s["lam_home"] > 0.0 and s["lam_away"] > 0.0
    assert (s["lam_home"] + s["lam_away"]) > 0.0


def test_to_jd_coherent_with_market_surface(predictor, teams):
    """to_jd() samples the SAME scoreline matrix predict() reads, so the JD moneyline
    matches the raw matrix 1X2 within MC sampling noise (the JD IS the joint)."""
    from scripts.platformkit.sim_framework import market_surface

    h, a = teams
    jd = predictor.to_jd(h, a, n_sims=200_000, seed=1)
    assert jd.joint_quality == "simulated"
    surf = market_surface(jd, {"home_idx": 0, "away_idx": 1, "total_lines": [2.5]})
    # the matrix 1X2 read by market_surface must be a coherent distribution
    assert surf["win_home"] + surf["draw"] + surf["win_away"] == pytest.approx(1.0, abs=1e-9)

    pr = predictor.predict(h, a)
    # anchored win-prob parity: JD is the matrix sampled, so it matches predict()'s
    # 1X2 within Monte-Carlo noise at this sim count.
    assert abs(surf["win_home"] - pr["p_home_win"]) < 5e-3
    assert abs(surf["win_away"] - pr["p_away_win"]) < 5e-3
    assert abs(surf["draw"] - pr["p_draw"]) < 5e-3
    # JD over-2.5 (raw, before Platt) matches the engine's raw over within MC noise
    assert abs(surf["over_2.5"] - pr["over_2.5_raw"]) < 5e-3


def test_predict_live_reprices_off_pregame(predictor, teams):
    """A non-trivial live state changes the surface vs pregame, and the output is sane."""
    h, a = teams
    pre = predictor.predict(h, a)
    live = predictor.predict_live(h, a, 30.0, 1, 0)  # home leads 1-0 at 30'
    assert live["sport"] == "soccer"
    for k in ("p_home_win", "p_draw", "p_away_win", "over_2.5", "under_2.5"):
        assert 0.0 <= live[k] <= 1.0
    assert live["p_home_win"] + live["p_draw"] + live["p_away_win"] == pytest.approx(1.0, abs=2e-4)
    assert live["remaining_minutes"] == pytest.approx(60.0, abs=1e-6)
    # repriced: a held lead makes the home win-prob differ materially from pregame
    assert abs(live["p_home_win"] - pre["p_home_win"]) > 1e-3
    # leading home team is more likely to win than its pregame number
    assert live["p_home_win"] > pre["p_home_win"]


def test_predict_live_sharpens_with_elapsed(predictor, teams):
    """The same held 1-0 lead is worth MORE later (less time to surrender it)."""
    h, a = teams
    early = predictor.predict_live(h, a, 30.0, 1, 0)
    late = predictor.predict_live(h, a, 80.0, 1, 0)
    assert late["remaining_minutes"] < early["remaining_minutes"]
    # sharper: home win-prob rises toward 1 as the clock runs with the lead held
    assert late["p_home_win"] > early["p_home_win"]
    # a level game at full time is a certain draw (degenerate-state sanity)
    ft_level = predictor.predict_live(h, a, 90.0, 1, 1)
    assert ft_level["p_draw"] == pytest.approx(1.0, abs=1e-9)
