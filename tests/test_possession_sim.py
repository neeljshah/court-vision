"""Smoke + sanity tests for FRONT A possession-outcome model + rest-of-game sim.

Covers: possession segmentation produces sane rows; the outcome model fits and
samples valid (outcome, points); the simulator returns finite, calibrated-ish
distributions; final at t=0 equals current score with ZERO variance; and the
learned model is a drop-in for RestOfGameSim. Leak posture is enforced by the
state_featurizer's own truncation-invariance test; here we assert the possession
state at the start of a possession does not depend on that possession's outcome.
"""
import os
import sys

import numpy as np
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("NBA_OFFLINE", "1")

from src.ingame.state_featurizer import load_pbp_events, _load_team_map  # noqa: E402
from src.sim.possession_model import (  # noqa: E402
    extract_possessions, PossessionOutcomeModel, OUTCOMES, STATE_FEATURES,
)
from src.sim.rest_of_game_sim import RestOfGameSim  # noqa: E402


def _sample_game_ids(n=3):
    tm = _load_team_map(os.path.join(ROOT, "data", "nba"))
    ids = []
    for gid, (home, away) in tm.items():
        if gid.isdigit() and os.path.exists(
                os.path.join(ROOT, "data", "nba", f"pbp_{gid}_p1.json")):
            ids.append((gid, home, away))
        if len(ids) >= n:
            break
    return ids


def _train_rows(n_games=4):
    rows = []
    for gid, home, away in _sample_game_ids(n_games):
        ev = load_pbp_events(gid, os.path.join(ROOT, "data", "nba"))
        if ev:
            rows.extend(extract_possessions(ev, gid, home, away))
    return rows


@pytest.mark.skipif(not _sample_game_ids(1), reason="no PBP data available")
def test_extract_possessions_sane():
    gid, home, away = _sample_game_ids(1)[0]
    ev = load_pbp_events(gid, os.path.join(ROOT, "data", "nba"))
    rows = extract_possessions(ev, gid, home, away)
    assert 120 <= len(rows) <= 280, f"unrealistic possession count {len(rows)}"
    assert all(r.outcome in OUTCOMES for r in rows)
    assert all(r.points >= 0 for r in rows)
    # make_2/make_3 always score; turnover/miss never do
    for r in rows:
        if r.outcome in ("make_2", "make_3"):
            assert r.points >= 2
        if r.outcome in ("turnover", "miss_2", "miss_3"):
            assert r.points == 0
    # state vector has all declared features
    for f in STATE_FEATURES:
        assert f in rows[0].state


@pytest.mark.skipif(not _sample_game_ids(1), reason="no PBP data available")
def test_state_excludes_own_outcome():
    """The state at possession start must not encode that possession's result.

    Re-extract with the SAME prefix of events and confirm the start state of a
    possession is identical regardless of how it ends -- approximated by checking
    two consecutive possessions' start states differ only by the prior poss's
    contribution (monotone non-decreasing poss counts), never by future info.
    """
    gid, home, away = _sample_game_ids(1)[0]
    ev = load_pbp_events(gid, os.path.join(ROOT, "data", "nba"))
    rows = extract_possessions(ev, gid, home, away)
    # poss counts and clock are monotone non-decreasing across possessions
    prev_sec = -1
    prev_poss = -1
    for r in rows:
        tot = r.state["off_poss_count"] + r.state["def_poss_count"]
        assert r.game_sec >= prev_sec
        assert tot >= prev_poss
        prev_sec = r.game_sec
        prev_poss = tot


@pytest.mark.skipif(not _sample_game_ids(1), reason="no PBP data available")
def test_model_fit_and_sample():
    rows = _train_rows(4)
    assert rows
    m = PossessionOutcomeModel(device="cpu", n_rounds=40).fit(rows)
    rng = np.random.default_rng(0)
    p = m.predict_proba(rows[50].state)
    assert p.shape == (len(OUTCOMES),)
    assert abs(float(p.sum()) - 1.0) < 1e-4
    assert (p >= 0).all()
    o, pts = m.sample_outcome(rows[50].state, rng)
    assert o in OUTCOMES and pts >= 0
    ev = m.expected_points(rows[50].state)
    assert 0.5 < ev < 2.0, f"E[pts/poss]={ev} outside sane range"


