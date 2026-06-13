"""scripts/platformkit/calibration_ladder.py — Shared calibration ladder.

Extends walk_forward_recalibrate (isotonic, recalibration.py) with:
  - walk_forward_platt   : leak-free walk-forward Platt scaling
  - walk_forward_auto    : auto-select isotonic vs Platt by walk-forward log-loss
  - conformal_interval   : split-conformal absolute-residual predictive band
  - reliability          : Brier / log-loss / ECE / slope scorecard
  - crps_binary / crps_mean : CRPS (== Brier per-event for binary outcomes)

HONESTY: calibration != edge.  Better-calibrated probabilities do NOT imply
beating the closing line or a positive expected value.
See: feedback_accuracy_is_not_edge.md.
"""
from __future__ import annotations

from typing import Sequence, Tuple

import numpy as np
from sklearn.linear_model import LogisticRegression

from scripts.platformkit.recalibration import (
    CALIBRATION_NOTE,
    _ece,
    walk_forward_recalibrate,
)

__all__ = [
    "walk_forward_platt",
    "walk_forward_auto",
    "conformal_interval",
    "reliability",
    "crps_binary",
    "crps_mean",
    "CALIBRATION_NOTE",
]

_EPS: float = 1e-15  # clip before log to avoid -inf


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _logit(p: np.ndarray) -> np.ndarray:
    """Safe logit; NaN inputs stay NaN."""
    p = np.clip(p, _EPS, 1.0 - _EPS)
    return np.log(p / (1.0 - p))


def _logloss_vec(probs: np.ndarray, outcomes: np.ndarray) -> np.ndarray:
    """Per-event binary log-loss (NaN-safe)."""
    p = np.clip(probs, _EPS, 1.0 - _EPS)
    y = outcomes
    return -(y * np.log(p) + (1.0 - y) * np.log(1.0 - p))


# ---------------------------------------------------------------------------
# walk_forward_platt
# ---------------------------------------------------------------------------


def walk_forward_platt(
    raw_probs: Sequence[float],
    outcomes: Sequence[float],
    min_history: int = 50,
    refit_every: int = 1,
) -> np.ndarray:
    """Strictly leak-free walk-forward Platt scaling.

    Fits a 1-D logistic regression on logit(raw[:i]) → outcome[:i] for each
    event i, using only strictly-prior observations.  Events before min_history
    pass through raw unchanged.  NaN/inf entries are dropped from the fit
    window; invalid query points pass through raw.

    ``refit_every`` mirrors walk_forward_recalibrate semantics: refit every K
    events (leak-free for any K >= 1).  K=1 is per-row refit.

    Returns (N,) array clipped to [0, 1].
    calibration != edge.
    """
    p = np.asarray(raw_probs, dtype=float)
    y = np.asarray(outcomes, dtype=float)
    n = len(p)
    if n != len(y):
        raise ValueError(
            f"raw_probs and outcomes must have equal length ({n} vs {len(y)})"
        )
    step = max(1, int(refit_every))

    calibrated = np.empty(n, dtype=float)
    lr: LogisticRegression | None = None
    next_fit = min_history

    for i in range(n):
        if i < min_history:
            calibrated[i] = float(p[i])
            continue

        if i >= next_fit:
            # Build training window: strictly prior events, valid only.
            valid = np.isfinite(p[:i]) & np.isfinite(y[:i])
            if valid.sum() >= 2 and len(np.unique(y[:i][valid])) >= 2:
                X_tr = _logit(p[:i][valid]).reshape(-1, 1)
                y_tr = y[:i][valid]
                lr = LogisticRegression(C=1e9, solver="lbfgs", max_iter=500)
                lr.fit(X_tr, y_tr)
            next_fit = i + step

        if lr is not None and np.isfinite(p[i]):
            x_q = _logit(np.array([p[i]])).reshape(-1, 1)
            calibrated[i] = float(lr.predict_proba(x_q)[0, 1])
        else:
            calibrated[i] = float(p[i])

    return np.clip(calibrated, 0.0, 1.0)


# ---------------------------------------------------------------------------
# walk_forward_auto
# ---------------------------------------------------------------------------


def walk_forward_auto(
    raw_probs: Sequence[float],
    outcomes: Sequence[float],
    min_history: int = 50,
    refit_every: int = 1,
) -> Tuple[np.ndarray, str]:
    """Auto-select isotonic vs Platt by walk-forward log-loss.

    Runs both walk_forward_recalibrate (isotonic) and walk_forward_platt on
    the same (raw_probs, outcomes) sequence.  Computes mean log-loss on the
    post-warmup portion (i >= min_history) of each calibrated output — strictly
    walk-forward so leak-free.  Returns (chosen_array, method_name) where
    method_name is 'isotonic' or 'platt'.

    calibration != edge.
    """
    p = np.asarray(raw_probs, dtype=float)
    y = np.asarray(outcomes, dtype=float)

    iso = walk_forward_recalibrate(p, y, min_history=min_history,
                                   refit_every=refit_every)
    platt = walk_forward_platt(p, y, min_history=min_history,
                               refit_every=refit_every)

    # Evaluate only on post-warmup events with valid outcomes.
    mask = np.arange(len(p)) >= min_history
    mask &= np.isfinite(y) & np.isfinite(iso) & np.isfinite(platt)

    if not mask.any():
        # Fallback: not enough data to choose — prefer isotonic.
        return iso, "isotonic"

    ll_iso = float(_logloss_vec(iso[mask], y[mask]).mean())
    ll_platt = float(_logloss_vec(platt[mask], y[mask]).mean())

    if ll_platt < ll_iso:
        return platt, "platt"
    return iso, "isotonic"


