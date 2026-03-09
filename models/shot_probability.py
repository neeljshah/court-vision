"""Shot probability model (ML-01).

Predicts the probability that a given shot attempt results in a made basket.
Uses a sklearn LogisticRegression wrapped in a StandardScaler pipeline.

When no training data is available (< 10 rows), a synthetic seed dataset
reflecting real NBA averages is used: paint ~0.60, midrange ~0.40, three ~0.35.
"""

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from models.base import BaseModel


class ShotProbabilityModel(BaseModel):
    """LogisticRegression-based shot probability estimator.

    Features: nearest_defender_dist, shot_angle, fatigue_proxy, court_zone (ordinal).
    Label: made (int 0/1).
    Output: float probability that made == 1.
    """

    model_name = "shot_probability"
    ZONE_ORDINAL = {"paint": 0, "midrange": 1, "three": 2}
    SYNTHETIC_ROWS = 50  # used when DB has no shot data yet

    def __init__(self):
        self._pipeline: Pipeline | None = None

    def fit(self, df: pd.DataFrame) -> "ShotProbabilityModel":
        """Train on a DataFrame of shot records.

        Falls back to synthetic data if df has fewer than 10 rows.

        Args:
            df: DataFrame with columns nearest_defender_dist, shot_angle,
                fatigue_proxy, court_zone, made. May be empty.

        Returns:
            self (for chaining).
        """
        if len(df) < 10:
            df = self._synthetic_df()

        X = self._build_feature_matrix(df)
        y = df["made"].astype(int).values

        self._pipeline = Pipeline([
            ("scaler", StandardScaler()),
            ("clf", LogisticRegression(max_iter=1000, random_state=42)),
        ])
        self._pipeline.fit(X, y)
        return self

    def predict(self, features: dict) -> float:
        """Return probability [0, 1] that the shot is made.

        Args:
            features: dict with keys defender_dist (float), shot_angle (float),
                      fatigue_proxy (float), court_zone (str: 'paint'|'midrange'|'three').

        Returns:
            float — probability of made == 1.
        """
        if self._pipeline is None:
            raise RuntimeError("Model not trained. Call fit() before predict().")
        X = self._encode(features)
        prob = float(self._pipeline.predict_proba([X])[0][1])
        return prob

    def _encode(self, features: dict) -> list:
        """Convert a features dict to an ordered numeric list.

        Order must match the column order in _build_feature_matrix().
        """
        zone = features.get("court_zone", "midrange")
        zone_ordinal = self.ZONE_ORDINAL.get(zone, 1)
        return [
            float(features["defender_dist"]),
            float(features["shot_angle"]),
            float(features["fatigue_proxy"]),
            float(zone_ordinal),
        ]

    def _build_feature_matrix(self, df: pd.DataFrame) -> np.ndarray:
        """Convert training DataFrame to numpy feature matrix."""
        zone_encoded = df["court_zone"].map(self.ZONE_ORDINAL).fillna(1).astype(float)
        return np.column_stack([
            df["nearest_defender_dist"].astype(float).values,
            df["shot_angle"].astype(float).values,
            df["fatigue_proxy"].astype(float).values,
            zone_encoded.values,
        ])

    def _synthetic_df(self) -> pd.DataFrame:
        """Generate synthetic shot data reflecting real NBA made rates.

        Paint ~0.60, midrange ~0.40, three ~0.35.
        Each zone contributes SYNTHETIC_ROWS // 3 rows (remainder goes to paint).
        """
        rng = np.random.default_rng(42)
        n = self.SYNTHETIC_ROWS

        # Distribute rows across zones
        n_paint = n // 3 + n % 3
        n_mid = n // 3
        n_three = n // 3

        def _zone_rows(zone: str, count: int, made_rate: float, dist_range, angle_range):
            # Per plan spec: defender_dist=0 → higher probability than defender_dist=10.
            # Synthetic data encodes this: low dist → high made rate (close defender =
            # in-your-face shots near basket are still high percentage).
            # We split rows into half "close" (low dist, made_rate * 1.3)
            # and half "far" (high dist, made_rate * 0.6) so the model
            # learns that lower dist → higher probability.
            half = count // 2
            rem = count - half

            dist_lo, dist_hi = dist_range
            dist_mid = (dist_lo + dist_hi) / 2

            # Close defender: low dist, higher made rate
            close_dist = rng.uniform(dist_lo, dist_mid, half)
            close_made = (rng.random(half) < min(made_rate * 1.3, 0.95)).astype(int)

            # Far defender: high dist, lower made rate
            far_dist = rng.uniform(dist_mid, dist_hi, rem)
            far_made = (rng.random(rem) < made_rate * 0.6).astype(int)

            shot_angle = rng.uniform(*angle_range, count)
            fatigue_proxy = rng.uniform(0.0, 1.0, count)

            defender_dist = np.concatenate([close_dist, far_dist])
            made = np.concatenate([close_made, far_made])

            return pd.DataFrame({
                "nearest_defender_dist": defender_dist,
                "shot_angle": shot_angle,
                "fatigue_proxy": fatigue_proxy,
                "court_zone": zone,
                "made": made,
            })

        paint_df = _zone_rows("paint", n_paint, 0.60, (0.5, 4.0), (0.0, 90.0))
        mid_df = _zone_rows("midrange", n_mid, 0.40, (1.0, 6.0), (10.0, 60.0))
        three_df = _zone_rows("three", n_three, 0.35, (2.0, 8.0), (15.0, 75.0))

        return pd.concat([paint_df, mid_df, three_df], ignore_index=True)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Train and save ShotProbabilityModel")
    parser.add_argument("--train", action="store_true", help="Run training pipeline")
    args = parser.parse_args()

    if args.train:
        from models.training_data import load_shot_data

        df = load_shot_data()
        model = ShotProbabilityModel()
        model.fit(df)
        path = model.save()
        print(f"Saved: {path}")
