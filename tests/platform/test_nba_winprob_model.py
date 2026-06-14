"""tests/platform/test_nba_winprob_model.py

Tests for scripts/platformkit/nba_winprob_model.py.

Verified properties:
  1. Output shape matches input length.
  2. All outputs are in [0, 1].
  3. Strict no-future-leak invariant: truncating the input at row T gives the
     same prediction for row T-1 as the full run (truncation-invariance).
  4. Warmup rows fall back to the signal_col (Elo) value.
  5. Model activates (produces a non-passthrough value) after warmup.
  6. Works with a degenerate single-class warmup window (no crash).
"""
from __future__ import annotations

import numpy as np
import pytest

# ---------------------------------------------------------------------------
# Import under test
# ---------------------------------------------------------------------------

from scripts.platformkit.nba_winprob_model import fit_winprob, WARMUP


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

RNG = np.random.default_rng(42)


def _make_data(n: int = 300, n_features: int = 8):
    """Synthetic leak-free dataset."""
    base = RNG.standard_normal((n, n_features)).astype(float)
    # True latent signal is the first feature (roughly)
    logit_true = 0.3 * base[:, 0] + 0.1 * base[:, 1]
    p_true = 1.0 / (1.0 + np.exp(-logit_true))
    target = (RNG.random(n) < p_true).astype(float)
    # Noisy Elo proxy as signal_col
    signal_col = np.clip(p_true + RNG.standard_normal(n) * 0.05, 0.01, 0.99)
    return base, target, signal_col


# ---------------------------------------------------------------------------
# Test 1: output shape
# ---------------------------------------------------------------------------


def test_output_shape():
    base, target, signal_col = _make_data(200)
    out = fit_winprob(base, target, signal_col)
    assert out.shape == (200,), f"Expected (200,), got {out.shape}"


# ---------------------------------------------------------------------------
# Test 2: outputs in [0, 1]
# ---------------------------------------------------------------------------


def test_output_clipped():
    base, target, signal_col = _make_data(200)
    out = fit_winprob(base, target, signal_col)
    assert np.all(out >= 0.0), "Some outputs below 0"
    assert np.all(out <= 1.0), "Some outputs above 1"
    assert np.all(np.isfinite(out)), "Some outputs are NaN/inf"


# ---------------------------------------------------------------------------
# Test 3: truncation-invariance / no-future-leak
# ---------------------------------------------------------------------------


def test_no_future_leak():
    """Prediction at row T must not change when rows T+1..N are appended.

    We run fit_winprob on n rows, then on n+50 rows (same prefix), and assert
    the prediction for the LAST row of the shorter run is identical in both.
    This proves the model never looks ahead.
    """
    base, target, signal_col = _make_data(250)

    T = 150  # the "truncation point" row (0-indexed last row of short run)

    # Short run: rows 0..T inclusive
    out_short = fit_winprob(base[: T + 1], target[: T + 1], signal_col[: T + 1])

    # Long run: rows 0..N-1 (N > T+1)
    out_long = fit_winprob(base, target, signal_col)

    # Prediction at index T must be identical (it can only see rows 0..T-1 in both)
    assert out_short[T] == pytest.approx(out_long[T], abs=1e-10), (
        f"Truncation-invariance violated at row {T}: "
        f"short={out_short[T]:.8f}, long={out_long[T]:.8f}"
    )


# ---------------------------------------------------------------------------
# Test 4: warmup rows fall back to signal_col
# ---------------------------------------------------------------------------


def test_warmup_passthrough():
    """Rows before min_history must equal signal_col (fallback to Elo)."""
    base, target, signal_col = _make_data(300)
    min_hist = WARMUP  # default
    out = fit_winprob(base, target, signal_col, min_history=min_hist)
    # Every warmup row must exactly equal the signal_col value
    for i in range(min_hist):
        expected = float(signal_col[i]) if np.isfinite(signal_col[i]) else 0.5
        assert out[i] == pytest.approx(expected, abs=1e-10), (
            f"Warmup row {i}: expected signal_col={expected:.6f}, got {out[i]:.6f}"
        )


# ---------------------------------------------------------------------------
# Test 5: model activates after warmup
# ---------------------------------------------------------------------------


def test_model_activates_after_warmup():
    """After warmup the model should produce predictions different from raw signal_col.

    We use strongly predictive features so that a multi-feature model will
    diverge from the 1-D Elo fallback.
    """
    n = 300
    # Make feature 0 very predictive so LogReg departs from signal_col
    base = RNG.standard_normal((n, 8)).astype(float)
    logit_true = 2.0 * base[:, 0]  # strong signal in feature 0
    p_true = 1.0 / (1.0 + np.exp(-logit_true))
    target = (RNG.random(n) < p_true).astype(float)
    # signal_col is nearly uncorrelated with truth
    signal_col = np.full(n, 0.5)

    out = fit_winprob(base, target, signal_col, min_history=WARMUP)
    post_warmup = out[WARMUP:]
    # At least some post-warmup predictions should differ from 0.5
    assert not np.allclose(post_warmup, 0.5, atol=1e-3), (
        "Model never departed from signal_col=0.5 after warmup; it may not be fitting."
    )


# ---------------------------------------------------------------------------
# Test 6: degenerate single-class warmup does not crash
# ---------------------------------------------------------------------------


def test_single_class_warmup_no_crash():
    """If only one class exists in the first min_history rows, should not raise."""
    n = 150
    base = RNG.standard_normal((n, 8)).astype(float)
    target = np.zeros(n, dtype=float)   # all zeros — single class
    target[100:] = 1.0                  # second class appears later
    signal_col = np.full(n, 0.5)
    # Should complete without exception
    out = fit_winprob(base, target, signal_col)
    assert out.shape == (n,)
    assert np.all(np.isfinite(out))


# ---------------------------------------------------------------------------
# Test 7: mismatched lengths raise ValueError
# ---------------------------------------------------------------------------


def test_length_mismatch_raises():
    base = RNG.standard_normal((100, 8))
    target = np.zeros(90)       # wrong length
    signal_col = np.zeros(100)
    with pytest.raises(ValueError, match="same length"):
        fit_winprob(base, target, signal_col)
