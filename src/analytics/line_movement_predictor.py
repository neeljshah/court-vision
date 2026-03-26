"""
line_movement_predictor.py — M84: Predict expected line movement direction and magnitude.

Inputs: historical lines (opening vs closing delta), injury news timing, public%.
Output: expected_line_move direction + magnitude.
Helps determine whether to bet early vs wait.

Public API
----------
    train(seasons)                        -> dict
    predict_line_move(game_id, features)  -> dict
    get_timing_advice(ev, sharp_signal)   -> str
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

_EXT_CACHE = os.path.join(PROJECT_DIR, "data", "external")
_MODEL_DIR  = os.path.join(PROJECT_DIR, "data", "models")
_MODEL_PATH = os.path.join(_MODEL_DIR, "line_movement_predictor.pkl")

log = logging.getLogger(__name__)


def _build_movement_stats(seasons: list[str]) -> dict:
    """
    Analyse opening vs closing line delta from historical lines data.
    Returns distribution of movements by spread bucket.
    """
    movements: list[float] = []
    large_moves: list[float] = []  # games with > 2pt move

    for season in seasons:
        path = os.path.join(_EXT_CACHE, f"historical_lines_{season}.json")
        if not os.path.exists(path):
            continue
        lines = json.load(open(path))
        for g in lines:
            open_spread  = g.get("open_spread")
            close_spread = g.get("closing_spread")
            if open_spread is None or close_spread is None:
                continue
            try:
                delta = float(close_spread) - float(open_spread)
                movements.append(delta)
                if abs(delta) > 2:
                    large_moves.append(delta)
            except Exception:
                continue

    if not movements:
        return {"mean_move": 0.0, "std_move": 1.5, "large_move_rate": 0.15}

    arr = np.array(movements)
    return {
        "mean_move":      float(np.mean(arr)),
        "std_move":       float(np.std(arr)),
        "abs_mean_move":  float(np.mean(np.abs(arr))),
        "large_move_rate": len(large_moves) / max(len(movements), 1),
        "pct_move_toward_home": float(np.mean(arr > 0)),
        "games_analyzed": len(movements),
    }


def train(seasons: Optional[list[str]] = None) -> dict:
    if seasons is None:
        seasons = ["2022-23", "2023-24", "2024-25"]

    log.info("Training line movement predictor...")
    stats = _build_movement_stats(seasons)

    try:
        from sklearn.linear_model import Ridge
        import numpy as np

        # Simple regression: injury_severity + sharp_signal → line_move
        # Without real injury timestamps, use simulated training data
        n = 500
        rng = np.random.default_rng(42)
        injury_sev = rng.uniform(0, 1, n)
        sharp_sig  = rng.choice([-1, 0, 1], n, p=[0.2, 0.6, 0.2])
        noise      = rng.normal(0, 0.8, n)
        line_move  = injury_sev * 2.5 * np.sign(sharp_sig + 0.1) + sharp_sig * 1.2 + noise

        X = np.column_stack([injury_sev, sharp_sig, injury_sev * sharp_sig])
        model = Ridge(alpha=1.0)
        model.fit(X, line_move)
        stats["model"] = model
    except Exception as e:
        log.debug("Line movement regression failed: %s", e)

    os.makedirs(_MODEL_DIR, exist_ok=True)
    with open(_MODEL_PATH, "wb") as f:
        pickle.dump({"stats": stats, "version": "1.0"}, f)

    log.info("Line movement predictor: %d games analyzed", stats.get("games_analyzed", 0))
    return stats


_MODEL_CACHE: Optional[dict] = None


def _load_model() -> dict:
    global _MODEL_CACHE
    if _MODEL_CACHE is not None:
        return _MODEL_CACHE
    if os.path.exists(_MODEL_PATH):
        try:
            with open(_MODEL_PATH, "rb") as f:
                _MODEL_CACHE = pickle.load(f)
                return _MODEL_CACHE
        except Exception:
            pass
    train()
    if os.path.exists(_MODEL_PATH):
        with open(_MODEL_PATH, "rb") as f:
            _MODEL_CACHE = pickle.load(f)
    else:
        _MODEL_CACHE = {"stats": {"mean_move": 0.0, "std_move": 1.5}}
    return _MODEL_CACHE


def predict_line_move(game_id: str, features: dict) -> dict:
    """
    Predict expected line movement for a game.

    Returns:
        direction:     'toward_home' / 'toward_away' / 'neutral'
        magnitude:     expected absolute movement in points
        bet_early:     True if you should bet before more info comes in
        confidence:    'high' / 'medium' / 'low'
    """
    m = _load_model()
    stats = m.get("stats", {})

    injury_severity = float(features.get("injury_severity_score", 0.0))
    sharp_signal    = float(features.get("sharp_signal", 0.0))
    dnp_prob        = float(features.get("dnp_prob", 0.05))

    # Injury drives line movement more than anything else
    injury_factor = max(injury_severity, dnp_prob) if dnp_prob > 0.3 else injury_severity

    model = stats.get("model")
    if model is not None:
        try:
            import numpy as np
            X = np.array([[injury_factor, sharp_signal, injury_factor * sharp_signal]])
            magnitude = abs(float(model.predict(X)[0]))
        except Exception:
            magnitude = injury_factor * 2.0 + abs(sharp_signal) * 1.2
    else:
        magnitude = injury_factor * 2.0 + abs(sharp_signal) * 1.2

    direction = "neutral"
    if injury_factor > 0.5:
        direction = "away_from_injured_player_team"
    elif sharp_signal > 0.3:
        direction = "toward_sharp_side"
    elif sharp_signal < -0.3:
        direction = "against_public_side"

    # Should you bet before or after the move?
    # Bet early if: injury just broke and line hasn't moved yet
    # Wait if: news is stale and market already efficient
    bet_early = bool(injury_factor > 0.4 or abs(sharp_signal) > 0.5)

    return {
        "direction":    direction,
        "magnitude":    round(float(magnitude), 2),
        "bet_early":    bet_early,
        "confidence":   "high" if magnitude > 2.0 else "medium" if magnitude > 1.0 else "low",
    }


def get_timing_advice(ev: float, sharp_signal: float) -> str:
    """Return bet timing recommendation."""
    if ev > 0.05 and sharp_signal > 0.3:
        return "BET_NOW — high EV + sharp agreement, line will move against you"
    elif ev > 0.03 and sharp_signal < -0.2:
        return "WAIT — public fade, wait for line to move in your direction"
    elif ev > 0.03:
        return "BET_SOON — positive EV, line may move either way"
    else:
        return "MONITOR — EV too low to act"
