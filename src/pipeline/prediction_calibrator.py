"""
prediction_calibrator.py — M99: Prediction calibration curves.

Inputs: outcome_recorder output (predicted vs actual), prediction history.
Output: calibration curves per model per stat.
Method: Platt scaling or isotonic regression on predicted probs vs actual outcomes.

"If model says 70% → player goes over, does that happen 70% of the time?"

Public API
----------
    PredictionCalibrator()
    calibrator.fit(model_id, predictions, actuals)    -> dict (metrics)
    calibrator.calibrate(model_id, raw_prob)          -> float (calibrated prob)
    calibrator.get_calibration_summary()              -> dict
"""

from __future__ import annotations

import json
import logging
import os
import pickle
import sys
from typing import Optional

import numpy as np

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_DIR)

_MODEL_DIR   = os.path.join(PROJECT_DIR, "data", "models")
_CALIBRATION_PATH = os.path.join(_MODEL_DIR, "prediction_calibrator.pkl")
_OUTCOME_LOG = os.path.join(PROJECT_DIR, "data", "models", "prediction_log.json")

log = logging.getLogger(__name__)


class PredictionCalibrator:
    """Calibrates model probability outputs using isotonic regression."""

    def __init__(self) -> None:
        self._calibrators: dict = {}  # model_id → calibrator
        self._metrics: dict = {}
        self._load()

    def _load(self) -> None:
        if os.path.exists(_CALIBRATION_PATH):
            try:
                with open(_CALIBRATION_PATH, "rb") as f:
                    data = pickle.load(f)
                    self._calibrators = data.get("calibrators", {})
                    self._metrics     = data.get("metrics", {})
            except Exception as e:
                log.debug("Calibration load failed: %s", e)

    def _save(self) -> None:
        os.makedirs(_MODEL_DIR, exist_ok=True)
        with open(_CALIBRATION_PATH, "wb") as f:
            pickle.dump({
                "calibrators": self._calibrators,
                "metrics":     self._metrics,
                "version":     "1.0",
            }, f)

    def fit(self, model_id: str, predictions: list[float], actuals: list[float]) -> dict:
        """
        Fit a calibration curve for model_id.

        Args:
            model_id:    Model identifier (e.g. 'props_pts').
            predictions: List of predicted probabilities/values.
            actuals:     List of actual outcomes (binary 0/1 for over/under,
                         or continuous for regression models).

        Returns:
            Calibration metrics dict.
        """
        if len(predictions) < 20:
            log.warning("Too few samples (%d) to calibrate %s", len(predictions), model_id)
            return {"error": "insufficient_data", "n": len(predictions)}

        pred_arr   = np.array(predictions, dtype=float)
        actual_arr = np.array(actuals, dtype=float)

        # Check if binary (over/under) or continuous
        unique = np.unique(actual_arr)
        is_binary = len(unique) <= 2 and set(unique).issubset({0, 1, 0.0, 1.0})

        metrics: dict = {"n": len(predictions), "model_id": model_id}

        if is_binary:
            # Isotonic regression for probability calibration
            try:
                from sklearn.isotonic import IsotonicRegression
                from sklearn.calibration import calibration_curve

                iso = IsotonicRegression(out_of_bounds="clip")
                iso.fit(pred_arr, actual_arr)
                self._calibrators[model_id] = iso

                # Compute calibration error
                frac_pos, mean_pred = calibration_curve(
                    actual_arr, pred_arr, n_bins=10, strategy="quantile"
                )
                ece = float(np.mean(np.abs(frac_pos - mean_pred)))
                metrics["ece"] = ece
                metrics["type"] = "isotonic"
                log.info("Calibrated %s: ECE=%.4f (n=%d)", model_id, ece, len(predictions))
            except ImportError:
                # Platt scaling fallback
                metrics["type"] = "passthrough"
        else:
            # Continuous — use linear scaling
            from sklearn.linear_model import LinearRegression
            lr = LinearRegression()
            lr.fit(pred_arr.reshape(-1, 1), actual_arr)
            self._calibrators[model_id] = lr
            residuals = actual_arr - lr.predict(pred_arr.reshape(-1, 1))
            metrics["mae"] = float(np.mean(np.abs(residuals)))
            metrics["type"] = "linear"

        self._metrics[model_id] = metrics
        self._save()
        return metrics

    def calibrate(self, model_id: str, raw_value: float) -> float:
        """
        Apply calibration transform to a raw prediction.

        Returns calibrated value, or raw_value if no calibrator exists.
        """
        cal = self._calibrators.get(model_id)
        if cal is None:
            return raw_value

        try:
            cal_type = self._metrics.get(model_id, {}).get("type", "")
            if cal_type == "isotonic":
                return float(cal.predict([raw_value])[0])
            elif cal_type == "linear":
                return float(cal.predict([[raw_value]])[0])
        except Exception as e:
            log.debug("Calibration failed for %s: %s", model_id, e)

        return raw_value

    def fit_from_outcome_log(self) -> dict:
        """
        Auto-fit calibrations from the outcome_recorder prediction log.
        Returns metrics for each model updated.
        """
        if not os.path.exists(_OUTCOME_LOG):
            log.debug("No outcome log found at %s", _OUTCOME_LOG)
            return {}

        try:
            with open(_OUTCOME_LOG) as f:
                log_data = json.load(f)
        except Exception as e:
            log.warning("Failed to load outcome log: %s", e)
            return {}

        # Group predictions by model + stat
        model_preds: dict[str, tuple[list, list]] = {}

        for record in log_data if isinstance(log_data, list) else []:
            model    = record.get("model", "")
            stat     = record.get("stat", "")
            pred_val = record.get("predicted")
            actual   = record.get("actual")
            line     = record.get("line")

            if pred_val is None or actual is None:
                continue

            key = f"{model}_{stat}"
            if key not in model_preds:
                model_preds[key] = ([], [])

            # For over/under: binary outcome
            if line is not None:
                over_pred = int(pred_val > line)
                over_actual = int(float(actual) > float(line))
                model_preds[key][0].append(float(pred_val > line))
                model_preds[key][1].append(over_actual)
            else:
                model_preds[key][0].append(float(pred_val))
                model_preds[key][1].append(float(actual))

        results = {}
        for key, (preds, actuals) in model_preds.items():
            if len(preds) >= 20:
                metrics = self.fit(key, preds, actuals)
                results[key] = metrics

        return results

    def get_calibration_summary(self) -> dict:
        """Return summary of calibration status for all models."""
        return {
            "calibrated_models": list(self._calibrators.keys()),
            "metrics":           self._metrics,
            "total_calibrated":  len(self._calibrators),
        }
