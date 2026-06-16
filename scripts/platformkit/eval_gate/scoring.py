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
from typing import Sequence
import numpy as np

ArrayLike = Sequence[float]


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
