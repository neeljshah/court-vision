"""
load_management.py -- Phase E3: Load management DNP predictor.

Predicts load-managed DNPs based on schedule stress + fatigue + age.
Extends the base DNP predictor with schedule-aware features.

Public API
----------
    predict_load_management(player_name, season)  -> dict
    train_load_model(season)                      -> dict
"""
from __future__ import annotations

import json
import os
import sys
from typing import Optional

import numpy as np

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_DIR)

_MODEL_PATH = os.path.join(PROJECT_DIR, "data", "models", "load_management.json")


# ── Feature builder ───────────────────────────────────────────────────────────

def _build_load_features(player_name: str, season: str) -> dict:
    """Build load management features for a player."""
    feats: dict = {
        "age":              0.0,
        "games_played":     0.0,
        "minutes_per_game": 0.0,
        "is_b2b":           0.0,
        "days_rest":        2.0,
        "games_last_7":     0.0,
        "usage_rate":       0.0,
        "injury_history":   0.0,   # games missed prior season
        "contract_year":    0.0,
        "is_star":          0.0,   # usage > 28%
    }

    # Roster + schedule data
    try:
        from src.data.player_scraper import get_player_profile
        profile = get_player_profile(player_name)
        if profile:
            feats["age"]              = float(profile.get("age", 0) or 0)
            feats["minutes_per_game"] = float(profile.get("min", 0) or 0)
            feats["games_played"]     = float(profile.get("gp", 0) or 0)
            usg = float(profile.get("usg_pct", 0) or 0)
            feats["usage_rate"]  = usg
            feats["is_star"]     = 1.0 if usg > 28 else 0.0
    except Exception:
        pass

    # Schedule context — b2b and rest days
    try:
        from src.data.schedule_context import get_player_schedule_context
        sched = get_player_schedule_context(player_name, season)
        if sched:
            feats["is_b2b"]        = float(sched.get("is_b2b", 0))
            feats["days_rest"]     = float(sched.get("days_rest", 2))
            feats["games_last_7"]  = float(sched.get("games_last_7", 0))
    except Exception:
        pass

    # Contract data
    try:
        contracts_path = os.path.join(PROJECT_DIR, "data", "external", f"contracts_{season}.json")
        contracts = json.load(open(contracts_path))
        for c in contracts:
            if player_name.lower() in (c.get("player_name") or "").lower():
                feats["contract_year"] = float(c.get("is_contract_year", 0) or 0)
                break
    except Exception:
        pass

    return feats


def _load_model() -> Optional[dict]:
    if os.path.exists(_MODEL_PATH):
        try:
            return json.load(open(_MODEL_PATH))
        except Exception:
            pass
    return None


# ── Core predictor ────────────────────────────────────────────────────────────

def predict_load_management(
    player_name: str,
    season: str = "2024-25",
) -> dict:
    """
    Predict load management probability for a player tonight.

    Returns:
        {
            "player":        str,
            "load_mgmt_prob": float,    # 0-1 probability of load management DNP
            "risk_factors":  dict,      # which features are elevated
            "recommendation": str,      # "Rest", "Monitor", "Play"
        }
    """
    feats = _build_load_features(player_name, season)
    model = _load_model()

    if model:
        # Logistic regression scoring
        coefs = model.get("coefs", {})
        intercept = model.get("intercept", -3.0)
        score = intercept + sum(coefs.get(k, 0.0) * v for k, v in feats.items())
        prob = 1.0 / (1.0 + np.exp(-score))
    else:
        # Heuristic fallback
        prob = 0.0
        if feats["is_b2b"]:
            prob += 0.25
        if feats["days_rest"] < 1.5:
            prob += 0.15
        if feats["games_last_7"] >= 4:
            prob += 0.10
        if feats["age"] >= 32:
            prob += 0.10
        if feats["is_star"]:
            prob += 0.08
        prob = min(prob, 0.95)

    risk_factors = {
        k: v for k, v in feats.items()
        if (k == "is_b2b" and v > 0)
        or (k == "days_rest" and v < 2)
        or (k == "age" and v >= 32)
        or (k == "games_last_7" and v >= 4)
    }

    if prob >= 0.40:
        recommendation = "Rest"
    elif prob >= 0.20:
        recommendation = "Monitor"
    else:
        recommendation = "Play"

    return {
        "player":         player_name,
        "load_mgmt_prob": round(float(prob), 4),
        "risk_factors":   risk_factors,
        "recommendation": recommendation,
        "features":       feats,
    }


def train_load_model(season: str = "2024-25") -> dict:
    """
    Train load management model using historical game logs.
    Uses DNP records where reason includes 'rest' or 'load management'.

    Returns training metrics dict.
    """
    try:
        from sklearn.linear_model import LogisticRegression
        from sklearn.model_selection import cross_val_score
        import pandas as pd

        # Build training data from gamelogs — DNP=1 where noted as rest
        from src.data.nba_stats import get_all_player_gamelogs
        logs = get_all_player_gamelogs(season)

        rows = []
        for log in logs:
            reason = str(log.get("comment", "") or "").lower()
            is_rest = 1 if any(w in reason for w in ["rest", "load", "management", "dnp - rest"]) else 0
            rows.append({
                "is_b2b":           float(log.get("is_b2b", 0) or 0),
                "days_rest":        float(log.get("days_rest", 2) or 2),
                "games_last_7":     float(log.get("games_last_7", 0) or 0),
                "age":              float(log.get("age", 28) or 28),
                "usage_rate":       float(log.get("usg_pct", 0) or 0),
                "is_star":          1.0 if float(log.get("usg_pct", 0) or 0) > 28 else 0.0,
                "contract_year":    float(log.get("is_contract_year", 0) or 0),
                "injury_history":   float(log.get("games_missed_prev", 0) or 0),
                "minutes_per_game": float(log.get("min", 0) or 0),
                "games_played":     float(log.get("gp", 0) or 0),
                "target":           is_rest,
            })

        if len(rows) < 20:
            return {"error": "insufficient_data", "n": len(rows)}

        df = pd.DataFrame(rows)
        feat_cols = [c for c in df.columns if c != "target"]
        X = df[feat_cols].fillna(0).values
        y = df["target"].values

        clf = LogisticRegression(class_weight="balanced", max_iter=500)
        cv_scores = cross_val_score(clf, X, y, cv=5, scoring="roc_auc")
        clf.fit(X, y)

        coefs = dict(zip(feat_cols, clf.coef_[0].tolist()))
        model_data = {
            "coefs":     coefs,
            "intercept": float(clf.intercept_[0]),
            "auc":       round(float(cv_scores.mean()), 4),
            "n":         len(rows),
        }
        os.makedirs(os.path.dirname(_MODEL_PATH), exist_ok=True)
        with open(_MODEL_PATH, "w") as f:
            json.dump(model_data, f, indent=2)
        return model_data

    except Exception as e:
        return {"error": str(e)}


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--player", help="Predict for a specific player")
    parser.add_argument("--train",  action="store_true", help="Train the model")
    parser.add_argument("--season", default="2024-25")
    args = parser.parse_args()

    if args.train:
        result = train_load_model(args.season)
        print(f"[load_management] Train result: {result}")
    elif args.player:
        result = predict_load_management(args.player, args.season)
        print(f"[load_management] {args.player}: {result}")
    else:
        parser.print_help()
