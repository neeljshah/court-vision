"""Tests for the MLB in-game re-pricer (domains/mlb/repricer.py).

Honest invariants only: the repricer is MACHINERY (no edge claimed). We assert
coherence — ML reacts correctly to lead + innings remaining, totals shrink as innings
run out, the final state is deterministic, probabilities sum to ~1, and the factory
routes 'mlb' to the real engine (no longer a stub).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.platformkit.live_repricer import GameState, Repricer, get_repricer
from domains.mlb.repricer import MLBRepricer

_PARAMS = {"lam_home": 4.6, "lam_away": 4.3}


def _state(innings: float, home: int, away: int) -> GameState:
    return GameState(sport="mlb", elapsed_minutes=0.0, home_score=home, away_score=away,
                     pregame_params=_PARAMS, extra={"innings_played": innings})


def test_factory_routes_mlb_to_real_engine():
    r = get_repricer("mlb")
    assert isinstance(r, MLBRepricer)
    assert isinstance(r, Repricer)
    out = r.reprice(_state(0.0, 0, 0))
    assert out.get("status") != "not_wired"


def test_ml_probs_sum_to_one():
    r = MLBRepricer()
    for inn, h, a in [(0.0, 0, 0), (5.0, 4, 1), (8.0, 3, 3), (9.0, 5, 2)]:
        out = r.reprice(_state(inn, h, a))
        assert out["ml_home"] + out["ml_away"] == pytest.approx(1.0, abs=1e-6)


def test_lead_boosts_home_win():
    """A 3-run lead with 3 innings left makes the home team a heavy favorite."""
    r = MLBRepricer()
    tied = r.reprice(_state(6.0, 2, 2))
    leading = r.reprice(_state(6.0, 5, 2))
    assert leading["ml_home"] > tied["ml_home"]
    assert leading["ml_home"] > 0.8


def test_totals_shrink_as_innings_run_out():
    """With few runs scored, over_8.5 collapses as innings remaining drops."""
    r = MLBRepricer()
    early = r.reprice(_state(2.0, 1, 1))   # 7 innings left
    late = r.reprice(_state(8.0, 1, 1))    # 1 inning left
    assert early["over_8.5"] > late["over_8.5"]
    assert late["over_8.5"] < 0.15


def test_final_state_deterministic():
    r = MLBRepricer()
    out = r.reprice(_state(9.0, 5, 2))
    assert out["ml_home"] == 1.0 and out["ml_away"] == 0.0
    assert out["over_8.5"] == 0.0      # 7 total runs < 8.5
    assert out["under_8.5"] == 1.0
    assert out["_innings_remaining"] == 0.0


def test_metadata_present():
    r = MLBRepricer()
    out = r.reprice(_state(4.0, 2, 1))
    for k in ("_sport", "_innings_remaining", "_current_score",
              "_lam_remaining_home", "_honest_note"):
        assert k in out
    assert out["_sport"] == "mlb"
    assert out["_current_score"] == (2, 1)
    assert "no edge" in out["_honest_note"].lower()


def test_run_line_coherent():
    """rl_home_minus15 + rl_away_plus15 == 1 and a big lead clears the -1.5 line."""
    r = MLBRepricer()
    out = r.reprice(_state(8.0, 6, 1))
    assert out["rl_home_minus15"] + out["rl_away_plus15"] == pytest.approx(1.0, abs=1e-6)
    assert out["rl_home_minus15"] > 0.9
