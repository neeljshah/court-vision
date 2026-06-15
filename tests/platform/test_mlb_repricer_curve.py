"""Per-file test for the MLB in-game repricer per-inning run curve (domains/mlb/repricer.py).

The per-inning curve (early innings score more, 8th/9th less) makes a sharper in-game
forecaster than flat (9-n)/9 scaling. Prediction-quality test; a live book also sees the
score so this is forecaster quality, not a price edge.

Run: python -m pytest tests/platform/test_mlb_repricer_curve.py -q
"""
from __future__ import annotations

import pytest

from domains.mlb.repricer import _INNING_SHARES, _remaining_frac, MLBRepricer


class _State:
    def __init__(self, h, a, innings, homogeneous=False):
        self.sport = "mlb"
        self.elapsed_minutes = 0.0
        self.home_score = h
        self.away_score = a
        self.pregame_params = {"lam_home": 4.5, "lam_away": 4.5}
        self.extra = {"innings_played": float(innings)}
        if homogeneous:
            self.extra["homogeneous_frac"] = True


def test_curve_endpoints():
    assert _remaining_frac(0) == pytest.approx(1.0, abs=1e-9)
    assert _remaining_frac(9) == 0.0
    assert _remaining_frac(12) == 0.0


def test_curve_below_homogeneous_late_and_early():
    # 1st inning scores most + 8th/9th least => after any played inning, the curve leaves
    # LESS expected scoring than flat scaling once the high-scoring 1st is already gone.
    for n in (1, 3, 5, 7, 8):
        assert _remaining_frac(n) < _remaining_frac(n, homogeneous=True) + 1e-9
    # late game the gap is real (8th/9th are the lowest-scoring innings)
    assert _remaining_frac(7, homogeneous=True) - _remaining_frac(7) > 0.01


def test_shares_are_a_distribution():
    assert len(_INNING_SHARES) == 9
    assert abs(sum(_INNING_SHARES) - 1.0) < 0.02   # empirical shares ~sum to 1
    assert _INNING_SHARES[0] == max(_INNING_SHARES)   # 1st inning highest
    assert _INNING_SHARES[8] == min(_INNING_SHARES)   # 9th inning lowest


def test_repricer_curve_lowers_remaining_lambda_vs_homogeneous():
    rep = MLBRepricer()
    out_curve = rep.reprice(_State(2, 1, 7))
    out_homo = rep.reprice(_State(2, 1, 7, homogeneous=True))
    lam_curve = out_curve["_lam_remaining_home"] + out_curve["_lam_remaining_away"]
    lam_homo = out_homo["_lam_remaining_home"] + out_homo["_lam_remaining_away"]
    assert lam_curve < lam_homo          # curve leaves less late-game scoring
    # both still produce a coherent moneyline
    assert 0.0 <= out_curve["ml_home"] <= 1.0
    assert out_curve["ml_home"] + out_curve["ml_away"] == pytest.approx(1.0, abs=1e-6)
