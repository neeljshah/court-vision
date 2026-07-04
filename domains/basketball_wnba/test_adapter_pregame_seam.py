"""Per-file tests for WNBAAdapter.predict / predict_live_state (LANE 2: the
pregame-paper-seam surface added so predictor_jd/predict_matchup/bet_board can
drive WNBA without any new model logic -- both delegate to the existing,
already-tested baseline_probability/predict_live).

Synthetic data only -- no network, no real corpus dependency.

Run: cd /c/Users/neelj/nba-ai-system && python -m pytest domains/basketball_wnba/test_adapter_pregame_seam.py -q
"""
from __future__ import annotations

import datetime as dt

import pandas as pd
import pytest

from domains.basketball_wnba.adapter import WNBAAdapter, SPORT_ID


def _synthetic_games() -> pd.DataFrame:
    rows = []
    for i in range(12):
        rows.append({
            "event_id": str(i), "date": pd.Timestamp("2024-05-03") + pd.Timedelta(days=i),
            "season": "2024", "home_team": "Aces", "away_team": "Fever",
            "home_score": 85.0 + i, "away_score": 78.0,
            "home_win": 1.0, "neutral_site": False, "status_name": "STATUS_FINAL",
        })
    return pd.DataFrame(rows)


def _adapter() -> WNBAAdapter:
    return WNBAAdapter(games_df=_synthetic_games())


# ---------------------------------------------------------------------------
# predict() -- moneyline-only pregame view
# ---------------------------------------------------------------------------
def test_predict_shape_and_reciprocal_probs(monkeypatch):
    a = _adapter()
    # Freeze "now" isn't needed: with only 2024 games, any real as_of after them
    # yields a stable Elo state; just assert the contract.
    out = a.predict("Aces", "Fever")
    assert out["sport"] == SPORT_ID
    assert out["home"] == "Aces" and out["away"] == "Fever"
    assert 0.0 <= out["p_home_win"] <= 1.0
    assert out["p_away_win"] == pytest.approx(1.0 - out["p_home_win"], abs=1e-9)
    assert "Elo" in out["honest_note"]
    assert "no $ edge" in out["honest_note"].lower() or "no \\$ edge" in out["honest_note"].lower() \
        or "edge" in out["honest_note"].lower()


def test_predict_matches_baseline_probability_directly():
    a = _adapter()
    now = dt.datetime.now(dt.timezone.utc)
    p0 = a.baseline_probability({"meta": {"home_team": "Aces", "away_team": "Fever"}}, now)
    out = a.predict("Aces", "Fever")
    # both computed "as of now" -- Elo state is static (games all in the past),
    # so these should agree tightly.
    assert out["p_home_win"] == pytest.approx(p0, abs=1e-3)


def test_predict_unknown_teams_defaults_to_elo_mean_prob():
    # Two unrated teams both fall back to ELO_MEAN; the only asymmetry left is
    # home-field advantage (ELO_HFA), so home is favored but not by much.
    a = _adapter()
    out = a.predict("Unknown Team A", "Unknown Team B")
    assert 0.5 < out["p_home_win"] < 0.65


# ---------------------------------------------------------------------------
# predict_live_state() -- generic elapsed_minutes/home_score/away_score shape
# ---------------------------------------------------------------------------
def test_predict_live_state_tipoff_matches_pregame():
    a = _adapter()
    out = a.predict_live_state("Aces", "Fever", elapsed_minutes=0.0,
                               home_score=0, away_score=0)
    p0 = out["pregame_p_home"]
    assert out["p_home_win"] == pytest.approx(p0, abs=1e-3)
    assert out["period"] == 1


def test_predict_live_state_buzzer_at_40_minutes_decided():
    a = _adapter()
    out = a.predict_live_state("Aces", "Fever", elapsed_minutes=40.0,
                               home_score=90, away_score=80)
    assert out["period"] == 4
    assert out["p_home_win"] == 1.0
    assert out["p_away_win"] == 0.0


def test_predict_live_state_mid_third_quarter_period_and_clock():
    a = _adapter()
    out = a.predict_live_state("Aces", "Fever", elapsed_minutes=25.0,
                               home_score=60, away_score=55)
    assert out["period"] == 3
    assert 0.0 <= out["p_home_win"] <= 1.0


def test_predict_live_state_clamps_out_of_range_elapsed():
    a = _adapter()
    out_neg = a.predict_live_state("Aces", "Fever", elapsed_minutes=-5.0,
                                   home_score=0, away_score=0)
    out_over = a.predict_live_state("Aces", "Fever", elapsed_minutes=999.0,
                                    home_score=90, away_score=70)
    assert out_neg["period"] == 1
    assert out_over["period"] == 4
    assert out_over["p_home_win"] == 1.0  # clamped to the buzzer boundary


def test_predict_live_state_does_not_shadow_existing_predict_live_signature():
    """predict_live keeps its original (as_of, period, clock_s, ...) signature --
    the new method is additive, never a breaking overload."""
    a = _adapter()
    as_of = dt.datetime(2025, 1, 1)
    out = a.predict_live("Aces", "Fever", as_of, period=2, clock_s=300,
                         home_score=40, away_score=38)
    assert out["sport"] == SPORT_ID
