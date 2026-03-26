"""
season_regression_detector.py — Detect players disconnected from efficiency metrics.

Identifies:
  Overperformer: pts/game > BPM-predicted by >2.5 pts → regression signal
  Underperformer: pts/game < BPM-predicted by >2.5 pts → uptick signal

Uses BBRef BPM/VORP/WS48 from data/external/bbref_advanced_{season}.json

Public API
----------
    predict_regression(player_name, season) -> dict
        -> {regression_signal (-1 to 1), pts_above_efficiency, likely_direction}
"""
from __future__ import annotations

import json
import os
import sys
from typing import Optional

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_DIR)

_NBA_CACHE  = os.path.join(PROJECT_DIR, "data", "nba")
_EXT_CACHE  = os.path.join(PROJECT_DIR, "data", "external")

# Regression threshold: pts gap needed to signal over/under-performance
_REGRESSION_THRESHOLD = 2.5

# BPM → expected pts/game linear coefficients
# Derived from NBA data: ~14 pts/game at BPM=0, ~+1.0 pts per BPM unit
_BPM_INTERCEPT  = 14.0
_BPM_SLOPE      = 1.0
# WS/48 contribution: ~+10 pts per 0.1 WS/48 above league avg (0.100)
_WS48_SCALE     = 80.0
_WS48_LEAGUE_AVG = 0.100


def _load_bbref_data(player_name: str, season: str) -> dict:
    """Load BBRef advanced stats for player. Returns {} on miss."""
    try:
        from src.data.bbref_scraper import get_player_bpm as _get_bpm
        return _get_bpm(player_name, season)
    except Exception:
        pass

    # Direct file fallback
    try:
        fpath = os.path.join(_EXT_CACHE, f"bbref_advanced_{season}.json")
        if not os.path.exists(fpath):
            return {}

        import unicodedata
        def _norm(s):
            return unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower()

        data = json.load(open(fpath))
        key = _norm(player_name)
        if isinstance(data, dict):
            norm_data = {_norm(k): v for k, v in data.items()}
            return norm_data.get(key, {})
        elif isinstance(data, list):
            for row in data:
                if _norm(str(row.get("player", ""))) == key:
                    return row
    except Exception:
        pass
    return {}


def _load_player_pts(player_name: str, season: str) -> Optional[float]:
    """Load player's current season pts/game from avgs cache."""
    try:
        import unicodedata
        def _norm(s):
            return unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower()

        avgs_path = os.path.join(_NBA_CACHE, f"player_avgs_{season}.json")
        avgs = json.load(open(avgs_path))
        key = _norm(player_name)
        norm_avgs = {_norm(k): v for k, v in avgs.items()}
        pdata = norm_avgs.get(key, {})
        pts = pdata.get("pts")
        return float(pts) if pts is not None else None
    except Exception:
        return None


def _bpm_to_expected_pts(bpm: float, ws_per_48: float = 0.100) -> float:
    """
    Estimate expected pts/game from BPM + WS/48.

    Formula: pts = intercept + bpm * slope + (ws48 - league_avg) * ws_scale
    """
    return (
        _BPM_INTERCEPT
        + bpm * _BPM_SLOPE
        + (ws_per_48 - _WS48_LEAGUE_AVG) * _WS48_SCALE
    )


def _regression_signal_from_gap(pts_gap: float) -> float:
    """
    Convert pts gap (actual - expected) to regression signal (-1 to 1).

    Positive signal = regression expected (overperformer → expect drop).
    Negative signal = uptick expected (underperformer → expect rise).
    """
    import math
    # Sigmoidal: maps -10…+10 pts gap to -1…+1 regression signal
    # +2.5 pts gap → ~0.5 signal; -2.5 pts gap → ~-0.5 signal
    return round(math.tanh(pts_gap / 5.0), 4)


def predict_regression(
    player_name: str,
    season: str = "2024-25",
) -> dict:
    """
    Compute regression signal from BBRef BPM vs actual box-score pts.

    Returns:
        {regression_signal, pts_above_efficiency, likely_direction, bpm, pts_actual, pts_expected}
    """
    bbref = _load_bbref_data(player_name, season)
    pts_actual = _load_player_pts(player_name, season)

    bpm       = float(bbref.get("bpm",        0.0) or 0.0)
    vorp      = float(bbref.get("vorp",       0.0) or 0.0)
    ws_per_48 = float(bbref.get("ws_per_48",  0.0) or 0.0)

    if pts_actual is None:
        pts_actual = float(bbref.get("pts_per_g", 14.0) or 14.0)

    pts_expected = _bpm_to_expected_pts(bpm, ws_per_48)
    pts_gap = pts_actual - pts_expected  # positive = overperforming vs efficiency

    signal = _regression_signal_from_gap(pts_gap)

    if pts_gap > _REGRESSION_THRESHOLD:
        likely_direction = "down"
    elif pts_gap < -_REGRESSION_THRESHOLD:
        likely_direction = "up"
    else:
        likely_direction = "neutral"

    return {
        "regression_signal":    signal,            # -1 to 1; positive = expect regression
        "pts_above_efficiency": round(pts_gap, 2), # positive = overperforming
        "likely_direction":     likely_direction,  # "up", "down", "neutral"
        "bpm":                  round(bpm, 2),
        "pts_actual":           round(pts_actual, 1),
        "pts_expected":         round(pts_expected, 1),
        "vorp":                 round(vorp, 2),
    }


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("player")
    ap.add_argument("--season", default="2024-25")
    args = ap.parse_args()
    r = predict_regression(args.player, args.season)
    print(json.dumps(r, indent=2))
