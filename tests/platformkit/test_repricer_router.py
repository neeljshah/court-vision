"""Per-file tests for the in-game REPRICER router (Milestone-6 spine).

Covers, with hand-built GameStates (NO network, NO corpus):
  * GOLDEN reprice: an early (Q1) vs late (Q4) state at the SAME lead ->
    repriced win-prob VARIANCE SHRINKS (Q1 wide -> Q4 tight) -- the validated
    freshness invariant;
  * repriced probs move TOWARD the realized state late (a home lead late pushes
    p_home above the pregame prior and above its own early-game value);
  * the unavailable path is clean (unknown sport / missing prior -> available
    False, no raise), and EDGE_CLAIMED is False everywhere.

Run (per-file ONLY -- a full pytest freezes this box):
  cd /c/Users/neelj/nba-ai-system && \
    python -m pytest tests/platformkit/test_repricer_router.py -q
"""
from __future__ import annotations

from scripts.platformkit.ingame import repricer_router as rr
from scripts.platformkit.ingame.state_bus import GameState

# 12-min NBA quarters -> period_len_sec lets fraction_elapsed derive from the clock.
_PERIOD_LEN = 720.0


def _state(period, clock_sec, home, away):
    """A live NBA GameState with enough info for fraction_elapsed()."""
    return GameState(
        sport="nba", game_id="G1", period=period, clock_sec=clock_sec,
        home_score=home, away_score=away, status="live",
        extras={"period_len_sec": _PERIOD_LEN},
    )


# A near-even pregame prior so the live lead is what moves the number.
_PRIOR = {"p0": 0.50, "variance": 0.25, "regulation_min": 48.0,
          "pregame_params": {"mu_home": 113.0, "mu_away": 113.0}}


def _early_late_same_lead(lead=8):
    """Q1 (lots of time left) and Q4 (little time left) at the SAME home lead."""
    # Q1, 6:00 left in the quarter -> ~ frac elapsed 0.125.
    early = _state(period=1, clock_sec=360.0, home=20 + lead, away=20)
    # Q4, 2:00 left -> ~ frac elapsed 0.96.
    late = _state(period=4, clock_sec=120.0, home=90 + lead, away=90)
    return early, late


def test_variance_shrinks_q1_to_q4():
    """FRESHNESS invariant: same lead, Q1 variance > Q4 variance (wide -> tight)."""
    early, late = _early_late_same_lead(lead=8)
    re = rr.reprice("nba", early, _PRIOR)
    rl = rr.reprice("nba", late, _PRIOR)
    assert re["available"] and rl["available"]
    assert re["variance"] is not None and rl["variance"] is not None
    # Q1 distribution is WIDE, Q4 is TIGHT for the same realized lead.
    assert re["variance"] > rl["variance"], (re["variance"], rl["variance"])
    # remaining_frac is monotone-decreasing in elapsed time.
    assert re["remaining_frac"] > rl["remaining_frac"]


def test_probs_move_toward_realized_state_late():
    """Late, a home lead pulls p_home ABOVE the pregame prior and above its own
    early value -- the live state dominates late (validated freshness shape)."""
    early, late = _early_late_same_lead(lead=8)
    re = rr.reprice("nba", early, _PRIOR)
    rl = rr.reprice("nba", late, _PRIOR)
    p0 = _PRIOR["p0"]
    # Home is leading; the blended number should favor home, more so late.
    assert rl["probs"]["p_home"] > p0
    assert rl["probs"]["p_home"] > re["probs"]["p_home"]
    # The blend weight w (trust-in-live) rises Q1 -> Q4.
    assert rl["probs"]["w"] >= re["probs"]["w"]
    # p_live (realized-state anchor) is also more confident late.
    assert rl["probs"]["p_live"] > re["probs"]["p_live"]


def test_trailing_home_pulls_prob_down_late():
    """Symmetry: a home DEFICIT late pulls p_home below the prior."""
    late_down = _state(period=4, clock_sec=120.0, home=90, away=90 + 8)
    r = rr.reprice("nba", late_down, _PRIOR)
    assert r["available"]
    assert r["probs"]["p_home"] < _PRIOR["p0"]


def test_per_market_surface_present():
    """The composed per-market repriced surface comes through with prob/value rows."""
    _, late = _early_late_same_lead(lead=8)
    r = rr.reprice("nba", late, _PRIOR)
    assert isinstance(r["markets"], list)
    # NBARepricer emits win_home plus spread/total markets.
    keys = {m["market"] for m in r["markets"]}
    assert "win_home" in keys
    for m in r["markets"]:
        assert ("prob" in m) or ("value" in m)


def test_unknown_sport_clean_unavailable():
    """Unknown sport -> clean unavailable result, no raise, no fabricated number."""
    _, late = _early_late_same_lead()
    r = rr.reprice("quidditch", late, _PRIOR)
    assert r["available"] is False
    assert r["probs"] == {} and r["markets"] == []
    assert r["variance"] is None
    assert r["edge_claimed"] is False


def test_missing_prior_clean_unavailable():
    """Missing / prior-without-winprob -> clean unavailable, never raises."""
    _, late = _early_late_same_lead()
    assert rr.reprice("nba", late, None)["available"] is False
    assert rr.reprice("nba", late, {})["available"] is False
    # A prior with no p0/win_home is unavailable (no fabricated win-prob).
    r = rr.reprice("nba", late, {"pregame_params": {}})
    assert r["available"] is False


def test_alias_sport_routes_to_nba():
    """basketball_nba alias resolves to the nba seed surface."""
    _, late = _early_late_same_lead(lead=8)
    r = rr.reprice("basketball_nba", late, _PRIOR)
    assert r["available"] and r["sport"] == "nba"


def test_no_edge_claimed_anywhere():
    """EDGE_CLAIMED is False on the module and in every emitted dict."""
    assert rr.EDGE_CLAIMED is False
    _, late = _early_late_same_lead()
    assert rr.reprice("nba", late, _PRIOR)["edge_claimed"] is False
    assert rr.reprice("nope", late, _PRIOR)["edge_claimed"] is False
