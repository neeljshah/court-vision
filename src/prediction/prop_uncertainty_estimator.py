"""
prop_uncertainty_estimator.py — Quantile regression confidence intervals for player props.

Trains XGBoost quantile regression models (q25, q75) for each of the 7 prop stats,
producing a p25/p75 confidence interval around the point estimate.

Public API
----------
    train_uncertainty(seasons, force) -> dict
    predict_uncertainty(features)     -> dict  (pts_p25, pts_p75, reb_p25, ...)
"""
from __future__ import annotations

import json
import os
import sys
from typing import Optional

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_DIR)

_MODEL_DIR = os.path.join(PROJECT_DIR, "data", "models")
_NBA_CACHE = os.path.join(PROJECT_DIR, "data", "nba")

_PROP_STATS = ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov")
_QUANTILES = (0.25, 0.75)

# Stat-specific default intervals (p25, p75) when model not available
_DEFAULT_INTERVALS = {
    "pts":  (8.0,  22.0),
    "reb":  (2.0,  7.0),
    "ast":  (1.5,  5.5),
    "fg3m": (0.0,  2.5),
    "stl":  (0.0,  1.5),
    "blk":  (0.0,  1.0),
    "tov":  (0.5,  3.0),
}


def _model_path(stat: str, quantile: float) -> str:
    q_tag = "q25" if quantile < 0.5 else "q75"
    return os.path.join(_MODEL_DIR, f"props_{stat}_{q_tag}.json")


def train_uncertainty(
    seasons: list = None,
    force: bool = False,
) -> dict:
    """
    Train XGBoost quantile regression models for p25 and p75 on each prop stat.

    Saves:  data/models/props_{stat}_q25.json + props_{stat}_q75.json
    Returns: {stat: {q25_mae, q75_mae}} metrics dict.
    """
    import numpy as np
    import xgboost as xgb
    from sklearn.metrics import mean_absolute_error

    if seasons is None:
        seasons = ["2022-23", "2023-24", "2024-25"]

    os.makedirs(_MODEL_DIR, exist_ok=True)

    # Check if all models exist already
    if not force and all(
        os.path.exists(_model_path(s, q))
        for s in _PROP_STATS
        for q in _QUANTILES
    ):
        print("[uncertainty] Models already trained. Use force=True to retrain.")
        return {}

    # Import player_props helpers to reuse the same data pipeline
    from src.prediction.player_props import (
        _get_all_player_avgs,
        _ALL_FEATS,
        _BAYES_K,
    )
    import pandas as pd

    all_rows = []
    for season in seasons:
        print(f"  [uncertainty] Loading {season}...")
        rows = _get_all_player_avgs(season)
        for r in rows:
            r["season"] = season
        all_rows.extend(rows)

    if len(all_rows) < 100:
        print(f"  [uncertainty] Not enough data ({len(all_rows)} rows). Skipping.")
        return {}

    df = pd.DataFrame(all_rows)

    # Simulate rolling noise (same approach as player_props train_props)
    rng = np.random.default_rng(7)
    for col, scale in [
        ("pts", 0.15), ("reb", 0.12), ("ast", 0.20), ("min", 0.12),
        ("fg3m", 0.25), ("stl", 0.30), ("blk", 0.30), ("tov", 0.20),
    ]:
        noise = rng.normal(0.0, scale, size=len(df))
        df[f"{col}_roll"] = (df[f"season_{col}"] * (1.0 + noise)).clip(lower=0.0)
        _n = 10.0
        df[f"{col}_bayes"] = (
            (_n / (_n + _BAYES_K)) * df[f"{col}_roll"]
            + (_BAYES_K / (_n + _BAYES_K)) * df[f"season_{col}"]
        ).round(2)

    rng_ha = np.random.default_rng(8)
    for stat in ("pts", "reb", "ast"):
        for loc in ("home", "away"):
            noise = rng_ha.normal(0.0, 0.08, size=len(df))
            df[f"{loc}_{stat}_avg"] = (df[f"season_{stat}"] * (1.0 + noise)).clip(lower=0.0)

    rng_opp = np.random.default_rng(9)
    for stat in ("pts", "reb", "ast"):
        noise = rng_opp.normal(0.0, 0.12, size=len(df))
        df[f"{stat}_vs_opp"] = (df[f"season_{stat}"] * (1.0 + noise)).clip(lower=0.0)

    df["opp_def_rtg"] = 113.0

    df = df.dropna(subset=["season_pts"])
    train_seasons = seasons[:-1]
    test_season = seasons[-1]
    train_df = df[df["season"].isin(train_seasons)]
    test_df = df[df["season"] == test_season]

    results = {}
    for stat in _PROP_STATS:
        feat_cols = [c for c in _ALL_FEATS if c != f"season_{stat}"]
        for col in feat_cols:
            if col not in df.columns:
                train_df = train_df.copy()
                train_df[col] = 0.0
                test_df = test_df.copy()
                test_df[col] = 0.0

        if f"season_{stat}" not in train_df.columns:
            continue

        X_train = train_df[feat_cols].fillna(0.0).values
        X_test  = test_df[feat_cols].fillna(0.0).values
        y_train = train_df[f"season_{stat}"].values
        y_test  = test_df[f"season_{stat}"].values if len(test_df) > 0 else y_train[:10]

        stat_results = {}
        for alpha in _QUANTILES:
            q_tag = "q25" if alpha < 0.5 else "q75"
            m = xgb.XGBRegressor(
                objective="reg:quantileerror",
                quantile_alpha=alpha,
                n_estimators=200,
                max_depth=4,
                learning_rate=0.05,
                subsample=0.8,
                colsample_bytree=0.8,
                random_state=42,
                verbosity=0,
            )
            m.fit(X_train, y_train)
            m.save_model(_model_path(stat, alpha))
            if len(X_test) > 0:
                preds = m.predict(X_test)
                stat_results[f"{q_tag}_mae"] = round(float(mean_absolute_error(y_test, preds)), 3)

        results[stat] = stat_results
        print(f"  [uncertainty] {stat.upper()} — {stat_results}")

    return results


