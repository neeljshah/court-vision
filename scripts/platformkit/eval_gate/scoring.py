"""Proper-scoring metrics for the calibration eval gate (blueprint N1).

REUSE, don't reimplement: brier + ece come from kernel.validation.proof_metrics
(read-only reuse of the validated kernel math). This module ADDS the gate-specific
metrics the kernel does not export -- brier_skill_score, log_loss, resolution,
sharpness -- per the blueprint. A defensive import keeps the module self-contained:
if the editable install is ever absent, brier/ece fall back to byte-equivalent
numpy bodies so the gate's tests still pass anywhere (numpy + stdlib only).

The bar is calibration vs the DEVIGGED market close, never a dollar edge:
- Brier Skill Score (BSS) vs the close is the primary metric.
- ECE is DIAGNOSTIC ONLY -- always paired with sharpness/resolution so a
  collapse-to-0.5 forecaster cannot look good.

`_KERNEL` (bool) exposes provenance so run_gate / SCHEMA can print whether the
metrics came from the kernel ("metrics=kernel") or the fallback ("metrics=fallback").
"""
from __future__ import annotations
import math
from typing import Sequence
import numpy as np

ArrayLike = Sequence[float]
_INV_SQRT_PI = 1.0 / math.sqrt(math.pi)


def _arr(x: ArrayLike) -> np.ndarray:
    return np.asarray(x, dtype=float)


# ---------------------------------------------------------------------------
# brier + ece: read-only reuse of kernel.validation.proof_metrics.
# Kernel signatures match the gate's: brier(probs, outcomes) and
# ece(probs, outcomes, bins=10) -- bins is positional-compatible, and the
# kernel ECE uses the identical [lo,hi) tie-break for all but the last bin
# (which is [lo,hi]), so test_ece_collapse_guard stays green either way.
# ---------------------------------------------------------------------------
try:
    from kernel.validation.proof_metrics import brier as _k_brier, ece as _k_ece

    def brier(p: ArrayLike, y: ArrayLike) -> float:
        """Mean squared error of probabilistic forecasts (kernel impl)."""
        return float(_k_brier(_arr(p), _arr(y)))

    def ece(p: ArrayLike, y: ArrayLike, bins: int = 10) -> float:
        """Expected Calibration Error (kernel impl). DIAGNOSTIC ONLY."""
        return float(_k_ece(_arr(p), _arr(y), bins))

    _KERNEL = True
except Exception:  # editable install absent -> self-contained numpy fallback
    def brier(p: ArrayLike, y: ArrayLike) -> float:
        """Mean squared error of probabilistic forecasts (lower is better)."""
        p, y = _arr(p), _arr(y)
        return float(np.mean((p - y) ** 2))

    def ece(p: ArrayLike, y: ArrayLike, bins: int = 10) -> float:
        """Expected Calibration Error (equal-width bins). DIAGNOSTIC ONLY.

        Never optimize ECE directly -- predicting 0.5 everywhere drives ECE
        toward zero with zero value. Read alongside sharpness() and resolution().
        """
        p, y = _arr(p), _arr(y)
        edges = np.linspace(0.0, 1.0, bins + 1)
        n = len(p)
        if n == 0:
            return 0.0
        total = 0.0
        for k in range(bins):
            lo, hi = edges[k], edges[k + 1]
            m = (p >= lo) & (p < hi) if k < bins - 1 else (p >= lo) & (p <= hi)
            if not m.any():
                continue
            conf = float(p[m].mean())
            acc = float(y[m].mean())
            total += (m.sum() / n) * abs(acc - conf)
        return float(total)

    _KERNEL = False


# ---------------------------------------------------------------------------
# Gate-specific additions (the kernel does NOT export these). Kept local.
# ---------------------------------------------------------------------------


def log_loss(p: ArrayLike, y: ArrayLike) -> float:
    """Negative log-likelihood; punishes confident-wrong harder than Brier."""
    p = np.clip(_arr(p), 1e-15, 1 - 1e-15)
    y = _arr(y)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def brier_skill_score(p_model: ArrayLike, p_ref: ArrayLike, y: ArrayLike) -> float:
    """BSS = 1 - Brier_model / Brier_ref. ref = devigged close.

    BSS > 0 -> better calibrated than the close on this sample.
    BSS <= 0 -> we do NOT beat the close here. That is an HONEST, recorded
    result (markets efficient on price), not a failure.
    """
    bm = brier(p_model, y)
    br = brier(p_ref, y)
    return float(1.0 - bm / br) if br > 0 else 0.0


