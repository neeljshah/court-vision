"""
usage_rate_model.py — M27: Dynamic usage rate prediction.

HIGH PRIORITY — static usage assumption is the biggest props error source.

Method: XGBoost on synergy usage share, lineup context, star availability,
        historical gamelogs, PBP possession data.
Output: proj_usg% for tonight (not season average).

Public API
----------
    train(seasons)             -> dict (metrics)
    predict_usage(features)    -> dict {proj_usg_pct}
"""

from __future__ import annotations

import glob
import json
import logging
import os
import pickle
import sys
from typing import Optional

import numpy as np

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_DIR)

_NBA_CACHE = os.path.join(PROJECT_DIR, "data", "nba")
_EXT_CACHE = os.path.join(PROJECT_DIR, "data", "external")
_MODEL_DIR  = os.path.join(PROJECT_DIR, "data", "models")
_MODEL_PATH = os.path.join(_MODEL_DIR, "usage_rate_model.pkl")

log = logging.getLogger(__name__)


def _parse_min(val) -> float:
    if val is None:
        return float("nan")
    s = str(val).strip()
    if s in ("", "None", "null", "0", "0:00"):
        return 0.0
    if ":" in s:
        parts = s.split(":")
        try:
            return float(parts[0]) + float(parts[1]) / 60
        except Exception:
            return float("nan")
    try:
        return float(s)
    except Exception:
        return float("nan")


def _build_training_data(season: str = "2024-25") -> tuple:
    """
    Build X, y where y = actual game usg% (estimated from gamelogs).
    usg% proxy: player FGA + 0.44*FTA + TOV / team FGA + 0.44*FTA + TOV
    """
    X_rows, y_vals = [], []

    # Load aggregate gamelogs for the season
    gl_path = os.path.join(_NBA_CACHE, f"gamelogs_all_{season}.json")
    if not os.path.exists(gl_path):
        return np.zeros((0, 8)), np.zeros(0)

    all_logs = json.load(open(gl_path))
    if not isinstance(all_logs, list):
        return np.zeros((0, 8)), np.zeros(0)

    # BBRef usg% as season baseline
    bbref_usg: dict[str, float] = {}
    bbref_path = os.path.join(_EXT_CACHE, f"bbref_advanced_{season}.json")
    if os.path.exists(bbref_path):
        bb = json.load(open(bbref_path))
        for p in bb:
            name = p.get("player_name", "")
            if name:
                bbref_usg[name.lower()] = float(p.get("usg_pct", 0.2) or 0.2)

    # Group by game and compute team totals
    from collections import defaultdict
    game_team_totals: dict[str, dict] = defaultdict(lambda: {"fga": 0, "fta": 0, "tov": 0})
    for row in all_logs:
        gid = str(row.get("game_id", ""))
        if gid:
            game_team_totals[gid]["fga"] += int(row.get("fga", 0) or 0)
            game_team_totals[gid]["fta"] += int(row.get("fta", 0) or 0)
            game_team_totals[gid]["tov"] += int(row.get("tov", 0) or 0)

    per_player_logs: dict[str, list] = defaultdict(list)
    for row in all_logs:
        pname = str(row.get("player_name", row.get("PLAYER_NAME", ""))).lower()
        per_player_logs[pname].append(row)

    for pname, logs in per_player_logs.items():
        logs = sorted(logs, key=lambda g: g.get("game_date", ""))
        season_usg = bbref_usg.get(pname, 0.2)

        for i in range(5, len(logs)):
            row = logs[i]
            min_val = _parse_min(row.get("min", 0))
            if min_val <= 5:  # skip low-minutes games
                continue

            gid = str(row.get("game_id", ""))
            ttl = game_team_totals.get(gid, {})
            team_poss_proxy = ttl.get("fga", 80) + 0.44 * ttl.get("fta", 20) + ttl.get("tov", 15)
            player_poss     = int(row.get("fga", 0) or 0) + 0.44 * int(row.get("fta", 0) or 0) + int(row.get("tov", 0) or 0)
            target_usg = player_poss / max(team_poss_proxy * 0.5, 1.0)  # 0.5 = 2 teams
            target_usg = min(max(target_usg, 0.05), 0.50)

            recent5 = logs[max(0, i-5):i]
            r5_usg = []
            for rg in recent5:
                m = _parse_min(rg.get("min", 0))
                if m <= 0:
                    continue
                gid2 = str(rg.get("game_id", ""))
                t2 = game_team_totals.get(gid2, {})
                tp = t2.get("fga", 80) + 0.44 * t2.get("fta", 20) + t2.get("tov", 15)
                pp = int(rg.get("fga", 0) or 0) + 0.44 * int(rg.get("fta", 0) or 0) + int(rg.get("tov", 0) or 0)
                r5_usg.append(pp / max(tp * 0.5, 1.0))

            recent5_usg = float(np.mean(r5_usg)) if r5_usg else season_usg
            is_b2b = 0
            try:
                from datetime import datetime
                if i > 0:
                    d1 = datetime.strptime(logs[i-1].get("game_date", "")[:10], "%Y-%m-%d")
                    d2 = datetime.strptime(row.get("game_date", "")[:10], "%Y-%m-%d")
                    is_b2b = int((d2 - d1).days == 1)
            except Exception:
                pass

            X_rows.append([
                season_usg,
                recent5_usg,
                float(row.get("pts", 0) or 0) / max(min_val, 1),  # pts per min
                min_val / 40.0,     # minutes fraction
                is_b2b,
                float(row.get("plus_minus", 0) or 0),
                float(row.get("fga", 0) or 0),
                float(row.get("tov", 0) or 0),
            ])
            y_vals.append(float(target_usg))

    if not X_rows:
        return np.zeros((0, 8)), np.zeros(0)
    return np.array(X_rows, dtype=float), np.array(y_vals, dtype=float)


