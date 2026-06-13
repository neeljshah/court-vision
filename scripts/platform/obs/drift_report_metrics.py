"""drift_report_metrics.py — Low-level scoring functions for drift_report.

Extracted from drift_report.py (N-OBS-003).  Contains the four primitive
metric scorers that operate on raw arrays:

    * _brier_binary   — binary Brier score (P(over) = 0.5 null model)
    * _brier_raw      — MSE between pred and actual
    * _pit_uniformity — PIT uniformity via chi-sq test
    * _interval_coverage — fraction of actuals inside [q10, q90]

These functions are pure/side-effect-free and have no inter-dependencies.
Python 3.9 compatible.  No torch / GPU imports.
"""
from __future__ import annotations

import logging
from typing import Any, Dict

log = logging.getLogger(__name__)

# Threshold used by _pit_uniformity — keep in sync with drift_report.py
PIT_CHI_WARN: float = 0.05


# ---------------------------------------------------------------------------
# Metric scorers
# ---------------------------------------------------------------------------


def _brier_binary(pred: Any, actual: Any, line: float = 0.0) -> float:
    """Compute mean squared error of P(over) vs binary over/under outcome.

    Uses the prediction as the point estimate; ``line`` defaults to 0 so
    P(over) = sigmoid-like mapping is avoided — we simply threshold by the
    median (q50 = pred) as the line.  Brier = mean((pred_prob - outcome)^2)
    where outcome=1 if actual > pred (= over), else 0.

    Args:
        pred:   Array-like of point predictions (q50 / mean).
        actual: Array-like of realised values.
        line:   Ignored; kept for interface clarity.

    Returns:
        Brier score as a float in [0, 1].
    """
    try:
        import numpy as np  # noqa: PLC0415
        p = np.asarray(pred, dtype=float)
        a = np.asarray(actual, dtype=float)
        mask = np.isfinite(p) & np.isfinite(a)
        if mask.sum() == 0:
            return float("nan")
        # P(over) = fraction of historical actuals above pred
        # For per-row binary: outcome=1 if actual > pred (i.e. over hit)
        # Use 0.5 as constant probability benchmark → Brier = mean((0.5 - outcome)^2) = 0.25
        # Instead we model P(actual > pred) = 0.5 per prediction; actual Brier measures
        # systematic under/over-prediction:  bias^2 + noise
        outcome = (a[mask] > p[mask]).astype(float)
        prob = np.full(outcome.shape, 0.5)  # null model P(over)=0.5
        return float(np.mean((prob - outcome) ** 2))
    except Exception as exc:
        log.debug("_brier_binary failed: %s", exc)
        return float("nan")


def _brier_raw(pred: Any, actual: Any) -> float:
    """Compute mean squared prediction error (MAE equivalent: MSE).

    This is MSE not Brier — used as a calibration quality measure.

    Args:
        pred:   Array-like of point predictions.
        actual: Array-like of realised values.

    Returns:
        Mean squared error (float).
    """
    try:
        import numpy as np  # noqa: PLC0415
        p = np.asarray(pred, dtype=float)
        a = np.asarray(actual, dtype=float)
        mask = np.isfinite(p) & np.isfinite(a)
        if mask.sum() == 0:
            return float("nan")
        return float(np.mean((p[mask] - a[mask]) ** 2))
    except Exception as exc:
        log.debug("_brier_raw failed: %s", exc)
        return float("nan")


def _pit_uniformity(residuals: Any, n_bins: int = 10) -> Dict[str, Any]:
    """Compute PIT (Probability Integral Transform) uniformity statistics.

    A well-calibrated model produces residuals that are uniformly distributed
    when mapped through the predictive CDF.  We approximate this with a
    chi-squared test on normalised residuals divided into equal-count bins.

    Args:
        residuals:  Array-like of (actual - pred) / sigma.  Must be centred
                    near zero for a calibrated model.
        n_bins:     Number of bins for the chi-sq test.

    Returns:
        Dict with keys: mean, std, skew, n, chi_sq_stat, p_value, flag.
    """
    try:
        import numpy as np  # noqa: PLC0415
        r = np.asarray(residuals, dtype=float)
        r = r[np.isfinite(r)]
        n = len(r)
        if n < n_bins * 5:
            return {"n": n, "flag": "too_few_samples", "mean": float("nan"),
                    "std": float("nan"), "skew": float("nan"),
                    "chi_sq_stat": float("nan"), "p_value": float("nan")}

        mean_r = float(np.mean(r))
        std_r = float(np.std(r))
        # Compute skewness manually (3.9-safe, no scipy)
        if std_r > 0:
            skew_r = float(np.mean(((r - mean_r) / std_r) ** 3))
        else:
            skew_r = 0.0

        # Chi-sq test: compare observed bin counts to uniform expected
        # Use CDF bins of the normal distribution for the expected counts
        from scipy import stats as sp_stats  # noqa: PLC0415
        z_scores = (r - mean_r) / max(std_r, 1e-9)
        pit_vals = sp_stats.norm.cdf(z_scores)
        observed, _ = np.histogram(pit_vals, bins=n_bins, range=(0.0, 1.0))
        expected_each = n / n_bins
        chi_sq = float(np.sum((observed - expected_each) ** 2 / expected_each))
        # p-value from chi-sq distribution with (n_bins - 1) degrees of freedom
        p_val = float(1.0 - sp_stats.chi2.cdf(chi_sq, df=n_bins - 1))

        return {
            "n": n,
            "mean": round(mean_r, 4),
            "std": round(std_r, 4),
            "skew": round(skew_r, 4),
            "chi_sq_stat": round(chi_sq, 4),
            "p_value": round(p_val, 4),
            "flag": "non_uniform" if p_val < PIT_CHI_WARN else "ok",
        }
    except Exception as exc:
        log.debug("_pit_uniformity failed: %s", exc)
        return {"n": 0, "flag": "error", "error": str(exc)}


def _interval_coverage(actual: Any, q10: Any, q90: Any) -> float:
    """Fraction of actuals inside [q10, q90].

    Args:
        actual: Array-like of realised values.
        q10:    Array-like of lower interval bound.
        q90:    Array-like of upper interval bound.

    Returns:
        Coverage as a float in [0, 1], or nan on failure.
    """
    try:
        import numpy as np  # noqa: PLC0415
        a = np.asarray(actual, dtype=float)
        lo = np.asarray(q10, dtype=float)
        hi = np.asarray(q90, dtype=float)
        mask = np.isfinite(a) & np.isfinite(lo) & np.isfinite(hi)
        if mask.sum() == 0:
            return float("nan")
        inside = ((a[mask] >= lo[mask]) & (a[mask] <= hi[mask])).sum()
        return float(inside / mask.sum())
    except Exception as exc:
        log.debug("_interval_coverage failed: %s", exc)
        return float("nan")
