"""Tests for scripts.platformkit.live_repricer.

All tests use SYNTHETIC inputs; no corpus data required. Fast (<1s total).

Correctness anchors
-------------------
- elapsed=0  : remaining==full match; surface should ~match pregame scoreline_matrix.
- elapsed=90 : no remaining goals; final result is deterministic from current score.
- 1-0 at 80' : live home-win prob >> pregame home-win (lead + little time left).
- O/U live   : accounts for goals already in the scoreboard.
- BTTS live  : updates correctly given current score.
- Stub sports: return {'status': 'not_wired'} gracefully (no exception).
- Factory    : routes soccer -> SoccerRepricer, others -> stub.
"""
from __future__ import annotations

import math

import pytest

from scripts.platformkit.live_repricer import (
    GameState,
    Repricer,
    SoccerRepricer,
    _SportStub,
    get_repricer,
)
from domains.soccer.scoreline_engine import markets_from_matrix, scoreline_matrix


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_LAM_H = 1.5
_LAM_A = 1.1
_PREGAME = {"lam_home": _LAM_H, "lam_away": _LAM_A, "rho": 0.0}

_TOL = 0.02   # 2 pp tolerance for elapsed=0 vs pregame (floating-point/truncation)


def _state(elapsed: float, home: int, away: int, params: dict = _PREGAME) -> GameState:
    return GameState(
        sport="soccer",
        elapsed_minutes=elapsed,
        home_score=home,
        away_score=away,
        pregame_params=params,
    )


def _pregame_surface() -> dict:
    P = scoreline_matrix(_LAM_H, _LAM_A, rho=0.0)
    return markets_from_matrix(P)


# ---------------------------------------------------------------------------
# Test 1: elapsed=0 reproduces pregame surface within tolerance
# ---------------------------------------------------------------------------

def test_elapsed_zero_matches_pregame():
    """At kick-off (0 min elapsed) the re-pricer should match the pregame surface."""
    repricer = SoccerRepricer()
    live = repricer.reprice(_state(0.0, 0, 0))
    pre = _pregame_surface()

    assert abs(live["1X2_home"] - pre["1X2_home"]) < _TOL, (
        f"home-win diverges: live={live['1X2_home']:.4f} pre={pre['1X2_home']:.4f}"
    )
    assert abs(live["1X2_draw"] - pre["1X2_draw"]) < _TOL
    assert abs(live["1X2_away"] - pre["1X2_away"]) < _TOL
    assert abs(live["over_2.5"] - pre["over_2.5"]) < _TOL
    assert abs(live["btts_yes"] - pre["btts_yes"]) < _TOL


# ---------------------------------------------------------------------------
# Test 2: elapsed=90 collapses to current score (deterministic)
# ---------------------------------------------------------------------------

def test_elapsed_90_deterministic_home_win():
    """At full time with score 2-1, home win = 1.0."""
    repricer = SoccerRepricer()
    live = repricer.reprice(_state(90.0, 2, 1))

    assert live["1X2_home"] == pytest.approx(1.0)
    assert live["1X2_draw"] == pytest.approx(0.0)
    assert live["1X2_away"] == pytest.approx(0.0)
    assert live["btts_yes"] == pytest.approx(1.0)  # both scored


def test_elapsed_90_deterministic_draw():
    """At full time with score 1-1, draw = 1.0."""
    repricer = SoccerRepricer()
    live = repricer.reprice(_state(90.0, 1, 1))

    assert live["1X2_draw"] == pytest.approx(1.0)
    assert live["1X2_home"] == pytest.approx(0.0)


def test_elapsed_90_deterministic_nil_nil():
    """At full time 0-0, draw=1.0 and btts_no=1.0."""
    repricer = SoccerRepricer()
    live = repricer.reprice(_state(90.0, 0, 0))

    assert live["1X2_draw"] == pytest.approx(1.0)
    assert live["btts_no"] == pytest.approx(1.0)
    # over_2.5 must be 0 (0 goals total)
    assert live["over_2.5"] == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# Test 3: 1-0 lead at 80' — live home-win >> pregame home-win
# ---------------------------------------------------------------------------

def test_lead_at_80_boosts_home_win():
    """1-0 with 10 minutes left: live home-win prob >> pregame home-win."""
    repricer = SoccerRepricer()
    live = repricer.reprice(_state(80.0, 1, 0))
    pre = _pregame_surface()

    assert live["1X2_home"] > pre["1X2_home"] + 0.20, (
        f"Expected live home-win >> pregame; live={live['1X2_home']:.3f} "
        f"pre={pre['1X2_home']:.3f}"
    )
    assert live["1X2_home"] > 0.70, (
        f"1-0 at 80' should be heavily favoured; got {live['1X2_home']:.3f}"
    )


# ---------------------------------------------------------------------------
# Test 4: live O/U conditions on goals already scored
# ---------------------------------------------------------------------------

def test_over25_accounts_for_scored_goals():
    """With score already 2-0 at 70', over_2.5 should be > pregame over_2.5.

    2 goals are already in the scoreboard; over_2.5 = P(at least 1 more goal
    in remaining 20 min). lam_rem_total = (1.5+1.1)*(20/90) ≈ 0.578, so
    P(>=1 more) ≈ 1 - e^{-0.578} ≈ 0.44. That is BELOW pregame over_2.5 ~0.56
    because only 20 min remain — but it must still substantially exceed the
    probability that zero more goals are scored.
    """
    repricer = SoccerRepricer()
    live = repricer.reprice(_state(70.0, 2, 0))

    # P(at least 1 more goal in ~20 min) ≈ 1 - e^{-(1.5+1.1)*(20/90)} ≈ 0.44
    lam_rem_total = (_LAM_H + _LAM_A) * (20.0 / 90.0)
    expected_at_least_one = 1.0 - math.exp(-lam_rem_total)
    assert abs(live["over_2.5"] - expected_at_least_one) < 0.08, (
        f"over_2.5 with 2-0 at 70' should ≈ P(>=1 more goal); "
        f"live={live['over_2.5']:.4f} expected≈{expected_at_least_one:.4f}"
    )

    # Also check that under_2.5 is the complement
    assert abs(live["over_2.5"] + live["under_2.5"] - 1.0) < 1e-9


