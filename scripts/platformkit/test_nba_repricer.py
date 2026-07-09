"""scripts.platformkit.test_nba_repricer — per-file test for the NBA live re-pricer.

Verifies the Gaussian score-anchor remaining-points model used for NBA in-game
re-pricing (domains.basketball_nba.repricer.NBARepricer, returned by
live_repricer.get_repricer("nba")):

  * elapsed=0 degrades gracefully to the pregame prior (win-prob == the pregame
    margin prior; proj_total == the pregame total mean);
  * a big lead late pushes win-prob toward the leader and the score anchor
    dominates the projection;
  * projected total scales sensibly with elapsed + observed score;
  * monotonicity: more margin -> higher home win-prob, more time elapsed with a
    fixed lead -> higher win-prob for the leader;
  * the final-buzzer surface converges to the realized outcome;
  * the return dict carries exactly the keys predict_live() consumes
    (win_home, proj_total, proj_margin_home) so predict_matchup is unchanged.

HONEST: this tests CALIBRATION/coherence machinery only. No $ edge is asserted or
implied. Run ONLY this file (full pytest freezes the box):
    python -m pytest scripts/platformkit/test_nba_repricer.py -q
"""
from __future__ import annotations

import math

from scripts.platformkit.live_repricer import GameState, get_repricer

_FULL = 48.0
_PP = {"mu_home": 116.0, "mu_away": 110.0, "margin_sigma": 13.5, "total_sigma": 18.0}


def _phi(z: float) -> float:
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def _reprice(elapsed: float, h: int, a: int, pp=None):
    return get_repricer("nba").reprice(
        GameState("nba", elapsed, h, a, pregame_params=pp or _PP)
    )


def test_factory_returns_real_repricer():
    rep = get_repricer("nba")
    assert type(rep).__name__ == "NBARepricer"
    out = _reprice(0.0, 0, 0)
    # NOT the not-wired stub
    assert "status" not in out
    assert out.get("_sport") == "nba"


def test_return_dict_has_keys_predict_live_consumes():
    out = _reprice(24.0, 60, 55)
    for k in ("win_home", "win_away", "proj_total", "proj_margin_home"):
        assert k in out, f"missing key {k} that predict_live() reads"
    assert abs((out["win_home"] + out["win_away"]) - 1.0) < 1e-9


def test_elapsed_zero_equals_pregame_prior():
    """At tip-off the repricer must return the pregame number, not drift from it."""
    out = _reprice(0.0, 0, 0)
    # pregame margin mean = mu_home - mu_away = 6.0; sigma = 13.5
    expected_win = _phi((_PP["mu_home"] - _PP["mu_away"]) / _PP["margin_sigma"])
    assert abs(out["win_home"] - expected_win) < 1e-6
    # pregame total mean = mu_home + mu_away = 226.0
    assert abs(out["proj_total"] - (_PP["mu_home"] + _PP["mu_away"])) < 1e-6
    assert abs(out["proj_margin_home"]
               - (_PP["mu_home"] - _PP["mu_away"])) < 1e-6


def test_big_lead_late_pushes_winprob_toward_leader():
    home_big = _reprice(45.0, 112, 90)   # +22, 3 min left
    away_big = _reprice(45.0, 90, 112)   # -22, 3 min left
    assert home_big["win_home"] > 0.98
    assert away_big["win_home"] < 0.02
    # same magnitude lead -> symmetric (allowing the small pregame tilt)
    assert home_big["win_home"] + away_big["win_home"] == \
        2.0 or abs((home_big["win_home"]) - (1.0 - away_big["win_home"])) < 0.05


def test_winprob_monotonic_in_margin():
    """More home margin at a fixed clock -> strictly higher home win-prob."""
    ps = [_reprice(24.0, 50 + d, 50)["win_home"] for d in (-15, -5, 0, 5, 15)]
    assert all(ps[i] < ps[i + 1] for i in range(len(ps) - 1))


def test_winprob_monotonic_in_time_with_fixed_lead():
    """A fixed lead becomes more decisive as the clock runs (variance collapses)."""
    lead = [_reprice(e, 60, 52)["win_home"] for e in (6.0, 24.0, 36.0, 46.0)]
    assert all(lead[i] <= lead[i + 1] + 1e-9 for i in range(len(lead) - 1))
    assert lead[-1] > lead[0]


def test_proj_total_scales_with_elapsed_and_score():
    """proj_total = observed + remaining_fraction * pregame_total; anchors to the
    realized score as the clock runs out."""
    rem6 = (_FULL - 6.0) / _FULL
    rem46 = (_FULL - 46.0) / _FULL
    pre_total = _PP["mu_home"] + _PP["mu_away"]  # 226.0
    early = _reprice(6.0, 30, 28)["proj_total"]
    late = _reprice(46.0, 118, 110)["proj_total"]
    # exact model: observed + remaining-fraction * pregame expectation
    assert abs(early - (58.0 + rem6 * pre_total)) < 1e-6
    # late: almost entirely the realized 228, only a sliver of pregame left
    assert abs(late - (228.0 + rem46 * pre_total)) < 1e-6
    assert late > 228.0 and (late - 228.0) < 12.0  # little time -> small add
    # a faster-scoring game at the same clock projects a higher total than a slow one
    fast = _reprice(36.0, 100, 96)["proj_total"]
    slow = _reprice(36.0, 70, 66)["proj_total"]
    assert fast > slow
    # and the gap equals the observed-score gap (same remaining expectation added)
    assert abs((fast - slow) - ((196.0) - (136.0))) < 1e-6


def test_final_buzzer_converges_to_realized_outcome():
    out_home = _reprice(48.0, 105, 99)
    assert out_home["win_home"] == 1.0
    assert out_home["proj_total"] == 204.0
    assert out_home["proj_margin_home"] == 6.0
    out_away = _reprice(48.0, 99, 105)
    assert out_away["win_home"] == 0.0
    # tie at the buzzer -> overtime, marked 0.5 (not a claim, just neutral)
    out_tie = _reprice(48.0, 100, 100)
    assert out_tie["win_home"] == 0.5


def test_overtime_no_longer_degenerate():
    """OT defect fix: elapsed>48 (period>4) used to clamp rem_frac to 0, degenerating
    the price to current-score-sign. It must now use time left in the current
    5-minute OT period, keeping the anchor a shrinking-but-nonzero-variance draw."""
    pickem = {"mu_home": 113.0, "mu_away": 113.0, "margin_sigma": 13.5, "total_sigma": 18.0}
    ot_start = _reprice(48.0001, 100, 100, pickem)  # tied at the buzzer -> OT tips off
    assert ot_start["_remaining_fraction"] > 0.0
    assert abs(ot_start["win_home"] - 0.5) < 1e-9  # pick'em + tied -> exact coinflip
    deep_ot = _reprice(52.5, 100, 100, pickem)  # 0.5 min left in OT1
    assert deep_ot["_remaining_fraction"] < ot_start["_remaining_fraction"]


def test_no_edge_is_claimed():
    out = _reprice(24.0, 60, 55)
    note = str(out.get("_honest_note", "")).lower()
    assert "no edge" in note
