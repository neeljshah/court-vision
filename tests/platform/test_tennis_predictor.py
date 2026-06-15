"""Per-file test for domains/tennis/predictor.py — the usable tennis predictor.

Asserts a coherent calibrated surface, leak-free id-order resolution, in-game evolution,
and JointDistribution coherence with predict(). Calibration/accuracy only; no edge.

Run: python -m pytest tests/platform/test_tennis_predictor.py -q
"""
from __future__ import annotations

import pytest

from domains.tennis.predictor import TennisPredictor


@pytest.fixture(scope="module")
def predictor():
    try:
        return TennisPredictor()
    except (FileNotFoundError, OSError):
        pytest.skip("tennis matches corpus not present")


def test_surface_coherent(predictor):
    s = predictor.predict("Carlos Alcaraz", "Novak Djokovic", "Hard")
    assert s["sport"] == "tennis"
    assert s["p1_match_win"] + s["p2_match_win"] == pytest.approx(1.0, abs=1e-6)
    assert 0.0 < s["p1_match_win"] < 1.0
    assert 12.0 < s["total_games_mean"] < 60.0
    for t in s["totals"]:
        assert t["over"] + t["under"] == pytest.approx(1.0, abs=1e-6)
        assert 0.0 <= t["over"] <= 1.0
    overs = [t["over"] for t in s["totals"]]   # over prob decreases as the line rises
    assert all(b <= a + 1e-9 for a, b in zip(overs, overs[1:]))


def test_caller_order_symmetric(predictor):
    """Swapping player order swaps the probabilities (outcome-independent id-order)."""
    a = predictor.predict("Carlos Alcaraz", "Novak Djokovic", "Hard")["p1_match_win"]
    b = predictor.predict("Novak Djokovic", "Carlos Alcaraz", "Hard")["p2_match_win"]
    assert abs(a - b) < 0.05   # same matchup, just relabeled; MC noise only


def test_wta_temperature_shrinks(predictor):
    """The WTA temperature option (T=1.36>1) pulls a favourite toward 0.5."""
    base = predictor.predict("Carlos Alcaraz", "Learner Tien", "Hard")["p1_match_win_raw_elo"]
    temp = predictor.predict("Carlos Alcaraz", "Learner Tien", "Hard",
                             use_wta_temp=True)["p1_match_win"]
    assert abs(temp - 0.5) < abs(base - 0.5)


def test_unknown_player_falls_back(predictor):
    s = predictor.predict("Nobody XYZ", "Carlos Alcaraz", "Clay")
    assert 0.0 < s["p1_match_win"] < 1.0    # base-rating fallback, no crash


def test_predict_live_evolves(predictor):
    pre = predictor.predict("Carlos Alcaraz", "Novak Djokovic", "Hard")["p1_match_win"]
    up = predictor.predict_live("Carlos Alcaraz", "Novak Djokovic", 1, 0)
    decided = predictor.predict_live("Carlos Alcaraz", "Novak Djokovic", 2, 0)
    assert up["pregame_p1_match_win"] == pre
    assert up["p1_match_win"] > pre          # leading a set raises win prob
    assert decided["p1_match_win"] == pytest.approx(1.0)
    assert decided["decided"] is True


def test_to_jd_coherent_with_predict(predictor):
    """The JointDistribution's set-moneyline must match predict() within MC noise."""
    from scripts.platformkit.sim_framework import market_surface

    jd = predictor.to_jd("Carlos Alcaraz", "Novak Djokovic", "Hard", n_sims=40_000, seed=1)
    surf = market_surface(jd, {"home_idx": 0, "away_idx": 1})
    pr = predictor.predict("Carlos Alcaraz", "Novak Djokovic", "Hard", n_sims=40_000, seed=1)
    assert surf["win_home"] + surf["win_away"] + surf["draw"] == pytest.approx(1.0, abs=1e-6)
    assert surf["draw"] == pytest.approx(0.0, abs=1e-9)     # every sim is a finished match
    assert abs(surf["win_home"] - pr["p1_match_win"]) < 0.05
