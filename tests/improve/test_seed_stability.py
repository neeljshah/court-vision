"""tests/improve/test_seed_stability.py -- per-file guard for improve.seed_stability.

Two scenarios that encode the hard-learned single-seed artifact invariant:

  1. ROBUST improvement: a metric_fn whose improvement is genuinely positive on
     every bootstrap draw (tight positive signal) -> stable=True, p10 >= 0.

  2. FRAGILE spike: a metric_fn that looks good on seed=0 / the single draw but
     collapses (mean > 0 but p10 < 0) under multi-seed resampling ->
     stable=False. This is the artifact the guard is designed to catch.

Run only this file:
    cd /c/Users/neelj/nba-ai-system && python -m pytest tests/improve/test_seed_stability.py -q

stdlib + numpy only. No network, no files, no external deps.
"""
from __future__ import annotations

import math
import os
import sys
from typing import List

import numpy as np
import pytest

# ---- path bootstrap (mirrors the pattern used across tests/) ------------------
PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

from improve.seed_stability import stable, StabilityResult


# ---- helpers ------------------------------------------------------------------

def _make_data(n: int = 300, rng: np.random.Generator = None) -> List[dict]:
    """Synthetic dataset rows: each row has 'x' (feature) and 'y' (label)."""
    if rng is None:
        rng = np.random.default_rng(0)
    xs = rng.standard_normal(n)
    ys = (xs + rng.standard_normal(n) * 0.3 > 0).astype(float)
    return [{"x": float(xs[i]), "y": float(ys[i])} for i in range(n)]


def _brier(p: np.ndarray, y: np.ndarray) -> float:
    return float(np.mean((p - y) ** 2))


# ---- scenario 1: robust improvement -------------------------------------------
# The "candidate" is a well-calibrated predictor; the "baseline" is the
# unconditional mean. On any bootstrap the candidate reliably beats the baseline
# because the signal (x) is genuine and strong (low sigma noise).

def _robust_metric_fn(train_rows, test_rows) -> float:
    """Return improvement = baseline_brier - candidate_brier on test_rows.

    baseline : predict unconditional mean of train labels.
    candidate: predict sign(x) * 0.85 + 0.5 * 0.15 (strong calibrated signal).
    The improvement is genuine and always positive -> stable guard should PASS.
    """
    train_y = np.array([r["y"] for r in train_rows])
    test_y = np.array([r["y"] for r in test_rows])
    test_x = np.array([r["x"] for r in test_rows])

    baseline_p = np.full(len(test_y), float(train_y.mean()))
    # Candidate: a calibrated probability based on the strong feature x.
    # sigmoid-like squeeze: P(y=1) = 0.15 + 0.7 * sigma(3*x)
    candidate_p = 0.15 + 0.70 / (1.0 + np.exp(-3.0 * test_x))

    baseline_brier = _brier(baseline_p, test_y)
    candidate_brier = _brier(candidate_p, test_y)
    return baseline_brier - candidate_brier  # positive -> candidate better


def test_robust_improvement_is_stable():
    """A genuine, tight improvement should pass the p10 >= 0 guard."""
    data = _make_data(300)
    result = stable(
        _robust_metric_fn,
        data,
        seeds=(0, 1, 2, 7, 42),
        n_boot=150,
    )
    assert isinstance(result, StabilityResult), "must return StabilityResult"
    assert result.stable is True, (
        f"robust improvement should be stable; p10={result.p10:.6f} mean={result.mean:.6f}"
    )
    assert result.p10 >= 0.0, f"p10={result.p10:.6f} must be >= 0"
    assert result.mean > 0.0, f"mean={result.mean:.6f} must be positive"
    assert result.n_draws > 0, "must have numeric draws"
    assert len(result.seeds_used) == 5
    # Sanity: delta_pct (fraction of draws > 0) should be very high for a strong signal.
    assert result.deltas_pct > 0.90, (
        f"expected > 90% positive draws; got {result.deltas_pct:.2%}"
    )


# ---- scenario 2: fragile single-seed spike ------------------------------------
# The "candidate" has a tiny genuine signal but also a large variance component
# that depends heavily on which specific rows land in the OOB set.  We manufacture
# this by: the delta is signal_true + noise, where noise dominates so the
# distribution is centered slightly above 0 but the p10 tail dips negative.

