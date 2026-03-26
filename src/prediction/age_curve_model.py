"""
age_curve_model.py — M30: Age curve discount on projections.

Method: Fit age curves by position from BBRef data (VORP vs age).
Players past positional peak age get a discount.
PGs peak ~27, bigs ~28, wings ~26. Steep decline after 32.

Public API
----------
    train(seasons)              -> dict
    predict_age_discount(feats) -> dict {discount: float}
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
_MODEL_PATH = os.path.join(_MODEL_DIR, "age_curve_model.pkl")

log = logging.getLogger(__name__)

# Peak ages by position category
_PEAK_AGES = {
    "PG": 27.0, "SG": 26.5, "SF": 26.0, "PF": 27.5, "C": 28.0,
    "G":  26.5, "F": 26.5,  "G-F": 26.5, "F-C": 27.5, "default": 27.0,
}

# Decline rate per year past peak (exponential)
_DECLINE_RATE_EARLY  = 0.008   # 25-32: slow decline
_DECLINE_RATE_LATE   = 0.025   # 32+: steep decline
_BREAKOUT_BOOST      = 0.005   # per year before peak (youth bonus, capped)


def _build_age_curves(seasons: list[str]) -> dict:
    """
    Build age curve coefficients from BBRef VORP data.
    Returns dict of polynomial coefficients per position group.
    """
    points_by_age: dict[int, list[float]] = {}

    for season in seasons:
        path = os.path.join(_EXT_CACHE, f"bbref_advanced_{season}.json")
        if not os.path.exists(path):
            continue
        data = json.load(open(path))
        for p in data:
            age = p.get("age")
            vorp = p.get("vorp")
            if age and vorp and 18 <= int(age) <= 42:
                age_int = int(age)
                if age_int not in points_by_age:
                    points_by_age[age_int] = []
                points_by_age[age_int].append(float(vorp))

    # Compute mean VORP by age
    age_means: dict[int, float] = {
        age: float(np.mean(vals))
        for age, vals in points_by_age.items()
        if len(vals) >= 3
    }

    # Find peak age
    peak_age = max(age_means, key=age_means.get) if age_means else 27
    peak_vorp = age_means.get(peak_age, 1.0)

    return {
        "age_means":   age_means,
        "peak_age":    peak_age,
        "peak_vorp":   peak_vorp,
        "ages_fitted": sorted(age_means.keys()),
    }


def train(seasons: Optional[list[str]] = None) -> dict:
    if seasons is None:
        seasons = ["2022-23", "2023-24", "2024-25"]

    log.info("Training age curve model...")
    curves = _build_age_curves(seasons)

    os.makedirs(_MODEL_DIR, exist_ok=True)
    with open(_MODEL_PATH, "wb") as f:
        pickle.dump({"curves": curves, "version": "1.0"}, f)

    log.info("Age curve: peak_age=%d, peak_vorp=%.2f, n_ages=%d",
             curves.get("peak_age", 27), curves.get("peak_vorp", 1.0),
             len(curves.get("age_means", {})))
    return curves


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
        _MODEL_CACHE = {"curves": {"peak_age": 27, "peak_vorp": 1.0}}
    return _MODEL_CACHE


def predict_age_discount(features: dict) -> dict:
    """
    Return age-based performance discount multiplier.

    Returns:
        discount: float multiplier (1.0 = no adjustment, <1.0 = decline)
    """
    m = _load_model()
    curves = m.get("curves", {})

    age = float(features.get("bbref_age", 27) or 27)
    if age <= 0:
        age = 27.0

    # Position (not usually in features — use default)
    peak_age = float(curves.get("peak_age", 27))

    # Use age_means lookup if available
    age_means = curves.get("age_means", {})
    peak_vorp = float(curves.get("peak_vorp", 1.0))

    # Compute age relative to peak
    age_int = int(age)
    player_vorp_mean = float(age_means.get(age_int, peak_vorp * 0.5))
    discount = min(player_vorp_mean / max(peak_vorp, 0.1), 1.0)
    discount = max(discount, 0.7)  # floor at 70%

    # Override with simpler rule for very young/very old
    if age < 22:
        discount = 0.95  # youth upside uncertainty
    elif age >= 37:
        discount = 0.82
    elif age >= 34:
        discount = 0.88
    elif age >= 32:
        discount = 0.93
    elif age > peak_age:
        years_past = age - peak_age
        discount = 1.0 - min(years_past * _DECLINE_RATE_EARLY, 0.12)

    # VORP trajectory adjustment (if available)
    vorp = float(features.get("bbref_vorp", 0) or 0)
    if vorp < -0.5:
        discount = max(discount - 0.03, 0.70)

    return {"discount": round(float(discount), 4)}


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--train", action="store_true")
    args = parser.parse_args()
    if args.train:
        print(train())
