"""
beat_reporter_credibility.py — Track historical accuracy of beat reporter injury alerts.

Computes per-reporter precision:
  True positive:  reported "out/questionable" → player actually DNP or <20 min
  False positive: reported alert → player played normal minutes (>20 min)

Uses outcome_recorder output + beat_reporter alert cache.

Public API
----------
    train()                              -> dict
    get_reporter_credibility(handle)     -> float (0–1 precision score)
    get_max_credibility_for_player(player_name) -> float
"""
from __future__ import annotations

import json
import os
import sys
from collections import defaultdict
from typing import Optional

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_DIR)

_MODEL_DIR    = os.path.join(PROJECT_DIR, "data", "models")
_NBA_CACHE    = os.path.join(PROJECT_DIR, "data", "nba")
_CRED_PATH    = os.path.join(_MODEL_DIR, "reporter_credibility.json")

# DNP or low-minutes threshold (< this = true positive)
_DNP_MIN_THRESHOLD = 20.0

# Laplace smoothing pseudo-count (avoids zero precision for new reporters)
_LAPLACE_K    = 2
_LAPLACE_PRIOR = 0.65   # prior precision: reporters are usually ~65% accurate

# Known high-credibility reporters (hardcoded bootstrap while we accumulate data)
_KNOWN_CREDIBLE = {
    "wojespn":         0.92,
    "shamscharania":   0.91,
    "adrianwojnarowski": 0.92,
    "shams":           0.91,
    "ianbegg":         0.78,
    "davidaldridgenba": 0.82,
    "markstein":       0.75,
    "cbssports":       0.70,
    "bleacherreport":  0.65,
}


def train() -> dict:
    """
    Compute reporter precision from historical alert log vs actual game results.

    Reads:
      data/nba/beat_reporter_alerts_history.json  — past alerts with outcomes
      data/models/outcome_records.json            — actual game outcomes

    Saves: data/models/reporter_credibility.json
    Returns: {n_reporters, mean_precision}
    """
    os.makedirs(_MODEL_DIR, exist_ok=True)

    # accumulator: handle → {tp, fp, total}
    stats: dict = defaultdict(lambda: {"tp": 0, "fp": 0, "total": 0})

    # Load historical alert log
    alert_history_path = os.path.join(_NBA_CACHE, "beat_reporter_alerts_history.json")
    outcome_path = os.path.join(_MODEL_DIR, "outcome_records.json")

    if os.path.exists(alert_history_path):
        try:
            alerts = json.load(open(alert_history_path))
            # Expected structure: [{handle, player_name, alert_time, actual_min_played}]
            outcomes = {}
            if os.path.exists(outcome_path):
                outcomes = json.load(open(outcome_path))

            for alert in alerts:
                handle = str(alert.get("handle", "")).lower().strip("@")
                player = alert.get("player_name", "")
                min_played = alert.get("actual_min_played")

                # Resolve min_played from outcomes if not directly in alert
                if min_played is None and player and outcomes:
                    outcome_row = outcomes.get(player, {})
                    min_played  = outcome_row.get("min_played")

                if min_played is not None and handle:
                    stats[handle]["total"] += 1
                    if float(min_played) < _DNP_MIN_THRESHOLD:
                        stats[handle]["tp"] += 1
                    else:
                        stats[handle]["fp"] += 1
        except Exception:
            pass

    # Compute precision with Laplace smoothing
    cred_table = {}

    # Seed with known credible reporters
    for handle, prior in _KNOWN_CREDIBLE.items():
        cred_table[handle] = prior

    # Update from data
    for handle, s in stats.items():
        tp    = s["tp"]
        total = s["total"]
        # Laplace smoothed precision
        precision = (tp + _LAPLACE_K * _LAPLACE_PRIOR) / (total + _LAPLACE_K)
        cred_table[handle] = round(precision, 4)

    with open(_CRED_PATH, "w") as f:
        json.dump(cred_table, f, indent=2)

    n = len(cred_table)
    mean_prec = sum(cred_table.values()) / n if n > 0 else _LAPLACE_PRIOR
    print(f"  [reporter_cred] {n} reporters, mean_precision={mean_prec:.3f}")
    return {"n_reporters": n, "mean_precision": round(mean_prec, 4)}


def get_reporter_credibility(handle: str) -> float:
    """
    Return historical precision score (0–1) for a beat reporter.

    Higher = more reliable injury alerts (true positive rate).
    Falls back to prior (0.65) for unknown reporters.
    """
    h = str(handle).lower().strip("@").strip()

    # Load from saved table
    if os.path.exists(_CRED_PATH):
        try:
            table = json.load(open(_CRED_PATH))
            # Try exact match, then prefix match
            if h in table:
                return float(table[h])
            for key in table:
                if key in h or h in key:
                    return float(table[key])
        except Exception:
            pass

    # Bootstrap from known list
    for key, cred in _KNOWN_CREDIBLE.items():
        if key in h or h in key:
            return cred

    return _LAPLACE_PRIOR


def get_max_credibility_for_player(player_name: str, hours: float = 3.0) -> float:
    """
    Get the maximum credibility score among all current alerts for a player.

    Returns 0.0 if no active alerts.
    """
    try:
        from src.data.beat_reporter_monitor import get_player_alerts as _get_alerts
        alerts = _get_alerts(player_name)
        if not alerts:
            return 0.0
        scores = [get_reporter_credibility(a.get("handle", "")) for a in alerts]
        return round(max(scores), 4)
    except Exception:
        pass

    # Fallback: just check if alert exists
    try:
        from src.data.beat_reporter_monitor import has_injury_alert as _has_alert
        if _has_alert(player_name, hours=hours):
            return _LAPLACE_PRIOR
    except Exception:
        pass

    return 0.0


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--train", action="store_true")
    ap.add_argument("--handle", default="wojespn")
    args = ap.parse_args()
    if args.train:
        r = train()
        print(json.dumps(r, indent=2))
    else:
        cred = get_reporter_credibility(args.handle)
        print(f"Credibility for @{args.handle}: {cred:.3f}")
