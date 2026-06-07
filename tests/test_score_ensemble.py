"""Tests for src.ingame.score_ensemble.project_score_ensemble.

Covers the measured-best combination contract:
  * POINT estimate comes from the injected ridge (its measured strength), and
    falls back to the sim mean when no ridge is supplied (never invents a number).
  * WIN PROB comes from the possession sim (its measured strength) and is NEVER
    moved by point-calibration.
  * The score DISTRIBUTION comes from the sim; with calibrate_to_point it is
    mean-shifted onto the ridge point with spread/shape PRESERVED.
  * Determinism (fixed seed) and leak-free pass-through of priors.
"""
import os
import sys

import numpy as np
import pytest

sys.path.insert(0, ".")
os.environ.setdefault("NBA_OFFLINE", "1")

from src.ingame.score_ensemble import (  # noqa: E402
    ScoreEnsembleResult,
    project_score_ensemble,
    _coerce_ridge_point,
    _recentre_samples,
    DEFAULT_N_SIMS,
)


def _state(home=55, away=50, rem=900, elapsed=1980, poss=88):
    """A mid-Q3-ish leak-free game-state row the sim consumes."""
    return {
        "home_score": home,
        "away_score": away,
        "game_remaining_sec": rem,
        "game_elapsed_sec": elapsed,
        "total_poss_count": poss,
        "home_poss": poss // 2,
        "away_poss": poss // 2,
        "home_fgm": 20, "home_fga": 44, "home_fg3a": 16, "home_ftm": 8,
        "away_fgm": 18, "away_fga": 43, "away_fg3a": 15, "away_ftm": 7,
        "home_team": "AAA", "away_team": "BBB",
    }


# --------------------------------------------------------------------------- #
# point estimate := ridge
# --------------------------------------------------------------------------- #
def test_point_is_ridge_when_supplied():
    rp = {"home_final": 112.0, "away_final": 105.0}
    res = project_score_ensemble(_state(), ridge_point=rp, n_sims=400, seed=0)
    assert isinstance(res, ScoreEnsembleResult)
    assert res.home_final == pytest.approx(112.0)
    assert res.away_final == pytest.approx(105.0)
    assert res.margin == pytest.approx(7.0)
    assert res.total == pytest.approx(217.0)
    assert res.point_source == "ridge"
    assert res.ridge_home_final == pytest.approx(112.0)


def test_point_falls_back_to_sim_mean_when_no_ridge():
    res = project_score_ensemble(_state(), ridge_point=None, n_sims=400, seed=0)
    assert res.point_source == "sim_fallback"
    # served point must equal the carried sim means (no invented number)
    assert res.home_final == pytest.approx(res.sim_home_final_mean)
    assert res.away_final == pytest.approx(res.sim_away_final_mean)
    assert res.ridge_home_final is None


def test_ridge_point_accepts_tuple():
    res = project_score_ensemble(_state(), ridge_point=(120.0, 99.0),
                                 n_sims=300, seed=1)
    assert res.point_source == "ridge"
    assert res.home_final == pytest.approx(120.0)
    assert res.away_final == pytest.approx(99.0)


def test_bad_ridge_point_falls_back():
    # unparseable -> fallback, never raises, never invents
    for bad in ({"foo": 1}, "not-a-point", (float("nan"), 100.0), (1,)):
        res = project_score_ensemble(_state(), ridge_point=bad,
                                     n_sims=200, seed=0)
        assert res.point_source == "sim_fallback"


# --------------------------------------------------------------------------- #
# win prob := sim, never moved by calibration
# --------------------------------------------------------------------------- #
def test_winprob_from_sim_and_invariant_to_calibration():
    st = _state()
    rp = {"home_final": 130.0, "away_final": 90.0}  # extreme ridge point
    on = project_score_ensemble(st, ridge_point=rp, n_sims=600, seed=3,
                                calibrate_to_point=True)
    off = project_score_ensemble(st, ridge_point=rp, n_sims=600, seed=3,
                                 calibrate_to_point=False)
    # calibration must NOT change the win prob (sim's measured strength)
    assert on.home_win_prob == pytest.approx(off.home_win_prob)
    assert on.winprob_source == "possession_sim"
    assert 0.0 <= on.home_win_prob <= 1.0


def test_winprob_matches_raw_sim():
    from src.sim.rest_of_game_sim import RestOfGameSim
    st = _state()
    raw = RestOfGameSim(n_sims=500, seed=7).simulate(st)
    res = project_score_ensemble(st, ridge_point={"home_final": 111, "away_final": 108},
                                 n_sims=500, seed=7)
    assert res.home_win_prob == pytest.approx(raw.home_win_prob)


