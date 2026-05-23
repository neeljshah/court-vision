"""
conformal_games.py — Split-conformal prediction intervals for game-level outputs.

Five models covered:
  - total        (regression) — total points scored
  - spread       (regression) — point differential home - away
  - first_half   (regression) — first-half total points
  - blowout_prob (classification) — P(|spread| > 15)
  - ot_prob      (classification) — P(OT)

For regression: signed residuals → lower (q10/q025) and upper (q90/q975) quantiles.
For classification: conformity = |predicted_prob - actual| → one-sided q90/q975.

Persisted format (data/models/conformal_games.json):
  {"total": {"q10": -10.2, "q90": 11.5, "q025": -16.8, "q975": 18.3, "n": 1225},
   "blowout_prob": {"q90_residual": 0.18, "q975_residual": 0.23, "n": 1225}, ...}

Usage
-----
    gc = GameConformalIntervals()
    gc.fit(predictions, actuals)          # calibrate from holdout arrays
    gc.save()                             # -> data/models/conformal_games.json

    gc2 = GameConformalIntervals.load()   # reload from JSON
    ivs = gc2.intervals({"total": 218.5, "spread": -4.5, ...}, level=0.80)
    # -> {"total": (208.3, 229.7), "spread": (-13.0, 4.0), ...}
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Dict, Optional, Tuple

import numpy as np

_PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_MODEL_DIR = os.path.join(_PROJECT_DIR, "data", "models")
_CONFORMAL_PATH = os.path.join(_MODEL_DIR, "conformal_games.json")

# Regression outputs use signed residuals (pred - actual).
_REGRESSION_KEYS = ("total", "spread", "first_half")
# Classification outputs use |pred_prob - actual_label| as conformity score.
_CLASSIFICATION_KEYS = ("blowout_prob", "ot_prob")
_ALL_KEYS = _REGRESSION_KEYS + _CLASSIFICATION_KEYS


class GameConformalIntervals:
    """
    Split-conformal prediction intervals for the 5 game-level model outputs.

    Fit once on a held-out calibration set, then call intervals() per prediction.
    Guarantees marginal coverage: P(y_true in interval) >= level for any future
    game drawn from the same distribution (finite-sample validity).
    """

    def __init__(self, model_dir: str = _MODEL_DIR) -> None:
        self.model_dir = model_dir
        # Regression: signed residuals (prediction - actual) sorted arrays
        self._reg_residuals: Dict[str, np.ndarray] = {}
        # Classification: absolute conformity scores sorted arrays
        self._clf_scores: Dict[str, np.ndarray] = {}
        # Cached quantile table {key: {"q10": ..., "q90": ..., "q025": ..., "q975": ..., "n": ...}}
        self._quantiles: Dict[str, dict] = {}

    # ── Public fit / save / load ───────────────────────────────────────────────

    def fit(
        self,
        predictions: Dict[str, np.ndarray],
        actuals: Dict[str, np.ndarray],
    ) -> "GameConformalIntervals":
        """
        Calibrate conformal quantiles from holdout predictions and actuals.

        Args:
            predictions: dict of arrays, keys from _ALL_KEYS.
                         Regression values are floats; classification values are
                         probabilities in [0, 1].
            actuals:     dict of arrays, same shape. Classification actuals are
                         binary labels {0, 1}.
        """
        self._reg_residuals.clear()
        self._clf_scores.clear()
        self._quantiles.clear()

        for key in _REGRESSION_KEYS:
            if key not in predictions or key not in actuals:
                continue
            preds = np.asarray(predictions[key], dtype=float)
            acts = np.asarray(actuals[key], dtype=float)
            valid = np.isfinite(preds) & np.isfinite(acts)
            if valid.sum() < 10:
                continue
            residuals = preds[valid] - acts[valid]  # signed: pred minus actual
            self._reg_residuals[key] = np.sort(residuals)
            n = len(residuals)
            self._quantiles[key] = {
                "q10":  round(float(np.quantile(residuals, 0.10)), 4),
                "q90":  round(float(np.quantile(residuals, 0.90)), 4),
                "q025": round(float(np.quantile(residuals, 0.025)), 4),
                "q975": round(float(np.quantile(residuals, 0.975)), 4),
                "n":    int(n),
            }

        for key in _CLASSIFICATION_KEYS:
            if key not in predictions or key not in actuals:
                continue
            preds = np.asarray(predictions[key], dtype=float)
            acts = np.asarray(actuals[key], dtype=float)
            valid = np.isfinite(preds) & np.isfinite(acts)
            if valid.sum() < 10:
                continue
            scores = np.abs(preds[valid] - acts[valid])  # conformity = |p - y|
            self._clf_scores[key] = np.sort(scores)
            n = len(scores)
            self._quantiles[key] = {
                "q90_residual":  round(float(np.quantile(scores, 0.90)), 4),
                "q975_residual": round(float(np.quantile(scores, 0.975)), 4),
                "n":             int(n),
            }

        return self

    def save(self, path: Optional[str] = None) -> str:
        """Persist quantile tables to JSON. Returns the path written."""
        if not self._quantiles:
            raise RuntimeError("Not fitted — call fit() first")
        out_path = path or _CONFORMAL_PATH
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        payload = dict(self._quantiles)
        payload["computed_at"] = datetime.utcnow().isoformat()
        with open(out_path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2)
        return out_path

    @classmethod
    def load(cls, path: Optional[str] = None) -> "GameConformalIntervals":
        """Load a previously saved GameConformalIntervals from JSON."""
        load_path = path or _CONFORMAL_PATH
        if not os.path.exists(load_path):
            raise FileNotFoundError(
                f"conformal_games.json not found at {load_path}. "
                "Run scripts/calibrate_game_conformal.py first."
            )
        with open(load_path, encoding="utf-8") as fh:
            data = json.load(fh)
        obj = cls()
        for key in _ALL_KEYS:
            if key in data:
                obj._quantiles[key] = data[key]
        return obj

    # ── Public interval API ────────────────────────────────────────────────────

    def intervals(
        self,
        predictions: Dict[str, float],
        level: float = 0.80,
    ) -> Dict[str, Tuple[float, float]]:
        """
        Return conformal prediction intervals for each output.

        Args:
            predictions: {key: point_prediction} for any subset of the 5 outputs.
            level:       Coverage level — 0.80 (default) or 0.95.

        Returns:
            dict mapping each key to (lower_bound, upper_bound).
            For classification keys, bounds are clamped to [0, 1].
        """
        result: Dict[str, Tuple[float, float]] = {}

        # Select quantile suffix based on level
        if abs(level - 0.95) < 0.01:
            lo_q, hi_q = "q025", "q975"
            clf_q = "q975_residual"
        else:
            # Default: 80%
            lo_q, hi_q = "q10", "q90"
            clf_q = "q90_residual"

        for key, pred in predictions.items():
            if key not in _ALL_KEYS:
                continue
            qt = self._quantiles.get(key)
            if qt is None:
                result[key] = self._fallback(key, float(pred))
                continue

            pred = float(pred)
            if key in _REGRESSION_KEYS:
                # Interval: [pred - q_upper_residual, pred - q_lower_residual]
                # q10 is the 10th pct of (pred-actual), so actual = pred - residual
                # lower bound: pred - q90 (subtract the large positive residual)
                # upper bound: pred - q10 (subtract the large negative residual)
                lo = round(pred - qt[hi_q], 3)
                hi = round(pred - qt[lo_q], 3)
                result[key] = (lo, hi)
            else:
                # Classification: symmetric interval around pred ± conformity quantile
                hw = float(qt.get(clf_q, 0.1))
                lo = round(max(0.0, pred - hw), 4)
                hi = round(min(1.0, pred + hw), 4)
                result[key] = (lo, hi)

        return result

    def coverage_check(
        self,
        predictions: Dict[str, np.ndarray],
        actuals: Dict[str, np.ndarray],
        level: float = 0.80,
    ) -> Dict[str, float]:
        """
        Compute empirical coverage on a test set.
        Returns {key: coverage_fraction} — should be >= level.
        """
        coverage: Dict[str, float] = {}
        for key in _ALL_KEYS:
            if key not in predictions or key not in actuals:
                continue
            preds = np.asarray(predictions[key], dtype=float)
            acts = np.asarray(actuals[key], dtype=float)
            valid = np.isfinite(preds) & np.isfinite(acts)
            if valid.sum() < 2:
                continue
            ivs_list = [
                self.intervals({key: float(p)}, level=level).get(key)
                for p in preds[valid]
            ]
            covered = sum(
                1 for (lo, hi), a in zip(ivs_list, acts[valid])
                if lo <= a <= hi
            )
            coverage[key] = round(covered / valid.sum(), 4)
        return coverage

    # ── Fallback when not calibrated ──────────────────────────────────────────

    @staticmethod
    def _fallback(key: str, pred: float) -> Tuple[float, float]:
        """Heuristic interval when no calibration data is available."""
        defaults = {
            "total":       14.0,
            "spread":      11.0,
            "first_half":  7.0,
            "blowout_prob": 0.15,
            "ot_prob":      0.04,
        }
        hw = defaults.get(key, 10.0)
        if key in _CLASSIFICATION_KEYS:
            return (round(max(0.0, pred - hw), 4), round(min(1.0, pred + hw), 4))
        return (round(pred - hw, 3), round(pred + hw, 3))
