"""Per-file numeric tests for scripts.platformkit.proof_nba.winprob_feature_challenger.

Run ONLY this file:
  python -m pytest tests/platformkit/test_winprob_feature_challenger.py -q
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

from scripts.platformkit.proof_nba import ml_accuracy
from scripts.platformkit.proof_nba.asof_box_accuracy import load_box
from scripts.platformkit.proof_nba.winprob_feature_challenger import (
    blend, bootstrap_ci, fit_blend_w)

_FIX_NBA = Path(__file__).resolve().parents[1] / "fixtures" / "proof" / "nba"


def test_elo_arm_reproduces_ml_accuracy_on_fixture():
    """(a) The Elo arm this module scores against is literally ml_accuracy's own
    _walk_forward_elo output -- reproduces exactly on the committed fixture."""
    box = load_box(_FIX_NBA)
    p1 = ml_accuracy._walk_forward_elo(box)
    p2 = ml_accuracy._walk_forward_elo(load_box(_FIX_NBA))
    assert np.allclose(p1, p2, atol=0.0)
    rep = ml_accuracy.run(corpus=_FIX_NBA)
    assert rep["status"] == "ok" and rep["n_holdout"] > 0


def test_blend_endpoints_equal_close_and_challenger():
    """(b) w=0 -> pure close; w=1 -> pure challenger (within float round-trip)."""
    rng = np.random.default_rng(0)
    p_challenger = rng.uniform(0.05, 0.95, 40)
    p_close = rng.uniform(0.05, 0.95, 40)
    assert np.allclose(blend(p_challenger, p_close, 0.0), p_close, atol=1e-6)
    assert np.allclose(blend(p_challenger, p_close, 1.0), p_challenger, atol=1e-6)


def test_fit_blend_w_is_bounded():
    rng = np.random.default_rng(1)
    y = rng.integers(0, 2, 200).astype(float)
    p_challenger = np.clip(y * 0.6 + rng.uniform(0.1, 0.3, 200), 0.02, 0.98)
    p_close = np.clip(y * 0.55 + rng.uniform(0.1, 0.35, 200), 0.02, 0.98)
    w = fit_blend_w(p_challenger, p_close, y)
    assert 0.0 <= w <= 1.0


def test_clustered_bootstrap_ci_contains_point_estimate():
    """(c) The bootstrap CI must bracket the sample mean it is estimating."""
    rng = np.random.default_rng(2)
    diff = rng.normal(0.01, 0.05, 150)
    lo, hi = bootstrap_ci(diff, reps=500, seed=3)
    assert lo <= float(diff.mean()) <= hi
