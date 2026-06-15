"""Tests for the tennis in-game re-pricer (domains/tennis/repricer.py).

Honest invariants only: machinery, no edge claimed. We assert coherence — winning a set
raises match-win prob, best-of-5 amplifies a lead, decided states are deterministic, and
probabilities sum to 1. The model is the analytic race-to-N-sets conditional (Brier-graded).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.platformkit.live_repricer import GameState, Repricer, get_repricer
from domains.tennis.repricer import TennisRepricer, _race_win_prob


def _state(best_of: int, s1: int, s2: int, p_set: float = 0.55, **extra) -> GameState:
    return GameState(sport="tennis", elapsed_minutes=0.0, home_score=0, away_score=0,
                     pregame_params={"best_of": best_of, "p_set": p_set},
                     extra={"sets_1": s1, "sets_2": s2, **extra})


def test_factory_routes_tennis_to_real_engine():
    r = get_repricer("tennis")
    assert isinstance(r, TennisRepricer)
    assert isinstance(r, Repricer)
    assert r.reprice(_state(3, 0, 0)).get("status") != "not_wired"


def test_probs_sum_to_one():
    r = TennisRepricer()
    for bo, s1, s2 in [(3, 0, 0), (3, 1, 0), (5, 2, 1), (5, 1, 2)]:
        out = r.reprice(_state(bo, s1, s2))
        assert out["match_win_p1"] + out["match_win_p2"] == pytest.approx(1.0, abs=1e-9)


def test_winning_a_set_raises_match_prob():
    r = TennisRepricer()
    pregame = r.reprice(_state(3, 0, 0))["match_win_p1"]
    up = r.reprice(_state(3, 1, 0))["match_win_p1"]
    down = r.reprice(_state(3, 0, 1))["match_win_p1"]
    assert up > pregame > down


def test_best_of_5_amplifies_two_set_lead():
    r = TennisRepricer()
    out = r.reprice(_state(5, 2, 0))
    assert out["match_win_p1"] > 0.85
    assert out["_decided"] is False  # still needs a 3rd set


def test_decided_match_deterministic():
    r = TennisRepricer()
    won = r.reprice(_state(3, 2, 0))
    lost = r.reprice(_state(3, 0, 2))
    assert won["match_win_p1"] == 1.0 and won["_decided"] is True
    assert lost["match_win_p1"] == 0.0 and lost["_decided"] is True


def test_even_set_prob_pregame_is_half():
    r = TennisRepricer()
    out = r.reprice(_state(3, 0, 0, p_set=0.5))
    assert out["match_win_p1"] == pytest.approx(0.5, abs=1e-9)


def test_games_lean_is_bounded_and_directional():
    """An in-progress set game lead nudges, but never flips, the set probability."""
    r = TennisRepricer()
    base = r.reprice(_state(3, 0, 0, p_set=0.5))["match_win_p1"]
    ahead = r.reprice(_state(3, 0, 0, p_set=0.5, games_1=4, games_2=1))["match_win_p1"]
    behind = r.reprice(_state(3, 0, 0, p_set=0.5, games_1=1, games_2=4))["match_win_p1"]
    assert ahead > base > behind
    assert abs(ahead - base) < 0.1  # bounded lean

def test_race_win_prob_basic():
    # Even sets, race to 2 from level: should be 0.5.
    assert _race_win_prob(0.5, 2, 2) == pytest.approx(0.5, abs=1e-9)
    # Already need 0 -> certain win.
    assert _race_win_prob(0.4, 0, 2) == 1.0
