"""Momentum detection model (ML-03).

Detects momentum shifts (swing points) using scoring run and possession streak
features. Returns 0 (no shift) or 1 (momentum shift detected).

Uses GradientBoostingClassifier — no scaler needed for tree-based models.
When no training data is available (< 10 rows), a synthetic 100-row dataset
is generated where swing_point=1 when abs(scoring_run) >= 6 AND streak_delta >= 3,
with ~10% label noise.
"""

import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingClassifier

from models.base import BaseModel

_FEATURES = ["scoring_run", "possession_streak", "scoring_run_prev", "streak_delta"]


class MomentumDetector(BaseModel):
    """GradientBoostingClassifier-based momentum shift detector.

    Features: scoring_run, possession_streak, scoring_run_prev, streak_delta.
    Label: swing_point (int 0/1).
    Output: int 0 (no shift) or 1 (shift detected).
    """

    model_name = "momentum_detector"
    SYNTHETIC_ROWS = 100

    def __init__(self):
        self._clf: GradientBoostingClassifier | None = None

    def fit(self, df: pd.DataFrame) -> "MomentumDetector":
        """Train on a DataFrame of momentum snapshots.

        Falls back to synthetic data if df has fewer than 10 rows.

        Args:
            df: DataFrame with columns scoring_run, possession_streak,
                scoring_run_prev, streak_delta, swing_point. May be empty.

        Returns:
            self (for chaining).
        """
        if len(df) < 10:
            df = self._synthetic_df()

        X = df[_FEATURES].astype(float).values
        y = df["swing_point"].astype(int).values

        self._clf = GradientBoostingClassifier(
            n_estimators=100, max_depth=3, random_state=42
        )
        self._clf.fit(X, y)
        return self

    def predict(self, features: dict) -> int:
        """Return 0 (no momentum shift) or 1 (shift detected).

        Args:
            features: dict with keys scoring_run (int), possession_streak (int),
                      scoring_run_prev (int), streak_delta (int).

        Returns:
            int — 0 or 1.
        """
        if self._clf is None:
            raise RuntimeError("Model not trained. Call fit() before predict().")
        X = self._feature_row(features)
        return int(self._clf.predict(X)[0])

    def predict_proba(self, features: dict) -> float:
        """Return probability [0, 1] that a momentum shift is occurring.

        Used by Phase 4 API to provide confidence alongside binary prediction.

        Args:
            features: Same dict as predict().

        Returns:
            float — shift probability.
        """
        if self._clf is None:
            raise RuntimeError("Model not trained. Call fit() before predict_proba().")
        X = self._feature_row(features)
        return float(self._clf.predict_proba(X)[0][1])

    def _feature_row(self, features: dict) -> list:
        """Convert a features dict to a 2D array row for sklearn."""
        return [[
            float(features["scoring_run"]),
            float(features["possession_streak"]),
            float(features["scoring_run_prev"]),
            float(features["streak_delta"]),
        ]]

    def _synthetic_df(self) -> pd.DataFrame:
        """Generate synthetic momentum data with realistic swing point rules.

        swing_point=1 when abs(scoring_run) >= 6 AND streak_delta >= 3,
        swing_point=0 otherwise, with ~10% label noise (flip).
        """
        rng = np.random.default_rng(42)
        n = self.SYNTHETIC_ROWS

        scoring_run = rng.integers(-15, 16, n)
        possession_streak = rng.integers(0, 10, n)
        scoring_run_prev = scoring_run + rng.integers(-3, 4, n)
        streak_delta = rng.integers(-3, 7, n)

        # Deterministic label: swing when big run + big streak change
        swing_point = (
            (np.abs(scoring_run) >= 6) & (streak_delta >= 3)
        ).astype(int)

        # ~10% label noise
        noise_mask = rng.random(n) < 0.10
        swing_point[noise_mask] = 1 - swing_point[noise_mask]

        return pd.DataFrame({
            "scoring_run": scoring_run,
            "possession_streak": possession_streak,
            "scoring_run_prev": scoring_run_prev,
            "streak_delta": streak_delta,
            "swing_point": swing_point,
        })


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Train and save MomentumDetector")
    parser.add_argument("--train", action="store_true", help="Run training pipeline")
    args = parser.parse_args()

    if args.train:
        import pandas as pd

        try:
            from models.training_data import load_momentum_data
            df = load_momentum_data()
        except Exception as exc:
            print(f"[warn] DB unavailable ({exc}); using synthetic training data.")
            df = pd.DataFrame()

        model = MomentumDetector()
        model.fit(df)
        path = model.save()
        print(f"Saved: {path}")
