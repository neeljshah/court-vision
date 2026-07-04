"""Per-file tests for domains.baseball_npb.pregame_gate (synthetic data, offline).

  cd /c/Users/neelj/nba-ai-system && python -m pytest domains/baseball_npb/test_pregame_gate.py -q
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from domains.baseball_npb import pregame_gate as pg


def _synthetic_corpus(n_per_season=80, seed=0, tie_rate=0.03):
    """Two synthetic seasons where a persistent-strength signal exists, plus a
    realistic small tie rate (NPB draws), so Elo SHOULD beat coin-flip and
    home-prior baselines on the decisive games."""
    rng = np.random.RandomState(seed)
    teams = ["Giants", "Tigers", "Carp", "Dragons", "Swallows", "BayStars"]
    strength = {t: rng.normal(0, 1) for t in teams}
    rows = []
    for season in ["2024", "2025"]:
        dates = pd.date_range(f"{season}-04-01", periods=n_per_season, freq="D")
        for i in range(n_per_season):
            home, away = rng.choice(teams, size=2, replace=False)
            if rng.random_sample() < tie_rate:
                hw = np.nan
                hs, as_ = 3.0, 3.0
            else:
                d = strength[home] - strength[away] + 0.2
                p_true = 1.0 / (1.0 + np.exp(-d))
                hw = 1.0 if rng.random_sample() < p_true else 0.0
                hs, as_ = (4.0, 2.0) if hw else (2.0, 4.0)
            rows.append({
                "date": dates[i], "season": season,
                "home_team": home, "away_team": away,
                "home_score": hs, "away_score": as_,
                "home_win": hw, "tied": bool(np.isnan(hw)),
            })
    return pd.DataFrame(rows)


def test_gate_pregame_two_corpora_returns_result_per_corpus():
    df = _synthetic_corpus()
    verdict = pg.gate_pregame(df, {"2024": ["2024"], "2025_2026": ["2025"]})
    assert len(verdict.corpora) == 2
    labels = {c["corpus"] for c in verdict.corpora}
    assert labels == {"2024", "2025_2026"}


def test_gate_pregame_reports_tie_exclusion_honestly():
    df = _synthetic_corpus(n_per_season=150, tie_rate=0.05, seed=1)
    verdict = pg.gate_pregame(df, {"2024": ["2024"], "2025": ["2025"]})
    for c in verdict.corpora:
        assert c["n_ties_excluded"] > 0
        assert 0.0 < c["tie_rate"] < 0.15
        assert c["n_games"] > c["n_ties_excluded"]


def test_gate_pregame_calibration_baseline_ok_on_signal_rich_corpus():
    df = _synthetic_corpus(n_per_season=200, seed=2)
    verdict = pg.gate_pregame(df, {"2024": ["2024"], "2025": ["2025"]})
    assert verdict.verdict in ("CALIBRATION_BASELINE_OK", "PARTIAL")
    assert verdict.close_comparison == "PENDING_CLOSE_COMPARISON"


def test_gate_pregame_insufficient_data_on_tiny_corpus():
    df = _synthetic_corpus(n_per_season=5, seed=3)
    verdict = pg.gate_pregame(df, {"2024": ["2024"], "2025": ["2025"]})
    assert verdict.verdict == "INSUFFICIENT_DATA"


def test_gate_pregame_reject_on_pure_noise():
    """No team-strength signal at all -> Elo should not reliably beat
    baselines; verdict must not be CALIBRATION_BASELINE_OK."""
    rng = np.random.RandomState(7)
    teams = ["Giants", "Tigers", "Carp", "Dragons"]
    rows = []
    for season in ["2024", "2025"]:
        dates = pd.date_range(f"{season}-04-01", periods=100, freq="D")
        for i in range(100):
            home, away = rng.choice(teams, size=2, replace=False)
            hw = 1.0 if rng.random_sample() < 0.5 else 0.0
            rows.append({
                "date": dates[i], "season": season,
                "home_team": home, "away_team": away,
                "home_score": 3.0, "away_score": 2.0,
                "home_win": hw, "tied": False,
            })
    df = pd.DataFrame(rows)
    verdict = pg.gate_pregame(df, {"2024": ["2024"], "2025": ["2025"]})
    assert verdict.verdict != "CALIBRATION_BASELINE_OK"


def test_all_ties_corpus_is_insufficient_not_a_crash():
    """A corpus that is entirely tied games has zero decisive rows -- must
    degrade to INSUFFICIENT_DATA, never raise/NaN-propagate into a verdict."""
    rows = []
    dates = pd.date_range("2024-04-01", periods=25, freq="D")
    for i in range(25):
        rows.append({
            "date": dates[i], "season": "2024",
            "home_team": "Giants", "away_team": "Tigers",
            "home_score": 3.0, "away_score": 3.0,
            "home_win": np.nan, "tied": True,
        })
    df = pd.DataFrame(rows)
    verdict = pg.gate_pregame(df, {"2024": ["2024"]})
    assert verdict.verdict == "INSUFFICIENT_DATA"


def test_brier_logloss_ece_basic_properties():
    y = np.array([1.0, 0.0, 1.0, 0.0])
    p_perfect = np.array([1.0, 0.0, 1.0, 0.0])
    p_coin = np.full(4, 0.5)
    assert pg._brier(y, p_perfect) < pg._brier(y, p_coin)
    assert pg._logloss(y, p_perfect) < pg._logloss(y, p_coin)
    ece_perfect = pg._ece(y, p_perfect)
    assert ece_perfect >= 0.0


def test_ece_empty_array_is_nan():
    assert np.isnan(pg._ece(np.array([]), np.array([])))