def predict_uncertainty(features: dict) -> dict:
    """
    Predict p25/p75 confidence interval for each prop stat from a pre-built feature dict.

    Args:
        features: Output of player_props._build_player_features() (or any dict with _ALL_FEATS keys).

    Returns:
        {pts_p25, pts_p75, reb_p25, reb_p75, ast_p25, ast_p75,
         fg3m_p25, fg3m_p75, stl_p25, stl_p75, blk_p25, blk_p75, tov_p25, tov_p75}
    """
    import numpy as np

    try:
        import xgboost as xgb
        from src.prediction.player_props import _ALL_FEATS
    except ImportError:
        return _default_uncertainty(features)

    result = {}
    for stat in _PROP_STATS:
        feat_cols = [c for c in _ALL_FEATS if c != f"season_{stat}"]
        X = np.array([[features.get(k, 0.0) for k in feat_cols]])

        p25_path = _model_path(stat, 0.25)
        p75_path = _model_path(stat, 0.75)

        p25_val, p75_val = _DEFAULT_INTERVALS[stat]

        if os.path.exists(p25_path):
            try:
                m = xgb.XGBRegressor()
                m.load_model(p25_path)
                p25_val = float(max(m.predict(X)[0], 0.0))
            except Exception:
                pass

        if os.path.exists(p75_path):
            try:
                m = xgb.XGBRegressor()
                m.load_model(p75_path)
                p75_val = float(max(m.predict(X)[0], 0.0))
            except Exception:
                pass

        # Enforce ordering: p25 <= p75
        if p25_val > p75_val:
            p25_val, p75_val = p75_val, p25_val

        result[f"{stat}_p25"] = round(p25_val, 2)
        result[f"{stat}_p75"] = round(p75_val, 2)

    return result


def _default_uncertainty(features: dict) -> dict:
    """Return stat-scaled defaults when models are unavailable."""
    result = {}
    for stat, (lo_pct, hi_pct) in [
        ("pts", (0.55, 1.45)), ("reb", (0.50, 1.50)), ("ast", (0.55, 1.45)),
        ("fg3m", (0.0, 2.2)), ("stl", (0.0, 1.8)), ("blk", (0.0, 1.6)),
        ("tov", (0.45, 1.55)),
    ]:
        base = features.get(f"season_{stat}", features.get(f"{stat}_bayes",
               _DEFAULT_INTERVALS[stat][0]))
        result[f"{stat}_p25"] = round(max(float(base) * lo_pct, 0.0), 2)
        result[f"{stat}_p75"] = round(max(float(base) * hi_pct, 0.0), 2)
    return result


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--train", action="store_true")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    if args.train:
        r = train_uncertainty(force=args.force)
        print(json.dumps(r, indent=2))
