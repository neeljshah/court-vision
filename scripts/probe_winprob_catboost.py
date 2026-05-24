"""probe_winprob_catboost.py — does CatBoost as 6th NNLS learner improve WinProb?

The cycle-10 WinProb 5-way stack (XGB + LGB + LR + 5-seed MLP + NB) sits at
0.7094 walk-forward acc / 0.193 Brier. CatBoost has a different bias than
the existing learners — let's see if adding it as a 6th NNLS feature lifts
either metric.

Identical to scripts/winprob_walk_forward.py but with one extra base learner.
"""
from __future__ import annotations

import os
import sys
import warnings

warnings.filterwarnings("ignore")

import numpy as np

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from src.data import nba_api_headers_patch  # noqa: F401, E402
from src.prediction.win_probability import (  # noqa: E402
    _MODEL_FEATURE_COLS, _available_feature_cols, _fetch_season_games,
)


def _train_5way(X_tr, y_tr, X_val, y_val):
    """Production 5-way stack — cycle-10 baseline."""
    from xgboost import XGBClassifier
    import lightgbm as lgb
    from sklearn.linear_model import LogisticRegression, LinearRegression
    from sklearn.neural_network import MLPClassifier
    from sklearn.naive_bayes import GaussianNB
    from sklearn.preprocessing import StandardScaler
    from sklearn.metrics import accuracy_score, brier_score_loss

    xgb = XGBClassifier(n_estimators=300, learning_rate=0.035, max_depth=5,
                        subsample=0.8, colsample_bytree=0.5, gamma=0.4,
                        eval_metric="logloss", random_state=42, n_jobs=-1,
                        early_stopping_rounds=20)
    xgb.fit(X_tr, y_tr, eval_set=[(X_val, y_val)], verbose=False)
    xp = xgb.predict_proba(X_val)[:, 1]
    lc = lgb.LGBMClassifier(n_estimators=300, learning_rate=0.035, max_depth=4, num_leaves=15,
                            subsample=0.8, subsample_freq=1, colsample_bytree=0.5,
                            min_gain_to_split=0.4, objective="binary",
                            random_state=42, n_jobs=-1, verbose=-1)
    lc.fit(X_tr, y_tr, eval_set=[(X_val, y_val)],
           callbacks=[lgb.early_stopping(20, verbose=False)])
    lp = lc.predict_proba(X_val)[:, 1]
    scaler = StandardScaler().fit(X_tr)
    X_tr_s, X_val_s = scaler.transform(X_tr), scaler.transform(X_val)
    lr = LogisticRegression(max_iter=1000, C=1.0, random_state=42, n_jobs=-1)
    lr.fit(X_tr_s, y_tr)
    rp = lr.predict_proba(X_val_s)[:, 1]
    mps = []
    for seed in [1, 7, 42, 100, 2024]:
        m = MLPClassifier(hidden_layer_sizes=(64,), alpha=0.001,
                          early_stopping=True, validation_fraction=0.15,
                          n_iter_no_change=20, max_iter=500, random_state=seed)
        m.fit(X_tr_s, y_tr)
        mps.append(m.predict_proba(X_val_s)[:, 1])
    mp = np.mean(mps, axis=0)
    nb = GaussianNB().fit(X_tr_s, y_tr)
    np_ = nb.predict_proba(X_val_s)[:, 1]

    st = LinearRegression(positive=True, fit_intercept=False)
    st.fit(np.column_stack([xp, lp, rp, mp, np_]), y_val)
    w = st.coef_
    if not (0.5 <= float(w.sum()) <= 1.5):
        w = np.array([0.2]*5)
    blend = np.clip(w[0]*xp + w[1]*lp + w[2]*rp + w[3]*mp + w[4]*np_, 0.0, 1.0)
    return {
        "acc": float(accuracy_score(y_val, (blend >= 0.5).astype(int))),
        "brier": float(brier_score_loss(y_val, blend)),
        "preds_val": [xp, lp, rp, mp, np_],
    }


