"""
bridge_model.py — CV-feature to public-stat bridge for graceful degradation.

Maps CV behavioral features (defender_distance, spacing, etc.) to public stats
(efg, usage, etc.) so prediction models work when broadcast video is offline.

Public API
----------
    BridgeModel.fit(X_cv, X_pub, y)    -> self
    BridgeModel.predict(X_cv, X_pub)   -> np.ndarray
    BridgeModel.score(X_cv, X_pub, y)  -> float  (R²)
    BridgeModel.save(path)             -> None
    BridgeModel.load(path)             -> BridgeModel
"""

from __future__ import annotations

import os
import sys
import pickle
from typing import Optional, List

import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import TimeSeriesSplit
from sklearn.metrics import r2_score

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_DIR)

_MODEL_DIR = os.path.join(PROJECT_DIR, "data", "models")

# CV feature columns (from broadcast tracking)
CV_FEATURES: List[str] = [
    "defender_distance",
    "spacing",
    "paint_touches",
    "drive_frequency",
    "catch_and_shoot_rate",
    "contested_shot_rate",
    "off_ball_screens",
]

# Public stat targets (NBA Stats API)
PUBLIC_TARGETS: List[str] = [
    "efg",
    "usage",
    "ts_pct",
    "ast_ratio",
    "reb_rate",
]


class BridgeModel:
    """Regressor mapping CV features -> public stats for graceful degradation.

    When CV input is fully missing (all NaN), falls back to public-only
    mean-baseline prediction.  When CV is partially available, imputes
    missing CV features with column medians before inference.

    Parameters
    ----------
    n_estimators : int
        Trees per target regressor.
    cv_weight : float
        Blend weight [0,1] for CV sub-model vs public-only sub-model.
        Tuned automatically during fit if None.
    """

    def __init__(self, n_estimators: int = 100, cv_weight: Optional[float] = None):
        self.n_estimators = n_estimators
        self.cv_weight = cv_weight
        self._cv_models: dict = {}
        self._pub_models: dict = {}
        self._cv_scaler = StandardScaler()
        self._pub_scaler = StandardScaler()
        self._cv_medians: Optional[np.ndarray] = None
        self._pub_medians: Optional[np.ndarray] = None
        self._target_names: List[str] = []
        self._cv_feature_names: List[str] = []
        self._pub_feature_names: List[str] = []
        self._cv_weight_auto: float = 0.6
        self.is_fitted: bool = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def fit(
        self,
        X_cv: pd.DataFrame,
        X_pub: pd.DataFrame,
        y: pd.DataFrame,
    ) -> "BridgeModel":
        """Train CV-bridge and public-only sub-models per target.

        Parameters
        ----------
        X_cv : DataFrame  shape (n, n_cv_features)   — CV behavioral features
        X_pub : DataFrame shape (n, n_pub_features)  — public stats (lagged)
        y : DataFrame     shape (n, n_targets)        — public stat targets
        """
        self._target_names = list(y.columns)
        self._cv_feature_names = list(X_cv.columns)
        self._pub_feature_names = list(X_pub.columns)

        # Imputation medians (fit on training data only)
        self._cv_medians = np.nanmedian(X_cv.values.astype(float), axis=0)
        self._pub_medians = np.nanmedian(X_pub.values.astype(float), axis=0)

        Xc = self._impute(X_cv.values.astype(float), self._cv_medians)
        Xp = self._impute(X_pub.values.astype(float), self._pub_medians)

        Xc_s = self._cv_scaler.fit_transform(Xc)
        Xp_s = self._pub_scaler.fit_transform(Xp)

        # Use TimeSeriesSplit for internal weight calibration
        tscv = TimeSeriesSplit(n_splits=3)
        cv_r2_sum, pub_r2_sum = 0.0, 0.0
        n_targets = len(self._target_names)

        for col in self._target_names:
            yi = y[col].values.astype(float)
            # CV sub-model (uses CV + pub features concatenated)
            Xcomb = np.hstack([Xc_s, Xp_s])
            cv_mdl = GradientBoostingRegressor(
                n_estimators=self.n_estimators, max_depth=3,
                learning_rate=0.05, subsample=0.8, random_state=42,
            )
            cv_mdl.fit(Xcomb, yi)
            self._cv_models[col] = cv_mdl

            # Public-only sub-model
            pub_mdl = GradientBoostingRegressor(
                n_estimators=self.n_estimators, max_depth=3,
                learning_rate=0.05, subsample=0.8, random_state=42,
            )
            pub_mdl.fit(Xp_s, yi)
            self._pub_models[col] = pub_mdl

            # Calibrate blend weight via last fold
            for train_idx, val_idx in tscv.split(Xc_s):
                pass  # keep last split
            y_pred_cv = cv_mdl.predict(Xcomb[val_idx])
            y_pred_pub = pub_mdl.predict(Xp_s[val_idx])
            yi_val = yi[val_idx]
            if len(yi_val) > 1:
                cv_r2_sum += max(0.0, r2_score(yi_val, y_pred_cv))
                pub_r2_sum += max(0.0, r2_score(yi_val, y_pred_pub))

        # Auto-calibrate blend: weight proportional to holdout R²
        if self.cv_weight is None:
            total = cv_r2_sum + pub_r2_sum
            self._cv_weight_auto = (cv_r2_sum / total) if total > 0 else 0.6
        else:
            self._cv_weight_auto = self.cv_weight

        self.is_fitted = True
        return self

    def predict(
        self,
        X_cv: Optional[pd.DataFrame],
        X_pub: pd.DataFrame,
    ) -> np.ndarray:
        """Predict public stats, falling back to public-only when CV missing.

        Parameters
        ----------
        X_cv  : DataFrame or None.  None triggers full public-only fallback.
        X_pub : DataFrame  shape (n, n_pub_features)
        """
        if not self.is_fitted:
            raise RuntimeError("BridgeModel: call fit() before predict()")

        Xp = self._impute(X_pub.values.astype(float), self._pub_medians)
        Xp_s = self._pub_scaler.transform(Xp)

        cv_available = X_cv is not None and not X_cv.isnull().all(axis=None)

        if cv_available:
            Xc = self._impute(X_cv.values.astype(float), self._cv_medians)
            Xc_s = self._cv_scaler.transform(Xc)
            Xcomb = np.hstack([Xc_s, Xp_s])
            w = self._cv_weight_auto
        else:
            w = 0.0  # full pub-only

        n = Xp_s.shape[0]
        out = np.zeros((n, len(self._target_names)), dtype=float)
        for i, col in enumerate(self._target_names):
            pub_pred = self._pub_models[col].predict(Xp_s)
            if cv_available:
                cv_pred = self._cv_models[col].predict(Xcomb)
                out[:, i] = w * cv_pred + (1 - w) * pub_pred
            else:
                out[:, i] = pub_pred

        return out

    def score(
        self,
        X_cv: Optional[pd.DataFrame],
        X_pub: pd.DataFrame,
        y: pd.DataFrame,
    ) -> float:
        """Mean R² across all targets on holdout data."""
        preds = self.predict(X_cv, X_pub)
        scores = []
        for i, col in enumerate(self._target_names):
            scores.append(r2_score(y[col].values, preds[:, i]))
        return float(np.mean(scores))

    def save(self, path: str) -> None:
        """Persist model to disk."""
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            pickle.dump(self, f)

    @classmethod
    def load(cls, path: str) -> "BridgeModel":
        """Load model from disk."""
        with open(path, "rb") as f:
            return pickle.load(f)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    @staticmethod
    def _impute(X: np.ndarray, medians: np.ndarray) -> np.ndarray:
        """Replace NaN with column medians (in-place copy)."""
        out = X.copy()
        for j in range(out.shape[1]):
            mask = np.isnan(out[:, j])
            if mask.any():
                out[mask, j] = medians[j]
        return out


