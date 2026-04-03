"""
segment_calibrator.py — D-8: Per-segment Platt calibration for prop probabilities.

Separate calibration curves for contextual segments (star players, B2B games,
post-injury returns, etc.) ensure that P(over | model=70%) = 70% within each
segment, not just globally.

Public API
----------
    SegmentCalibrator  — class
    SegmentCalibrator.fit_segment(segment_name, y_proba, y_true)
    SegmentCalibrator.calibrate(y_proba, segment_name) -> float
    SegmentCalibrator.save(path) / load(path)

Segments
--------
    star, role, b2b, early_season, home, road, post_injury, post_trade

Usage
-----
    sc = SegmentCalibrator()
    sc.fit_segment('b2b', b2b_proba, b2b_outcomes)
    p_cal = sc.calibrate(0.70, 'b2b')  # calibrated P(over) for B2B game
"""

from __future__ import annotations

import os
import pickle
from typing import Optional

import numpy as np

_MODEL_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data", "models",
)

SEGMENTS = [
    "star",
    "role",
    "b2b",
    "early_season",
    "home",
    "road",
    "post_injury",
    "post_trade",
]


class SegmentCalibrator:
    """
    D-8: Logistic Platt calibration per contextual segment.

    Each segment gets its own sigmoid calibration curve fit on historical
    prop outcomes. A confidence of 70% in B2B games should hit 70% of the
    time in B2B games specifically, not just globally.
    """

    def __init__(self) -> None:
        self.calibrators: dict = {}  # {segment_name: LogisticRegression}

    def fit_segment(
        self,
        segment_name: str,
        y_proba: np.ndarray,
        y_true: np.ndarray,
    ) -> "SegmentCalibrator":
        """
        Fit a Platt scaler for the given segment.

        Args:
            segment_name: One of SEGMENTS.
            y_proba:      Raw model probabilities (n_samples,).
            y_true:       Binary outcomes (n_samples,) — 1=over, 0=under.
        """
        from sklearn.linear_model import LogisticRegression

        X = np.asarray(y_proba, dtype=float).reshape(-1, 1)
        y = np.asarray(y_true, dtype=int)

        if len(np.unique(y)) < 2:
            return self  # cannot calibrate with single class

        lr = LogisticRegression(C=1e5, solver="lbfgs", max_iter=1000, random_state=42)
        lr.fit(X, y)
        self.calibrators[segment_name] = lr
        return self

    def calibrate(self, y_proba: float, segment_name: str) -> float:
        """
        Apply segment-specific calibration to a raw probability.

        Args:
            y_proba:      Raw model probability in [0, 1].
            segment_name: Segment identifier.

        Returns:
            Calibrated probability in [0, 1].
            If segment not calibrated, returns y_proba unchanged.
        """
        if segment_name not in self.calibrators:
            return float(y_proba)
        try:
            lr = self.calibrators[segment_name]
            X = np.array([[float(y_proba)]])
            return float(lr.predict_proba(X)[0][1])
        except Exception:
            return float(y_proba)

    def save(self, path: Optional[str] = None) -> str:
        """Save calibrators to disk."""
        if path is None:
            path = os.path.join(_MODEL_DIR, "segment_calibrator.pkl")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            pickle.dump({"calibrators": self.calibrators, "segments": SEGMENTS}, f)
        return path

    @classmethod
    def load(cls, path: Optional[str] = None) -> "SegmentCalibrator":
        """Load calibrators from disk."""
        if path is None:
            path = os.path.join(_MODEL_DIR, "segment_calibrator.pkl")
        with open(path, "rb") as f:
            data = pickle.load(f)
        obj = cls()
        obj.calibrators = data.get("calibrators", {})
        return obj
