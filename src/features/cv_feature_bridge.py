"""
cv_feature_bridge.py — Aggregate per-player spatial stats from data/features.csv.

Exposes get_cv_features(player_name) -> dict of 6 broadcast-derived spatial signals.
Falls back to empty dict when features.csv is absent or player has no rows.
These features are not available to sportsbooks — CV moat signals.
"""
from __future__ import annotations

import os
from typing import Optional

_FEATURES_CSV = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data", "features.csv",
)

# Module-level cache: loaded once per process
_cache: Optional[dict] = None
_cache_mtime: float = 0.0

_DEFAULTS: dict = {
    "cvb_avg_defender_dist": 0.0,
    "cvb_avg_spacing":       0.0,
    "cvb_avg_velocity":      0.0,
    "cvb_fatigue_score":     0.0,
    "cvb_paint_time_pct":    0.0,
    "cvb_off_ball_dist":     0.0,
}

# CSV columns to aggregate → output key, aggregation
_COL_MAP = {
    "defender_dist_mean_90": "cvb_avg_defender_dist",
    "team_spacing":          "cvb_avg_spacing",
    "velocity":              "cvb_avg_velocity",
    "dist_traveled_90":      "cvb_fatigue_score",  # proxy: distance as fatigue
    "paint_pressure_90":     "cvb_paint_time_pct",
    "off_ball_dist_mean_90": "cvb_off_ball_dist",
}


def _load_cache() -> dict:
    """Load features.csv into {player_name: {col: [values]}} cache."""
    global _cache, _cache_mtime
    if not os.path.exists(_FEATURES_CSV):
        return {}
    mtime = os.path.getmtime(_FEATURES_CSV)
    if _cache is not None and mtime == _cache_mtime:
        return _cache

    import csv
    result: dict = {}
    try:
        with open(_FEATURES_CSV, newline="", encoding="utf-8", errors="ignore") as f:
            reader = csv.DictReader(f)
            for row in reader:
                name = (row.get("player_name") or "").strip().lower()
                if not name or name.startswith("green#") or name.startswith("white#"):
                    continue
                if name not in result:
                    result[name] = {col: [] for col in _COL_MAP}
                for col in _COL_MAP:
                    raw = row.get(col, "")
                    try:
                        val = float(raw)
                        if val != 0.0:  # skip default-zero rows
                            result[name][col].append(val)
                    except (ValueError, TypeError):
                        pass
    except Exception:
        return {}
    _cache = result
    _cache_mtime = mtime
    return result


def get_cv_features(player_name: str) -> dict:
    """
    Return aggregated CV spatial features for player_name.

    Matches by lowercase full name. Returns _DEFAULTS (all zeros) when
    the player has no rows in features.csv, so callers can unconditionally
    merge the result into their feature dict.

    Args:
        player_name: Full player name, e.g. "LeBron James".

    Returns:
        Dict with keys: cvb_avg_defender_dist, cvb_avg_spacing, cvb_avg_velocity,
        cvb_fatigue_score, cvb_paint_time_pct, cvb_off_ball_dist.
    """
    cache = _load_cache()
    key = player_name.strip().lower()
    if key not in cache:
        return _DEFAULTS.copy()

    player_data = cache[key]
    out = _DEFAULTS.copy()
    for col, out_key in _COL_MAP.items():
        vals = player_data.get(col, [])
        if vals:
            out[out_key] = round(sum(vals) / len(vals), 4)
    return out
