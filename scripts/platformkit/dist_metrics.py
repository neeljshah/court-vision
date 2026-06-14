"""scripts/platformkit/dist_metrics.py — Proper scoring for distribution/interval markets.

Proper scoring rules for totals, props, and scoreline markets (real-valued / count outcomes).
Does NOT duplicate crps_binary / crps_mean from calibration_ladder.py (binary-only).

HONESTY: calibration metrics only.  Better CRPS or coverage does NOT imply a positive
expected value or beating the closing line.  See: feedback_accuracy_is_not_edge.md.
"""
from __future__ import annotations
from typing import Sequence, Union
import numpy as np

__all__ = [
    "pinball_loss", "interval_coverage", "coverage_calibration",
    "crps_ensemble", "crps_poisson_pmf", "distribution_scorecard",
]

ArrayLike = Union[Sequence[float], np.ndarray]


def _arr(x: ArrayLike) -> np.ndarray:
    return np.atleast_1d(np.asarray(x, dtype=float))


def _finite(*arrays: np.ndarray) -> np.ndarray:
    mask = np.ones(len(arrays[0]), dtype=bool)
    for a in arrays:
        mask &= np.isfinite(a)
    return mask


# ---------------------------------------------------------------------------
# pinball_loss
# ---------------------------------------------------------------------------

def pinball_loss(y_true: ArrayLike, q_pred: ArrayLike, quantile: float) -> float:
    """Quantile (pinball) loss — proper scoring rule for quantile forecasts.

    L_tau(y, q) = tau * max(y-q, 0) + (1-tau) * max(q-y, 0).
    Minimised (in expectation) at the true tau-quantile.  Lower is better.
    Vectorised; NaN rows skipped.  calibration != edge.
    """
    if not (0.0 < quantile < 1.0):
        raise ValueError(f"quantile must be in (0, 1), got {quantile!r}")
    y, q = _arr(y_true), _arr(q_pred)
    if y.shape != q.shape:
        raise ValueError(f"y_true and q_pred must have the same shape ({y.shape} vs {q.shape})")
    mask = _finite(y, q)
    if not mask.any():
        return float("nan")
    diff = y[mask] - q[mask]
    loss = np.where(diff >= 0, quantile * diff, (quantile - 1.0) * diff)
    return float(loss.mean())


# ---------------------------------------------------------------------------
# interval_coverage
# ---------------------------------------------------------------------------

def interval_coverage(y_true: ArrayLike, lo: ArrayLike, hi: ArrayLike) -> dict:
    """Empirical coverage fraction and mean width of predictive intervals [lo, hi].

    Returns {coverage, mean_width, n}.  Use to verify an X% interval covers ~X% of obs.
    NaN observations or bounds excluded.  calibration != edge.
    """
    y, lo_a, hi_a = _arr(y_true), _arr(lo), _arr(hi)
    mask = _finite(y, lo_a, hi_a)
    n = int(mask.sum())
    if n == 0:
        return {"coverage": float("nan"), "mean_width": float("nan"), "n": 0}
    y_v, lo_v, hi_v = y[mask], lo_a[mask], hi_a[mask]
    coverage = float(((y_v >= lo_v) & (y_v <= hi_v)).mean())
    mean_width = float((hi_v - lo_v).mean())
    return {"coverage": coverage, "mean_width": mean_width, "n": n}


# ---------------------------------------------------------------------------
# coverage_calibration
# ---------------------------------------------------------------------------

def coverage_calibration(
    y_true: ArrayLike, lo: ArrayLike, hi: ArrayLike,
    nominal: float, tol: float = 0.05,
) -> dict:
    """Check whether an interval achieves its nominal coverage level.

    Returns {nominal, empirical, gap (empirical-nominal), calibrated (|gap|<tol)}.
    Negative gap = interval too tight; positive = too wide.  calibration != edge.
    """
    result = interval_coverage(y_true, lo, hi)
    empirical = result["coverage"]
    if not np.isfinite(empirical):
        return {"nominal": nominal, "empirical": float("nan"), "gap": float("nan"), "calibrated": False}
    gap = float(empirical - nominal)
    return {"nominal": nominal, "empirical": empirical, "gap": gap, "calibrated": bool(abs(gap) < tol)}


# ---------------------------------------------------------------------------
# crps_ensemble
# ---------------------------------------------------------------------------

