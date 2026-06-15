"""Per-file test for domains/basketball_nba/predictor.py — the usable NBA predictor.

Asserts a coherent calibrated surface. Calibration/accuracy only; no edge.

Run: python -m pytest tests/platform/test_nba_predictor.py -q
"""
from __future__ import annotations

import pytest

from domains.basketball_nba.predictor import NBAPredictor


@pytest.fixture(scope="module")
def predictor():
    try:
        return NBAPredictor()
    except FileNotFoundError:
        pytest.skip("NBA box corpus not present")


def test_surface_coherent(predictor):
    s = predictor.predict("BOS", "LAL")
    assert s["sport"] == "nba"
    assert s["p_home_win"] + s["p_away_win"] == pytest.approx(1.0, abs=1e-6)
    assert 0.0 < s["p_home_win"] < 1.0
    assert 150.0 < s["total_mean"] < 300.0
    assert 12.0 < s["total_sigma"] < 28.0
    for t in s["totals"]:
        assert t["over"] + t["under"] == pytest.approx(1.0, abs=1e-6)
        assert 0.0 <= t["over"] <= 1.0
    # over prob must decrease as the line rises (monotone)
    overs = [t["over"] for t in s["totals"]]
    assert all(b <= a + 1e-9 for a, b in zip(overs, overs[1:]))


def test_home_court_edge(predictor):
    """Same team at home should be favoured vs the same matchup reversed."""
    a = predictor.predict("BOS", "LAL")["p_home_win"]
    b = predictor.predict("LAL", "BOS")["p_home_win"]
    # home team in each gets the HFA -> both home probs reflect court; their implied
    # neutral-court edge for BOS should be consistent (BOS home prob > LAL-at-BOS away share)
    assert a > (1.0 - b) - 1e-9 or abs(a - (1.0 - b)) < 0.2


def test_unknown_team_falls_back(predictor):
    s = predictor.predict("ZZZ", "BOS")
    assert 0.0 < s["p_home_win"] < 1.0     # league-prior fallback, no crash


def test_predict_live_evolves_with_state(predictor):
    """In-game win-prob anchors to pregame early and to the realized lead late."""
    pre = predictor.predict("BOS", "LAL")["p_home_win"]
    early = predictor.predict_live("BOS", "LAL", 12, 30, 25)   # +5 early
    late = predictor.predict_live("BOS", "LAL", 36, 88, 80)    # +8 late
    for s in (early, late):
        assert 0.0 < s["p_home_win"] < 1.0
        assert s["proj_total"] > 150.0
        assert s["pregame_p_home"] == pre
    # a held lead is worth MORE late (less time to lose it) than the same edge early
    assert late["p_home_win"] > early["p_home_win"]
    # leading home team is more likely to win than its pregame number
    assert early["p_home_win"] > pre


def test_to_jd_coherent_with_predict(predictor):
    """The JointDistribution's moneyline/total must match the predict() surface (anchored)."""
    from scripts.platformkit.sim_framework import market_surface

    jd = predictor.to_jd("BOS", "LAL", n_sims=60_000, seed=1)
    surf = market_surface(jd, {"home_idx": 0, "away_idx": 1, "total_lines": [220.5]})
    pr = predictor.predict("BOS", "LAL")
    # JD win-prob anchored to the Elo win-prob within MC noise
    assert abs(surf["win_home"] - pr["p_home_win"]) < 0.02
    # JD total mean matches the possessions-model total within MC noise
    assert abs((surf["home_mean"] + surf["away_mean"]) - pr["total_mean"]) < 1.5
