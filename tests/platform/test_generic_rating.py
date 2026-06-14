"""Tests for scripts.platformkit.generic_rating — synthetic games, no pandas."""
from __future__ import annotations

import numpy as np

from scripts.platformkit.generic_rating import GenericRatingModel, validate_sport


def _make_games(n=400, seed=0):
    """Two-tier league: 'strong' teams beat 'weak' ones ~75% of the time."""
    rng = np.random.default_rng(seed)
    strong = [f"S{i}" for i in range(5)]
    weak = [f"W{i}" for i in range(5)]
    teams = strong + weak
    games = []
    for i in range(n):
        h, a = rng.choice(teams, size=2, replace=False)
        ph = 0.5
        if h in strong and a in weak:
            ph = 0.78
        elif h in weak and a in strong:
            ph = 0.30
        season = "2020" if i < n // 2 else "2021"
        games.append({"home": str(h), "away": str(a), "season": season,
                      "home_win": float(rng.random() < ph)})
    return games


def test_elo_learns_strength():
    games = _make_games()
    probs = GenericRatingModel().walkforward(games)
    assert probs.shape == (len(games),)
    assert np.all((probs >= 0) & (probs <= 1))
    # late in the replay, strong-home-vs-weak games should be predicted > 0.5
    late = [(i, g) for i, g in enumerate(games) if i > 250
            and g["home"].startswith("S") and g["away"].startswith("W")]
    if late:
        assert np.mean([probs[i] for i, _ in late]) > 0.55


def test_leak_free_truncation_invariance():
    games = _make_games()
    full = GenericRatingModel().walkforward(games)
    for k in (50, 123, 300):
        trunc = GenericRatingModel().walkforward(games[:k])
        assert np.allclose(full[:k], trunc, atol=1e-12)


def test_validate_with_injected_loader():
    games = _make_games(n=600)
    base_p = np.full(len(games), 0.5)
    base_y = np.array([g["home_win"] for g in games])

    def _loader(sport):
        return games, base_p, base_y

    res = validate_sport("nba", min_history=100, loader=_loader)
    assert res["sport"] == "nba" and res["n_eval"] == 500
    assert 0 <= res["generic_elo"]["brier"] <= 1
    assert "baseline" in res and "brier_gap_vs_baseline" in res
    assert "accuracy != edge" in res["note"].lower()


def test_validate_no_baseline_ok():
    games = _make_games(n=500)

    def _loader(sport):
        return games, None, None

    res = validate_sport("mlb", min_history=100, loader=_loader)
    assert "generic_elo" in res and "baseline" not in res


def test_unwired_sport_errors():
    res = validate_sport("cricket")
    assert "error" in res and "not wired" in res["error"]


def test_tennis_wired_and_per_sport_hfa():
    from scripts.platformkit.generic_rating import _SPORT_CFG, _SPORT_HFA
    # tennis is a wired (player-schema) sport with zero home advantage
    assert "tennis" in _SPORT_CFG and _SPORT_CFG["tennis"].get("kind") == "player"
    assert _SPORT_HFA["tennis"] == 0.0 and _SPORT_HFA["mlb"] < _SPORT_HFA["nba"]
    # validate_sport("tennis", ...) uses the hfa=0 default model on injected games
    games = _make_games(n=500)
    res = validate_sport("tennis", min_history=100, loader=lambda s: (games, None, None))
    assert "generic_elo" in res and res["n_eval"] == 400
