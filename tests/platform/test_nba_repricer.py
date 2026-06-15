"""Tests for the NBA in-game re-pricer (domains/basketball_nba/repricer.py).

Honest invariants only: machinery, no edge claimed. We assert coherence — win-prob
reacts to lead + time remaining, the distribution collapses onto the realized score as
the clock runs (score-anchor), the final state is deterministic, and win_home/win_away
sum to 1.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.platformkit.live_repricer import GameState, Repricer, get_repricer
from domains.basketball_nba.repricer import NBARepricer

_PARAMS = {"mu_home": 114.0, "mu_away": 112.0}


def _state(elapsed: float, home: int, away: int) -> GameState:
    return GameState(sport="nba", elapsed_minutes=elapsed, home_score=home,
                     away_score=away, pregame_params=_PARAMS)


def test_factory_routes_nba_to_real_engine():
    r = get_repricer("nba")
    assert isinstance(r, NBARepricer)
    assert isinstance(r, Repricer)
    assert r.reprice(_state(0.0, 0, 0)).get("status") != "not_wired"


def test_win_probs_sum_to_one():
    r = NBARepricer()
    for el, h, a in [(0.0, 0, 0), (24.0, 58, 50), (42.0, 98, 103), (48.0, 110, 104)]:
        out = r.reprice(_state(el, h, a))
        assert out["win_home"] + out["win_away"] == pytest.approx(1.0, abs=1e-9)


def test_lead_boosts_win_prob():
    r = NBARepricer()
    tied = r.reprice(_state(24.0, 55, 55))
    leading = r.reprice(_state(24.0, 63, 55))
    assert leading["win_home"] > tied["win_home"]
    assert leading["win_home"] > 0.75


def test_variance_collapses_as_clock_runs():
    """Score-anchor: the same 6-point lead is far more decisive late than early."""
    r = NBARepricer()
    early = r.reprice(_state(6.0, 18, 12))    # +6 early
    late = r.reprice(_state(45.0, 106, 100))  # +6 with ~3 min left
    assert late["win_home"] > early["win_home"]
    assert late["_margin_sd"] < early["_margin_sd"]   # uncertainty shrank


def test_final_state_deterministic():
    r = NBARepricer()
    out = r.reprice(_state(48.0, 110, 104))
    assert out["win_home"] == 1.0 and out["win_away"] == 0.0
    assert out["proj_margin_home"] == 6.0
    assert out["proj_total"] == 214.0
    assert out["_remaining_fraction"] == 0.0


def test_final_tie_is_coinflip_overtime():
    r = NBARepricer()
    out = r.reprice(_state(48.0, 100, 100))
    assert out["win_home"] == pytest.approx(0.5)


def test_metadata_and_projection_present():
    r = NBARepricer()
    out = r.reprice(_state(24.0, 58, 50))
    for k in ("_sport", "_remaining_fraction", "_current_score", "_margin_sd",
              "proj_margin_home", "proj_total", "_honest_note"):
        assert k in out
    assert out["_sport"] == "nba"
    assert out["_current_score"] == (58, 50)
    assert "no edge" in out["_honest_note"].lower()