def resolution(p: ArrayLike, y: ArrayLike, bins: int = 10) -> float:
    """Murphy resolution component (higher = more discriminating/sharp+correct)."""
    p, y = _arr(p), _arr(y)
    o_bar = float(y.mean())
    edges = np.linspace(0.0, 1.0, bins + 1)
    res = 0.0
    for k in range(bins):
        lo, hi = edges[k], edges[k + 1]
        m = (p >= lo) & (p < hi) if k < bins - 1 else (p >= lo) & (p <= hi)
        if not m.any():
            continue
        res += float(m.mean()) * (float(y[m].mean()) - o_bar) ** 2
    return float(res)


def sharpness(p: ArrayLike) -> float:
    """Variance of the forecasts -- guards against collapse-to-base-rate."""
    return float(np.var(_arr(p)))


# ---------------------------------------------------------------------------
# Distributional metrics (MASTER_PLAN C7). Brier/log-loss grade a binary
# probability; these grade the FULL predictive distribution -- the thing an
# in-game / live system must prove honest for continuous markets (totals,
# margins) and for served prop-interval bounds. Lower is better for all.
# ---------------------------------------------------------------------------


def _norm_cdf(x: np.ndarray) -> np.ndarray:
    """Standard-normal CDF via erf (numpy + stdlib only, no scipy)."""
    erf = np.vectorize(math.erf, otypes=[float])
    return 0.5 * (1.0 + erf(x / math.sqrt(2.0)))


def _norm_pdf(x: np.ndarray) -> np.ndarray:
    return np.exp(-0.5 * x * x) / math.sqrt(2.0 * math.pi)


def crps_gaussian(mu: ArrayLike, sigma: ArrayLike, y: ArrayLike) -> float:
    """Mean CRPS for a Gaussian predictive distribution N(mu, sigma) vs actual y.

    Closed form (Gneiting & Raftery 2007). Use for continuous markets (totals,
    margins) where the forecast is a calibrated mean + sigma. As sigma -> 0 the
    score collapses to MAE (|mu - y|); CRPS is the distribution-aware
    generalization the point/binary metrics could not express -- it rewards a
    sharp, accurate predictive density and penalizes overconfident sigmas.
    """
    mu, sigma, y = _arr(mu), _arr(sigma), _arr(y)
    sigma = np.clip(sigma, 1e-12, None)
    z = (y - mu) / sigma
    crps = sigma * (z * (2.0 * _norm_cdf(z) - 1.0) + 2.0 * _norm_pdf(z) - _INV_SQRT_PI)
    return float(np.mean(crps))


def crps_ensemble(samples, y: ArrayLike) -> float:
    """Empirical CRPS from Monte-Carlo sample forecasts -- the possession sim's
    NATIVE output. `samples` is (n_obs, n_samples) (a 1-D vector is treated as a
    single observation's sample set); `y` is (n_obs,).

    CRPS = E|X - y| - 0.5 * E|X - X'|, with the pairwise term computed in
    O(n log n) per row via the sorted-order identity (no n^2 blow-up).
    """
    samples = np.asarray(samples, dtype=float)
    if samples.ndim == 1:
        samples = samples[None, :]
    y = _arr(y)
    n = samples.shape[1]
    if n == 0:
        return float("nan")
    term1 = np.mean(np.abs(samples - y[:, None]), axis=1)
    idx = np.arange(n)
    xs = np.sort(samples, axis=1)
    # E|X - X'| = (2 / n^2) * sum_j (2j - n + 1) * xs[j]   (xs ascending)
    term2 = 2.0 * np.sum((2 * idx - n + 1) * xs, axis=1) / (n * n)
    return float(np.mean(term1 - 0.5 * term2))


def pinball_loss(y: ArrayLike, q_pred: ArrayLike, quantile: float) -> float:
    """Quantile (pinball) loss at level `quantile` in (0, 1). Grades a single
    served interval bound: does that quantile actually cover at the claimed
    rate? Averaging pinball across the interval's quantiles scores the band.
    """
    if not 0.0 < quantile < 1.0:
        raise ValueError(f"quantile must be in (0,1), got {quantile}")
    y, q_pred = _arr(y), _arr(q_pred)
    diff = y - q_pred
    return float(np.mean(np.maximum(quantile * diff, (quantile - 1.0) * diff)))