def _fragile_metric_fn(train_rows, test_rows) -> float:
    """Simulate a metric where mean improvement > 0 but variance is huge.

    We inject per-draw noise proportional to the first row's 'x' value
    (to make it look like a real feature-dependent pattern that the single seed
    happened to sample favorably), creating a distribution where mean > 0 but
    the 10th percentile is definitively negative.
    """
    test_y = np.array([r["y"] for r in test_rows])
    test_x = np.array([r["x"] for r in test_rows])

    # Small genuine signal: candidate uses x slightly
    candidate_p = 0.48 + 0.04 / (1.0 + np.exp(-0.5 * test_x))
    baseline_p = np.full(len(test_y), 0.5)

    true_delta = _brier(baseline_p, test_y) - _brier(candidate_p, test_y)
    # Artificial variance: the OOB set is small & its mean(x) is random; we
    # amplify that randomness to simulate a high-variance estimator.
    noise_seed = int(abs(test_x[0]) * 1e6) % (2**31)
    noise_rng = np.random.default_rng(noise_seed)
    noise = noise_rng.standard_normal() * 0.08  # SD >> signal -> heavy tails
    return true_delta + noise


def test_fragile_spike_is_not_stable():
    """A metric with mean > 0 but high variance should NOT pass p10 >= 0 guard."""
    data = _make_data(300, rng=np.random.default_rng(99))
    result = stable(
        _fragile_metric_fn,
        data,
        seeds=(0, 1, 2, 3, 7, 42, 137, 1337),
        n_boot=200,
    )
    assert isinstance(result, StabilityResult), "must return StabilityResult"
    # The mean should be modestly positive (the scenario has small true signal)
    # but the p10 should be negative due to the large noise.
    assert result.p10 < 0.0, (
        f"fragile spike should have p10 < 0; got p10={result.p10:.6f} "
        f"mean={result.mean:.6f} stable={result.stable}"
    )
    assert result.stable is False, (
        f"fragile spike must NOT be stable; p10={result.p10:.6f}"
    )
    assert result.n_draws > 0, "must have numeric draws"


# ---- edge-case / contract tests -----------------------------------------------

def test_empty_data_returns_not_stable():
    """An empty dataset must return stable=False without raising."""
    result = stable(lambda t, o: 1.0, [], seeds=(0, 1), n_boot=5)
    assert result.stable is False
    assert result.n_draws == 0


def test_result_is_deterministic_given_seeds():
    """Same seeds + data + n_boot -> byte-identical StabilityResult."""
    data = _make_data(100)
    r1 = stable(_robust_metric_fn, data, seeds=(0, 7), n_boot=50)
    r2 = stable(_robust_metric_fn, data, seeds=(0, 7), n_boot=50)
    assert r1.p10 == r2.p10
    assert r1.mean == r2.mean
    assert r1.n_draws == r2.n_draws


def test_single_seed_exposes_artifact_multi_seed_catches():
    """Single-seed run may appear stable (mean > 0) while multi-seed correctly rejects."""
    data = _make_data(300, rng=np.random.default_rng(99))
    # Force a small n_boot so single-seed has high variance.
    single = stable(_fragile_metric_fn, data, seeds=(42,), n_boot=20)
    multi = stable(_fragile_metric_fn, data, seeds=(0, 1, 2, 3, 7, 42, 137, 1337), n_boot=200)
    # Multi-seed must reject or be at most equal -- never more permissive than single.
    # The purpose of the test is to document the guard's purpose, not to be brittle
    # about the single-seed outcome (which varies by seed).
    # What we assert: multi-seed has strictly more draws.
    assert multi.n_draws > single.n_draws
    # And the multi-seed result correctly identifies the fragile spike.
    assert multi.stable is False, (
        f"multi-seed must reject the fragile spike; p10={multi.p10:.6f}"
    )


def test_metric_fn_exception_is_swallowed():
    """A metric_fn that raises on some draws must not propagate."""
    call_count = {"n": 0}

    def _sometimes_raises(train_rows, test_rows) -> float:
        call_count["n"] += 1
        if call_count["n"] % 3 == 0:
            raise ValueError("simulated metric failure")
        return 0.05

    data = _make_data(50)
    result = stable(_sometimes_raises, data, seeds=(0,), n_boot=30)
    # Should complete without raising; some draws lost to exception -> fewer n_draws
    assert result.n_draws > 0
    assert math.isfinite(result.p10)


if __name__ == "__main__":
    tests = [
        test_robust_improvement_is_stable,
        test_fragile_spike_is_not_stable,
        test_empty_data_returns_not_stable,
        test_result_is_deterministic_given_seeds,
        test_single_seed_exposes_artifact_multi_seed_catches,
        test_metric_fn_exception_is_swallowed,
    ]
    passed = 0
    for fn in tests:
        try:
            fn()
            print(f"PASS  {fn.__name__}")
            passed += 1
        except Exception as exc:
            print(f"FAIL  {fn.__name__}: {exc}")
    print(f"\n{passed}/{len(tests)} seed_stability tests passed.")
