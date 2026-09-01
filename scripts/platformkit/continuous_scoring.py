"""Proper scoring and uncertainty checks for continuous forecasting targets.

CRPS is the battery scalar for continuous targets from now on; MAE stays only
as a legacy comparator.  These metrics assess forecast accuracy and interval
calibration only, not betting edge or return.
"""
from __future__ import annotations

from math import ceil, sqrt
from typing import Sequence

import numpy as np
from scipy.special import ndtr


ArrayLike = Sequence[float] | np.ndarray | float


def _finite_1d(values: ArrayLike, name: str) -> np.ndarray:
    """Return a finite one-dimensional float array."""
    array = np.asarray(values, dtype=float)
    if array.ndim != 1:
        raise ValueError("{} must be one-dimensional.".format(name))
    if not np.all(np.isfinite(array)):
        raise ValueError("{} must contain only finite values.".format(name))
    return array


def crps_sample(forecast_samples: ArrayLike, observed: ArrayLike) -> float:
    """Return mean empirical CRPS using the energy form.

    ``forecast_samples`` is ``(n_observations, n_samples)`` or one-dimensional
    for one observation.  The empirical distribution assigns equal mass to
    every sample: E|X-y| - 0.5 E|X-X'|.  Lower is better.
    """
    samples = np.asarray(forecast_samples, dtype=float)
    obs = np.asarray(observed, dtype=float)
    if samples.ndim == 1:
        samples = samples[None, :]
    if samples.ndim != 2 or samples.shape[1] == 0:
        raise ValueError("forecast_samples must have shape (n, n_samples) with n_samples > 0.")
    obs = np.atleast_1d(obs)
    if obs.ndim != 1 or obs.size != samples.shape[0]:
        raise ValueError("observed length must match the number of forecast rows.")
    if not np.all(np.isfinite(samples)) or not np.all(np.isfinite(obs)):
        raise ValueError("forecast_samples and observed must contain only finite values.")
    observation_term = np.mean(np.abs(samples - obs[:, None]), axis=1)
    pairwise_term = np.mean(np.abs(samples[:, :, None] - samples[:, None, :]), axis=(1, 2))
    return float(np.mean(observation_term - 0.5 * pairwise_term))


def crps_gaussian(mu: ArrayLike, sigma: ArrayLike, observed: ArrayLike) -> float:
    """Return mean closed-form CRPS for normal forecasts; lower is better."""
    mean, std, obs = np.broadcast_arrays(
        np.asarray(mu, dtype=float), np.asarray(sigma, dtype=float), np.asarray(observed, dtype=float)
    )
    if not (np.all(np.isfinite(mean)) and np.all(np.isfinite(std)) and np.all(np.isfinite(obs))):
        raise ValueError("mu, sigma, and observed must contain only finite values.")
    if np.any(std <= 0.0):
        raise ValueError("sigma must be strictly positive.")
    z = (obs - mean) / std
    density = np.exp(-0.5 * z * z) / sqrt(2.0 * np.pi)
    scores = std * (z * (2.0 * ndtr(z) - 1.0) + 2.0 * density - 1.0 / sqrt(np.pi))
    return float(np.mean(scores))


def conformal_intervals(
    residuals_calib: ArrayLike, predictions: ArrayLike, alpha: float = 0.1
) -> tuple[np.ndarray, np.ndarray]:
    """Construct split-conformal intervals with finite-sample correction.

    Residuals are converted to absolute nonconformity scores.  The radius is
    the ``ceil((n + 1) * (1 - alpha))`` order statistic, capped at ``n``.
    """
    if not 0.0 < alpha < 1.0:
        raise ValueError("alpha must be in (0, 1).")
    residuals = np.abs(_finite_1d(residuals_calib, "residuals_calib"))
    if residuals.size == 0:
        raise ValueError("residuals_calib must not be empty.")
    predictions_array = np.asarray(predictions, dtype=float)
    if not np.all(np.isfinite(predictions_array)):
        raise ValueError("predictions must contain only finite values.")
    rank = min(int(ceil((residuals.size + 1) * (1.0 - alpha))), residuals.size)
    radius = float(np.sort(residuals)[rank - 1])
    return predictions_array - radius, predictions_array + radius


def coverage_report(
    intervals: tuple[ArrayLike, ArrayLike], observed: ArrayLike, nominal: float = 0.9,
    tolerance: float = 0.05,
) -> dict[str, float | int | str]:
    """Report empirical coverage and flag intervals materially below nominal."""
    if not 0.0 < nominal < 1.0:
        raise ValueError("nominal must be in (0, 1).")
    if tolerance < 0.0:
        raise ValueError("tolerance must be non-negative.")
    lower, upper = (np.asarray(bound, dtype=float) for bound in intervals)
    obs = np.asarray(observed, dtype=float)
    lower, upper, obs = np.broadcast_arrays(lower, upper, obs)
    if obs.size == 0:
        raise ValueError("intervals and observed must not be empty.")
    if not (np.all(np.isfinite(lower)) and np.all(np.isfinite(upper)) and np.all(np.isfinite(obs))):
        raise ValueError("intervals and observed must contain only finite values.")
    if np.any(lower > upper):
        raise ValueError("interval lower bounds must not exceed upper bounds.")
    coverage = float(np.mean((lower <= obs) & (obs <= upper)))
    return {
        "coverage": coverage,
        "mean_width": float(np.mean(upper - lower)),
        "nominal_coverage": float(nominal),
        "gap": float(coverage - nominal),
        "n": int(obs.size),
        "verdict": "UNDERCOVER" if coverage < nominal - tolerance else "PASS",
    }


def score_model(
    pred_mu: ArrayLike, pred_sigma: ArrayLike, observed: ArrayLike, residuals_calib: ArrayLike,
    alpha: float = 0.1, coverage_tolerance: float = 0.05,
) -> dict[str, object]:
    """Bundle Gaussian CRPS, legacy MAE, and split-conformal interval diagnostics."""
    mean, std, obs = np.broadcast_arrays(
        np.asarray(pred_mu, dtype=float), np.asarray(pred_sigma, dtype=float), np.asarray(observed, dtype=float)
    )
    lower, upper = conformal_intervals(residuals_calib, mean, alpha=alpha)
    report = coverage_report((lower, upper), obs, nominal=1.0 - alpha, tolerance=coverage_tolerance)
    return {
        "crps_gaussian": crps_gaussian(mean, std, obs),
        "mae_legacy": float(np.mean(np.abs(mean - obs))),
        "alpha": float(alpha),
        "conformal_lower": lower,
        "conformal_upper": upper,
        "coverage": report,
    }
