"""screen_extra_learners.py — does adding HGB/MLP/Catboost lift the prop_pergame blend?

Loops over base learners and tests if a 3-way NNLS stack beats XGB+LGB.
Reports per-stat lift in R² and MAE. Decides whether to ship by adding the
winner to prop_pergame.train_pergame_models.

Strategy:
  1. Build the dataset once.
  2. Train XGB + LGB (the production baseline) per stat — record metrics.
  3. Train each extra learner per stat with sample_weight + early stop where
     supported.
  4. Fit NNLS over [xgb_val, lgb_val, extra_val] -> y_val to find optimal weights.
  5. Score 3-way blend on holdout vs 2-way blend.
  6. Print a per-stat lift table and write data/models/extra_learners_screen.json.
"""
from __future__ import annotations

import json
import os
import sys
import time
import warnings
from typing import Dict, List

warnings.filterwarnings("ignore")

import numpy as np

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from src.prediction.prop_pergame import (  # noqa: E402
    STATS, build_pergame_dataset, feature_columns,
)


def _split(n: int, holdout_frac=0.2, val_frac=0.15):
    tr = int(n * (1.0 - holdout_frac - val_frac))
    va = int(n * (1.0 - holdout_frac))
    return tr, va


def _stat_params(stat: str) -> dict:
    _DEFAULT_REG = {"max_depth": 4, "min_child_weight": 10, "reg_lambda": 2.0,
                    "gamma": 0.2, "n_estimators": 800, "learning_rate": 0.04,
                    "subsample": 0.8, "colsample_bytree": 0.8, "reg_alpha": 0.5}
    _DEFAULT_COUNT = {**_DEFAULT_REG, "max_depth": 3}
    overrides = {
        "pts":  {"max_depth": 6, "min_child_weight": 20, "reg_lambda": 4.0,
                 "learning_rate": 0.025, "colsample_bytree": 0.9, "reg_alpha": 2.0},
        "ast":  {"max_depth": 5, "min_child_weight": 20, "reg_lambda": 5.0,
                 "learning_rate": 0.025, "subsample": 0.7},
        "reb":  {"max_depth": 3, "min_child_weight": 30, "reg_lambda": 4.0,
                 "gamma": 0.3, "learning_rate": 0.025, "subsample": 0.7,
                 "colsample_bytree": 0.9},
        "fg3m": {"max_depth": 4, "min_child_weight": 15, "reg_lambda": 8.0,
                 "gamma": 0.0, "n_estimators": 600, "learning_rate": 0.025,
                 "subsample": 0.7},
        "stl":  {"max_depth": 2, "min_child_weight": 40, "reg_lambda": 6.0,
                 "gamma": 0.6, "n_estimators": 400, "learning_rate": 0.06,
                 "subsample": 0.9, "reg_alpha": 0.25},
        "blk":  {"max_depth": 3, "min_child_weight": 25, "reg_lambda": 4.0,
                 "gamma": 0.4, "n_estimators": 800, "learning_rate": 0.06,
                 "colsample_bytree": 1.0},
        "tov":  {"max_depth": 3, "min_child_weight": 30, "reg_lambda": 6.0,
                 "gamma": 0.4, "n_estimators": 700, "learning_rate": 0.025},
    }
    is_count = stat in ("stl", "blk")
    base = _DEFAULT_COUNT if is_count else _DEFAULT_REG
    return {**base, **overrides.get(stat, {})}


def _nnls(preds_val: np.ndarray, y_val: np.ndarray) -> np.ndarray:
    """Fit non-negative weights via sklearn LinearRegression(positive=True)."""
    from sklearn.linear_model import LinearRegression
    reg = LinearRegression(positive=True, fit_intercept=False)
    reg.fit(preds_val, y_val)
    return reg.coef_


def train_xgb_lgb(stat, X_tr, y_tr, X_val, y_val, sample_w_tr):
    import xgboost as xgb
    import lightgbm as lgb
    is_count = stat in ("stl", "blk")
    p = _stat_params(stat)
    xgb_m = xgb.XGBRegressor(
        n_estimators=p["n_estimators"], max_depth=p["max_depth"],
        learning_rate=p["learning_rate"], subsample=p["subsample"],
        colsample_bytree=p["colsample_bytree"],
        min_child_weight=p["min_child_weight"], reg_lambda=p["reg_lambda"],
        reg_alpha=p["reg_alpha"], gamma=p["gamma"], random_state=42,
        objective="count:poisson" if is_count else "reg:squarederror",
        early_stopping_rounds=40, eval_metric="mae",
    )
    xgb_m.fit(X_tr, y_tr, eval_set=[(X_val, y_val)], sample_weight=sample_w_tr, verbose=False)
    lgb_m = lgb.LGBMRegressor(
        n_estimators=p["n_estimators"], max_depth=p["max_depth"],
        learning_rate=p["learning_rate"], subsample=p["subsample"], subsample_freq=1,
        colsample_bytree=p["colsample_bytree"],
        min_child_samples=max(20, p["min_child_weight"] * 2),
        reg_lambda=p["reg_lambda"], reg_alpha=p["reg_alpha"], random_state=42,
        objective="poisson" if is_count else "regression", n_jobs=-1, verbosity=-1,
    )
    lgb_m.fit(X_tr, y_tr, eval_set=[(X_val, y_val)], sample_weight=sample_w_tr,
              callbacks=[lgb.early_stopping(40, verbose=False)])
    return xgb_m, lgb_m