def test_over25_impossible_already_exceeded():
    """With score 3-1 at 60' (4 goals), over_2.5 must be 1.0."""
    repricer = SoccerRepricer()
    live = repricer.reprice(_state(60.0, 3, 1))

    assert live["over_2.5"] == pytest.approx(1.0), (
        f"4 goals already scored; over_2.5 must be 1.0; got {live['over_2.5']:.4f}"
    )


# ---------------------------------------------------------------------------
# Test 5: BTTS updates correctly
# ---------------------------------------------------------------------------

def test_btts_home_has_scored_away_hasnt():
    """1-0 at 45': BTTS-yes = P(away scores >= 1 in remaining 45 min)."""
    repricer = SoccerRepricer()
    live = repricer.reprice(_state(45.0, 1, 0))

    # lam_away_rem = 1.1 * 0.5 = 0.55; P(away>=1) = 1 - e^{-0.55} ≈ 0.423
    expected_approx = 1.0 - math.exp(-_LAM_A * 0.5)
    assert abs(live["btts_yes"] - expected_approx) < 0.05, (
        f"btts_yes diverges: live={live['btts_yes']:.4f} expected≈{expected_approx:.4f}"
    )
    assert live["btts_yes"] + live["btts_no"] == pytest.approx(1.0)


def test_btts_both_already_scored():
    """1-1 at 70': BTTS-yes = 1.0 (both already scored)."""
    repricer = SoccerRepricer()
    live = repricer.reprice(_state(70.0, 1, 1))

    assert live["btts_yes"] == pytest.approx(1.0)
    assert live["btts_no"] == pytest.approx(0.0)


def test_btts_impossible_almost_ft_nil_nil():
    """0-0 at 89': btts_yes should be tiny (almost no time left for 2 goals)."""
    repricer = SoccerRepricer()
    live = repricer.reprice(_state(89.0, 0, 0))

    # ~1 min left; very unlikely both sides score
    assert live["btts_yes"] < 0.05


# ---------------------------------------------------------------------------
# Test 6: stub sports return not_wired without crashing
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("sport", ["nba", "tennis", "mlb", "cricket", "rugby"])
def test_stub_sport_no_crash(sport: str):
    """Unwired sports return {'status': 'not_wired', ...} gracefully."""
    stub = _SportStub(sport)
    state = GameState(
        sport=sport,
        elapsed_minutes=20.0,
        home_score=1,
        away_score=0,
        pregame_params={},
    )
    result = stub.reprice(state)
    assert result["status"] == "not_wired"
    assert result["sport"] == sport
    assert "note" in result
    assert "not_wired" in result["status"]


# ---------------------------------------------------------------------------
# Test 7: factory routing
# ---------------------------------------------------------------------------

def test_factory_soccer_returns_soccer_repricer():
    """get_repricer('soccer') returns a SoccerRepricer."""
    r = get_repricer("soccer")
    assert isinstance(r, SoccerRepricer)


def test_factory_soccer_satisfies_protocol():
    """SoccerRepricer satisfies the Repricer protocol."""
    r = get_repricer("soccer")
    assert isinstance(r, Repricer)


@pytest.mark.parametrize("sport", ["cricket", "rugby"])
def test_factory_unwired_sport_returns_stub(sport: str):
    """get_repricer for unwired sports returns a stub that doesn't crash."""
    r = get_repricer(sport)
    state = GameState(
        sport=sport,
        elapsed_minutes=10.0,
        home_score=0,
        away_score=0,
    )
    result = r.reprice(state)
    assert result.get("status") == "not_wired"


# ---------------------------------------------------------------------------
# Test 8: metadata fields present on live surface
# ---------------------------------------------------------------------------

def test_metadata_keys_present():
    """Live surface includes _sport, _elapsed_minutes, _current_score, _honest_note."""
    repricer = SoccerRepricer()
    live = repricer.reprice(_state(70.0, 1, 0))

    for key in ("_sport", "_elapsed_minutes", "_current_score", "_remaining_minutes", "_honest_note"):
        assert key in live, f"Missing metadata key: {key}"

    assert live["_sport"] == "soccer"
    assert live["_elapsed_minutes"] == pytest.approx(70.0)
    assert live["_current_score"] == (1, 0)
    assert live["_remaining_minutes"] == pytest.approx(20.0)


# ---------------------------------------------------------------------------
# Test 9: 1X2 probabilities sum to 1.0 at any game state
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("elapsed,home,away", [
    (0.0, 0, 0),
    (45.0, 1, 0),
    (70.0, 2, 1),
    (85.0, 0, 0),
    (90.0, 3, 2),
])
def test_1x2_sums_to_one(elapsed, home, away):
    """1X2 probabilities always sum to 1.0."""
    repricer = SoccerRepricer()
    live = repricer.reprice(_state(elapsed, home, away))
    total = live["1X2_home"] + live["1X2_draw"] + live["1X2_away"]
    assert abs(total - 1.0) < 1e-9, f"1X2 sums to {total:.10f} at {elapsed}' {home}-{away}"
