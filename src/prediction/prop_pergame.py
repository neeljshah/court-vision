"""
prop_pergame.py — Per-game prop models trained on real game logs (PRED-13).

The legacy prop pipeline (player_props.train_props) trains on SEASON
averages: it predicts a player's season-average stat from features that are
essentially that same season average, plus simulated noise. Its reported
R²≈0.99 is therefore meaningless — a near-identity fit. The honest holdout
(predictions vs realised box scores) is only ~0.45.

This module trains the real task, the way a sharp quant would: each row is
one game, every feature is computed strictly from the player's PRIOR games
(rolling form, EWMA recency, rest, home/away), and the target is THAT game's
actual stat line. No leakage — features never see the game they predict.

Public API
----------
    build_pergame_dataset(gamelog_dir, min_prior) -> (rows, feature_cols)
    train_pergame_models(...)                     -> dict   (honest holdout R²/MAE)
    load_pergame_model(stat)                      -> model or None
    predict_pergame(stat, feature_row)            -> float
"""
from __future__ import annotations

import glob
import json
import os
import sys
from datetime import datetime
from typing import Dict, List, Optional, Tuple

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_DIR)

_NBA_CACHE = os.path.join(PROJECT_DIR, "data", "nba")
_MODEL_DIR = os.path.join(PROJECT_DIR, "data", "models")

# Stats predicted, and their box-score column names in the gamelog JSON.
STATS = ["pts", "reb", "ast", "fg3m", "stl", "blk", "tov"]
_BOX_COL = {"pts": "PTS", "reb": "REB", "ast": "AST", "fg3m": "FG3M",
            "stl": "STL", "blk": "BLK", "tov": "TOV", "min": "MIN"}
_FORM_STATS = STATS + ["min"]          # min drives every counting stat

_MIN_PLAYED = 5.0                      # a game counts only if the player played
_EWMA_ALPHA = 0.30                     # recency weight — recent games dominate


# ── feature helpers ───────────────────────────────────────────────────────────

def _parse_date(raw: str) -> Optional[datetime]:
    """Parse an NBA gamelog date ('Apr 13, 2025'). Returns None on failure."""
    try:
        return datetime.strptime(str(raw).strip(), "%b %d, %Y")
    except Exception:
        return None


def _num(v) -> float:
    try:
        return float(v) if v is not None else 0.0
    except (TypeError, ValueError):
        return 0.0


def _mean(vals: List[float]) -> float:
    return sum(vals) / len(vals) if vals else 0.0


def _ewma(vals: List[float], alpha: float = _EWMA_ALPHA) -> float:
    """Exponentially-weighted mean — most recent game weighted highest."""
    if not vals:
        return 0.0
    weighted = total_w = 0.0
    for i, v in enumerate(reversed(vals)):       # i=0 is the most recent game
        w = alpha * (1.0 - alpha) ** i
        weighted += w * v
        total_w += w
    return weighted / total_w if total_w > 0 else 0.0


def feature_columns() -> List[str]:
    """Ordered feature names — 5 form features per stat + 3 game-context."""
    cols: List[str] = []
    for stat in _FORM_STATS:
        cols += [f"l5_{stat}", f"l10_{stat}", f"std_{stat}",
                 f"ewma_{stat}", f"prev_{stat}"]
    cols += ["rest_days", "is_home", "games_played"]
    return cols


def _row_features(prior_played: List[dict], rest_days: float,
                  is_home: int, games_played: int) -> Dict[str, float]:
    """Build the leakage-free feature row from a player's prior played games."""
    feats: Dict[str, float] = {}
    for stat in _FORM_STATS:
        col = _BOX_COL[stat]
        vals = [_num(g.get(col)) for g in prior_played]
        feats[f"l5_{stat}"]   = _mean(vals[-5:])
        feats[f"l10_{stat}"]  = _mean(vals[-10:])
        feats[f"std_{stat}"]  = _mean(vals)              # season-to-date
        feats[f"ewma_{stat}"] = _ewma(vals)
        feats[f"prev_{stat}"] = vals[-1] if vals else 0.0
    feats["rest_days"]     = rest_days
    feats["is_home"]       = float(is_home)
    feats["games_played"]  = float(games_played)
    return feats


# ── dataset construction ──────────────────────────────────────────────────────

