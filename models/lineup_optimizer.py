"""Lineup optimization model — offensive gravity + defensive disruption scoring (ML-05).

Scores any lineup combination (list of 5 track_ids) by combining:
  - Offensive gravity: derived from per-player EPA (Expected Points Added per 100 possessions)
  - Defensive disruption: derived from per-player closing speed in feature_vectors

Architecture: lookup + scoring model (not a traditional classifier). Stores a dict
of per-player stats and computes lineup scores analytically. joblib serializes the
full object including the stats dict.

Depends on:
  - models.player_impact.PlayerImpactModel: provides per-player EPA via rank_players()
  - tracking.database.get_connection: provides defensive pressure stats
  - models.base.BaseModel: ABC contract (fit/predict/save/load)
"""

import argparse
import logging

import numpy as np
import pandas as pd

from models.base import BaseModel

logger = logging.getLogger(__name__)


class LineupOptimizer(BaseModel):
    """Lookup-and-score lineup optimizer using EPA + defensive pressure metrics.

    fit() loads per-player stats from PlayerImpactModel and the feature_vectors
    table. predict() scores a 5-player lineup by combining offensive gravity
    (EPA-based) and defensive disruption (closing-speed-based).

    Attributes:
        model_name: Artifact filename stem.
        LEAGUE_AVG_EPA: Fallback EPA for unknown players (0.0).
        CLOSING_SPEED_MAX: Normalization ceiling for avg_closing_speed (15 px/s).
        EPA_RANGE: Normalization denominator for EPA range [-10, +10] = 20.
        SYNTHETIC_PLAYERS: Number of synthetic players generated when DB is empty.
    """

    model_name = "lineup_optimizer"
    LEAGUE_AVG_EPA = 0.0
    CLOSING_SPEED_MAX = 15.0
    EPA_RANGE = 20.0  # normalization denominator (-10 to +10)
    SYNTHETIC_PLAYERS = 20

    # Fallback stats for unknown track_ids
    _FALLBACK_STATS = {
        "epa_per_100": 0.0,
        "avg_def_dist": 150.0,
        "avg_closing_speed": 5.0,
    }

    def __init__(self):
        self._player_stats: dict | None = None

    def fit(self, df: pd.DataFrame) -> "LineupOptimizer":
        """Build per-player stats from PlayerImpactModel EPA and DB defensive metrics.

        Steps:
          1. Load per-player EPA from PlayerImpactModel artifact (log warning if missing).
          2. Load defensive pressure stats from feature_vectors via DB.
          3. Merge EPA + defensive stats into self._player_stats.
          4. If no DB stats available, generate synthetic stats for 20 players.

        Args:
            df: Lineup DataFrame (from load_lineup_data). May be empty — used as
                a trigger for the fit pipeline but not directly consumed here.

        Returns:
            self (for chaining).
        """
        # Step 1: Load EPA per player from PlayerImpactModel
        epa_map: dict[int, float] = {}
        try:
            from models.player_impact import PlayerImpactModel

            impact_model = PlayerImpactModel.load("player_impact")
            rankings = impact_model.rank_players()
            for entry in rankings:
                epa_map[int(entry["track_id"])] = float(entry["epa_per_100"])
        except FileNotFoundError:
            logger.warning(
                "player_impact artifact not found — EPA values will default to 0.0."
            )
        except Exception as exc:
            logger.warning("Could not load PlayerImpactModel: %s", exc)

        # Step 2: Load defensive pressure stats from DB
        defensive_stats = self._load_defensive_stats()

        # Step 3: Merge EPA + defensive into unified player stats dict
        if defensive_stats:
            all_track_ids = set(epa_map.keys()) | set(defensive_stats.keys())
            merged: dict[int, dict] = {}
            for tid in all_track_ids:
                def_row = defensive_stats.get(tid, {})
                merged[tid] = {
                    "epa_per_100": epa_map.get(tid, self.LEAGUE_AVG_EPA),
                    "avg_def_dist": float(def_row.get("avg_def_dist", 150.0)),
                    "avg_closing_speed": float(def_row.get("avg_closing_speed", 5.0)),
                }
            self._player_stats = merged
        elif epa_map:
            # Have EPA but no DB defensive stats — use defaults for defensive features
            self._player_stats = {
                tid: {
                    "epa_per_100": epa,
                    "avg_def_dist": 150.0,
                    "avg_closing_speed": 5.0,
                }
                for tid, epa in epa_map.items()
            }
        else:
            # Step 4: No data at all — use synthetic fallback
            logger.warning(
                "No player stats available from DB or PlayerImpactModel. "
                "Using synthetic stats for %d players.",
                self.SYNTHETIC_PLAYERS,
            )
            self._player_stats = self._synthetic_stats()

        return self

    def predict(self, features: dict) -> dict:
        """Score a 5-player lineup by offensive gravity and defensive disruption.

        Args:
            features: dict with key 'lineup' = list of 5 track_ids (ints).

        Returns:
            dict with keys:
                offensive_gravity (float in [0, 1])
                defensive_disruption (float in [0, 1])
                lineup_score (float in [0, 1]) = 0.5 * og + 0.5 * dd

        Raises:
            RuntimeError: if called before fit().
        """
        if self._player_stats is None:
            raise RuntimeError(
                "LineupOptimizer not fitted. Call fit() before predict()."
            )

        lineup: list[int] = [int(tid) for tid in features["lineup"]]

        epas: list[float] = []
        closing_speeds: list[float] = []
        for tid in lineup:
            stats = self._player_stats.get(tid, self._FALLBACK_STATS)
            epas.append(float(stats["epa_per_100"]))
            closing_speeds.append(float(stats["avg_closing_speed"]))

        mean_epa = float(np.mean(epas))
        mean_closing_speed = float(np.mean(closing_speeds))

        # Normalize offensive_gravity: (mean_epa + 10) / 20, clipped to [0, 1]
        offensive_gravity = float(
            np.clip((mean_epa + 10.0) / self.EPA_RANGE, 0.0, 1.0)
        )

        # Normalize defensive_disruption: mean_closing_speed / 15, clipped to [0, 1]
        defensive_disruption = float(
            np.clip(mean_closing_speed / self.CLOSING_SPEED_MAX, 0.0, 1.0)
        )

        lineup_score = 0.5 * offensive_gravity + 0.5 * defensive_disruption

        return {
            "offensive_gravity": offensive_gravity,
            "defensive_disruption": defensive_disruption,
            "lineup_score": lineup_score,
        }

    def score_lineup(self, lineup: list[int]) -> dict:
        """Convenience wrapper: score a lineup list directly.

        Args:
            lineup: List of 5 track_ids.

        Returns:
            Same dict as predict({'lineup': lineup}).
        """
        return self.predict({"lineup": lineup})

    def compare_lineups(self, lineups: list[list[int]]) -> list[dict]:
        """Score all provided lineups and return sorted by lineup_score descending.

        Args:
            lineups: List of lineups, each a list of 5 track_ids.

        Returns:
            List of dicts: {'lineup': list[int], 'offensive_gravity': float,
            'defensive_disruption': float, 'lineup_score': float}, sorted desc.
        """
        results = []
        for lineup in lineups:
            scores = self.predict({"lineup": lineup})
            results.append({"lineup": list(lineup), **scores})
        results.sort(key=lambda r: r["lineup_score"], reverse=True)
        return results

    def _load_defensive_stats(self) -> dict[int, dict]:
        """Query feature_vectors for per-player avg defensive pressure stats.

        Returns:
            dict mapping track_id (int) -> {'avg_def_dist': float, 'avg_closing_speed': float}.
            Empty dict if DB unavailable or query returns no rows.
        """
        try:
            from tracking.database import get_connection

            conn = get_connection()
            try:
                sql = """
                    SELECT
                        track_id,
                        AVG(nearest_defender_dist) AS avg_def_dist,
                        AVG(ABS(closing_speed)) AS avg_closing_speed
                    FROM feature_vectors
                    GROUP BY track_id
                """
                df = pd.read_sql(sql, conn)
            finally:
                conn.close()

            if df.empty:
                logger.warning("feature_vectors query returned 0 rows.")
                return {}

            stats: dict[int, dict] = {}
            for _, row in df.iterrows():
                tid = int(row["track_id"])
                stats[tid] = {
                    "avg_def_dist": float(row["avg_def_dist"]),
                    "avg_closing_speed": float(row["avg_closing_speed"]),
                }
            return stats

        except Exception as exc:
            logger.warning("Could not load defensive stats from DB: %s", exc)
            return {}

    def _synthetic_stats(self) -> dict[int, dict]:
        """Generate synthetic per-player stats for SYNTHETIC_PLAYERS track_ids 1–20.

        Distributions:
            epa_per_100 ~ Uniform(-5, 10)
            avg_def_dist ~ Uniform(50, 250)
            avg_closing_speed ~ Uniform(0, 15)

        Returns:
            dict mapping track_id (int 1–20) -> stats dict.
        """
        rng = np.random.default_rng(42)
        n = self.SYNTHETIC_PLAYERS
        epas = rng.uniform(-5.0, 10.0, n)
        def_dists = rng.uniform(50.0, 250.0, n)
        closing_speeds = rng.uniform(0.0, 15.0, n)

        return {
            i + 1: {
                "epa_per_100": float(epas[i]),
                "avg_def_dist": float(def_dists[i]),
                "avg_closing_speed": float(closing_speeds[i]),
            }
            for i in range(n)
        }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Train and save LineupOptimizer")
    parser.add_argument("--train", action="store_true", help="Run training pipeline")
    args = parser.parse_args()

    if args.train:
        try:
            from models.training_data import load_lineup_data

            df = load_lineup_data()
        except Exception as exc:
            print(f"[warn] DB unavailable ({exc}); using empty DataFrame for training.")
            df = pd.DataFrame()

        model = LineupOptimizer()
        model.fit(df)
        path = model.save()
        print(f"Saved: {path}")