def train(seasons: Optional[list[str]] = None) -> dict:
    if seasons is None:
        seasons = ["2024-25"]

    log.info("Training usage rate model...")
    X, y = _build_training_data(seasons[0])

    if len(X) < 100:
        log.warning("Insufficient data (%d rows) — using heuristic", len(X))
        os.makedirs(_MODEL_DIR, exist_ok=True)
        with open(_MODEL_PATH, "wb") as f:
            pickle.dump({"type": "heuristic", "version": "1.0"}, f)
        return {"rows": len(X), "type": "heuristic"}

    try:
        from xgboost import XGBRegressor
        from sklearn.model_selection import cross_val_score

        model = XGBRegressor(
            n_estimators=200, max_depth=4, learning_rate=0.05,
            subsample=0.8, colsample_bytree=0.8, random_state=42
        )
        model.fit(X, y)
        scores = cross_val_score(model, X, y, cv=5, scoring="neg_mean_absolute_error")
        mae = -float(np.mean(scores))

        os.makedirs(_MODEL_DIR, exist_ok=True)
        with open(_MODEL_PATH, "wb") as f:
            pickle.dump({"type": "xgb", "model": model, "version": "1.0"}, f)
        log.info("Usage rate model: %d rows, MAE=%.4f", len(X), mae)
        return {"rows": len(X), "mae": mae}

    except ImportError:
        from sklearn.linear_model import Ridge
        model = Ridge(alpha=0.5)
        model.fit(X, y)
        os.makedirs(_MODEL_DIR, exist_ok=True)
        with open(_MODEL_PATH, "wb") as f:
            pickle.dump({"type": "ridge", "model": model, "version": "1.0"}, f)
        return {"rows": len(X), "type": "ridge"}


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
    log.info("usage_rate_model.pkl not found — training")
    train()
    if os.path.exists(_MODEL_PATH):
        with open(_MODEL_PATH, "rb") as f:
            _MODEL_CACHE = pickle.load(f)
    else:
        _MODEL_CACHE = {"type": "heuristic"}
    return _MODEL_CACHE


def predict_usage(features: dict) -> dict:
    """
    Predict dynamic usage rate for tonight.

    Returns:
        proj_usg_pct: float (0-0.5)
    """
    m = _load_model()

    season_usg   = float(features.get("bbref_usg_pct", 0.2) or 0.2)
    # Approximate recent game usg from scoring rate if available
    pts_l5  = float(features.get("pts_l5", 0) or 0)
    min_l5  = float(features.get("min_l5", 24) or 24)
    pts_per_min = pts_l5 / max(min_l5, 1)
    usg_proxy_recent = min(0.45, season_usg * (1 + (pts_per_min - 0.5) * 0.1))
    is_b2b  = int(features.get("is_b2b", 0) or features.get("sched_is_b2b", 0))
    dnp_prob = float(features.get("dnp_prob", 0.05))

    if m.get("type") in ("xgb", "ridge") and m.get("model") is not None:
        X = np.array([[
            season_usg,
            usg_proxy_recent,
            pts_per_min,
            float(features.get("min_l5", 24)) / 40.0,
            is_b2b,
            float(features.get("on_off_diff", 0) or 0),
            float(features.get("pts_l5", 0) or 0) / 5,  # avg FGA proxy
            float(features.get("tov_l5", 0) or 0),
        ]])
        try:
            proj_usg = float(m["model"].predict(X)[0])
        except Exception:
            proj_usg = season_usg
    else:
        proj_usg = season_usg

    # Adjust for star availability (boosted usage when star sits)
    star_min_boost = float(features.get("min_boost_from_star_dnp", 0.0))
    if star_min_boost > 3:
        proj_usg = min(proj_usg * 1.05, 0.45)

    # Clip
    proj_usg = max(0.05, min(0.50, proj_usg))

    return {"proj_usg_pct": round(proj_usg, 4)}


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--train", action="store_true")
    args = parser.parse_args()
    if args.train:
        print(train())