def train_hgb(stat, X_tr, y_tr, X_val, y_val, sample_w_tr):
    from sklearn.ensemble import HistGradientBoostingRegressor
    is_count = stat in ("stl", "blk")
    p = _stat_params(stat)
    m = HistGradientBoostingRegressor(
        loss="poisson" if is_count else "squared_error",
        learning_rate=p["learning_rate"], max_iter=p["n_estimators"],
        max_depth=p["max_depth"] + 1, min_samples_leaf=max(20, p["min_child_weight"] * 2),
        l2_regularization=p["reg_lambda"], random_state=42,
        early_stopping=True, validation_fraction=0.15, n_iter_no_change=40, tol=1e-4,
    )
    m.fit(X_tr, y_tr, sample_weight=sample_w_tr)
    return m


def train_mlp(stat, X_tr, y_tr, X_val, y_val, sample_w_tr):
    from sklearn.neural_network import MLPRegressor
    from sklearn.preprocessing import StandardScaler
    sc = StandardScaler()
    Xs_tr = sc.fit_transform(X_tr)
    Xs_val = sc.transform(X_val)
    m = MLPRegressor(
        hidden_layer_sizes=(128, 64), activation="relu", solver="adam",
        learning_rate_init=1e-3, alpha=1e-4, batch_size=512,
        max_iter=80, random_state=42, early_stopping=True,
        validation_fraction=0.15, n_iter_no_change=10,
    )
    m.fit(Xs_tr, y_tr)
    return m, sc


def train_knn(stat, X_tr, y_tr, X_val, y_val, sample_w_tr):
    from sklearn.neighbors import KNeighborsRegressor
    from sklearn.preprocessing import StandardScaler
    sc = StandardScaler()
    Xs_tr = sc.fit_transform(X_tr)
    m = KNeighborsRegressor(n_neighbors=25, weights="distance", n_jobs=-1)
    m.fit(Xs_tr, y_tr)
    return m, sc