# --------------------------------------------------------------------------- #
# distribution := sim, recentred onto ridge point (shape preserved)
# --------------------------------------------------------------------------- #
def test_calibration_recenters_distribution_preserving_spread():
    st = _state()
    rp = {"home_final": 118.0, "away_final": 101.0}
    res = project_score_ensemble(st, ridge_point=rp, n_sims=2000, seed=5,
                                 calibrate_to_point=True)
    assert res.distribution_source == "possession_sim+ridge_recentred"
    # recentred sample mean == ridge point
    assert res.home_final_samples.mean() == pytest.approx(118.0, abs=1e-6)
    assert res.away_final_samples.mean() == pytest.approx(101.0, abs=1e-6)
    # spread preserved vs the un-recentred sim
    raw = project_score_ensemble(st, ridge_point=rp, n_sims=2000, seed=5,
                                 calibrate_to_point=False)
    assert res.home_final_samples.std() == pytest.approx(
        raw.home_final_samples.std(), abs=1e-9)


def test_no_calibration_leaves_distribution_at_sim_mean():
    st = _state()
    rp = {"home_final": 118.0, "away_final": 101.0}
    res = project_score_ensemble(st, ridge_point=rp, n_sims=1500, seed=2,
                                 calibrate_to_point=False)
    assert res.distribution_source == "possession_sim"
    # distribution still centred on the SIM mean, not the ridge point
    assert res.home_final_samples.mean() == pytest.approx(
        res.sim_home_final_mean, abs=1e-6)


def test_fallback_never_recenters():
    res = project_score_ensemble(_state(), ridge_point=None, n_sims=400, seed=0,
                                 calibrate_to_point=True)
    assert res.distribution_source == "possession_sim"


# --------------------------------------------------------------------------- #
# determinism + plumbing
# --------------------------------------------------------------------------- #
def test_deterministic_with_seed():
    st = _state()
    a = project_score_ensemble(st, ridge_point=(110, 108), n_sims=500, seed=9)
    b = project_score_ensemble(st, ridge_point=(110, 108), n_sims=500, seed=9)
    assert a.home_win_prob == pytest.approx(b.home_win_prob)
    assert np.array_equal(a.home_final_samples, b.home_final_samples)


def test_as_dict_has_provenance():
    res = project_score_ensemble(_state(), ridge_point=(110, 108),
                                 n_sims=200, seed=0)
    d = res.as_dict()
    for k in ("home_final", "away_final", "margin", "total", "home_win_prob",
              "point_source", "winprob_source", "distribution_source",
              "sim_home_final_mean", "sim_away_final_mean"):
        assert k in d
    assert d["winprob_source"] == "possession_sim"


def test_priors_passed_through_to_sim():
    # supplying priors must not error and should be honoured by the sim
    st = _state()
    priors = {"home_ppp": 1.25, "away_ppp": 1.00,
              "home_pace_per48": 102.0, "away_pace_per48": 96.0}
    res = project_score_ensemble(st, ridge_point=None, priors=priors,
                                 n_sims=500, seed=0)
    # home has a much stronger ppp prior -> sim should favour home on average
    assert res.sim_home_final_mean > res.sim_away_final_mean


def test_default_n_sims_constant():
    assert DEFAULT_N_SIMS == 2000


# --------------------------------------------------------------------------- #
# helper unit tests
# --------------------------------------------------------------------------- #
def test_coerce_ridge_point_variants():
    assert _coerce_ridge_point({"home_final": 1, "away_final": 2}) == {"home": 1.0, "away": 2.0}
    assert _coerce_ridge_point({"home_score": 3, "away_score": 4}) == {"home": 3.0, "away": 4.0}
    assert _coerce_ridge_point({"home": 5, "away": 6}) == {"home": 5.0, "away": 6.0}
    assert _coerce_ridge_point([7, 8]) == {"home": 7.0, "away": 8.0}
    assert _coerce_ridge_point(None) is None
    assert _coerce_ridge_point({"x": 1}) is None
    assert _coerce_ridge_point((float("nan"), 1.0)) is None


def test_recentre_samples_shifts_mean_keeps_shape():
    s = np.array([1.0, 2.0, 3.0, 4.0])
    out = _recentre_samples(s, current_mean=2.5, target_mean=10.0)
    assert out.mean() == pytest.approx(10.0)
    assert out.std() == pytest.approx(s.std())
    # empty / None safe
    assert _recentre_samples(np.zeros(0), 0.0, 5.0).size == 0