# ---------------------------------------------------------------------------
# Synthetic data helpers
# ---------------------------------------------------------------------------

def _make_synthetic(n: int = 300, seed: int = 0) -> tuple:
    """Generate synthetic CV + public stat data for smoke-testing."""
    rng = np.random.default_rng(seed)

    X_cv = pd.DataFrame(
        rng.normal(0, 1, (n, len(CV_FEATURES))), columns=CV_FEATURES
    )
    X_pub = pd.DataFrame(
        rng.normal(0, 1, (n, 4)),
        columns=["efg_lag1", "usage_lag1", "ts_pct_lag1", "ast_lag1"],
    )
    # targets correlated with inputs
    y = pd.DataFrame({
        "efg":      0.4 + 0.05 * X_cv["spacing"]   + 0.03 * X_pub["efg_lag1"]   + rng.normal(0, 0.02, n),
        "usage":    0.2 + 0.04 * X_cv["drive_frequency"] + 0.05 * X_pub["usage_lag1"] + rng.normal(0, 0.02, n),
        "ts_pct":   0.5 + 0.04 * X_cv["defender_distance"] + 0.03 * X_pub["ts_pct_lag1"] + rng.normal(0, 0.02, n),
        "ast_ratio":0.15 + 0.03 * X_cv["spacing"]  + 0.02 * X_pub["ast_lag1"]   + rng.normal(0, 0.01, n),
        "reb_rate": 0.1  + 0.02 * X_cv["paint_touches"] + rng.normal(0, 0.01, n),
    })
    return X_cv, X_pub, y


# ---------------------------------------------------------------------------
# CLI smoke test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("BridgeModel smoke test — synthetic data")
    X_cv, X_pub, y = _make_synthetic(n=400)

    # Temporal split: train on first 300, test on last 100
    n_train = 300
    X_cv_tr, X_pub_tr, y_tr = X_cv.iloc[:n_train], X_pub.iloc[:n_train], y.iloc[:n_train]
    X_cv_ts, X_pub_ts, y_ts = X_cv.iloc[n_train:], X_pub.iloc[n_train:], y.iloc[n_train:]

    model = BridgeModel(n_estimators=100)
    model.fit(X_cv_tr, X_pub_tr, y_tr)

    r2_full = model.score(X_cv_ts, X_pub_ts, y_ts)
    r2_pub  = model.score(None,    X_pub_ts, y_ts)

    print(f"  R² (CV+pub):  {r2_full:.4f}")
    print(f"  R² (pub-only fallback): {r2_pub:.4f}")
    print(f"  CV blend weight: {model._cv_weight_auto:.3f}")

    assert r2_full >= 0.3, f"R² {r2_full:.4f} < 0.3 — FAIL"
    assert r2_pub  >= 0.1, f"pub-only R² {r2_pub:.4f} < 0.1 — FAIL"
    print("PASS")
