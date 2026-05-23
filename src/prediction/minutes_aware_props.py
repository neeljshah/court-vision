"""
minutes_aware_props.py — Post-process raw prop predictions with expected minutes.

Each counting stat is scaled by (expected_minutes / season_avg_minutes) raised
to its elasticity exponent.  Rate stats (FT%, 3P%) are NOT scaled.

Public API
----------
    adjust_props_for_minutes(base_props, player_id, game_context,
                             season_avg_minutes) -> dict
    MINUTES_ELASTICITY  -- the scaling table (importable for tests)
"""
from __future__ import annotations

import logging
from typing import Dict, Optional

log = logging.getLogger(__name__)

# ── Scaling table ─────────────────────────────────────────────────────────────
# elasticity = exponent applied to minutes_factor.
# 1.0 = fully linear  |  <1.0 = sublinear  |  >1.0 = superlinear
# Rate stats (fg_pct, ft_pct, fg3_pct) are excluded — they don't scale with time.
MINUTES_ELASTICITY: Dict[str, float] = {
    "pts":   0.95,   # sublinear — fatigue + starter usage compression
    "reb":   1.00,   # linear
    "ast":   0.95,   # sublinear — playmaking compressed in short stints
    "fg3m":  0.95,   # sublinear
    "stl":   1.00,   # linear
    "blk":   1.00,   # linear
    "tov":   1.05,   # superlinear — turnover rate higher in compressed/tired minutes
    "fga":   0.95,
    "fta":   0.95,
    "drb":   1.00,
    "orb":   1.00,
    "pf":    1.00,
    "plus_minus": 0.90,  # blowout/garbage time compression
}

# Stats that are rates/percentages — never scaled by minutes
_RATE_STATS = frozenset({
    "fg_pct", "fg3_pct", "ft_pct",
    "ts_pct", "efg_pct", "usg_pct",
    "ast_pct", "reb_pct", "stl_pct", "blk_pct",
})


# ── Core function ─────────────────────────────────────────────────────────────

def adjust_props_for_minutes(
    base_props: dict,
    player_id: int,
    game_context: dict,
    season_avg_minutes: float,
    *,
    predictor=None,
) -> dict:
    """
    Scale base prop predictions by expected minutes vs season average.

    Parameters
    ----------
    base_props           : Raw prop dict (e.g. {"pts": 28.3, "reb": 8.1, ...})
    player_id            : NBA player ID (int)
    game_context         : Dict passed to MinutesPredictor (is_b2b, rest_days, etc.)
    season_avg_minutes   : Player's season average minutes per game (float)
    predictor            : Optional pre-loaded MinutesPredictor instance.
                           One is created automatically if None.

    Returns
    -------
    dict with all original keys preserved, each counting stat rescaled,
    plus injected keys: "expected_minutes", "p_dnp", "p_load_mgmt",
    "minutes_factor", "minutes_std".
    """
    if season_avg_minutes <= 0:
        log.warning("season_avg_minutes=%.1f is invalid, defaulting to 28.0", season_avg_minutes)
        season_avg_minutes = 28.0

    # Lazy import to avoid circular deps
    if predictor is None:
        from src.prediction.minutes_predictor import MinutesPredictor
        predictor = MinutesPredictor()

    dist = predictor.predict_minutes_distribution(player_id, game_context)
    expected_min = dist["expected_minutes"]
    p_dnp = dist["p_dnp"]
    p_load = dist["p_load_mgmt"]

    minutes_factor = expected_min / season_avg_minutes  # e.g. 0.88 for a B2B

    adjusted = dict(base_props)  # shallow copy — preserve all original keys

    for stat, base_val in base_props.items():
        if stat in _RATE_STATS:
            # Rate stats: unchanged
            continue
        if not isinstance(base_val, (int, float)):
            continue

        elasticity = MINUTES_ELASTICITY.get(stat, 1.0)
        try:
            scaled = float(base_val) * (minutes_factor ** elasticity)
        except Exception:
            scaled = float(base_val)

        adjusted[stat] = round(scaled, 4)

    # Inject metadata
    adjusted["expected_minutes"] = round(expected_min, 2)
    adjusted["p_dnp"] = round(p_dnp, 4)
    adjusted["p_load_mgmt"] = round(p_load, 4)
    adjusted["minutes_factor"] = round(minutes_factor, 4)
    adjusted["minutes_std"] = round(dist.get("minutes_std", 0.0), 2)

    return adjusted


# ── Batch helper ──────────────────────────────────────────────────────────────

def adjust_roster_props(
    roster_props: Dict[int, dict],
    game_context: dict,
    season_avg_minutes_map: Dict[int, float],
) -> Dict[int, dict]:
    """
    Adjust props for an entire roster dict.

    Parameters
    ----------
    roster_props          : {player_id: base_props_dict}
    game_context          : Shared game context (is_b2b, rest_days, …)
    season_avg_minutes_map: {player_id: season_avg_min}

    Returns
    -------
    {player_id: adjusted_props_dict}
    """
    from src.prediction.minutes_predictor import MinutesPredictor
    predictor = MinutesPredictor()  # single instance, lazy model loads

    result: Dict[int, dict] = {}
    for pid, props in roster_props.items():
        avg_min = season_avg_minutes_map.get(pid, 28.0)
        result[pid] = adjust_props_for_minutes(
            props, pid, game_context, avg_min, predictor=predictor
        )
    return result
