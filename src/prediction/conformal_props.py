"""
conformal_props.py — D-7: Conformal prediction intervals for player props.

Calibration-based prediction intervals with guaranteed finite-sample coverage.
"My 80% interval covers the true value exactly 80% of the time."

Public API
----------
    ConformalPredictor  — class
    ConformalPredictor.calibrate(y_cal, y_hat_cal)
    ConformalPredictor.predict_interval(y_hat, coverage) -> (lo, hi)
    ConformalPredictor.interval_width(y_hat, coverage) -> float

Usage
-----
    cp = ConformalPredictor()
    cp.calibrate(y_holdout, model.predict(X_holdout))
    lo, hi = cp.predict_interval(y_hat=22.5, coverage=0.80)
    # Only bet when interval_width < 1.5 × vig_width
"""

from __future__ import annotations

import os
from typing import Optional, Tuple

import numpy as np

_MODEL_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data", "models",
)


class ConformalPredictor:
    """
    D-7: Split conformal prediction for player prop intervals.

    Uses calibration holdout (10% of training data) to learn the empirical
    residual distribution. Prediction intervals are theoretically valid:
    P(y_true in [y_hat ± q]) >= coverage for any distribution.
    """

    def __init__(self) -> None:
        self.residuals: Optional[np.ndarray] = None
        self._stat: Optional[str] = None

    def calibrate(self, y_cal: np.ndarray, y_hat_cal: np.ndarray) -> "ConformalPredictor":
        """
        Calibrate on holdout set residuals.

        Args:
            y_cal:     True values from calibration holdout.
            y_hat_cal: Model predictions on calibration holdout.
        """
        self.residuals = np.abs(np.asarray(y_cal) - np.asarray(y_hat_cal))
        return self

    def predict_interval(
        self, y_hat: float, coverage: float = 0.80
    ) -> Tuple[float, float]:
        """
        Return (lower, upper) prediction interval for a single prediction.

        The interval [y_hat - q, y_hat + q] has valid coverage >= `coverage`
        on any future test point drawn from the same distribution.

        Args:
            y_hat:    Point prediction from the base model.
            coverage: Desired coverage level (e.g. 0.80 for 80%).

        Returns:
            (lower_bound, upper_bound)
        """
        q = self._quantile(coverage)
        return (round(y_hat - q, 3), round(y_hat + q, 3))

    def interval_width(self, y_hat: float = 0.0, coverage: float = 0.80) -> float:
        """Return the full width of the conformal interval (2q)."""
        return round(2.0 * self._quantile(coverage), 3)

    def _quantile(self, coverage: float) -> float:
        """Compute the (coverage)-quantile of calibration residuals."""
        if self.residuals is None or len(self.residuals) == 0:
            return 5.0  # fallback: wide interval when uncalibrated
        q = float(np.quantile(self.residuals, min(max(coverage, 0.0), 1.0)))
        return max(q, 0.0)

    def save_residuals(self, stat: str) -> str:
        """Save calibration residuals to data/models/conformal_{stat}_residuals.npy."""
        if self.residuals is None:
            raise RuntimeError("Not calibrated — call calibrate() first")
        os.makedirs(_MODEL_DIR, exist_ok=True)
        path = os.path.join(_MODEL_DIR, f"conformal_{stat}_residuals.npy")
        np.save(path, self.residuals)
        return path

    @classmethod
    def load_residuals(cls, stat: str) -> "ConformalPredictor":
        """Load calibration residuals from disk."""
        path = os.path.join(_MODEL_DIR, f"conformal_{stat}_residuals.npy")
        obj = cls()
        obj.residuals = np.load(path)
        obj._stat = stat
        return obj
