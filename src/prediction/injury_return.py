"""
injury_return.py -- Phase E3: Injury return timeline curve.

Predicts expected return date and performance trajectory after injury.
Uses injury type + player age + historical injury return data.

Public API
----------
    predict_return_timeline(player_name, injury_type, days_out)  -> dict
    get_performance_curve(injury_type, days_since_return)        -> float
"""
from __future__ import annotations

import os
import sys
from typing import Optional

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_DIR)

# Expected days out by injury type (median from historical NBA data)
_INJURY_DAYS = {
    "ankle_sprain_mild":      7,
    "ankle_sprain_moderate": 14,
    "ankle_sprain_severe":   42,
    "knee_sprain":           21,
    "hamstring_strain":      14,
    "calf_strain":           14,
    "quad_strain":           10,
    "hip_flexor":             7,
    "back_soreness":          3,
    "illness":                3,
    "concussion":             7,
    "finger":                 5,
    "wrist":                 14,
    "shoulder":              21,
    "acl":                  270,
    "achilles":             270,
    "fracture":              60,
    "other":                 10,
}

# Performance recovery curve by days since return (0=full, 1=return day)
# Index = day since return, value = performance multiplier
_RECOVERY_CURVES = {
    "ankle":     [0.82, 0.86, 0.90, 0.93, 0.95, 0.97, 0.98, 0.99, 1.00],
    "hamstring": [0.80, 0.85, 0.89, 0.92, 0.95, 0.97, 0.99, 1.00, 1.00],
    "knee":      [0.75, 0.80, 0.85, 0.89, 0.92, 0.95, 0.97, 0.99, 1.00],
    "back":      [0.85, 0.88, 0.91, 0.94, 0.96, 0.98, 1.00, 1.00, 1.00],
    "illness":   [0.88, 0.92, 0.96, 0.99, 1.00, 1.00, 1.00, 1.00, 1.00],
    "acl":       [0.72, 0.78, 0.83, 0.87, 0.91, 0.94, 0.96, 0.98, 1.00],
    "default":   [0.83, 0.87, 0.91, 0.94, 0.96, 0.98, 0.99, 1.00, 1.00],
}


def _categorize_injury(injury_type: str) -> str:
    """Map detailed injury string to curve category."""
    inj = injury_type.lower()
    if "ankle" in inj:     return "ankle"
    if "hamstring" in inj: return "hamstring"
    if "knee" in inj:      return "knee"
    if "back" in inj:      return "back"
    if "illness" in inj or "sick" in inj: return "illness"
    if "acl" in inj or "achilles" in inj: return "acl"
    return "default"


def get_performance_curve(injury_type: str, days_since_return: int) -> float:
    """
    Return performance multiplier for a player N days after returning from injury.

    Args:
        injury_type:       Injury description string
        days_since_return: Days since the player returned to play (0 = return day)

    Returns:
        Performance multiplier 0–1 (1.0 = fully healthy).
    """
    category = _categorize_injury(injury_type)
    curve = _RECOVERY_CURVES.get(category, _RECOVERY_CURVES["default"])
    idx = min(days_since_return, len(curve) - 1)
    return curve[idx]


def predict_return_timeline(
    player_name:  str,
    injury_type:  str,
    days_out:     Optional[int] = None,
    season:       str = "2024-25",
) -> dict:
    """
    Predict return timeline and post-return performance curve.

    Args:
        player_name:  Player name
        injury_type:  Injury description (e.g. "ankle_sprain_moderate")
        days_out:     Days already missed (None = use median for injury type)
        season:       Season string

    Returns:
        {
            "player":           str,
            "injury_type":      str,
            "days_out":         int,
            "expected_return":  str,   # "X days remaining"
            "performance_curve": list, # multipliers day 0-8 after return
            "age_penalty":      float, # additional penalty for older players
            "projected_stats":  dict,  # adjusted props on return
        }
    """
    # Lookup baseline days out
    best_match = injury_type.lower().replace(" ", "_")
    baseline_days = _INJURY_DAYS.get(best_match, _INJURY_DAYS["other"])
    if days_out is None:
        days_out = baseline_days

    days_remaining = max(0, baseline_days - days_out)

    # Age penalty — players 32+ recover ~15% slower
    age = 0.0
    try:
        from src.data.player_scraper import get_player_profile
        profile = get_player_profile(player_name)
        if profile:
            age = float(profile.get("age", 0) or 0)
    except Exception:
        pass

    age_penalty = 0.0
    if age >= 35:
        age_penalty = 0.08
    elif age >= 32:
        age_penalty = 0.04

    category = _categorize_injury(injury_type)
    raw_curve = _RECOVERY_CURVES.get(category, _RECOVERY_CURVES["default"])
    adj_curve = [round(v * (1.0 - age_penalty), 3) for v in raw_curve]

    # Project stats on return (day 0 multiplier)
    return_mult = adj_curve[0]
    projected_stats: dict = {}
    try:
        from src.prediction.player_props import predict_props
        preds = predict_props(player_name=player_name, season=season)
        props = preds.get("props", preds)
        for stat, val in props.items():
            if isinstance(val, (int, float)):
                projected_stats[stat] = round(float(val) * return_mult, 2)
            elif isinstance(val, dict) and "prediction" in val:
                projected_stats[stat] = round(float(val["prediction"]) * return_mult, 2)
    except Exception:
        pass

    return {
        "player":            player_name,
        "injury_type":       injury_type,
        "days_out":          days_out,
        "days_remaining":    days_remaining,
        "expected_return":   f"{days_remaining} days" if days_remaining > 0 else "available",
        "performance_curve": adj_curve,
        "age_penalty":       age_penalty,
        "projected_stats":   projected_stats,
    }


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--player",  default="LeBron James")
    parser.add_argument("--injury",  default="ankle_sprain_moderate")
    parser.add_argument("--days",    type=int, default=None)
    parser.add_argument("--season",  default="2024-25")
    args = parser.parse_args()

    result = predict_return_timeline(args.player, args.injury, args.days, args.season)
    import json
    print(json.dumps(result, indent=2))