def crps_ensemble(y_true: ArrayLike, samples: ArrayLike) -> float:
    """CRPS for an ensemble forecast via the energy-form estimator (Gneiting & Raftery 2007).

    CRPS(F, y) = E|S-y| - 0.5*E|S-S'|.  Proper scoring rule; lower is better.
    Degenerate 1-member ensemble collapses to |pred - y|.
    samples: shape (m,) for single obs or (n, m) for n observations.  NaN-safe.
    calibration != edge.
    """
    s = np.asarray(samples, dtype=float)
    y = np.asarray(y_true, dtype=float)
    if s.ndim == 1:
        y_flat = np.atleast_1d(y)
        if y_flat.size != 1:
            raise ValueError("When samples is 1-D, y_true must be scalar or 1-element.")
        s, y = s[np.newaxis, :], y_flat
    elif s.ndim == 2:
        y = np.atleast_1d(y)
        if y.shape[0] != s.shape[0]:
            raise ValueError(f"y_true length {y.shape[0]} must match samples rows {s.shape[0]}.")
    else:
        raise ValueError("samples must be 1-D (single obs) or 2-D (n_obs x n_members).")

    crps_vals = np.empty(s.shape[0], dtype=float)
    for i in range(s.shape[0]):
        yi, si = y[i], s[i][np.isfinite(s[i])]
        if not np.isfinite(yi) or len(si) == 0:
            crps_vals[i] = float("nan")
            continue
        mean_abs = float(np.mean(np.abs(si - yi)))
        m = len(si)
        if m == 1:
            spread = 0.0
        else:
            si_s = np.sort(si)
            # O(m log m) energy-form spread: sum|s_i - s_j| / m^2 = dot(weights, sorted) / (m*(m-1))
            spread = float(np.dot(2.0 * np.arange(m, dtype=float) - (m - 1), si_s)) / (m * (m - 1))
        crps_vals[i] = mean_abs - 0.5 * spread
    valid = crps_vals[np.isfinite(crps_vals)]
    return float(valid.mean()) if len(valid) > 0 else float("nan")


# ---------------------------------------------------------------------------
# crps_poisson_pmf
# ---------------------------------------------------------------------------

def crps_poisson_pmf(y_true: ArrayLike, pmf: ArrayLike, support: ArrayLike) -> float:
    """CRPS from a discrete PMF over an integer support (CDF-integral form).

    CRPS(F, y) = sum_{k in support} (F(k) - 1[y<=k])^2.
    Proper scoring rule for count/integer outcomes (total goals, game totals, etc.).
    PMF is normalised internally.  NaN-safe.  Lower is better.  calibration != edge.
    """
    sup = np.asarray(support, dtype=float)
    K = len(sup)
    pmf_arr = np.asarray(pmf, dtype=float)
    y = np.atleast_1d(np.asarray(y_true, dtype=float))
    if pmf_arr.ndim == 1:
        if pmf_arr.shape[0] != K:
            raise ValueError("pmf length must match support length.")
        pmf_arr = np.tile(pmf_arr, (len(y), 1))
    elif pmf_arr.ndim == 2:
        if pmf_arr.shape[1] != K:
            raise ValueError("pmf.shape[1] must match support length.")
        if pmf_arr.shape[0] != len(y):
            raise ValueError("pmf.shape[0] must match len(y_true).")
    else:
        raise ValueError("pmf must be 1-D or 2-D (n_obs x K).")

    crps_vals = np.empty(len(y), dtype=float)
    for i in range(len(y)):
        yi, pi = y[i], pmf_arr[i]
        if not np.isfinite(yi):
            crps_vals[i] = float("nan")
            continue
        pi_sum = pi.sum()
        if pi_sum <= 0 or not np.isfinite(pi_sum):
            crps_vals[i] = float("nan")
            continue
        cdf = np.cumsum(pi / pi_sum)
        crps_vals[i] = float(np.sum((cdf - (yi <= sup).astype(float)) ** 2))
    valid = crps_vals[np.isfinite(crps_vals)]
    return float(valid.mean()) if len(valid) > 0 else float("nan")


# ---------------------------------------------------------------------------
# distribution_scorecard
# ---------------------------------------------------------------------------

def distribution_scorecard(
    y_true: ArrayLike, samples: ArrayLike,
    lo: ArrayLike, hi: ArrayLike,
    nominal_coverage: float = 0.90,
    q_lo: float = 0.05, q_hi: float = 0.95,
    tol: float = 0.05,
) -> dict:
    """Bundled scorecard for a totals/interval market.

    Returns: crps, pinball_lo, pinball_hi, coverage, mean_width,
             nominal_coverage, coverage_gap, calibrated, n.
    All are accuracy/calibration metrics.  calibration != edge.
    """
    y, lo_a, hi_a = _arr(y_true), _arr(lo), _arr(hi)
    cov = interval_coverage(y, lo_a, hi_a)
    cal = coverage_calibration(y, lo_a, hi_a, nominal=nominal_coverage, tol=tol)
    return {
        "crps": crps_ensemble(y_true, samples),
        "pinball_lo": pinball_loss(y, lo_a, q_lo),
        "pinball_hi": pinball_loss(y, hi_a, q_hi),
        "coverage": cov["coverage"],
        "mean_width": cov["mean_width"],
        "nominal_coverage": nominal_coverage,
        "coverage_gap": cal["gap"],
        "calibrated": cal["calibrated"],
        "n": cov["n"],
    }