def build_pergame_dataset(
    gamelog_dir: Optional[str] = None,
    min_prior: int = 6,
) -> Tuple[List[dict], List[str]]:
    """Build the per-game training set from every player gamelog.

    Each emitted row holds leakage-free pre-game features and the realised
    target_{stat} values for one game.  A game is used as a row only when the
    player actually played (>= _MIN_PLAYED minutes) and has at least
    ``min_prior`` prior played games for stable rolling features.

    Returns:
        (rows, feature_cols) — rows are dicts with the feature columns,
        target_{stat} columns, and a 'date' key for the temporal split.
    """
    gamelog_dir = gamelog_dir or _NBA_CACHE
    feature_cols = feature_columns()
    rows: List[dict] = []

    for path in glob.glob(os.path.join(gamelog_dir, "gamelog_*.json")):
        try:
            games = json.load(open(path, encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(games, list) or len(games) <= min_prior:
            continue

        # Sort chronologically; keep games with a parseable date.
        dated = [(d, g) for g in games if (d := _parse_date(g.get("GAME_DATE"))) is not None]
        dated.sort(key=lambda x: x[0])

        prior_played: List[dict] = []
        for idx, (gdate, game) in enumerate(dated):
            played = _num(game.get("MIN")) >= _MIN_PLAYED

            if played and len(prior_played) >= min_prior:
                rest = 3.0
                if idx > 0:
                    delta = (gdate - dated[idx - 1][0]).days
                    rest = float(min(max(delta, 0), 10))
                is_home = 1 if " vs. " in str(game.get("MATCHUP", "")) else 0
                feats = _row_features(prior_played, rest, is_home, len(prior_played))
                row = {c: feats[c] for c in feature_cols}
                for stat in STATS:
                    row[f"target_{stat}"] = _num(game.get(_BOX_COL[stat]))
                row["date"] = gdate.isoformat()
                rows.append(row)

            if played:
                prior_played.append(game)

    return rows, feature_cols


# ── training ──────────────────────────────────────────────────────────────────

def train_pergame_models(
    gamelog_dir: Optional[str] = None,
    model_dir: Optional[str] = None,
    *,
    min_prior: int = 6,
    holdout_frac: float = 0.2,
) -> dict:
    """Train one XGBoost regressor per stat on the per-game dataset.

    The split is temporal — the most recent ``holdout_frac`` of games are held
    out — so the reported R²/MAE are honest out-of-sample numbers.

    Returns a metrics dict ``{stat: {train_r2, holdout_r2, train_mae,
    holdout_mae, gap}}`` and writes props_pg_{stat}.json + a metrics JSON.
    """
    import numpy as np
    import xgboost as xgb
    from sklearn.metrics import mean_absolute_error, r2_score

    model_dir = model_dir or _MODEL_DIR
    rows, feature_cols = build_pergame_dataset(gamelog_dir, min_prior=min_prior)
    if len(rows) < 200:
        return {"status": "insufficient_data", "n_rows": len(rows)}

    rows.sort(key=lambda r: r["date"])           # temporal order
    split = int(len(rows) * (1.0 - holdout_frac))
    X_all = np.array([[r[c] for c in feature_cols] for r in rows], dtype=float)

    os.makedirs(model_dir, exist_ok=True)
    metrics: dict = {"n_rows": len(rows), "n_train": split,
                     "n_holdout": len(rows) - split, "stats": {}}

    for stat in STATS:
        y = np.array([r[f"target_{stat}"] for r in rows], dtype=float)
        # Count stats (stl/blk) — Poisson; shallower trees curb overfit.
        is_count = stat in ("stl", "blk")
        model = xgb.XGBRegressor(
            n_estimators=300,
            max_depth=3 if is_count else 5,
            learning_rate=0.05,
            subsample=0.8,
            colsample_bytree=0.8,
            min_child_weight=5,
            reg_lambda=1.5,
            random_state=42,
            objective="count:poisson" if is_count else "reg:squarederror",
        )
        model.fit(X_all[:split], y[:split])
        train_pred = model.predict(X_all[:split])
        hold_pred  = model.predict(X_all[split:])

        m = {
            "train_r2":    round(float(r2_score(y[:split], train_pred)), 4),
            "holdout_r2":  round(float(r2_score(y[split:], hold_pred)), 4),
            "train_mae":   round(float(mean_absolute_error(y[:split], train_pred)), 4),
            "holdout_mae": round(float(mean_absolute_error(y[split:], hold_pred)), 4),
        }
        m["gap"] = round(m["train_r2"] - m["holdout_r2"], 4)
        metrics["stats"][stat] = m
        model.save_model(os.path.join(model_dir, f"props_pg_{stat}.json"))
        print(f"  [prop_pergame] {stat.upper():4s} holdout R²={m['holdout_r2']:.3f} "
              f"MAE={m['holdout_mae']:.2f}  (train R²={m['train_r2']:.3f}, gap={m['gap']:.3f})")

    metrics["feature_cols"] = feature_cols
    with open(os.path.join(model_dir, "props_pergame_metrics.json"), "w", encoding="utf-8") as f:
        json.dump(metrics, f, indent=2)
    return metrics


# ── inference ─────────────────────────────────────────────────────────────────

def load_pergame_model(stat: str, model_dir: Optional[str] = None):
    """Load the per-game XGBoost model for a stat, or None if untrained."""
    path = os.path.join(model_dir or _MODEL_DIR, f"props_pg_{stat}.json")
    if not os.path.exists(path):
        return None
    try:
        import xgboost as xgb
        model = xgb.XGBRegressor()
        model.load_model(path)
        return model
    except Exception:
        return None


def predict_pergame(stat: str, feature_row: Dict[str, float],
                    model_dir: Optional[str] = None) -> Optional[float]:
    """Predict one stat for one game from a pre-game feature row."""
    import numpy as np

    model = load_pergame_model(stat, model_dir)
    if model is None:
        return None
    cols = feature_columns()
    X = np.array([[float(feature_row.get(c, 0.0) or 0.0) for c in cols]], dtype=float)
    return round(max(float(model.predict(X)[0]), 0.0), 2)


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="Per-game prop models")
    ap.add_argument("--train", action="store_true", help="Build dataset + train all stats")
    args = ap.parse_args()
    if args.train:
        print(json.dumps(train_pergame_models(), indent=2))
    else:
        ap.print_help()
