"""
injury_severity.py — M91: Injury report severity classifier.

HIGH PRIORITY — 10-15 min edge window when news breaks before lines move.

Method: Rule-based NLP first (keyword/pattern classifier):
    "questionable" → 0.35 prob DNP
    "doubtful"     → 0.75 prob DNP
    "out"          → 0.99 prob DNP
    "day-to-day"   → 0.15 prob DNP

Injury type keywords: "ankle" → games_missed_est=2-5, "knee" → 10-30+, etc.
Feeds directly into M01 DNP predictor as a feature.

Public API
----------
    classify_injury(text)               -> dict {severity, dnp_prob, games_missed_est}
    train(seasons)                      -> dict (trains on historical injury records)
    batch_classify(texts)               -> list[dict]
"""

from __future__ import annotations

import json
import logging
import os
import pickle
import re
import sys
from typing import Optional

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_DIR)

_MODEL_DIR  = os.path.join(PROJECT_DIR, "data", "models")
_MODEL_PATH = os.path.join(_MODEL_DIR, "injury_severity.pkl")

log = logging.getLogger(__name__)


# ── Status keywords → DNP probability ────────────────────────────────────────

_STATUS_DNP_PROB = {
    "out":           0.99,
    "will not play": 0.99,
    "ruled out":     0.99,
    "inactive":      0.99,
    "doubtful":      0.75,
    "questionable":  0.35,
    "day-to-day":    0.15,
    "day to day":    0.15,
    "probable":      0.05,
    "game-time":     0.25,
    "game time":     0.25,
    "limited":       0.10,
    "available":     0.02,
}


# ── Injury type → games missed estimate ───────────────────────────────────────

_INJURY_GAMES_MISSED = {
    # High severity
    "acl":          (30, 50),
    "torn acl":     (30, 50),
    "torn mcl":     (20, 40),
    "fracture":     (15, 40),
    "broken":       (15, 40),
    "surgery":      (20, 50),
    "torn":         (15, 40),

    # Medium severity
    "knee":         (3, 15),
    "hamstring":    (3, 15),
    "calf":         (3, 10),
    "hip":          (3, 15),
    "shoulder":     (5, 20),
    "elbow":        (3, 15),
    "wrist":        (5, 20),
    "hand":         (3, 10),
    "back":         (3, 20),
    "neck":         (2, 15),
    "groin":        (3, 10),
    "quad":         (3, 10),

    # Low severity
    "ankle":        (2, 8),
    "foot":         (2, 8),
    "shin":         (2, 5),
    "illness":      (1, 3),
    "flu":          (1, 2),
    "covid":        (5, 10),
    "concussion":   (3, 10),
    "head":         (1, 5),
    "thumb":        (2, 8),
    "finger":       (1, 5),
    "knee soreness":(1, 5),
    "rest":         (1, 2),
    "load":         (1, 1),
    "maintenance":  (1, 2),
}


# ── Severity score mapping ─────────────────────────────────────────────────────

def _compute_severity(dnp_prob: float, games_missed_low: int) -> float:
    """Compute composite severity score 0-1."""
    # Higher dnp_prob + more games missed = higher severity
    prob_component  = dnp_prob * 0.6
    games_component = min(games_missed_low / 30.0, 1.0) * 0.4
    return round(min(1.0, prob_component + games_component), 3)


def classify_injury(text: str) -> dict:
    """
    Classify injury severity from text (injury report or news article).

    Args:
        text: Raw text from injury report or news source.

    Returns:
        severity_score:    float 0-1 (0=minor, 1=season-ending)
        dnp_prob:          probability player misses next game
        games_missed_est:  (low, high) tuple of expected games missed
        injury_type:       detected injury type string
        status:            detected status string
        return_timeline:   human-readable return estimate
    """
    if not text:
        return _default_result()

    text_lower = text.lower()

    # ── Detect status ─────────────────────────────────────────────────────────
    dnp_prob = 0.05  # default: assume available
    detected_status = "Available"
    for keyword, prob in sorted(_STATUS_DNP_PROB.items(), key=lambda x: -x[1]):
        if keyword in text_lower:
            dnp_prob = prob
            detected_status = keyword.title()
            break

    # ── Detect injury type ────────────────────────────────────────────────────
    games_low, games_high = 0, 2
    injury_type = "general"
    for injury, (g_low, g_high) in sorted(_INJURY_GAMES_MISSED.items(),
                                           key=lambda x: -x[1][0]):
        if injury in text_lower:
            games_low  = g_low
            games_high = g_high
            injury_type = injury
            break

    # ACL/torn keywords escalate probability
    high_severity_keywords = {"torn", "rupture", "fracture", "surgery", "acl", "season"}
    if any(kw in text_lower for kw in high_severity_keywords):
        dnp_prob = max(dnp_prob, 0.95)
        games_low = max(games_low, 20)

    # ── Return timeline string ────────────────────────────────────────────────
    if games_low == 0:
        timeline = "Probable for next game"
    elif games_low <= 2:
        timeline = f"Expected return: 1-2 games"
    elif games_low <= 10:
        timeline = f"Expected return: {games_low}-{games_high} games"
    elif games_low <= 30:
        timeline = f"Expected return: {games_low//7}-{games_high//7} weeks"
    else:
        timeline = f"Long-term: {games_low}+ games (potentially season-ending)"

    severity = _compute_severity(dnp_prob, games_low)

    return {
        "severity_score":   severity,
        "dnp_prob":         round(dnp_prob, 3),
        "games_missed_est": (games_low, games_high),
        "injury_type":      injury_type,
        "status":           detected_status,
        "return_timeline":  timeline,
    }


def _default_result() -> dict:
    return {
        "severity_score":   0.0,
        "dnp_prob":         0.05,
        "games_missed_est": (0, 1),
        "injury_type":      "unknown",
        "status":           "Available",
        "return_timeline":  "Day-to-day",
    }


def batch_classify(texts: list[str]) -> list[dict]:
    """Classify a list of injury report texts."""
    return [classify_injury(t) for t in texts]


def train(seasons: Optional[list[str]] = None) -> dict:
    """
    Save the rule-based model to pkl.
    Future: train logistic regression on historical injury records.
    """
    model_data = {
        "type":                "rule_based_nlp",
        "status_dnp_prob":     _STATUS_DNP_PROB,
        "injury_games_missed": _INJURY_GAMES_MISSED,
        "version": "1.0",
    }

    os.makedirs(_MODEL_DIR, exist_ok=True)
    with open(_MODEL_PATH, "wb") as f:
        pickle.dump(model_data, f)

    log.info("Injury severity NLP model saved (rule-based)")
    return {"type": "rule_based_nlp", "status_patterns": len(_STATUS_DNP_PROB),
            "injury_patterns": len(_INJURY_GAMES_MISSED)}


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--train", action="store_true")
    parser.add_argument("--test", type=str, help="Test with injury text")
    args = parser.parse_args()
    if args.train:
        print(train())
    if args.test:
        result = classify_injury(args.test)
        print(json.dumps(result, indent=2))
