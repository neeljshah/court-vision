"""Win probability model (ML-02).

Predicts the probability that the team in possession will win, based on
momentum-correlated possession-level features.

Real win labels require play-by-play box score data not yet ingested.
Synthetic labels are used: a possession is a 'win' if:
  - scoring_run > 0 AND possession_streak >= 2, OR
  - swing_point == 1 AND scoring_run > 0

Uses RandomForestClassifier(n_estimators=200, max_depth=5) wrapped in a
StandardScaler Pipeline. Synthetic data (200 rows, seed=42) is used when the
training DataFrame has fewer than 20 rows.
"""

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from legacy.models.base import BaseModel

_FEATURES = [
    "convex_hull_area",
    "avg_inter_player_dist",
    "scoring_run",
    "possession_streak",
    "swing_point",
]


class WinProbabilityModel(BaseModel):
    """RandomForestClassifier-based win probability estimator.

    Features: convex_hull_area, avg_inter_player_dist, scoring_run,
              possession_streak, swing_point (int 0/1).
    Label: synthetic win indicator derived from momentum rule.
    Output: float probability in [0, 1] that the team wins the possession.
    """

    model_name = "win_probability"
    SYNTHETIC_ROWS = 200

    def __init__(self):
        self._pipeline: Pipeline | None = None

    def fit(self, df: pd.DataFrame) -> "WinProbabilityModel":
        """Train on a DataFrame of possession records.

        Falls back to synthetic data if df has fewer than 20 rows.

        Args:
            df: DataFrame with columns convex_hull_area, avg_inter_player_dist,
                scoring_run, possession_streak, swing_point. May be empty.
                A 'won' column is ignored — labels are always derived synthetically.

        Returns:
            self (for chaining).
        """
        if len(df) < 20:
            df = self._synthetic_df()

        # Ensure required feature columns are present; derive label synthetically
        X = df[_FEATURES].astype(float).values
        y = self._label(df).values

        self._pipeline = Pipeline([
            ("scaler", StandardScaler()),
            ("clf", RandomForestClassifier(
                n_estimators=200, max_depth=5, random_state=42
            )),
        ])
        self._pipeline.fit(X, y)
        return self

    def predict(self, features: dict) -> float:
        """Return probability [0, 1] that the team wins.

        Args:
            features: dict with keys convex_hull_area (float),
                      avg_inter_player_dist (float), scoring_run (int),
                      possession_streak (int), swing_point (int 0/1).

        Returns:
            float — win probability in [0, 1].
        """
        if self._pipeline is None:
            raise RuntimeError("Model not trained. Call fit() before predict().")
        X = self._feature_row(features)
        return float(self._pipeline.predict_proba(X)[0][1])

    def _label(self, df: pd.DataFrame) -> pd.Series:
        """Derive synthetic win labels from momentum rule.

        A possession is labelled 'won' (1) if:
          - scoring_run > 0 AND possession_streak >= 2, OR
          - swing_point == 1 AND scoring_run > 0

        Args:
            df: DataFrame with scoring_run, possession_streak, swing_point columns.

        Returns:
            pd.Series of int (0 or 1).
        """
        cond_momentum = (df["scoring_run"] > 0) & (df["possession_streak"] >= 2)
        cond_swing = (df["swing_point"] == 1) & (df["scoring_run"] > 0)
        return (cond_momentum | cond_swing).astype(int)

    def _synthetic_df(self) -> pd.DataFrame:
        """Generate 200 synthetic possession rows for training when DB has no data.

        Distributions per plan spec:
          convex_hull_area ~ Uniform(5000, 20000)
          avg_inter_player_dist ~ Uniform(80, 300)
          scoring_run ~ randint(-15, 14) inclusive
          possession_streak ~ randint(0, 7) inclusive
          swing_point ~ Bernoulli(0.15)
        Label derived from synthetic rule via _label().

        Returns:
            pd.DataFrame with _FEATURES columns and 'won' column.
        """
        rng = np.random.default_rng(42)
        n = self.SYNTHETIC_ROWS

        df = pd.DataFrame({
            "convex_hull_area": rng.uniform(5000, 20000, n),
            "avg_inter_player_dist": rng.uniform(80, 300, n),
            "scoring_run": rng.integers(-15, 15, n),
            "possession_streak": rng.integers(0, 8, n),
            "swing_point": (rng.random(n) < 0.15).astype(int),
        })
        df["won"] = self._label(df)
        return df

    def _feature_row(self, features: dict) -> list:
        """Convert features dict to a 2D array row for sklearn."""
        return [[
            float(features["convex_hull_area"]),
            float(features["avg_inter_player_dist"]),
            float(features["scoring_run"]),
            float(features["possession_streak"]),
            float(features["swing_point"]),
        ]]


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Train and save WinProbabilityModel")
    parser.add_argument("--train", action="store_true", help="Run training pipeline")
    args = parser.parse_args()

    if args.train:
        try:
            from models.training_data import load_possession_data
            df = load_possession_data()
        except Exception as exc:
            print(f"[warn] DB unavailable ({exc}); using synthetic training data.")
            df = pd.DataFrame()

        model = WinProbabilityModel()
        model.fit(df)
        path = model.save()
        print(f"Saved: {path}")
