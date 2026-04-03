"""
regime_detector.py — D-2: HMM-based hot/cold streak regime detection.

Uses a 2-state Gaussian HMM (hot / cold) per player per stat.
Autocorrelation gate: only apply to streaky players (ACF lag-1 > 0.35).

Public API
----------
    RegimeDetector  — class
    RegimeDetector.fit(gamelog_series) -> dict
    RegimeDetector.get_hot_prob(player_id, stat, recent_games) -> float
    RegimeDetector.regime_adjusted_prediction(base_pred, player_id, stat) -> float

Dependencies
------------
    hmmlearn — optional. Graceful fallback if not installed.
"""

from __future__ import annotations

import json
import os
from typing import List, Optional

import numpy as np

_NBA_CACHE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data", "nba",
)


def _autocorr(series: List[float], lag: int = 1) -> float:
    """Pearson autocorrelation at given lag. Returns 0.0 on failure."""
    try:
        arr = np.array(series, dtype=float)
        if len(arr) <= lag + 1:
            return 0.0
        c = np.corrcoef(arr[:-lag], arr[lag:])
        return float(c[0, 1]) if not np.isnan(c[0, 1]) else 0.0
    except Exception:
        return 0.0


class RegimeDetector:
    """
    D-2: Two-state Gaussian HMM for hot/cold streak detection.

    Only applied to streaky players (autocorrelation > 0.35).
    Consistent players (Jokic, DeRozan) are left unmodified to avoid noise.
    """

    STREAK_THRESHOLD = 0.35   # ACF lag-1 threshold to apply HMM
    N_STATES = 2              # hot (state 1) and cold (state 0)

    def fit(self, gamelog_series: List[float]) -> dict:
        """
        Fit 2-state GaussianHMM on a gamelog series.

        Args:
            gamelog_series: List of per-game stat values (chronological order).

        Returns:
            {hot_mean, cold_mean, hot_prob_current, is_streaky, model}
        """
        _result = {
            "hot_mean": float(np.mean(gamelog_series)) if gamelog_series else 0.0,
            "cold_mean": float(np.mean(gamelog_series)) if gamelog_series else 0.0,
            "hot_prob_current": 0.5,
            "is_streaky": False,
            "model": None,
        }
        if len(gamelog_series) < 10:
            return _result

        acf = _autocorr(gamelog_series, lag=1)
        is_streaky = acf > self.STREAK_THRESHOLD
        _result["is_streaky"] = is_streaky

        try:
            from hmmlearn import hmm as _hmm
            arr = np.array(gamelog_series, dtype=float).reshape(-1, 1)

            model = _hmm.GaussianHMM(
                n_components=self.N_STATES,
                covariance_type="diag",
                n_iter=100,
                random_state=42,
            )
            model.fit(arr)

            state_means = model.means_.flatten()
            # State 1 = hot (higher mean), State 0 = cold (lower mean)
            hot_state  = int(np.argmax(state_means))
            cold_state = 1 - hot_state

            # Current regime: most likely state for recent observations
            _, state_seq = model.decode(arr, algorithm="viterbi")
            hot_prob = float(np.mean(state_seq[-5:] == hot_state)) if len(state_seq) >= 5 else 0.5

            _result.update({
                "hot_mean":          float(state_means[hot_state]),
                "cold_mean":         float(state_means[cold_state]),
                "hot_prob_current":  hot_prob,
                "is_streaky":        is_streaky,
                "model":             model,
                "hot_state_idx":     hot_state,
            })
        except ImportError:
            pass  # hmmlearn not installed — graceful fallback
        except Exception:
            pass

        return _result

    def get_hot_prob(
        self,
        player_id: int,
        stat: str,
        recent_games: int = 10,
    ) -> float:
        """
        Return P(player currently in hot state) for a given stat.

        Loads gamelog from cache, fits HMM, returns hot probability.
        Returns 0.5 for consistent (non-streaky) players.
        """
        season = "2024-25"
        gamelog_path = os.path.join(_NBA_CACHE, f"gamelog_{player_id}_{season}.json")
        if not os.path.exists(gamelog_path):
            return 0.5

        try:
            rows = json.load(open(gamelog_path))
            col_map = {"pts": "PTS", "reb": "REB", "ast": "AST",
                       "fg3m": "FG3M", "stl": "STL", "blk": "BLK", "tov": "TOV"}
            col = col_map.get(stat.lower(), stat.upper())
            series = [float(r.get(col, 0) or 0) for r in rows if r.get(col) is not None]
            if len(series) < 5:
                return 0.5
            result = self.fit(series[-recent_games * 3:])  # use broader window for fitting
            return result["hot_prob_current"] if result["is_streaky"] else 0.5
        except Exception:
            return 0.5

    def regime_adjusted_prediction(
        self,
        base_prediction: float,
        player_id: int,
        stat: str,
    ) -> float:
        """
        Adjust base prediction by current regime.

        For streaky players: blend toward hot_mean based on hot_prob.
        For consistent players: return base_prediction unchanged.
        """
        try:
            hot_prob = self.get_hot_prob(player_id, stat)
            season = "2024-25"
            gamelog_path = os.path.join(_NBA_CACHE, f"gamelog_{player_id}_{season}.json")
            if not os.path.exists(gamelog_path):
                return base_prediction

            rows = json.load(open(gamelog_path))
            col_map = {"pts": "PTS", "reb": "REB", "ast": "AST",
                       "fg3m": "FG3M", "stl": "STL", "blk": "BLK", "tov": "TOV"}
            col = col_map.get(stat.lower(), stat.upper())
            series = [float(r.get(col, 0) or 0) for r in rows if r.get(col) is not None]
            if len(series) < 5:
                return base_prediction

            result = self.fit(series)
            if not result["is_streaky"]:
                return base_prediction

            hot_delta = result["hot_mean"] - result["cold_mean"]
            is_streaky_weight = min(abs(_autocorr(series, 1)) * 2.0, 1.0)
            adjusted = base_prediction + hot_prob * hot_delta * is_streaky_weight
            return float(max(0.0, adjusted))
        except Exception:
            return base_prediction