def _add_catboost(X_tr, y_tr, X_val, y_val, preds_val_5way):
    """Train CatBoost binary classifier, refit 6-way NNLS."""
    from catboost import CatBoostClassifier
    from sklearn.linear_model import LinearRegression
    from sklearn.metrics import accuracy_score, brier_score_loss

    cb = CatBoostClassifier(iterations=400, depth=6, learning_rate=0.035,
                            l2_leaf_reg=3.0, random_state=42, verbose=False,
                            early_stopping_rounds=20)
    cb.fit(X_tr, y_tr, eval_set=(X_val, y_val), verbose=False)
    cbp = cb.predict_proba(X_val)[:, 1]
    cols = preds_val_5way + [cbp]
    st = LinearRegression(positive=True, fit_intercept=False)
    st.fit(np.column_stack(cols), y_val)
    w = st.coef_
    if not (0.5 <= float(w.sum()) <= 1.5):
        w = np.array([1.0/6]*6)
    blend = np.clip(sum(w[i]*cols[i] for i in range(6)), 0.0, 1.0)
    return {
        "acc": float(accuracy_score(y_val, (blend >= 0.5).astype(int))),
        "brier": float(brier_score_loss(y_val, blend)),
        "w_cb": float(w[5]),
    }


def main():
    seasons = ["2023-24", "2024-25"]
    print(f"Loading season_games for {seasons}", flush=True)
    rows = []
    for s in seasons:
        s_rows = _fetch_season_games(s)
        rows.extend(s_rows)
        print(f"  {s}: {len(s_rows)} games", flush=True)
    import pandas as pd
    df = pd.DataFrame(rows).dropna(subset=["home_win"])
    if "game_date" in df.columns:
        df = df.sort_values("game_date").reset_index(drop=True)
    cols = _available_feature_cols(df.to_dict("records") if len(df) else [])
    X = df[cols].values.astype(np.float32)
    y = df["home_win"].values.astype(int)
    n = len(X)
    fold_ends = [(i + 1) / 5 for i in range(4)]
    out = {"5way": {"acc": [], "brier": []}, "6way_cb": {"acc": [], "brier": []}}

    for fi, train_end_frac in enumerate(fold_ends):
        tr_end = int(n * train_end_frac)
        te_end = n if fi == 3 else int(n * fold_ends[fi+1])
        if tr_end < 500 or (te_end - tr_end) < 100:
            continue
        X_tr, y_tr = X[:tr_end], y[:tr_end]
        X_val, y_val = X[tr_end:te_end], y[tr_end:te_end]
        r5 = _train_5way(X_tr, y_tr, X_val, y_val)
        r6 = _add_catboost(X_tr, y_tr, X_val, y_val, r5["preds_val"])
        out["5way"]["acc"].append(r5["acc"]); out["5way"]["brier"].append(r5["brier"])
        out["6way_cb"]["acc"].append(r6["acc"]); out["6way_cb"]["brier"].append(r6["brier"])
        print(f"  fold {fi+1}: 5way acc={r5['acc']:.4f} brier={r5['brier']:.4f}  "
              f"6way+cb acc={r6['acc']:.4f} brier={r6['brier']:.4f}  w_cb={r6['w_cb']:.2f}",
              flush=True)

    print()
    a5 = np.array(out["5way"]["acc"]); a6 = np.array(out["6way_cb"]["acc"])
    b5 = np.array(out["5way"]["brier"]); b6 = np.array(out["6way_cb"]["brier"])
    print(f"  5way    acc={a5.mean():.4f}+-{a5.std():.4f}  brier={b5.mean():.4f}+-{b5.std():.4f}")
    print(f"  6way+cb acc={a6.mean():.4f}+-{a6.std():.4f}  brier={b6.mean():.4f}+-{b6.std():.4f}")
    print(f"  delta   acc={(a6-a5).mean():+.4f}  brier={(b6-b5).mean():+.4f}  "
          f"folds_acc_up={int((a6 > a5).sum())}/4  folds_brier_down={int((b6 < b5).sum())}/4")


if __name__ == "__main__":
    main()