def main():
    t0 = time.time()
    print("[screen] building dataset ...")
    rows, feature_cols = build_pergame_dataset(min_prior=0)
    rows.sort(key=lambda r: r["date"])
    n = len(rows)
    tr_end, va_end = _split(n)
    X_all = np.array([[r[c] for c in feature_cols] for r in rows], dtype=float)
    X_tr, X_val, X_ho = X_all[:tr_end], X_all[tr_end:va_end], X_all[va_end:]

    # Recency weights for the train slice (decay 0.5 was confirmed as good).
    from datetime import datetime
    tr_dates = [datetime.fromisoformat(rows[i]["date"]) for i in range(tr_end)]
    max_d = max(tr_dates)
    age = np.array([(max_d - d).days / 365.0 for d in tr_dates], dtype=float)
    sw = np.exp(-0.5 * age)
    print(f"[screen] n={n} train={tr_end} val={va_end-tr_end} ho={n-va_end} wall={time.time()-t0:.0f}s")

    from sklearn.metrics import mean_absolute_error, r2_score

    out = {"stats": {}, "summary": {}}
    summary_rows = []

    for stat in STATS:
        y = np.array([r[f"target_{stat}"] for r in rows], dtype=float)
        y_tr, y_val, y_ho = y[:tr_end], y[tr_end:va_end], y[va_end:]

        ts = time.time()
        xgb_m, lgb_m = train_xgb_lgb(stat, X_tr, y_tr, X_val, y_val, sw)
        xgb_val, lgb_val = xgb_m.predict(X_val), lgb_m.predict(X_val)
        xgb_ho,  lgb_ho  = xgb_m.predict(X_ho),  lgb_m.predict(X_ho)
        w2 = _nnls(np.column_stack([xgb_val, lgb_val]), y_val)
        wsum = w2.sum()
        if not (0.5 <= wsum <= 1.5):
            w2 = np.array([0.5, 0.5])
        blend2 = w2[0] * xgb_ho + w2[1] * lgb_ho
        mae2 = mean_absolute_error(y_ho, blend2)
        r2_2 = r2_score(y_ho, blend2)

        # Extra learner experiments.
        extras = {}

        # HGB
        try:
            hgb_m = train_hgb(stat, X_tr, y_tr, X_val, y_val, sw)
            hgb_val, hgb_ho_p = hgb_m.predict(X_val), hgb_m.predict(X_ho)
            w3 = _nnls(np.column_stack([xgb_val, lgb_val, hgb_val]), y_val)
            wsum3 = w3.sum()
            if not (0.5 <= wsum3 <= 1.5):
                w3 = np.array([0.4, 0.4, 0.2])
            blend3 = w3[0]*xgb_ho + w3[1]*lgb_ho + w3[2]*hgb_ho_p
            extras["hgb"] = {
                "mae_3way": float(mean_absolute_error(y_ho, blend3)),
                "r2_3way":  float(r2_score(y_ho, blend3)),
                "weights":  [float(x) for x in w3],
                "solo_mae": float(mean_absolute_error(y_ho, hgb_ho_p)),
                "solo_r2":  float(r2_score(y_ho, hgb_ho_p)),
            }
        except Exception as e:
            extras["hgb"] = {"error": str(e)}

        # MLP
        try:
            mlp_m, mlp_sc = train_mlp(stat, X_tr, y_tr, X_val, y_val, sw)
            mlp_val = mlp_m.predict(mlp_sc.transform(X_val))
            mlp_ho_p = mlp_m.predict(mlp_sc.transform(X_ho))
            w3 = _nnls(np.column_stack([xgb_val, lgb_val, mlp_val]), y_val)
            wsum3 = w3.sum()
            if not (0.5 <= wsum3 <= 1.5):
                w3 = np.array([0.4, 0.4, 0.2])
            blend3 = w3[0]*xgb_ho + w3[1]*lgb_ho + w3[2]*mlp_ho_p
            extras["mlp"] = {
                "mae_3way": float(mean_absolute_error(y_ho, blend3)),
                "r2_3way":  float(r2_score(y_ho, blend3)),
                "weights":  [float(x) for x in w3],
                "solo_mae": float(mean_absolute_error(y_ho, mlp_ho_p)),
                "solo_r2":  float(r2_score(y_ho, mlp_ho_p)),
            }
        except Exception as e:
            extras["mlp"] = {"error": str(e)}

        # KNN
        try:
            knn_m, knn_sc = train_knn(stat, X_tr, y_tr, X_val, y_val, sw)
            knn_val = knn_m.predict(knn_sc.transform(X_val))
            knn_ho_p = knn_m.predict(knn_sc.transform(X_ho))
            w3 = _nnls(np.column_stack([xgb_val, lgb_val, knn_val]), y_val)
            wsum3 = w3.sum()
            if not (0.5 <= wsum3 <= 1.5):
                w3 = np.array([0.4, 0.4, 0.2])
            blend3 = w3[0]*xgb_ho + w3[1]*lgb_ho + w3[2]*knn_ho_p
            extras["knn"] = {
                "mae_3way": float(mean_absolute_error(y_ho, blend3)),
                "r2_3way":  float(r2_score(y_ho, blend3)),
                "weights":  [float(x) for x in w3],
                "solo_mae": float(mean_absolute_error(y_ho, knn_ho_p)),
                "solo_r2":  float(r2_score(y_ho, knn_ho_p)),
            }
        except Exception as e:
            extras["knn"] = {"error": str(e)}

        out["stats"][stat] = {
            "baseline_2way": {"mae": float(mae2), "r2": float(r2_2),
                              "weights": [float(x) for x in w2]},
            "extras": extras,
        }

        # Compact one-line summary per stat.
        row = f"  {stat.upper():4s} 2way mae={mae2:.4f} r2={r2_2:.4f}"
        for name in ["hgb", "mlp", "knn"]:
            e = extras[name]
            if "error" in e:
                row += f"  {name}=ERR"
            else:
                dmae = e["mae_3way"] - mae2
                dr2  = e["r2_3way"] - r2_2
                tag = "+" if dmae < 0 else " "
                row += f"  {name}={tag}{dmae:+.4f}/{dr2:+.4f}"
        summary_rows.append(row)
        print(row, flush=True)
        print(f"    [time] {stat}: {time.time()-ts:.0f}s", flush=True)

    print("\n=== screen complete ===")
    for r in summary_rows:
        print(r)

    out["wall_seconds"] = round(time.time() - t0, 1)
    with open(os.path.join(PROJECT_DIR, "data", "models", "extra_learners_screen.json"), "w") as f:
        json.dump(out, f, indent=2)
    print(f"\n[screen] wall={out['wall_seconds']}s -> data/models/extra_learners_screen.json")


if __name__ == "__main__":
    main()