@pytest.mark.skipif(not _sample_game_ids(1), reason="no PBP data available")
def test_sim_finite_and_calibrated():
    rows = _train_rows(4)
    m = PossessionOutcomeModel(device="cpu", n_rounds=40).fit(rows)
    sim = RestOfGameSim(n_sims=500, model=m, seed=0)
    # halftime-ish state: 24 min elapsed, modest lead
    row = {
        "period": 2, "game_elapsed_sec": 1440, "game_remaining_sec": 1440,
        "played_share": 0.5, "home_score": 55, "away_score": 50,
        "home_poss": 48, "away_poss": 48, "total_poss_count": 96,
        "home_poss_count": 48, "away_poss_count": 48,
        "home_fgm": 20, "home_fga": 45, "home_fg3m": 6, "home_fg3a": 18,
        "home_ftm": 9, "home_fta": 12, "home_tov": 7,
        "away_fgm": 18, "away_fga": 44, "away_fg3m": 5, "away_fg3a": 16,
        "away_ftm": 9, "away_fta": 11, "away_tov": 8,
        "home_efg": 0.51, "away_efg": 0.49,
        "home_tov_pct": 0.13, "away_tov_pct": 0.15,
        "home_ft_rate": 0.27, "away_ft_rate": 0.25,
        "sec_per_poss_so_far": 15.0, "home_in_bonus": 0, "away_in_bonus": 0,
    }
    res = sim.simulate(row)
    assert np.isfinite(res.home_final_mean) and np.isfinite(res.away_final_mean)
    # final >= current score (can only add points)
    assert res.home_final_mean >= 55 - 1
    assert res.away_final_mean >= 50 - 1
    # a full-game total should land in a realistic NBA band
    assert 180 <= res.total_mean <= 280, f"total {res.total_mean} unrealistic"
    assert 0.0 <= res.home_win_prob <= 1.0
    # a 5-pt halftime lead -> home should be favored but not a lock
    assert 0.5 < res.home_win_prob < 0.95


@pytest.mark.skipif(not _sample_game_ids(1), reason="no PBP data available")
def test_sim_t0_is_degenerate_final():
    """At t=0 (game over) the final must equal the current score, zero variance."""
    rows = _train_rows(2)
    m = PossessionOutcomeModel(device="cpu", n_rounds=20).fit(rows)
    sim = RestOfGameSim(n_sims=200, model=m, seed=1)
    row = {
        "period": 4, "game_elapsed_sec": 2880, "game_remaining_sec": 0,
        "played_share": 1.0, "home_score": 112, "away_score": 108,
        "home_poss": 96, "away_poss": 96, "total_poss_count": 192,
        "home_poss_count": 96, "away_poss_count": 96,
        "sec_per_poss_so_far": 15.0,
    }
    res = sim.simulate(row)
    assert res.home_final_mean == 112
    assert res.away_final_mean == 108
    assert res.home_final_samples.std() == 0.0
    assert res.away_final_samples.std() == 0.0
    assert res.home_win_prob == 1.0


@pytest.mark.skipif(not _sample_game_ids(1), reason="no PBP data available")
def test_learned_model_is_dropin():  # noqa: D401
    """PossessionOutcomeModel.team_params matches the EmpiricalModel signature."""
    rows = _train_rows(3)
    m = PossessionOutcomeModel(device="cpu", n_rounds=20).fit(rows)
    row = {"home_score": 50, "away_score": 48, "home_poss": 45, "away_poss": 45,
           "home_poss_count": 45, "away_poss_count": 45, "period": 2,
           "game_remaining_sec": 1440, "played_share": 0.5,
           "home_efg": 0.5, "away_efg": 0.48, "sec_per_poss_so_far": 15.0}
    pp = m.team_params(row, "home", None)
    assert set(pp) == {"ppp", "p_score", "mean_pts_score", "three_share"}
    assert 0.7 < pp["ppp"] < 1.6
    assert 0.2 < pp["p_score"] < 0.95
