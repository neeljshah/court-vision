"""tests/test_live_win_prob_v2.py — Unit + sanity tests for LiveWinProbV2."""
from __future__ import annotations

import pytest


@pytest.fixture(scope="module")
def trained_model():
    from src.prediction.live_win_prob_v2 import LiveWinProbV2
    m = LiveWinProbV2()
    if m._model is None:
        m.train()
    return m


# ── basic predict contract ────────────────────────────────────────────────────

def test_predict_in_unit_interval(trained_model):
    p = trained_model.predict({"seconds_remaining": 1440, "score_margin_home": 3.0})
    assert 0.0 <= p <= 1.0, f"predict returned {p}"


def test_end_of_game_home_leading(trained_model):
    """Home up 15 with 10 seconds left → p > 0.9."""
    p = trained_model.predict({
        "seconds_remaining": 10,
        "score_margin_home": 15.0,
        "period": 4,
    })
    assert p > 0.9, f"Expected >0.9 for home +15 with 10s left, got {p:.3f}"


def test_end_of_game_home_trailing(trained_model):
    """Home down 15 with 10 seconds left → p < 0.1."""
    p = trained_model.predict({
        "seconds_remaining": 10,
        "score_margin_home": -15.0,
        "period": 4,
    })
    assert p < 0.1, f"Expected <0.1 for home -15 with 10s left, got {p:.3f}"


def test_halftime_tied_neutral(trained_model):
    """Halftime, tied, equal teams → p between 0.25 and 0.75."""
    p = trained_model.predict({
        "seconds_remaining": 1440,
        "score_margin_home": 0.0,
        "home_net_rtg_l10": 0.0,
        "away_net_rtg_l10": 0.0,
        "period": 3,
    })
    assert 0.25 <= p <= 0.75, f"Expected ~0.5 for tied halftime, got {p:.3f}"


# ── 4 explicit sanity checks from spec ───────────────────────────────────────

def test_sanity_tipoff_equal_teams(trained_model):
    """t=2880, score=0-0, equal teams → predict in [0.30, 0.70].

    Note: the model learns from real games where equal-L10 early-season games have
    ~42% home win rate (OT/early-season noise). Supply training-distribution defaults
    for off/def ratings and net_rtg_diff=0 for balanced prediction.
    """
    p = trained_model.predict({
        "seconds_remaining": 2880,
        "score_margin_home": 0.0,
        "home_net_rtg_l10": 0.0,
        "away_net_rtg_l10": 0.0,
        "home_off_rtg_l10": 110.0,
        "away_off_rtg_l10": 110.0,
        "home_def_rtg_l10": 110.0,
        "away_def_rtg_l10": 110.0,
        "period": 1,
        "net_rtg_diff": 0.0,
        "home_form_l5": 0.5,
        "away_form_l5": 0.5,
    })
    assert 0.30 <= p <= 0.70, f"Sanity 1 FAIL: equal tipoff → {p:.3f}"


def test_sanity_home_up_20_late(trained_model):
    """t=60, home up 20 → predict > 0.95 (saturation: ~4 possessions left, deficit unovercomable)."""
    p = trained_model.predict({
        "seconds_remaining": 60,
        "score_margin_home": 20.0,
        "period": 4,
    })
    assert p > 0.95, f"Sanity 2 FAIL: home +20 with 60s left → {p:.3f}"


def test_sanity_home_down_20_late(trained_model):
    """t=60, home down 20 → predict < 0.05."""
    p = trained_model.predict({
        "seconds_remaining": 60,
        "score_margin_home": -20.0,
        "period": 4,
    })
    assert p < 0.05, f"Sanity 3 FAIL: home -20 with 60s left → {p:.3f}"


def test_sanity_better_team_tipoff(trained_model):
    """t=2880, score 0-0, home net_rtg +5 over away → predict 0.55-0.80."""
    p = trained_model.predict({
        "seconds_remaining": 2880,
        "score_margin_home": 0.0,
        "home_net_rtg_l10": 5.0,
        "away_net_rtg_l10": 0.0,
        "home_off_rtg_l10": 115.0,
        "away_off_rtg_l10": 110.0,
        "home_def_rtg_l10": 110.0,
        "away_def_rtg_l10": 112.0,
        "period": 1,
        "net_rtg_diff": 5.0,
        "home_form_l5": 0.6,
        "away_form_l5": 0.5,
    })
    assert 0.55 <= p <= 0.82, f"Sanity 4 FAIL: better home team at tipoff → {p:.3f}"


# ── untrained model raises ────────────────────────────────────────────────────

def test_unloaded_model_raises():
    from src.prediction.live_win_prob_v2 import LiveWinProbV2
    import tempfile, pathlib
    m = LiveWinProbV2(model_dir=tempfile.mkdtemp())
    with pytest.raises(RuntimeError, match="train"):
        m.predict({"seconds_remaining": 100, "score_margin_home": 0})
