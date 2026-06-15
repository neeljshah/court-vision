"""Per-file test for scripts/platformkit/proof_soccer/fusion_soccer.py.

Unit asserts on the leak-free helpers + structural asserts on the honest finding:
the complementary engine + as-of SoT-form fusion does NOT beat the close (efficient
market); the expected verdict is absorbed_null / calibration_win (a SUCCESS), never a
manufactured narrows_gap, and the fused forecaster never blows up the baseline.

Run: python -m pytest tests/platform/test_soccer_fusion.py -q
"""
from __future__ import annotations

import numpy as np
import pytest

from scripts.platformkit.proof_soccer import fusion_soccer as mod


def test_logit_sigmoid_roundtrip():
    p = np.array([0.1, 0.3, 0.5, 0.7, 0.9])
    assert np.allclose(mod._sigmoid(mod._logit(p)), p, atol=1e-6)


def test_brier_perfect_is_zero():
    y = np.array([0.0, 1.0, 1.0, 0.0])
    assert mod._brier(y, y) < 1e-6


def test_ece_well_calibrated_is_small():
    rng = np.random.default_rng(0)
    p = rng.random(5000)
    y = (rng.random(5000) < p).astype(float)
    assert mod._ece(p, y) < 0.03


def test_fit_logistic_recovers_separable_sign():
    # y depends positively on the single feature -> learned weight should be positive.
    rng = np.random.default_rng(1)
    x = rng.normal(size=2000)
    y = (rng.random(2000) < mod._sigmoid(1.5 * x)).astype(float)
    X = np.column_stack([x, np.ones_like(x)])
    w = mod._fit_logistic(X, y)
    assert w[0] > 0.5


def test_fit_platt_identity_on_calibrated():
    rng = np.random.default_rng(2)
    p = rng.random(4000)
    y = (rng.random(4000) < p).astype(float)
    a, b = mod._fit_platt(p, y)
    assert 0.7 < a < 1.4 and abs(b) < 0.3


def test_run_fusion_absorbed_or_calibration_never_beats_close():
    rep = mod.run()
    if rep.get("status") != "ok":
        pytest.skip(f"corpus unavailable: {rep.get('status')}")
    # Honest classification: a pregame fusion vs an efficient market must NOT be a
    # fabricated narrows_gap unless it genuinely beats the engine AND moves toward close.
    assert rep["verdict_kind"] in {"absorbed_null", "calibration_win",
                                   "narrows_gap", "data_limited"}
    # The fusion must never materially WORSEN the engine baseline (leak-free, well-behaved).
    assert rep["fused_brier"] <= rep["base_brier"] + 0.002
    # The close stays at least as sharp as our pregame forecaster (markets efficient).
    assert rep["close_brier"] <= rep["fused_brier"] + 1e-6
    assert rep["gap_fused_to_close"] >= -0.002
    # If it claims to narrow the gap, that must be backed by a real Brier improvement.
    if rep["verdict_kind"] == "narrows_gap":
        assert rep["fused_brier"] < rep["base_brier"] - 0.0005
        assert rep["narrowing"] >= 0.002
    assert 0.0 <= rep["asof_coverage"] <= 1.0
