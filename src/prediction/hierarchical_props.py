"""
hierarchical_props.py — D-3/D-4: Bayesian hierarchical blending + optimal lookback.

D-3: Blend XGBoost predictions toward position-archetype priors for small sample players.
D-4: Fit AR(p) model per player to determine optimal lookback window.

Public API
----------
    blend_prediction(xgb_pred, player_id, stat, games_played) -> float
    compute_optimal_lookback(player_id, stat) -> int
    get_archetype_prior(player_id, stat) -> float
"""

from __future__ import annotations

import json
import os
from typing import Optional

import numpy as np

_NBA_CACHE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data", "nba",
)

# D-3: Position-archetype priors (league-average per position per stat)
ARCHETYPES = {
    "PG_handler":  {"pts": 18.5, "reb": 3.8, "ast": 6.2, "fg3m": 2.1, "stl": 1.3, "blk": 0.3, "tov": 2.8},
    "SG_scorer":   {"pts": 16.2, "reb": 3.5, "ast": 2.8, "fg3m": 2.0, "stl": 1.0, "blk": 0.4, "tov": 1.9},
    "SF_wing":     {"pts": 14.8, "reb": 5.2, "ast": 2.4, "fg3m": 1.4, "stl": 1.0, "blk": 0.6, "tov": 1.6},
    "PF_stretch":  {"pts": 13.1, "reb": 6.8, "ast": 1.9, "fg3m": 1.2, "stl": 0.7, "blk": 0.9, "tov": 1.4},
    "C_rim":       {"pts": 12.4, "reb": 9.1, "ast": 1.4, "fg3m": 0.3, "stl": 0.6, "blk": 1.8, "tov": 1.7},
}

# Fallback league average (across all positions)
_LEAGUE_AVG = {
    stat: round(np.mean([v[stat] for v in ARCHETYPES.values()]), 2)
    for stat in ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov")
}

# Position → archetype mapping (NBA position abbreviations)
_POS_TO_ARCHETYPE = {
    "PG": "PG_handler", "G": "PG_handler",
    "SG": "SG_scorer",
    "SF": "SF_wing",  "F": "SF_wing",
    "PF": "PF_stretch",
    "C":  "C_rim",    "FC": "C_rim",
}

# D-4: AR-order → lookback window mapping
_AR_TO_WINDOW = {1: 5, 2: 8, 3: 12, 4: 15, 5: 20}

# Module-level cache for optimal lookback (recompute monthly in production)
_LOOKBACK_CACHE: dict = {}


def get_archetype_prior(player_id: int, stat: str) -> float:
    """
    D-3: Return position-archetype prior for a player/stat.

    Loads player position from data/nba/player_bio.json.
    Falls back to league average if position unknown.
    """
    try:
        bio_path = os.path.join(_NBA_CACHE, "player_bio.json")
        if not os.path.exists(bio_path):
            return _LEAGUE_AVG.get(stat, 10.0)
        bios = json.load(open(bio_path))
        # Bio files may be list or dict keyed by player_id
        if isinstance(bios, list):
            pid_map = {int(r.get("id", r.get("player_id", 0))): r for r in bios}
        else:
            pid_map = {int(k): v for k, v in bios.items()}

        bio = pid_map.get(int(player_id), {})
        position = str(bio.get("position", bio.get("pos", ""))).strip().upper()

        # Normalise common position strings
        for pos_key in _POS_TO_ARCHETYPE:
            if pos_key in position:
                archetype = _POS_TO_ARCHETYPE[pos_key]
                return float(ARCHETYPES[archetype].get(stat, _LEAGUE_AVG.get(stat, 10.0)))
    except Exception:
        pass
    return _LEAGUE_AVG.get(stat, 10.0)


def blend_prediction(
    xgb_pred: float,
    player_id: int,
    stat: str,
    games_played: int,
) -> float:
    """
    D-3: Bayesian hierarchical blend of XGBoost prediction with archetype prior.

    season_weight ramps from 0 (0 games) to 1.0 (25+ games):
      Games 0-5:   ~20% season, ~80% archetype
      Games 11-25: ~50% season, ~50% archetype
      Games 25+:   100% season (no blending)

    Args:
        xgb_pred:     XGBoost model prediction.
        player_id:    NBA player ID.
        stat:         Prop stat name.
        games_played: Number of season games played so far.

    Returns:
        Blended prediction float.
    """
    season_weight = min(float(max(games_played, 0)) / 25.0, 1.0)
    archetype_prior = get_archetype_prior(player_id, stat)
    return round(season_weight * xgb_pred + (1.0 - season_weight) * archetype_prior, 3)


# ── D-4: Optimal lookback ─────────────────────────────────────────────────────

def compute_optimal_lookback(player_id: int, stat: str) -> int:
    """
    D-4: Select optimal rolling lookback window using AR(p) AIC minimisation.

    Fits AR(1) through AR(5) on player's last 50 game values.
    Returns lookback in [5, 30] games mapped from optimal AR order.

    Results cached in module-level dict.
    """
    cache_key = (int(player_id), stat.lower())
    if cache_key in _LOOKBACK_CACHE:
        return _LOOKBACK_CACHE[cache_key]

    _default = 10  # median lookback when undetermined

    try:
        season = "2024-25"
        gamelog_path = os.path.join(_NBA_CACHE, f"gamelog_{player_id}_{season}.json")
        if not os.path.exists(gamelog_path):
            return _default

        rows = json.load(open(gamelog_path))
        col_map = {"pts": "PTS", "reb": "REB", "ast": "AST",
                   "fg3m": "FG3M", "stl": "STL", "blk": "BLK", "tov": "TOV"}
        col = col_map.get(stat.lower(), stat.upper())
        series = np.array([float(r.get(col, 0) or 0) for r in rows
                           if r.get(col) is not None], dtype=float)[-50:]

        if len(series) < 10:
            return _default

        best_p, best_aic = 1, float("inf")
        for p in range(1, 6):
            if len(series) <= p + 1:
                continue
            try:
                aic = _aic_ar(series, p)
                if aic < best_aic:
                    best_aic = aic
                    best_p = p
            except Exception:
                continue

        window = int(np.clip(_AR_TO_WINDOW.get(best_p, 10), 5, 30))
        _LOOKBACK_CACHE[cache_key] = window
        return window
    except Exception:
        return _default


def _aic_ar(series: np.ndarray, p: int) -> float:
    """Compute AIC for AR(p) model via OLS."""
    n = len(series)
    y = series[p:]
    X = np.column_stack([series[p - i - 1: n - i - 1] for i in range(p)])
    # OLS: theta = (X'X)^{-1} X'y
    try:
        theta, residuals, _, _ = np.linalg.lstsq(X, y, rcond=None)
    except np.linalg.LinAlgError:
        return float("inf")
    if len(residuals) == 0:
        resid = y - X @ theta
        sse = float(np.sum(resid ** 2))
    else:
        sse = float(residuals[0])
    if sse <= 0:
        return float("inf")
    n_eff = len(y)
    log_lik = -0.5 * n_eff * (1.0 + np.log(2 * np.pi * sse / n_eff))
    return float(-2.0 * log_lik + 2.0 * (p + 1))
