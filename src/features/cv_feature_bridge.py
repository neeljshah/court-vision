"""
cv_feature_bridge.py — Aggregate per-player spatial stats from CV features CSV.

Exposes get_cv_features(player_name, game_id=None) -> dict of 6 broadcast-derived
spatial signals.  When game_id is provided, reads from:
    data/tracking/{game_id}/features.csv
Otherwise falls back to the legacy flat path data/features.csv for backward compat.
Falls back to _DEFAULTS (all zeros) when the file is absent or the player has no rows.
These features are not available to sportsbooks — CV moat signals.
"""
from __future__ import annotations

import os
from typing import Optional

_PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Legacy flat path — kept for backward compatibility when game_id is not provided.
_FEATURES_CSV = os.path.join(_PROJECT_DIR, "data", "features.csv")


def _per_game_path(game_id: str) -> str:
    """Return the features.csv path for a specific game."""
    return os.path.join(_PROJECT_DIR, "data", "tracking", game_id, "features.csv")


# Module-level cache: keyed by resolved file path
_cache: dict[str, dict] = {}       # path -> player data
_cache_mtime: dict[str, float] = {}  # path -> mtime at last load
_player_cache: dict[tuple, dict] = {}  # (path, player_name) -> features dict (fast-path)

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


def _load_cache(path: str) -> dict:
    """Load a features.csv at *path* into {player_name: {col: [values]}} cache."""
    if not os.path.exists(path):
        return {}
    mtime = os.path.getmtime(path)
    if path in _cache and _cache_mtime.get(path) == mtime:
        return _cache[path]

    import csv
    result: dict = {}
    try:
        with open(path, newline="", encoding="utf-8", errors="ignore") as f:
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
    _cache[path] = result
    _cache_mtime[path] = mtime
    return result


def get_cv_features(player_name: str, game_id: Optional[str] = None) -> dict:
    """
    Return aggregated CV spatial features for player_name.

    When game_id is provided, loads data/tracking/{game_id}/features.csv.
    Otherwise falls back to the legacy flat path data/features.csv.

    Matches by lowercase full name. Returns _DEFAULTS (all zeros) when
    the player has no rows, so callers can unconditionally merge the result.

    Args:
        player_name: Full player name, e.g. "LeBron James".
        game_id:     Optional NBA game ID (e.g. "0022400625") for per-game lookup.

    Returns:
        Dict with keys: cvb_avg_defender_dist, cvb_avg_spacing, cvb_avg_velocity,
        cvb_fatigue_score, cvb_paint_time_pct, cvb_off_ball_dist.
    """
    if game_id:
        path = _per_game_path(game_id)
        # Fallback to legacy if per-game file absent
        if not os.path.exists(path):
            path = _FEATURES_CSV
    else:
        path = _FEATURES_CSV

    key = player_name.strip().lower()
    cache_key = (path, key)
    # Fast-path: skip file reload if (path, player_name) already cached and file unchanged
    if cache_key in _player_cache:
        mtime = os.path.getmtime(path) if os.path.exists(path) else 0.0
        if _cache_mtime.get(path) == mtime:
            return _player_cache[cache_key]

    data = _load_cache(path)
    if key not in data:
        _player_cache[cache_key] = _DEFAULTS.copy()
        return _DEFAULTS.copy()

    player_data = data[key]
    out = _DEFAULTS.copy()
    for col, out_key in _COL_MAP.items():
        vals = player_data.get(col, [])
        if vals:
            out[out_key] = round(sum(vals) / len(vals), 4)

    # Bug 40 fix: per-game min-max scale cvb_fatigue_score to [0, 1].
    # dist_traveled_90 is raw pixel distance (~0-5000+); avg_fatigue_proxy
    # (tracking_feature_extractor.py Bug-4 fix) is already in [0, 1] via
    # z-score normalisation.  Comparing them raw inflated delta by ~222.7.
    # We normalise across all players in the same loaded game file so the
    # scale matches avg_fatigue_proxy's domain.
    raw_dist_vals = [
        sum(p["dist_traveled_90"]) / len(p["dist_traveled_90"])
        for p in data.values()
        if p.get("dist_traveled_90")
    ]
    if raw_dist_vals and len(raw_dist_vals) > 1:
        game_min = min(raw_dist_vals)
        game_max = max(raw_dist_vals)
        denom = game_max - game_min
        if denom > 0:
            raw_avg = out["cvb_fatigue_score"]
            out["cvb_fatigue_score"] = round((raw_avg - game_min) / denom, 4)

    _player_cache[cache_key] = out
    return out
