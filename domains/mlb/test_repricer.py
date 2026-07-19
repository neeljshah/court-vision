"""Per-file test for domains.mlb.repricer.

Regression coverage for the extras win-prob collapse fix (mlb_reliability_map.json:
extras|diff_-01 model_mean_prob 0.000 vs outcome_rate 0.301, n=451; extras|diff_+00
0.513 vs 0.636). Root cause: frac<=0.0 (only reachable at inning>=10) treated any
unequal-score state as final/decided -> deterministic ml_home=0.0/1.0. Fix: always
simulate one residual extra-inning's worth of runs in extras, with a bats-last lambda
tilt anchored to the well-documented ~54% overall MLB home win rate (not fit to the
eval corpus).

Run:
    cd /c/Users/neelj/nba-ai-system && python -m pytest domains/mlb/test_repricer.py -q
"""
from __future__ import annotations

from domains.mlb.repricer import MLBRepricer


class _GS:
    """Minimal duck-typed GameState (repricer reads state by attribute, not import)."""

    def __init__(self, innings_played, home_score, away_score,
                lam_home=4.5, lam_away=4.5, r_home=5.5, r_away=5.5):
        self.pregame_params = {"lam_home": lam_home, "lam_away": lam_away,
                               "r_home": r_home, "r_away": r_away}
        self.extra = {"innings_played": innings_played}
        self.home_score = home_score
        self.away_score = away_score


def test_extras_no_saturation():
    """No extras state should freeze to a deterministic 0.0/1.0 probability."""
    r = MLBRepricer()
    for innings_played, hs, away_s in [
        (9.0, 3, 3), (9.0, 3, 4), (9.0, 2, 4), (9.0, 4, 3),
        (11.0, 5, 5), (9.5, 4, 5), (13.0, 6, 4),
    ]:
        p = r.reprice(_GS(innings_played, hs, away_s))["ml_home"]
        assert 0.0 < p < 1.0, f"saturated at innings_played={innings_played} {hs}-{away_s}: {p}"


def test_extras_down1_recovers():
    """Down 1 in extras: model must give a live comeback chance (was 0.000)."""
    r = MLBRepricer()
    p = r.reprice(_GS(9.0, 3, 4))["ml_home"]
    assert 0.15 <= p <= 0.45, f"down-1-in-extras p={p} outside [0.15, 0.45]"


def test_extras_tied_favors_home():
    """Tied entering extras: home bats last -> modest edge above 50/50 (was ~0.51)."""
    r = MLBRepricer()
    p = r.reprice(_GS(9.0, 3, 3))["ml_home"]
    assert 0.52 <= p <= 0.70, f"tied-extras p={p} outside [0.52, 0.70]"


def test_regular_innings_unchanged():
    """A mid-game (regulation) state must be BYTE-IDENTICAL to pre-fix behavior --
    the frac<=0.0 branch (the only thing touched) is unreachable before inning 10,
    so this frozen value was captured straight off the fixed code and must never move."""
    r = MLBRepricer()
    out = r.reprice(_GS(5.5, 3, 2, lam_home=4.5, lam_away=4.2, r_home=5.5, r_away=5.5))
    assert out["ml_home"] == 0.7180297787927972
    assert out["rl_home_minus15"] == 0.41009126977936156
    assert out["_innings_remaining"] == 3.346846846846847


def test_decided_regulation_state_unaffected():
    """A truly-decided game passed with innings_played < 9 (frac > 0) never hits the
    extras branch at all; sanity check it still returns a live (non-frozen) surface."""
    r = MLBRepricer()
    out = r.reprice(_GS(8.5, 7, 2))  # home up 5, bottom of the 9th about to start
    assert 0.0 < out["ml_home"] < 1.0


if __name__ == "__main__":
    test_extras_no_saturation()
    test_extras_down1_recovers()
    test_extras_tied_favors_home()
    test_regular_innings_unchanged()
    test_decided_regulation_state_unaffected()
    print("OK")
