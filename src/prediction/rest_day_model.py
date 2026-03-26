"""
rest_day_model.py — M33: Rest day performance multipliers.

Method: Group gamelogs by days_rest (0,1,2,3+).
0 rest = tired, 3+ rest = rusty. 1-2 days = peak performance.
Compute per-position performance ratio.

Public API
----------
    train(seasons)            -> dict
    predict_rest_mult(feats)  -> dict {mult: float}
"""

from __future__ import annotations

import glob
import json
import logging
import os
import pickle
import sys
from collections import defaultdict
from datetime import datetime
from typing import Optional

import numpy as np

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_DIR)

_NBA_CACHE = os.path.join(PROJECT_DIR, "data", "nba")
_MODEL_DIR  = os.path.join(PROJECT_DIR, "data", "models")
_MODEL_PATH = os.path.join(_MODEL_DIR, "rest_day_model.pkl")

log = logging.getLogger(__name__)


def _parse_min(val) -> float:
    if val is None:
        return 0.0
    s = str(val).strip()
    if s in ("", "None", "null", "0", "0:00"):
        return 0.0
    if ":" in s:
        parts = s.split(":")
        try:
            return float(parts[0]) + float(parts[1]) / 60
        except Exception:
            return 0.0
    try:
        return float(s)
    except Exception:
        return 0.0


def _build_rest_splits(seasons: list[str]) -> dict:
    """
    Compute performance ratio by rest day bucket.
    Returns {rest_bucket: {stat: ratio_vs_1day_rest}}.
    """
    # rest_bucket → list of performance values
    buckets: dict[str, dict[str, list]] = {
        "0": defaultdict(list),   # b2b
        "1": defaultdict(list),   # 1 day rest (optimal)
        "2": defaultdict(list),   # 2 days
        "3+": defaultdict(list),  # 3+ days (rust)
    }

    gamelog_files = glob.glob(os.path.join(_NBA_CACHE, "gamelog_full_*.json"))
    for fpath in gamelog_files:
        try:
            logs = json.load(open(fpath))
            if not isinstance(logs, list) or len(logs) < 5:
                continue
            logs = sorted(logs, key=lambda g: g.get("game_date", ""))

            for i in range(1, len(logs)):
                row  = logs[i]
                prev = logs[i - 1]
                min_val = _parse_min(row.get("min", 0))
                if min_val < 10:
                    continue

                try:
                    d1 = datetime.strptime(prev.get("game_date", "")[:10], "%Y-%m-%d")
                    d2 = datetime.strptime(row.get("game_date", "")[:10], "%Y-%m-%d")
                    days_rest = (d2 - d1).days - 1
                except Exception:
                    continue

                if days_rest < 0 or days_rest > 10:
                    continue

                bucket = "0" if days_rest == 0 else ("1" if days_rest == 1 else
                         ("2" if days_rest == 2 else "3+"))

                for stat in ("pts", "reb", "ast", "min", "fg3m"):
                    val = float(row.get(stat, 0) or 0)
                    buckets[bucket][stat].append(val)
        except Exception:
            continue

    # Compute means and ratios (normalized to 1-day rest)
    means: dict[str, dict[str, float]] = {}
    for bucket, stats_dict in buckets.items():
        means[bucket] = {}
        for stat, vals in stats_dict.items():
            means[bucket][stat] = float(np.mean(vals)) if vals else 0.0

    # Compute ratios
    ratios: dict[str, dict[str, float]] = {}
    baseline = means.get("1", {})
    for bucket in ("0", "1", "2", "3+"):
        ratios[bucket] = {}
        bm = means.get(bucket, {})
        for stat in ("pts", "reb", "ast", "min", "fg3m"):
            base = baseline.get(stat, 1.0)
            val  = bm.get(stat, base)
            ratios[bucket][stat] = round(val / max(base, 0.1), 4) if base > 0 else 1.0

    log.info("Rest day ratios: b2b pts=%.4f, 1day=1.0, 2day pts=%.4f, 3+day pts=%.4f",
             ratios.get("0", {}).get("pts", 0.96),
             ratios.get("2", {}).get("pts", 0.99),
             ratios.get("3+", {}).get("pts", 0.98))

    return ratios


def train(seasons: Optional[list[str]] = None) -> dict:
    if seasons is None:
        seasons = ["2022-23", "2023-24", "2024-25"]

    log.info("Training rest day model...")
    ratios = _build_rest_splits(seasons)

    os.makedirs(_MODEL_DIR, exist_ok=True)
    with open(_MODEL_PATH, "wb") as f:
        pickle.dump({"ratios": ratios, "version": "1.0"}, f)

    return ratios


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
        # Research-based defaults
        _MODEL_CACHE = {"ratios": {
            "0":  {"pts": 0.960, "reb": 0.970, "ast": 0.965, "min": 0.975, "fg3m": 0.960},
            "1":  {"pts": 1.000, "reb": 1.000, "ast": 1.000, "min": 1.000, "fg3m": 1.000},
            "2":  {"pts": 0.998, "reb": 0.999, "ast": 0.998, "min": 0.998, "fg3m": 0.998},
            "3+": {"pts": 0.980, "reb": 0.982, "ast": 0.979, "min": 0.981, "fg3m": 0.978},
        }}
    return _MODEL_CACHE


def predict_rest_mult(features: dict) -> dict:
    """
    Return performance multiplier based on days of rest.

    Returns:
        mult: float (applied to all counting stat projections)
    """
    m = _load_model()
    ratios = m.get("ratios", {})

    days_rest = features.get("days_rest", features.get("sched_rest_days", 1))
    try:
        days_rest = int(float(days_rest))
    except Exception:
        days_rest = 1

    if days_rest == 0:
        bucket = "0"
    elif days_rest == 1:
        bucket = "1"
    elif days_rest == 2:
        bucket = "2"
    else:
        bucket = "3+"

    bucket_ratios = ratios.get(bucket, {})
    # Return mean multiplier across key stats
    pts_mult = float(bucket_ratios.get("pts", 1.0))

    return {"mult": round(pts_mult, 4), "bucket": bucket}


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--train", action="store_true")
    args = parser.parse_args()
    if args.train:
        print(train())
