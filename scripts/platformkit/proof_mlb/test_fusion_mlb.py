"""Per-file structural test for fusion_mlb (run THIS file only; never full pytest)."""
from __future__ import annotations

import numpy as np

from scripts.platformkit.proof_mlb import fusion_mlb as F


def test_sigmoid_logit_roundtrip():
    p = np.array([0.1, 0.3, 0.5, 0.7, 0.9])
    back = F._sigmoid(F._logit(p))
    assert np.allclose(back, p, atol=1e-6)


def test_brier_logloss_bounds():
    y = np.array([1.0, 0.0, 1.0, 0.0])
    p = np.array([0.9, 0.1, 0.8, 0.2])
    assert 0.0 <= F._brier(p, y) < 0.1
    assert F._logloss(p, y) > 0.0
    # perfect prediction -> ~0 brier
    assert F._brier(y, y) < 1e-6


def test_fit_logistic_recovers_separable_sign():
    rng = np.random.default_rng(0)
    n = 4000
    x = rng.normal(size=n)
    y = (F._sigmoid(1.5 * x) > rng.random(n)).astype(float)
    X = np.column_stack([np.ones(n), x])
    w = F._fit_logistic(X, y)
    # positive feature -> positive weight, intercept near 0
    assert w[1] > 0.5
    assert abs(w[0]) < 0.3


def test_ece_zero_for_calibrated():
    # each bin's empirical positive rate equals its constant predicted prob -> ECE 0.
    # bin [0.0,0.1): pred 0.05, so 5/100 positives; bin [0.9,1.0): pred 0.95, 95/100.
    p = np.concatenate([np.full(100, 0.05), np.full(100, 0.95)])
    y = np.concatenate([np.zeros(95), np.ones(5),       # 5% in low bin
                        np.zeros(5), np.ones(95)])       # 95% in high bin
    assert F._ece(p, y) < 1e-9


def test_run_contract_and_honest_verdict():
    rep = F.run()
    assert rep["status"] == "ok"
    assert rep["verdict_kind"] in {
        "narrows_gap", "calibration_win", "absorbed_null", "data_limited"}
    # close is the comparison forecaster and should be at least as sharp as base
    assert rep["close_brier"] <= rep["base_brier"] + 1e-6
    # baseline parity with the headline beat_the_close_ml proof (Elo-only Brier)
    assert abs(rep["base_brier"] - 0.2429) < 0.0005
    # fused must not be a leak-driven blowout below the close
    assert rep["fused_brier"] >= rep["close_brier"] - 0.005
    for k in ("base_brier", "fused_brier", "close_brier", "narrow",
              "gap_base_to_close", "gap_fused_to_close", "fusion_weights"):
        assert k in rep


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"PASS {name}")
    print("ALL PASS")
