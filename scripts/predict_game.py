"""predict_game.py — production prediction CLI for the M2 family game-level models.

Loads the 20-model ensemble (5 models × 4 targets) saved by
train_final_M2_family.py and predicts:
  - total_pts (game total)
  - score_diff (home - away)
  - home_pts
  - away_pts
  - implied probabilities at common O/U + ATS thresholds

USAGE:
    # Predict an upcoming game from season_games JSON
    python scripts/predict_game.py <game_id>

    # Predict latest unfinished game (auto)
    python scripts/predict_game.py --latest

    # Predict all upcoming games
    python scripts/predict_game.py --all-upcoming
"""
from __future__ import annotations
import json, os, sys, argparse, math
from typing import Dict, List
import numpy as np
import pandas as pd

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_NBA = os.path.join(PROJECT_DIR, "data", "nba")
MODELS_DIR = os.path.join(PROJECT_DIR, "data", "models", "m2_family")


def _load_feat_cols():
    with open(os.path.join(MODELS_DIR, "feature_cols.json")) as f:
        return json.load(f)


def _load_models(target):
    """Return list of fitted models for the given target."""
    import joblib
    with open(os.path.join(MODELS_DIR, "manifest.json")) as f:
        man = json.load(f)
    model_labels = man["targets"][target]["models"]  # e.g. ['lgb_s42','lgb_s7','lgb_s100','xgb_s42','xgb_s7']
    models = []
    for lab in model_labels:
        p = os.path.join(MODELS_DIR, f"{target}_{lab}.joblib")
        models.append(joblib.load(p))
    return models


def _ensemble_predict(models, X):
    """Equal-weight average of all model predictions on X."""
    preds = np.zeros(X.shape[0])
    for m in models:
        preds += m.predict(X)
    return preds / len(models)


def _load_game_row(game_id: str) -> Dict:
    """Find a game_id row in season_games_*.json. Returns raw dict (or None)."""
    for fname in ["season_games_2022-23.json", "season_games_2023-24.json",
                  "season_games_2024-25.json", "season_games_2025-26.json"]:
        p = os.path.join(DATA_NBA, fname)
        if not os.path.exists(p):
            continue
        with open(p, encoding="utf-8") as f:
            d = json.load(f)
        rows = d.get("rows", d) if isinstance(d, dict) else d
        for r in rows:
            if str(r.get("game_id", "")) == str(game_id):
                return r
    return None


def _build_X(game_row: Dict, feat_cols: List[str]) -> np.ndarray:
    """Build a 1-row feature vector from a game_row dict."""
    vals = []
    for c in feat_cols:
        v = game_row.get(c, 0.0)
        try:
            vals.append(float(v) if v is not None else 0.0)
        except (TypeError, ValueError):
            vals.append(0.0)
    return np.array([vals], dtype=np.float32)


def predict_game(game_id: str) -> Dict:
    """Predict a single game by game_id. Returns dict with totals, spread,
    team pts, and derived O/U + ATS probabilities (gaussian approximation)."""
    feat_cols = _load_feat_cols()
    row = _load_game_row(game_id)
    if row is None:
        return {"error": f"game_id {game_id} not found in season_games_*.json"}
    X = _build_X(row, feat_cols)

    total_models = _load_models("total")
    spread_models = _load_models("spread")
    home_models = _load_models("home_pts")
    away_models = _load_models("away_pts")

    total_pred = float(_ensemble_predict(total_models, X)[0])
    spread_pred = float(_ensemble_predict(spread_models, X)[0])
    home_pred = float(_ensemble_predict(home_models, X)[0])
    away_pred = float(_ensemble_predict(away_models, X)[0])

    # Implied probabilities via Gaussian approx (use historic std as scale)
    # For total: sd ~= 11; for spread: sd ~= 11; for team pts: sd ~= 11
    SD_TOTAL = 11.0
    SD_SPREAD = 11.0
    SD_TEAM = 11.0
    def _gauss_p_over(mu, sd, threshold):
        # P(X > threshold) for N(mu, sd)
        z = (mu - threshold) / sd
        return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))

    # Common O/U and ATS thresholds
    ou_thresholds = [215, 220, 225, 230, 235, 240, 245]
    ats_thresholds_home = [-1, -3, -5, -7, -10]  # home favorite spreads (negative = home wins by N+)
    p_ou = {f"P(over_{t})": round(_gauss_p_over(total_pred, SD_TOTAL, t), 4) for t in ou_thresholds}
    # Spread: home covers -N if score_diff > N
    p_ats = {}
    for s in ats_thresholds_home:
        # Home covers s means score_diff > -s (since spread of -3 means home favored by 3)
        threshold = -s  # convert
        p_ats[f"P(home_covers_{s})"] = round(_gauss_p_over(spread_pred, SD_SPREAD, threshold), 4)
    p_home_win = round(_gauss_p_over(spread_pred, SD_SPREAD, 0.0), 4)

    return {
        "game_id": game_id,
        "game_date": row.get("game_date"),
        "home_team": row.get("home_team"),
        "away_team": row.get("away_team"),
        "predictions": {
            "total_pts": round(total_pred, 2),
            "score_diff": round(spread_pred, 2),
            "home_pts": round(home_pred, 2),
            "away_pts": round(away_pred, 2),
            "p_home_win": p_home_win,
        },
        "ou_probabilities": p_ou,
        "ats_probabilities": p_ats,
        "ensemble": "M2_family_v1 = 3 LGB seeds + 2 XGB seeds (equal-weight, 5 models per target × 4 targets)",
    }


def _all_upcoming():
    """List game_ids in the most recent season that don't have a final score yet."""
    upcoming = []
    p = os.path.join(DATA_NBA, "season_games_2025-26.json")
    if os.path.exists(p):
        with open(p) as f:
            d = json.load(f)
        rows = d.get("rows", d) if isinstance(d, dict) else d
        for r in rows:
            # Heuristic: rest_days >= 0 and home_off_rtg > 0 = real game in JSON
            if r.get("home_off_rtg", 0) > 0:
                upcoming.append(str(r["game_id"]))
    return upcoming


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("game_id", nargs="?", help="game_id to predict")
    ap.add_argument("--latest", action="store_true", help="predict most recent game in 25-26 season")
    ap.add_argument("--all-upcoming", action="store_true", help="predict all 25-26 games")
    args = ap.parse_args()

    if args.all_upcoming:
        gids = _all_upcoming()
        print(f"Predicting {len(gids)} games ...", flush=True)
        for gid in gids[:5]:  # demo: first 5
            out = predict_game(gid)
            print(json.dumps(out, indent=2))
        return
    if args.latest:
        gids = _all_upcoming()
        if not gids:
            print("No upcoming games found.")
            return
        out = predict_game(gids[-1])
        print(json.dumps(out, indent=2))
        return
    if args.game_id:
        out = predict_game(args.game_id)
        print(json.dumps(out, indent=2))
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
