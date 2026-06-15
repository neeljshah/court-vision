"""Per-file test for domains/mlb/predictor.py — the usable MLB predictor.

Asserts a coherent calibrated surface (probs in [0,1], total>0, monotone O/U), a
JointDistribution coherent with predict() (anchored win-prob parity within MC noise +
sum-to-1 invariants exact), and an in-game predict_live() that reprices off a non-trivial
state and SHARPENS as the game elapses. Calibration/accuracy only; markets efficient; no edge.

Run: python -m pytest tests/platform/test_mlb_predictor.py -q
(NEVER run the full suite — it freezes the box.)
"""
from __future__ import annotations

import pytest

from domains.mlb.predictor import MLBPredictor


@pytest.fixture(scope="module")
def predictor():
    try:
        return MLBPredictor()
    except FileNotFoundError:
        pytest.skip("MLB games corpus not present")


@pytest.fixture(scope="module")
def matchup(predictor):
    """A real pair of teams from the ingested corpus (avoids league-prior degeneracy)."""
    return predictor.teams[0], predictor.teams[1]


def test_surface_coherent(predictor, matchup):
    """predict() returns a sane surface: probs in [0,1], total>0, monotone O/U."""
    home, away = matchup
    s = predictor.predict(home, away)
    assert s["sport"] == "mlb"
    # moneyline is a proper two-outcome split (Elo win-prob, no ties)
    assert s["p_home_win"] + s["p_away_win"] == pytest.approx(1.0, abs=1e-6)
    assert 0.0 < s["p_home_win"] < 1.0
    # expected runs / total are positive and sane for baseball
    assert s["expected_runs_home"] > 0.0
    assert s["expected_runs_away"] > 0.0
    assert s["expected_total"] > 0.0
    assert s["expected_total"] == pytest.approx(
        s["expected_runs_home"] + s["expected_runs_away"], abs=1e-2)
    assert 2.0 < s["expected_total"] < 25.0
    # O/U: each line is a proper complementary split in [0,1]
    for t in s["totals"]:
        assert t["over"] + t["under"] == pytest.approx(1.0, abs=1e-6)
        assert 0.0 <= t["over"] <= 1.0
    # over prob must be non-increasing as the line rises (monotone distribution)
    overs = [t["over"] for t in s["totals"]]
    assert all(b <= a + 1e-9 for a, b in zip(overs, overs[1:]))
    # fitted dispersion r is reported and positive (FITTED, not hardcoded)
    assert s["dispersion_r"]["home"] > 0.0
    assert s["dispersion_r"]["away"] > 0.0


def test_unknown_team_falls_back(predictor):
    """Unknown teams fall back to league priors without crashing."""
    s = predictor.predict("ZZZ", "QQQ")
    assert 0.0 < s["p_home_win"] < 1.0
    assert s["expected_total"] > 0.0


def test_to_jd_coherent_with_predict(predictor, matchup):
    """to_jd() is coherent with sim_framework.market_surface.

    The JD's moneyline is anchored so P(home_runs > away_runs) == the Elo win-prob; the
    raw market_surface win_home reads that same event off the sample matrix, so it matches
    predict()'s p_home_win within MC sampling noise (1e-6 is unattainable for a SAMPLED
    distribution with baseball ties — the established predictor-test convention is an MC
    tolerance). The win/draw/loss split sums to exactly 1.0, and the total mean matches the
    run-rate expected total within MC noise.
    """
    from scripts.platformkit.sim_framework import market_surface

    home, away = matchup
    jd = predictor.to_jd(home, away, n_sims=80_000, seed=1)
    surf = market_surface(jd, {"home_idx": 0, "away_idx": 1, "total_lines": [8.5]})
    pr = predictor.predict(home, away)
    # coherence: the three outcome counts sum to exactly 1.0 (counting invariant)
    assert surf["win_home"] + surf["win_away"] + surf["draw"] == pytest.approx(1.0, abs=1e-6)
    assert surf["draw"] >= 0.0   # ties (extra-innings unresolved in the matrix) are a real slice
    # anchored win-prob parity: MLB has no real ties (same-runs games go to extras, ~50/50),
    # so the coherent home-win estimate is TIE-ADJUSTED (win_home + 0.5*draw). to_jd anchors
    # that to the Elo win-prob on the NegBinom matrix, so it matches within MC noise.
    assert abs((surf["win_home"] + 0.5 * surf["draw"]) - pr["p_home_win"]) < 0.01
    # JD total mean matches the run-rate expected total within MC noise
    assert abs((surf["home_mean"] + surf["away_mean"]) - pr["expected_total"]) < 0.3
    # O/U read off the JD is a proper complementary split
    assert surf["over_8.5"] + surf["under_8.5"] == pytest.approx(1.0, abs=1e-6)


def test_predict_live_reprices(predictor, matchup):
    """predict_live() reprices: a non-trivial in-game state shifts the output off pregame."""
    home, away = matchup
    pre = predictor.predict(home, away)
    live = predictor.predict_live(home, away, inning=6, half="top",
                                  home_runs=4, away_runs=2)
    assert live["sport"] == "mlb"
    assert 0.0 < live["p_home_win"] < 1.0
    assert live["p_home_win"] + live["p_away_win"] == pytest.approx(1.0, abs=1e-6)
    assert live["proj_remaining_runs"] >= 0.0
    assert live["innings_remaining"] >= 0.0
    # a 4-2 home lead with most of the game gone must move the number off pregame
    assert abs(live["p_home_win"] - pre["p_home_win"]) > 1e-3
    # leading home team is more likely to win than its pregame number
    assert live["p_home_win"] > pre["p_home_win"]


def test_predict_live_sharpens_with_elapsed(predictor, matchup):
    """The SAME held lead is worth more later (less time to surrender it)."""
    home, away = matchup
    early = predictor.predict_live(home, away, inning=4, half="top",
                                   home_runs=4, away_runs=2)
    late = predictor.predict_live(home, away, inning=8, half="top",
                                  home_runs=4, away_runs=2)
    for s in (early, late):
        assert 0.0 < s["p_home_win"] < 1.0
    # fewer innings remaining late, and the held lead is sharper (closer to 1.0)
    assert late["innings_remaining"] < early["innings_remaining"]
    assert late["p_home_win"] > early["p_home_win"]
