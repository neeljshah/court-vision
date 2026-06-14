"""Tests for scripts.platformkit.rating_calibrated — synthetic injected loader."""
from __future__ import annotations

import numpy as np

from scripts.platformkit.rating_calibrated import run_sport


def _make_games(n=700, seed=0):
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


def _loader_with_baseline(games):
    base_y = np.array([g["home_win"] for g in games])
    base_p = np.full(len(games), 0.5)  # weak baseline
    return lambda sport: (games, base_p, base_y)


def test_stack_composes_and_calibration_never_hurts_logloss():
    games = _make_games()
    res = run_sport("nba", min_history=150, refit_every=20,
                    loader=_loader_with_baseline(games))
    assert res["sport"] == "nba" and res["n_eval"] == 550
    assert res["chosen_calibrator"] in {
        "identity", "temperature", "platt", "beta", "isotonic"}
    # identity is in the zoo, so the OOS-selected calibrator can never be worse on
    # log-loss than raw Elo:
    assert res["calib_improves_logloss"] is True
    assert "accuracy" in res["note"].lower() and "edge" in res["note"].lower()


def test_baseline_present_and_compared():
    games = _make_games()
    res = run_sport("nba", min_history=150, loader=_loader_with_baseline(games))
    assert "baseline" in res
    assert isinstance(res["calibrated_beats_baseline_brier"], bool)


def test_no_baseline_ok():
    games = _make_games()
    res = run_sport("mlb", min_history=150, loader=lambda s: (games, None, None))
    assert "calibrated_elo" in res and "baseline" not in res


def test_too_few_games_errors():
    res = run_sport("nba", min_history=500, loader=lambda s: (_make_games(50), None, None))
    assert "error" in res and "too few" in res["error"]
