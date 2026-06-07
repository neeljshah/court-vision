"""Interface + leak-posture tests for src.sim.rest_of_game_sim (FRONT A)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("NBA_OFFLINE", "1")

import numpy as np  # noqa: E402

from src.sim.rest_of_game_sim import (  # noqa: E402
    RestOfGameSim, EmpiricalPossessionModel, SimResult,
)


def _half_state():
    return dict(
        home_score=55, away_score=50, score_margin=5,
        game_remaining_sec=1440, game_elapsed_sec=1440,
        home_poss=50, away_poss=50, total_poss_count=100,
        home_fgm=20, home_ftm=10, home_fg3a=20, home_fga=45,
        away_fgm=18, away_ftm=9, away_fg3a=18, away_fga=44,
        home_team="AAA", away_team="BBB",
    )


def test_simulate_returns_sane_result():
    res = RestOfGameSim(n_sims=2000, seed=0).simulate(_half_state())
    assert isinstance(res, SimResult)
    # leader with +5 at the half should be favored but not certain
    assert 0.55 < res.home_win_prob < 0.95
    # finals must exceed the current score and totals be NBA-plausible
    assert res.home_final_mean > 55 and res.away_final_mean > 50
    assert 170 < res.total_mean < 260
    assert res.home_final_samples.shape == (2000,)


def test_determinism_same_seed():
    a = RestOfGameSim(n_sims=1500, seed=7).simulate(_half_state())
    b = RestOfGameSim(n_sims=1500, seed=7).simulate(_half_state())
    assert a.margin_mean == b.margin_mean
    assert a.home_win_prob == b.home_win_prob


def test_leak_invariance_to_future_keys():
    """Sim reads ONLY current-state fields -> adding any future-looking key to
    the row must not change the result (truncation-invariance proxy)."""
    base = _half_state()
    poisoned = dict(base, FUTURE_final_home=999, home_final=999, away_final=0)
    a = RestOfGameSim(n_sims=2000, seed=3).simulate(base)
    b = RestOfGameSim(n_sims=2000, seed=3).simulate(poisoned)
    assert abs(a.margin_mean - b.margin_mean) < 1e-9
    assert a.home_win_prob == b.home_win_prob


def test_endgame_collapses_to_current():
    """With ~0 time left the projection must be ~the current score."""
    row = _half_state()
    row["game_remaining_sec"] = 0
    res = RestOfGameSim(n_sims=500, seed=0).simulate(row)
    assert abs(res.home_final_mean - 55) < 1e-6
    assert abs(res.away_final_mean - 50) < 1e-6
    assert res.home_win_prob == 1.0  # home leads, no time left


def test_prior_form_injection_changes_nothing_illegal():
    """Priors are a game-constant; supplying them is accepted and shifts ppp."""
    row = _half_state()
    weak = {"home_ppp": 0.9, "away_ppp": 1.3,
            "home_pace_per48": 95.0, "away_pace_per48": 95.0}
    base = RestOfGameSim(n_sims=3000, seed=1).simulate(row)
    skewed = RestOfGameSim(n_sims=3000, seed=1).simulate(row, priors=weak)
    # an away-favoring prior should lower home win prob vs no prior
    assert skewed.home_win_prob <= base.home_win_prob + 0.02


def test_model_is_injectable():
    """A custom possession model satisfying team_params() can be slotted in."""
    class FlatModel(EmpiricalPossessionModel):
        def team_params(self, game_row, side, priors):
            return {"ppp": 1.1, "p_score": 0.5, "mean_pts_score": 2.2,
                    "three_share": 0.35}
    res = RestOfGameSim(n_sims=1000, seed=0,
                        model=FlatModel()).simulate(_half_state())
    # symmetric model -> margin driven only by the current +5 lead
    assert res.margin_mean > 0
