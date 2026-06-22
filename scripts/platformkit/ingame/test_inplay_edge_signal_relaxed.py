"""Per-file test: scripts/platformkit/ingame/test_inplay_edge_signal_relaxed.py
Run: python -m pytest scripts/platformkit/ingame/test_inplay_edge_signal_relaxed.py -q

Covers the OPT-IN relaxed in-game EV floor (min_ev) added so live WC in-game positions can
surface on a smaller model-vs-market divergence than the strict pre-registered policy floor.
Default (min_ev=None) is byte-identical to the strict floor. A relaxed bet is a LOWER-
CONFIDENCE, honestly-CLV-graded paper bet (reason='ok_relaxed'), never an edge claim.
"""
from __future__ import annotations

from scripts.platformkit.ingame import inplay_edge_signal as sig

_BASE = dict(yes_home_prob=0.55, yes_away_prob=0.49,
             calibration_justified=True, is_liquid=True)


def test_min_ev_none_is_strict_default():
    # ev ~ 2.83% (below the proxy floor 0.03): strict -> no_bet
    out = sig.evaluate(model_prob=0.545, **_BASE)
    assert out["action"] == "no_bet" and out["reason"] == "below_floor"
    assert out.get("relaxed_floor") is False


def test_relaxed_floor_surfaces_marginal_edge():
    out = sig.evaluate(model_prob=0.545, min_ev=0.01, **_BASE)
    assert out["action"] == "bet"
    assert out["tier"] == "C"               # marginal tier
    assert out["reason"] == "ok_relaxed"    # clearly flagged as relaxed, not a strict edge
    assert out["relaxed_floor"] is True


def test_relaxed_floor_still_requires_positive_edge():
    # model == market -> ev ~ 0 -> NO bet even with a relaxed floor (never bets noise<=0)
    out = sig.evaluate(model_prob=0.50, min_ev=0.0, **_BASE)
    assert out["action"] == "no_bet" and out["reason"] == "below_floor"


def test_relaxed_floor_does_not_override_gates():
    # not calibration-justified -> no bet regardless of a relaxed floor
    out = sig.evaluate(model_prob=0.545, min_ev=0.01,
                       yes_home_prob=0.55, yes_away_prob=0.49,
                       calibration_justified=False, is_liquid=True)
    assert out["action"] == "no_bet" and out["reason"] == "not_calibration_justified"
    # illiquid -> no bet
    out2 = sig.evaluate(model_prob=0.545, min_ev=0.01,
                        yes_home_prob=0.55, yes_away_prob=0.49,
                        calibration_justified=True, is_liquid=False)
    assert out2["action"] == "no_bet" and out2["reason"] == "illiquid"


def test_strict_edge_still_bets_ok_not_relaxed():
    out = sig.evaluate(model_prob=0.56, min_ev=0.01, **_BASE)
    assert out["action"] == "bet" and out["reason"] == "ok"
    assert out["relaxed_floor"] is False
