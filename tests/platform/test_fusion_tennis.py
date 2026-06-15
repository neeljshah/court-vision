"""tests.platform.test_fusion_tennis — offline tests for the ATP complementary fusion.

Synthetic ONLY: no real parquet, no heavy walk-forward. Verifies the load-bearing
plumbing + verdict classification of scripts.platformkit.proof_tennis.fusion_tennis:

  1. _brier_logloss / _ece return sane values on known inputs.
  2. _devig_market devigs Pinnacle odds to a P(p1) in (0,1) and dedups event_id.
  3. _fit_logistic standardises and returns a fitted classifier whose probs separate.
  4. _logit / clip round-trip is finite at the extremes (no inf leak into the gate).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

import scripts.platformkit.proof_tennis.fusion_tennis as mod


def test_brier_logloss_perfect_vs_coinflip() -> None:
    y = np.array([1.0, 0.0, 1.0, 0.0])
    b_good, ll_good = mod._brier_logloss(np.array([0.99, 0.01, 0.99, 0.01]), y)
    b_flip, ll_flip = mod._brier_logloss(np.array([0.5, 0.5, 0.5, 0.5]), y)
    assert b_good < b_flip
    assert ll_good < ll_flip
    assert abs(b_flip - 0.25) < 1e-9


def test_ece_well_calibrated_is_low() -> None:
    rng = np.random.default_rng(0)
    p = rng.uniform(0.0, 1.0, 5000)
    y = (rng.uniform(0.0, 1.0, 5000) < p).astype(float)
    assert mod._ece(p, y) < 0.05


def test_devig_market_devigs_and_dedups() -> None:
    odds = pd.DataFrame({
        "event_id": ["a", "a", "b"],          # duplicate 'a' -> must dedup
        "ps_p1": [1.5, 1.5, 3.0],
        "ps_p2": [2.5, 2.5, 1.4],
    })
    out = mod._devig_market(odds)
    assert list(out["event_id"]) == ["a", "b"]   # dedup kept first
    assert out["p_market"].between(0.0, 1.0).all()
    # 1/1.5 / (1/1.5 + 1/2.5) ~ 0.625 for event a
    assert abs(float(out.loc[out["event_id"] == "a", "p_market"].iloc[0]) - 0.625) < 1e-6


def test_devig_market_drops_bad_odds() -> None:
    odds = pd.DataFrame({
        "event_id": ["a", "b"],
        "ps_p1": [1.0, 2.0],     # 1.0 is non-payout -> dropped
        "ps_p2": [2.0, 2.0],
    })
    out = mod._devig_market(odds)
    assert list(out["event_id"]) == ["b"]


def test_fit_logistic_separates() -> None:
    rng = np.random.default_rng(1)
    x = np.concatenate([rng.normal(-2, 1, 200), rng.normal(2, 1, 200)])
    y = np.concatenate([np.zeros(200), np.ones(200)])
    X = x.reshape(-1, 1)
    clf, mu, sd = mod._fit_logistic(X, y)
    assert sd[0] > 0
    p = clf.predict_proba(((X - mu) / sd))[:, 1]
    assert p[:200].mean() < 0.4 < 0.6 < p[200:].mean()


def test_logit_finite_at_extremes() -> None:
    z = mod._logit(np.array([0.0, 1.0, 0.5]))
    assert np.all(np.isfinite(z))
    assert abs(z[2]) < 1e-9
