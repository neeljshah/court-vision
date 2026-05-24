"""winprob_walk_forward.py — walk-forward cross-validation of the 5-way stack.

The cycle-1 to cycle-14 cycles all evaluated on a single chronological 80/20
split (737 games in val). Cycle-12 demonstrated how noisy that signal can be:
a single seed flip swung val accuracy by +1.76pp. This script answers a
sharper question: across MULTIPLE temporal folds, what's the realistic
accuracy + Brier of the 5-way XGB+LGB+LR+MLP-ensemble+NB stack?

Fold layout: TimeSeriesSplit-style with `n_splits` expanding folds. Each
fold trains on `[0, fold_end_train)` and evaluates on `[fold_end_train,
fold_end_test)`, then advances. The training fraction grows fold-to-fold,
so the last fold has the most training data (mirrors production retrain
discipline).

Run:
    python scripts/winprob_walk_forward.py
    python scripts/winprob_walk_forward.py --seasons 2022-23 2023-24 2024-25 --splits 4
    python scripts/winprob_walk_forward.py --seasons 2018-19 2019-20 2020-21 2021-22 2022-23 2023-24 2024-25 --splits 5
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from typing import List, Tuple

import numpy as np
import pandas as pd

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

# Header patch must run before any nba_api imports.
from src.data import nba_api_headers_patch  # noqa: F401, E402

from src.prediction.win_probability import (  # noqa: E402
    _MODEL_DIR,
    _MODEL_FEATURE_COLS,
    _available_feature_cols,
    _fetch_season_games,
)

import warnings
warnings.filterwarnings("ignore")


def _train_5way(X_tr, y_tr, X_val, y_val) -> dict:
    """Train the 5-way stack and return per-fold metrics + NNLS weights.

    Mirrors the architecture in win_probability.train(): XGB + LGB + LR
    + 5-MLP-ensemble + NB, blended by LinearRegression(positive=True,
    fit_intercept=False) on the val set.
    """
    from xgboost import XGBClassifier
    import lightgbm as lgb
    from sklearn.linear_model import LogisticRegression, LinearRegression
    from sklearn.neural_network import MLPClassifier
    from sklearn.naive_bayes import GaussianNB
    from sklearn.preprocessing import StandardScaler
    from sklearn.metrics import accuracy_score, brier_score_loss

    xgb = XGBClassifier(
        n_estimators=300, learning_rate=0.035, max_depth=5,
        subsample=0.8, colsample_bytree=0.5, gamma=0.4,
        eval_metric="logloss", random_state=42, n_jobs=-1,
        early_stopping_rounds=20,
    )
    xgb.fit(X_tr, y_tr, eval_set=[(X_val, y_val)], verbose=False)
    xp = xgb.predict_proba(X_val)[:, 1]

    lc = lgb.LGBMClassifier(
        n_estimators=300, learning_rate=0.035, max_depth=4, num_leaves=15,
        subsample=0.8, subsample_freq=1, colsample_bytree=0.5,
        min_gain_to_split=0.4, objective="binary",
        random_state=42, n_jobs=-1, verbose=-1,
    )
    lc.fit(X_tr, y_tr, eval_set=[(X_val, y_val)],
           callbacks=[lgb.early_stopping(20, verbose=False)])
    lp = lc.predict_proba(X_val)[:, 1]

    scaler = StandardScaler().fit(X_tr)
    X_tr_s  = scaler.transform(X_tr)
    X_val_s = scaler.transform(X_val)

    lr = LogisticRegression(max_iter=1000, C=1.0, random_state=42, n_jobs=-1)
    lr.fit(X_tr_s, y_tr)
    rp = lr.predict_proba(X_val_s)[:, 1]

    mps = []
    for seed in [1, 7, 42, 100, 2024]:
        m = MLPClassifier(
            hidden_layer_sizes=(64,), alpha=0.001,
            early_stopping=True, validation_fraction=0.15,
            n_iter_no_change=20, max_iter=500, random_state=seed,
        )
        m.fit(X_tr_s, y_tr)
        mps.append(m.predict_proba(X_val_s)[:, 1])
    mp = np.mean(mps, axis=0)

    nb = GaussianNB().fit(X_tr_s, y_tr)
    np_ = nb.predict_proba(X_val_s)[:, 1]

    # NNLS blend
    st = LinearRegression(positive=True, fit_intercept=False)
    st.fit(np.column_stack([xp, lp, rp, mp, np_]), y_val)
    w = st.coef_
    w_sum = float(w.sum())
    if not (0.5 <= w_sum <= 1.5):
        w = np.array([0.2, 0.2, 0.2, 0.2, 0.2])
        meta = "fallback_equal"
    else:
        meta = "val_nnls_5way"
    blend = w[0]*xp + w[1]*lp + w[2]*rp + w[3]*mp + w[4]*np_
    blend = np.clip(blend, 0.0, 1.0)

    return {
        "acc":      float(accuracy_score(y_val, (blend >= 0.5).astype(int))),
        "brier":    float(brier_score_loss(y_val, blend)),
        "xgb_brier": float(brier_score_loss(y_val, xp)),
        "lgb_brier": float(brier_score_loss(y_val, lp)),
        "lr_brier":  float(brier_score_loss(y_val, rp)),
        "mlp_brier": float(brier_score_loss(y_val, mp)),
        "nb_brier":  float(brier_score_loss(y_val, np_)),
        "w_xgb":    float(w[0]), "w_lgb": float(w[1]),
        "w_lr":     float(w[2]), "w_mlp": float(w[3]),
        "w_nb":     float(w[4]),
        "meta":     meta,
        "n_train":  int(len(y_tr)),
        "n_val":    int(len(y_val)),
    }


def _load_dataset(seasons: List[str]) -> Tuple[np.ndarray, np.ndarray, List[str]]:
    rows: list = []
    for s in seasons:
        s_rows = _fetch_season_games(s)
        rows.extend(s_rows)
        print(f"  {s}: {len(s_rows)} games", flush=True)
    df = pd.DataFrame(rows).dropna(subset=["home_win"])
    if "game_date" in df.columns:
        df = df.sort_values("game_date").reset_index(drop=True)
    cols = _available_feature_cols(df.to_dict("records") if len(df) else [])
    X = df[cols].values.astype(np.float32)
    y = df["home_win"].values.astype(int)
    return X, y, cols


def walk_forward(seasons: List[str], n_splits: int = 4) -> dict:
    """Run walk-forward expanding-window cross-validation."""
    print(f"Walk-forward backtest | seasons={seasons} | folds={n_splits}\n",
          flush=True)
    print("Loading cached season rows...")
    X, y, cols = _load_dataset(seasons)
    print(f"  Total: n={len(X)} games | features={X.shape[1]}/{len(_MODEL_FEATURE_COLS)} "
          f"| home win rate {y.mean():.1%}\n", flush=True)

    n = len(X)
    # Expanding window: first fold starts at 1/(n_splits+1), grows.
    # E.g., n_splits=4 -> evaluate on [20%, 40%, 60%, 80%, 100%) slices.
    # Train end fractions: 0.20, 0.40, 0.60, 0.80
    # Test slice: that train_end -> next train_end (or 100% for last fold)
    fold_ends = [(i + 1) / (n_splits + 1) for i in range(n_splits)]
    folds_data = []
    for fold_idx, train_end_frac in enumerate(fold_ends):
        train_end = int(n * train_end_frac)
        if fold_idx == n_splits - 1:
            test_end = n
        else:
            test_end = int(n * fold_ends[fold_idx + 1])
        if train_end < 500 or (test_end - train_end) < 100:
            print(f"  fold {fold_idx+1}: too small "
                  f"(train={train_end}, test={test_end-train_end}) — skip")
            continue
        X_tr, y_tr = X[:train_end], y[:train_end]
        X_val, y_val = X[train_end:test_end], y[train_end:test_end]

        t0 = time.time()
        print(f"[fold {fold_idx+1}/{n_splits}] training on "
              f"{train_end} games, evaluating on {test_end-train_end}...",
              flush=True)
        m = _train_5way(X_tr, y_tr, X_val, y_val)
        m["fold"] = fold_idx + 1
        m["train_end_frac"] = train_end_frac
        m["elapsed_s"] = round(time.time() - t0, 1)
        folds_data.append(m)
        print(f"  acc {m['acc']:.4f}  brier {m['brier']:.4f}  "
              f"w_xgb={m['w_xgb']:.2f} w_lgb={m['w_lgb']:.2f} "
              f"w_lr={m['w_lr']:.2f} w_mlp={m['w_mlp']:.2f} w_nb={m['w_nb']:.2f}  "
              f"({m['elapsed_s']}s)\n", flush=True)

    accs   = [d["acc"]   for d in folds_data]
    briers = [d["brier"] for d in folds_data]
    summary = {
        "n_folds":      len(folds_data),
        "acc_mean":     float(np.mean(accs))   if accs else None,
        "acc_std":      float(np.std(accs))    if accs else None,
        "brier_mean":   float(np.mean(briers)) if briers else None,
        "brier_std":    float(np.std(briers))  if briers else None,
        "acc_min":      float(min(accs))       if accs else None,
        "acc_max":      float(max(accs))       if accs else None,
        "folds":        folds_data,
        "seasons":      seasons,
        "n_features":   len(cols),
    }

    print("=== WALK-FORWARD SUMMARY ===")
    print(f"  folds: {summary['n_folds']}")
    if accs:
        print(f"  accuracy: {summary['acc_mean']:.4f} +/- {summary['acc_std']:.4f}  "
              f"(range {summary['acc_min']:.4f}-{summary['acc_max']:.4f})")
        print(f"  Brier:    {summary['brier_mean']:.4f} +/- {summary['brier_std']:.4f}")

    out_path = os.path.join(_MODEL_DIR, "winprob_walk_forward_results.json")
    with open(out_path, "w") as f:
        json.dump(summary, f, indent=2)
    print(f"\nWrote {out_path}")
    return summary


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seasons", nargs="+",
                    default=["2022-23", "2023-24", "2024-25"])
    ap.add_argument("--splits", type=int, default=4)
    args = ap.parse_args()
    walk_forward(args.seasons, args.splits)
