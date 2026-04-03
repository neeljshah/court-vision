"""
quantile_props.py — D-1: Quantile regression wrapper for player props.

Trains GradientBoostingRegressor at 5 quantile levels per stat, enabling
direct P(stat > line) computation without Gaussian assumptions.

Public API
----------
    QuantilePropsModel  — class
    build_quantile_models()  — entry point (does NOT run training automatically)

Usage
-----
    from src.prediction.quantile_props import QuantilePropsModel
    qm = QuantilePropsModel()
    qm.train(X_train, y_train, stat='pts')
    prob = qm.predict_proba_over(X_test, line=20.5)  # P(pts > 20.5)
    qm.save('data/models/quantile_props_pts.pkl')
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


class QuantilePropsModel:
    """
    D-1: Quantile regression model for player prop distributions.

    Trains GradientBoostingRegressor at each of 5 quantile levels:
      0.10 (floor), 0.25, 0.50 (median), 0.75, 0.90 (ceiling)

    predict_proba_over() interpolates the quantile curve to return
    P(stat > line) without assuming a Gaussian distribution.
    """

    QUANTILES = [0.10, 0.25, 0.50, 0.75, 0.90]

    def __init__(self) -> None:
        self._models: dict = {}   # {quantile: fitted GBR}
        self._stat: Optional[str] = None

    # ── Training ───────────────────────────────────────────────────────────────

    def train(self, X, y, stat: str = "pts") -> "QuantilePropsModel":
        """
        Train one GradientBoostingRegressor per quantile level.

        Args:
            X:    Feature matrix (n_samples, n_features).
            y:    Target values (n_samples,).
            stat: Prop stat name (used for save path).
        """
        from sklearn.ensemble import GradientBoostingRegressor

        self._stat = stat
        y_arr = np.asarray(y, dtype=float)

        for q in self.QUANTILES:
            gbr = GradientBoostingRegressor(
                loss="quantile",
                alpha=q,
                n_estimators=200,
                max_depth=4,
                learning_rate=0.05,
                subsample=0.8,
                random_state=42,
            )
            gbr.fit(X, y_arr)
            self._models[q] = gbr

        return self

    # ── Prediction ─────────────────────────────────────────────────────────────

    def predict_quantiles(self, X) -> np.ndarray:
        """
        Return predicted quantile values for each sample.

        Returns array of shape (n_samples, 5) — one column per quantile.
        """
        if not self._models:
            raise RuntimeError("Model not trained — call train() first")
        preds = np.column_stack([
            self._models[q].predict(X) for q in self.QUANTILES
        ])
        return preds

    def predict_proba_over(self, X, line: float) -> float:
        """
        Return P(stat > line) by interpolating the quantile curve.

        Uses np.interp on the predicted quantile values.
        Returns a scalar float in [0.0, 1.0].
        """
        if not self._models:
            return 0.5

        preds = self.predict_quantiles(X)    # shape (n_samples, 5)
        n = preds.shape[0]
        probs = []

        for i in range(n):
            q_vals = preds[i]                # predicted values at each quantile
            # np.interp: find what quantile corresponds to line
            # q_vals are sorted ascending (quantiles are 0.10→0.90)
            # P(X > line) = 1 - P(X <= line) = 1 - interpolated_quantile
            q_at_line = float(np.interp(line, q_vals, self.QUANTILES))
            probs.append(max(0.0, min(1.0, 1.0 - q_at_line)))

        return float(np.mean(probs)) if len(probs) > 1 else (probs[0] if probs else 0.5)

    # ── Persistence ────────────────────────────────────────────────────────────

    def save(self, path: Optional[str] = None) -> str:
        """Pickle the dict of quantile models to disk."""
        if path is None:
            stat = self._stat or "stat"
            path = os.path.join(_MODEL_DIR, f"quantile_props_{stat}.pkl")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            pickle.dump({"models": self._models, "stat": self._stat,
                         "quantiles": self.QUANTILES}, f)
        return path

    @classmethod
    def load(cls, path: str) -> "QuantilePropsModel":
        """Load a previously saved QuantilePropsModel."""
        with open(path, "rb") as f:
            data = pickle.load(f)
        obj = cls()
        obj._models  = data["models"]
        obj._stat    = data.get("stat")
        return obj


# ── Entry point ────────────────────────────────────────────────────────────────

def build_quantile_models() -> None:
    """
    D-1: Print instructions for training quantile models.

    Does NOT auto-run training — requires retrain after Phase G 20 clean games.
    """
    _STATS = ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov")
    print("QuantilePropsModel training instructions:")
    print("  from src.prediction.quantile_props import QuantilePropsModel")
    print("  for stat in", _STATS, ":")
    print("    qm = QuantilePropsModel()")
    print("    qm.train(X_train, y_train, stat=stat)")
    print(f"    qm.save()  # saves to data/models/quantile_props_{{stat}}.pkl")
    print()
    print("Use predict_proba_over(X, line) to get P(stat > line) without Gaussian assumption.")
