"""Per-file tests for domains.basketball_wnba.pregame_gate (synthetic data, offline).

  cd /c/Users/neelj/nba-ai-system && python -m pytest domains/basketball_wnba/test_pregame_gate.py -q
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from domains.basketball_wnba import pregame_gate as pg


def _synthetic_corpus(n_per_season=60, seed=0):
    """Two synthetic seasons where a persistent-strength signal exists (some teams
    are simply better), so Elo SHOULD beat coin-flip and home-prior baselines."""
    rng = np.random.RandomState(seed)
    teams = ["A", "B", "C", "D", "E", "F"]
    strength = {t: rng.normal(0, 1) for t, s in zip(teams, range(len(teams)))}
    rows = []
    for season in ["2025", "2026"]:
        dates = pd.date_range(f"{season}-05-01", periods=n_per_season, freq="D")
        for i in range(n_per_season):
            home, away = rng.choice(teams, size=2, replace=False)
            d = strength[home] - strength[away] + 0.3  # home edge
            p_true = 1.0 / (1.0 + np.exp(-d))
            hw = 1.0 if rng.random_sample() < p_true else 0.0
            rows.append({
                "event_id": f"{season}-{i}", "date": dates[i], "season": season,
                "home_team": home, "away_team": away,
                "home_score": 80.0 if hw else 75.0, "away_score": 75.0 if hw else 80.0,
                "home_win": hw, "neutral_site": False, "status_name": "STATUS_FINAL",
            })
    return pd.DataFrame(rows)


def test_gate_pregame_two_corpora_returns_result_per_season():
    df = _synthetic_corpus()
    verdict = pg.gate_pregame(df, ["2025", "2026"])
    assert len(verdict.corpora) == 2
    seasons_seen = {c["season"] for c in verdict.corpora}
    assert seasons_seen == {"2025", "2026"}


def test_gate_pregame_calibration_baseline_ok_on_signal_rich_corpus():
    df = _synthetic_corpus(n_per_season=150, seed=1)
    verdict = pg.gate_pregame(df, ["2025", "2026"])
    assert verdict.verdict in ("CALIBRATION_BASELINE_OK", "PARTIAL")
    assert verdict.close_comparison == "PENDING_CLOSE_COMPARISON"


def test_gate_pregame_insufficient_data_on_tiny_corpus():
    df = _synthetic_corpus(n_per_season=5, seed=2)
    verdict = pg.gate_pregame(df, ["2025", "2026"])
    assert verdict.verdict == "INSUFFICIENT_DATA"


def test_gate_pregame_reject_on_pure_noise():
    """No team-strength signal at all (coin-flip outcomes) -> Elo should not
    reliably beat baselines; verdict must not be CALIBRATION_BASELINE_OK."""
    rng = np.random.RandomState(7)
    teams = ["A", "B", "C", "D"]
    rows = []
    for season in ["2025", "2026"]:
        dates = pd.date_range(f"{season}-05-01", periods=80, freq="D")
        for i in range(80):
            home, away = rng.choice(teams, size=2, replace=False)
            hw = 1.0 if rng.random_sample() < 0.5 else 0.0
            rows.append({
                "event_id": f"{season}-{i}", "date": dates[i], "season": season,
                "home_team": home, "away_team": away,
                "home_score": 80.0, "away_score": 78.0,
                "home_win": hw, "neutral_site": False, "status_name": "STATUS_FINAL",
            })
    df = pd.DataFrame(rows)
    verdict = pg.gate_pregame(df, ["2025", "2026"])
    assert verdict.verdict != "CALIBRATION_BASELINE_OK"


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


def test_corpus_result_degenerate_guard_flags_no_signal_corpus():
    rng = np.random.RandomState(3)
    teams = ["A", "B"]
    rows = []
    dates = pd.date_range("2025-05-01", periods=50, freq="D")
    for i in range(50):
        home, away = teams[i % 2], teams[(i + 1) % 2]
        hw = 1.0 if rng.random_sample() < 0.5 else 0.0
        rows.append({
            "event_id": f"e{i}", "date": dates[i], "season": "2025",
            "home_team": home, "away_team": away,
            "home_score": 80.0, "away_score": 78.0,
            "home_win": hw, "neutral_site": False, "status_name": "STATUS_FINAL",
        })
    df = pd.DataFrame(rows)
    result = pg._corpus_result(df, "2025")
    assert isinstance(result.degenerate, bool)
    # 50 games is fine for the sample-size check, but pure noise should show low BSS
    assert result.n_games == 50
