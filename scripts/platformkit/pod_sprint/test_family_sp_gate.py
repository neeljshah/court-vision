"""Synthetic-fixture tests for scripts.platformkit.pod_sprint.family_sp_gate.
No real data/ needed -- games + sp_quality frames are built in-memory and
passed directly into run(games=..., sp_quality=...)."""
from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd
import pytest

from scripts.platformkit.pod_sprint import family_sp_gate as fsg

_N_TRAIN = 150
_N_TEST = 250


def _make_games_and_sp(n_train: int, n_test: int, predictive: bool, seed: int = 0):
    """Each game uses a UNIQUE (home, away) team pair -- Elo never accumulates
    real signal across games, isolating sp_diff's own predictive power."""
    rng = np.random.default_rng(seed)
    game_rows, sp_rows = [], []
    n_total = n_train + n_test
    base_date = dt.date(2022, 4, 1)
    for i in range(n_total):
        season = fsg.TRAIN_SEASON if i < n_train else fsg.TEST_SEASON
        date = base_date + dt.timedelta(days=i)
        home_team, away_team = f"H{i}", f"A{i}"

        if predictive:
            sign = -1 if i % 2 == 0 else 1  # sign<0 => home pitcher BETTER (lower xwoba)
        else:
            sign = rng.choice([-1, 1])
        home_val, away_val = (0.280, 0.330) if sign < 0 else (0.330, 0.280)
        sp_diff = home_val - away_val  # <0 => home pitcher better -> should favor home win

        if predictive:
            home_win = sp_diff < 0
        else:
            home_win = bool(rng.integers(0, 2))  # outcome independent of sp_diff -> noise
        home_runs, away_runs = (5, 2) if home_win else (2, 5)

        game_rows.append({
            "date": date, "season": season, "home_team": home_team, "away_team": away_team,
            "home_runs": float(home_runs), "away_runs": float(away_runs), "game_seq": i,
        })
        sp_rows.append({"pitcher": 1000 + 2 * i, "game_pk": i, "game_date": pd.Timestamp(date),
                         "team": home_team, "sp_xwoba_against_asof": home_val, "n_prior_starts": 3})
        sp_rows.append({"pitcher": 1001 + 2 * i, "game_pk": i, "game_date": pd.Timestamp(date),
                         "team": away_team, "sp_xwoba_against_asof": away_val, "n_prior_starts": 3})

    return pd.DataFrame(game_rows), pd.DataFrame(sp_rows)


def test_perfectly_predictive_sp_diff_detected():
    games, sp_quality = _make_games_and_sp(_N_TRAIN, _N_TEST, predictive=True)
    rep = fsg.run(games=games, sp_quality=sp_quality)
    assert rep["verdict"]["win"] == "SP1_DETECTED"
    assert rep["verdict"]["margin"] == "SP1_DETECTED"
    assert rep["ci"]["win"][1] < 0
    assert rep["edge_claimed"] is False
    assert rep["n"]["train"] >= fsg.MIN_N_TRAIN
    assert rep["n"]["test"] >= fsg.MIN_N_TEST


def test_noise_sp_diff_honest_null():
    games, sp_quality = _make_games_and_sp(_N_TRAIN, _N_TEST, predictive=False, seed=7)
    rep = fsg.run(games=games, sp_quality=sp_quality)
    assert rep["verdict"]["win"] == "NULL_LOCAL"
    assert rep["edge_claimed"] is False


def test_underpowered_below_floor():
    games, sp_quality = _make_games_and_sp(10, 20, predictive=True, seed=3)
    rep = fsg.run(games=games, sp_quality=sp_quality)
    assert rep["verdict"]["win"] == "UNDERPOWERED"
    assert rep["verdict"]["margin"] == "UNDERPOWERED"


def test_not_testable_when_games_absent():
    rep = fsg.run(games=pd.DataFrame(), sp_quality=pd.DataFrame({"x": [1]}))
    assert rep["verdict"] == {"win": "NOT_TESTABLE", "margin": "NOT_TESTABLE"}
    assert rep["edge_claimed"] is False
    assert rep["effect"] is None


def test_not_testable_when_statcast_absent_default_paths():
    """Exercises the REAL fail-closed default-path loader: this worktree has
    no data/, so build_sp_quality_asof(DEFAULT_STATCAST_PATHS) returns empty
    and run() must fail closed without raising."""
    games = pd.DataFrame({
        "date": [dt.date(2022, 4, 1)], "season": [2022], "home_team": ["AAA"],
        "away_team": ["BBB"], "home_runs": [5.0], "away_runs": [2.0], "game_seq": [0],
    })
    rep = fsg.run(games=games)
    assert rep["verdict"] == {"win": "NOT_TESTABLE", "margin": "NOT_TESTABLE"}
    assert rep["edge_claimed"] is False


def test_verdict_json_shape_has_required_keys():
    games, sp_quality = _make_games_and_sp(_N_TRAIN, _N_TEST, predictive=True)
    rep = fsg.run(games=games, sp_quality=sp_quality)
    for key in ("verdict", "effect", "ci", "n", "edge_claimed", "honest_note"):
        assert key in rep