# ---------------------------------------------------------------------------
# conformal_interval
# ---------------------------------------------------------------------------


def conformal_interval(
    point: float,
    residuals_prior: Sequence[float],
    alpha: float = 0.1,
) -> Tuple[float, float]:
    """Split-conformal absolute-residual predictive interval.

    Given a point prediction and a pool of prior absolute residuals
    (|pred - outcome| from a calibration set strictly before this event),
    returns a (lo, hi) band that covers at least 1-alpha of future events
    under exchangeability.

    The quantile used is ceil((1-alpha)(n+1))/n — the standard finite-sample
    conformal quantile.  If the residual pool is empty, returns (0.0, 1.0).

    Designed to widen with larger residual spread (as required).
    calibration != edge.
    """
    res = np.asarray(residuals_prior, dtype=float)
    res = res[np.isfinite(res)]
    n = len(res)
    if n == 0:
        return (0.0, 1.0)

    # Finite-sample conformal quantile level.
    level = min(1.0, np.ceil((1.0 - alpha) * (n + 1)) / n)
    q = float(np.quantile(np.abs(res), level))

    lo = float(np.clip(point - q, 0.0, 1.0))
    hi = float(np.clip(point + q, 0.0, 1.0))
    return (lo, hi)


# ---------------------------------------------------------------------------
# reliability
# ---------------------------------------------------------------------------


def reliability(
    probs: Sequence[float],
    outcomes: Sequence[float],
    bins: int = 10,
) -> dict:
    """Calibration scorecard: Brier, log-loss, ECE, reliability slope, N.

    reliability_slope: slope of a linear fit of (mean_pred per bin) vs
    (mean_obs per bin), weighted by bin count.  A perfectly calibrated model
    has slope = 1.0; slope < 1 = over-confident, slope > 1 = under-confident.

    Returns dict with keys:
        brier (float), log_loss (float), ece (float),
        reliability_slope (float), n (int).

    calibration != edge.
    """
    p = np.asarray(probs, dtype=float)
    y = np.asarray(outcomes, dtype=float)
    valid = np.isfinite(p) & np.isfinite(y)
    p, y = p[valid], y[valid]
    n = int(len(p))

    if n == 0:
        return dict(brier=float("nan"), log_loss=float("nan"),
                    ece=float("nan"), reliability_slope=float("nan"), n=0)

    brier = float(np.mean((p - y) ** 2))
    ll = float(_logloss_vec(p, y).mean())
    ece_val = _ece(p, y, bins=bins)

    # Reliability-curve slope via weighted linear fit of bin centres.
    edges = np.linspace(0.0, 1.0, bins + 1)
    bin_pred, bin_obs, bin_w = [], [], []
    for i in range(bins):
        lo, hi = edges[i], edges[i + 1]
        mask = (p >= lo) & (p < hi) if i < bins - 1 else (p >= lo) & (p <= hi)
        n_bin = int(mask.sum())
        if n_bin < 2:
            continue
        bin_pred.append(float(p[mask].mean()))
        bin_obs.append(float(y[mask].mean()))
        bin_w.append(n_bin)

    if len(bin_pred) >= 2:
        bp = np.array(bin_pred)
        bo = np.array(bin_obs)
        bw = np.array(bin_w, dtype=float)
        bw /= bw.sum()
        # Weighted least-squares slope through origin not forced — standard WLS.
        x_bar = float((bw * bp).sum())
        y_bar = float((bw * bo).sum())
        num = float((bw * (bp - x_bar) * (bo - y_bar)).sum())
        den = float((bw * (bp - x_bar) ** 2).sum())
        slope = num / den if abs(den) > 1e-12 else float("nan")
    else:
        slope = float("nan")

    return dict(brier=brier, log_loss=ll, ece=ece_val,
                reliability_slope=slope, n=n)


# ---------------------------------------------------------------------------
# CRPS (binary)
# ---------------------------------------------------------------------------


def crps_binary(prob: float, outcome: float) -> float:
    """CRPS for a single binary forecast.

    For Bernoulli outcomes CRPS == Brier score per event:
        CRPS(p, y) = (p - y)^2.
    Exposed named for the distribution scorecard.
    calibration != edge.
    """
    return float((prob - outcome) ** 2)


def crps_mean(
    probs: Sequence[float],
    outcomes: Sequence[float],
) -> float:
    """Mean CRPS over a sequence of binary forecasts (== mean Brier score).

    calibration != edge.
    """
    p = np.asarray(probs, dtype=float)
    y = np.asarray(outcomes, dtype=float)
    valid = np.isfinite(p) & np.isfinite(y)
    if not valid.any():
        return float("nan")
    return float(np.mean((p[valid] - y[valid]) ** 2))
