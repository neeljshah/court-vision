"""Player impact model — EPA per 100 possessions (ML-04).

Predicts Expected Points Added per 100 possessions for each player,
derived from shot quality and event contribution (cuts, screens, etc.).

Base rate: NBA average ~107 points per 100 possessions.
Player adjustment: RandomForestRegressor predicts deviation from league
average based on shot quality (court zone proxy via x,y) and event mix.

EPA label formula:
  y = (made_rate - 0.45) * 2.2 * 100  # deviation from avg, per-100 scaled

Synthetic data (10 players, seed=42) is used when the training DataFrame
has fewer than 5 unique track_ids.
"""

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor

from models.base import BaseModel

_AGG_FEATURES = [
    "made_rate",
    "shots_taken",
    "cut_rate",
    "screen_rate",
    "avg_confidence",
    "x_mean",
]


class PlayerImpactModel(BaseModel):
    """RandomForestRegressor-based player EPA estimator.

    Features per player (aggregated from event log):
        made_rate, shots_taken, cut_rate, screen_rate,
        avg_confidence, x_mean (court zone proxy).
    Label: EPA deviation from league average efficiency (regression).
    Output: {'epa_per_100': float} — points above/below average per 100 possessions.
    """

    model_name = "player_impact"
    LEAGUE_AVG_EFFICIENCY = 0.45
    SCALE_FACTOR = 2.2
    SYNTHETIC_PLAYERS = 10

    def __init__(self):
        self._regressor: RandomForestRegressor | None = None

    def fit(self, df: pd.DataFrame) -> "PlayerImpactModel":
        """Train on a DataFrame of player event records.

        Falls back to synthetic data if df has fewer than 5 unique track_ids.

        Args:
            df: DataFrame with columns track_id, game_id, event_type, confidence,
                made (int 0/1), x, y. May be empty.

        Returns:
            self (for chaining).
        """
        if df.empty or df.get("track_id", pd.Series([], dtype=int)).nunique() < 5:
            agg = self._synthetic_df()
        else:
            agg = self._aggregate(df)

        X = agg[_AGG_FEATURES].astype(float).values
        y = (
            (agg["made_rate"] - self.LEAGUE_AVG_EFFICIENCY)
            * self.SCALE_FACTOR
            * 100
        ).values

        self._regressor = RandomForestRegressor(
            n_estimators=100, max_depth=4, random_state=42
        )
        self._regressor.fit(X, y)
        return self

    def predict(self, features: dict) -> dict:
        """Return EPA per 100 possessions for a player.

        Args:
            features: dict with keys:
                track_id (int, for logging only),
                made_rate (float),
                event_mix (dict mapping event_type -> count),
                shots_taken (int).

        Returns:
            dict with key 'epa_per_100' (float).
        """
        if self._regressor is None:
            raise RuntimeError("Model not trained. Call fit() before predict().")

        shots_taken = max(int(features["shots_taken"]), 1)
        event_mix = features.get("event_mix", {})
        made_rate = float(features["made_rate"])
        cut_rate = event_mix.get("cut", 0) / shots_taken
        screen_rate = event_mix.get("screen", 0) / shots_taken
        avg_confidence = 0.75  # no confidence signal at predict time; use mean
        x_mean = 400.0  # neutral court position at predict time

        X = [[made_rate, shots_taken, cut_rate, screen_rate, avg_confidence, x_mean]]
        epa = float(self._regressor.predict(X)[0])
        return {"epa_per_100": epa}

    def rank_players(self, game_id: str | None = None) -> list[dict]:
        """Rank all players in a game (or all games) by EPA per 100 possessions.

        Args:
            game_id: Restrict to a single game UUID, or None for all games.

        Returns:
            list of {'track_id': int, 'epa_per_100': float} sorted desc by epa_per_100.
        """
        try:
            from models.training_data import load_player_event_data

            df = load_player_event_data(game_id=game_id)
        except Exception:
            df = pd.DataFrame()

        if df.empty:
            return []

        agg = self._aggregate(df)
        results = []
        for _, row in agg.iterrows():
            features = {
                "track_id": int(row["track_id"]),
                "made_rate": float(row["made_rate"]),
                "event_mix": {},  # event mix already encoded in aggregated features
                "shots_taken": int(row["shots_taken"]),
            }
            # Use pre-aggregated features directly for ranking accuracy
            X = [[
                float(row["made_rate"]),
                float(row["shots_taken"]),
                float(row["cut_rate"]),
                float(row["screen_rate"]),
                float(row["avg_confidence"]),
                float(row["x_mean"]),
            ]]
            epa = float(self._regressor.predict(X)[0])
            results.append({"track_id": int(row["track_id"]), "epa_per_100": epa})

        results.sort(key=lambda r: r["epa_per_100"], reverse=True)
        return results

    def _aggregate(self, df: pd.DataFrame) -> pd.DataFrame:
        """Aggregate per-player event records into one feature row per track_id.

        Computes:
            made_rate: mean(made)
            shots_taken: count of rows
            cut_rate: fraction of events where event_type='cut'
            screen_rate: fraction where event_type='screen'
            avg_confidence: mean(confidence)
            x_mean: mean(x) — court zone proxy

        Args:
            df: DataFrame with columns track_id, event_type, confidence, made, x.

        Returns:
            pd.DataFrame with one row per track_id and _AGG_FEATURES + track_id columns.
        """
        agg = df.groupby("track_id").apply(
            lambda g: pd.Series({
                "made_rate": g["made"].mean(),
                "shots_taken": float(len(g)),
                "cut_rate": (g["event_type"] == "cut").mean(),
                "screen_rate": (g["event_type"] == "screen").mean(),
                "avg_confidence": g["confidence"].mean(),
                "x_mean": g["x"].mean(),
            }),
            include_groups=False,
        ).reset_index()
        return agg

    def _synthetic_df(self) -> pd.DataFrame:
        """Generate synthetic per-player feature rows for training when DB has no data.

        Distributions per plan spec:
            made_rate ~ Uniform(0.30, 0.65)
            shots_taken ~ randint(5, 19) inclusive
            cut_rate ~ Uniform(0, 0.5)
            screen_rate ~ Uniform(0, 0.3)
            avg_confidence ~ Uniform(0.6, 0.95)
            x_mean ~ Uniform(100, 800)

        Returns:
            pd.DataFrame with _AGG_FEATURES + track_id columns.
        """
        rng = np.random.default_rng(42)
        n = self.SYNTHETIC_PLAYERS

        df = pd.DataFrame({
            "track_id": list(range(1, n + 1)),
            "made_rate": rng.uniform(0.30, 0.65, n),
            "shots_taken": rng.integers(5, 20, n).astype(float),
            "cut_rate": rng.uniform(0, 0.5, n),
            "screen_rate": rng.uniform(0, 0.3, n),
            "avg_confidence": rng.uniform(0.6, 0.95, n),
            "x_mean": rng.uniform(100, 800, n),
        })
        return df


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Train and save PlayerImpactModel")
    parser.add_argument("--train", action="store_true", help="Run training pipeline")
    args = parser.parse_args()

    if args.train:
        try:
            from models.training_data import load_player_event_data

            df = load_player_event_data()
        except Exception as exc:
            print(f"[warn] DB unavailable ({exc}); using synthetic training data.")
            df = pd.DataFrame()

        model = PlayerImpactModel()
        model.fit(df)
        path = model.save()
        print(f"Saved: {path}")
