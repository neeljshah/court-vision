"""Tests for scripts.platformkit.poisson_rating — synthetic games, no pandas."""
from __future__ import annotations

import numpy as np

from scripts.platformkit.poisson_rating import PoissonRatingModel, validate_sport


def _make_games(n=600, seed=0):
    """Two-tier offenses: 'BIG' teams average ~6 runs, 'SML' teams ~3."""
    rng = np.random.default_rng(seed)
    big = [f"B{i}" for i in range(4)]
    sml = [f"S{i}" for i in range(4)]
    teams = big + sml
    games = []
    for i in range(n):
        h, a = rng.choice(teams, size=2, replace=False)
        mh = 6.0 if h in big else 3.0
        ma = 6.0 if a in big else 3.0
        season = "2020" if i < n // 2 else "2021"
        games.append({"home": str(h), "away": str(a), "season": season,
                      "home_ct": float(rng.poisson(mh)), "away_ct": float(rng.poisson(ma))})
    return games


def test_rating_learns_offense():
    games = _make_games()
    lh, la = PoissonRatingModel().walkforward(games)
    assert lh.shape == (len(games),) and la.shape == (len(games),)
    assert np.all(lh > 0) and np.all(la > 0)
    # late: BIG-home games should predict more home runs than SML-home games
    big_home = [lh[i] for i, g in enumerate(games) if i > 400 and g["home"].startswith("B")]
    sml_home = [lh[i] for i, g in enumerate(games) if i > 400 and g["home"].startswith("S")]
    assert np.mean(big_home) > np.mean(sml_home)


def test_leak_free_truncation_invariance():
    games = _make_games()
    fh, fa = PoissonRatingModel().walkforward(games)
    for k in (60, 200, 450):
        th, ta = PoissonRatingModel().walkforward(games[:k])
        assert np.allclose(fh[:k], th, atol=1e-12)
        assert np.allclose(fa[:k], ta, atol=1e-12)


def test_validate_with_injected_loader():
    games = _make_games(n=900)

    def _loader(sport):
        return games

    res = validate_sport("mlb", min_history=200, loader=_loader)
    assert res["sport"] == "mlb" and res["n_eval"] == 700
    assert res["model_total_rmse"] > 0 and res["naive_total_rmse"] > 0
    # with real offense spread, the team-rating model should beat the naive mean
    assert res["model_total_rmse"] < res["naive_total_rmse"]
    assert "accuracy != edge" in res["note"].lower()


def test_unwired_sport_errors():
    res = validate_sport("nba", loader=lambda s: [])
    assert "error" in res and "not wired" in res["error"]
