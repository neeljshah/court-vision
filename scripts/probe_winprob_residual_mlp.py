"""probe_winprob_residual_mlp.py — does a RESIDUAL MLP improve WinProb?

Hypothesis (post-cycle-41 catboost failure): an MLP REGRESSOR trained on the
residual (y - mean(XGB, LGB) probability) might pick up nonlinearity the
boosters miss WITHOUT competing with them on the main signal.

Three variants per fold (4 expanding walk-forward folds):
  trees_only   :  p = mean(XGB.predict_proba, LGB.predict_proba)
  trees+resMLP :  p = clip(trees_only + MLPRegressor(X, y - trees_only_train), 0, 1)
  full5way     :  current production stack — XGB + LGB + LR + 5-MLP + NB, NNLS-blended

Mirrors scripts/winprob_walk_forward.py fold logic + hyperparameters from
src/prediction/win_probability.py. RESEARCH ONLY — does not modify
production code; results saved to scripts/_results/probe_winprob_residual_mlp.txt.
"""
from __future__ import annotations

import os
import sys
import warnings

warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from src.data import nba_api_headers_patch  # noqa: F401, E402
from src.prediction.win_probability import (  # noqa: E402
    _available_feature_cols, _fetch_season_games,
)


def _train_trees_only(X_tr, y_tr, X_val, y_val, X_ho, y_ho):
    """Train XGB + LGB exactly as in production; return tree-mean probs on tr/val/ho."""
    from xgboost import XGBClassifier
    import lightgbm as lgb
    from sklearn.metrics import accuracy_score, brier_score_loss

    xgb_clf = XGBClassifier(
        n_estimators=300, learning_rate=0.035, max_depth=5,
        subsample=0.8, colsample_bytree=0.5, gamma=0.4,
        eval_metric="logloss", random_state=42, n_jobs=-1,
        early_stopping_rounds=20,
    )
    xgb_clf.fit(X_tr, y_tr, eval_set=[(X_val, y_val)], verbose=False)

    lgb_clf = lgb.LGBMClassifier(
        n_estimators=300, learning_rate=0.035, max_depth=4, num_leaves=15,
        subsample=0.8, subsample_freq=1, colsample_bytree=0.5,
        min_gain_to_split=0.4, objective="binary",
        random_state=42, n_jobs=-1, verbose=-1,
    )
    lgb_clf.fit(X_tr, y_tr, eval_set=[(X_val, y_val)],
                callbacks=[lgb.early_stopping(20, verbose=False)])

    xp_tr  = xgb_clf.predict_proba(X_tr)[:, 1]
    xp_val = xgb_clf.predict_proba(X_val)[:, 1]
    xp_ho  = xgb_clf.predict_proba(X_ho)[:, 1]
    lp_tr  = lgb_clf.predict_proba(X_tr)[:, 1]
    lp_val = lgb_clf.predict_proba(X_val)[:, 1]
    lp_ho  = lgb_clf.predict_proba(X_ho)[:, 1]

    p_tr  = (xp_tr  + lp_tr)  / 2
    p_val = (xp_val + lp_val) / 2
    p_ho  = (xp_ho  + lp_ho)  / 2

    return {
        "p_tr": p_tr, "p_val": p_val, "p_ho": p_ho,
        "xp_val": xp_val, "lp_val": lp_val,
        "xp_ho": xp_ho,   "lp_ho": lp_ho,
        "acc_ho":   float(accuracy_score(y_ho, (p_ho >= 0.5).astype(int))),
        "brier_ho": float(brier_score_loss(y_ho, p_ho)),
    }


def _trees_plus_residual_mlp(X_tr, y_tr, X_ho, y_ho, p_tr, p_ho):
    """Train MLPRegressor on residual; final = clip(p_ho + mlp_residual_ho, 0, 1)."""
    from sklearn.neural_network import MLPRegressor
    from sklearn.preprocessing import StandardScaler
    from sklearn.metrics import accuracy_score, brier_score_loss

    scaler = StandardScaler().fit(X_tr)
    X_tr_s = scaler.transform(X_tr)
    X_ho_s = scaler.transform(X_ho)

    residual_tr = y_tr.astype(float) - p_tr

    mlp = MLPRegressor(
        hidden_layer_sizes=(64,), alpha=0.001,
        early_stopping=True, validation_fraction=0.15,
        n_iter_no_change=15, max_iter=80, random_state=42,
    )
    mlp.fit(X_tr_s, residual_tr)
    res_ho = mlp.predict(X_ho_s)

    p_final = np.clip(p_ho + res_ho, 0.0, 1.0)
    return {
        "acc_ho":   float(accuracy_score(y_ho, (p_final >= 0.5).astype(int))),
        "brier_ho": float(brier_score_loss(y_ho, p_final)),
        "res_mean": float(np.mean(np.abs(res_ho))),
    }


def _train_full5way(X_tr, y_tr, X_val, y_val, X_ho, y_ho,
                    xp_val, lp_val, xp_ho, lp_ho):
    """Production 5-way stack: add LR + 5-MLP + NB, fit NNLS on val, eval on ho."""
    from sklearn.linear_model import LogisticRegression, LinearRegression
    from sklearn.neural_network import MLPClassifier
    from sklearn.naive_bayes import GaussianNB
    from sklearn.preprocessing import StandardScaler
    from sklearn.metrics import accuracy_score, brier_score_loss

    scaler = StandardScaler().fit(X_tr)
    X_tr_s  = scaler.transform(X_tr)
    X_val_s = scaler.transform(X_val)
    X_ho_s  = scaler.transform(X_ho)

    lr = LogisticRegression(max_iter=1000, C=1.0, random_state=42, n_jobs=-1)
    lr.fit(X_tr_s, y_tr)
    rp_val = lr.predict_proba(X_val_s)[:, 1]
    rp_ho  = lr.predict_proba(X_ho_s)[:, 1]

    mps_val, mps_ho = [], []
    for seed in [1, 7, 42, 100, 2024]:
        m = MLPClassifier(
            hidden_layer_sizes=(64,), alpha=0.001,
            early_stopping=True, validation_fraction=0.15,
            n_iter_no_change=20, max_iter=500, random_state=seed,
        )
        m.fit(X_tr_s, y_tr)
        mps_val.append(m.predict_proba(X_val_s)[:, 1])
        mps_ho.append(m.predict_proba(X_ho_s)[:, 1])
    mp_val = np.mean(mps_val, axis=0)
    mp_ho  = np.mean(mps_ho,  axis=0)

    nb = GaussianNB().fit(X_tr_s, y_tr)
    np_val = nb.predict_proba(X_val_s)[:, 1]
    np_ho  = nb.predict_proba(X_ho_s)[:, 1]

    st = LinearRegression(positive=True, fit_intercept=False)
    st.fit(np.column_stack([xp_val, lp_val, rp_val, mp_val, np_val]), y_val)
    w = st.coef_
    w_sum = float(w.sum())
    if not (0.5 <= w_sum <= 1.5):
        w = np.array([0.2] * 5)

    blend_ho = (w[0]*xp_ho + w[1]*lp_ho + w[2]*rp_ho
                + w[3]*mp_ho + w[4]*np_ho)
    blend_ho = np.clip(blend_ho, 0.0, 1.0)

    return {
        "acc_ho":   float(accuracy_score(y_ho, (blend_ho >= 0.5).astype(int))),
        "brier_ho": float(brier_score_loss(y_ho, blend_ho)),
    }


def main():
    seasons = ["2023-24", "2024-25"]
    print(f"Loading season_games for {seasons}", flush=True)
    rows = []
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
    n = len(X)
    print(f"  Total: n={n}  features={X.shape[1]}  home_win_rate={y.mean():.3f}\n",
          flush=True)

    # 4 expanding folds: train on [0, train_end_frac), holdout on
    # [train_end_frac, next_frac).  This mirrors winprob_walk_forward.py.
    # An inner val split (last 25% of train) is used for tree early-stopping
    # AND for fitting the NNLS weights of the full-5way variant.
    fold_ends = [(i + 1) / 5 for i in range(4)]
    fold_results = []

    import time
    for fi, train_end_frac in enumerate(fold_ends):
        tr_end = int(n * train_end_frac)
        te_end = n if fi == 3 else int(n * fold_ends[fi + 1])
        if tr_end < 500 or (te_end - tr_end) < 100:
            print(f"  fold {fi+1}: too small — skip")
            continue
        # Inner val = last 25% of the training window (chronological).
        va_start = int(tr_end * 0.75)
        X_tr,  y_tr  = X[:va_start],       y[:va_start]
        X_val, y_val = X[va_start:tr_end], y[va_start:tr_end]
        X_ho,  y_ho  = X[tr_end:te_end],   y[tr_end:te_end]

        t0 = time.time()
        print(f"[fold {fi+1}/4] train={len(y_tr)} val={len(y_val)} ho={len(y_ho)}",
              flush=True)

        trees = _train_trees_only(X_tr, y_tr, X_val, y_val, X_ho, y_ho)
        res   = _trees_plus_residual_mlp(
            X_tr, y_tr, X_ho, y_ho,
            p_tr=trees["p_tr"], p_ho=trees["p_ho"],
        )
        full  = _train_full5way(
            X_tr, y_tr, X_val, y_val, X_ho, y_ho,
            xp_val=trees["xp_val"], lp_val=trees["lp_val"],
            xp_ho=trees["xp_ho"],   lp_ho=trees["lp_ho"],
        )
        elapsed = time.time() - t0
        fold_results.append({
            "fold":          fi + 1,
            "trees_acc":     trees["acc_ho"],
            "trees_brier":   trees["brier_ho"],
            "resmlp_acc":    res["acc_ho"],
            "resmlp_brier":  res["brier_ho"],
            "full5_acc":     full["acc_ho"],
            "full5_brier":   full["brier_ho"],
            "elapsed_s":     round(elapsed, 1),
        })
        print(f"  trees      acc={trees['acc_ho']:.4f}  brier={trees['brier_ho']:.4f}")
        print(f"  trees+res  acc={res['acc_ho']:.4f}  brier={res['brier_ho']:.4f}  "
              f"|residual|={res['res_mean']:.4f}")
        print(f"  full5way   acc={full['acc_ho']:.4f}  brier={full['brier_ho']:.4f}  "
              f"({elapsed:.1f}s)\n", flush=True)

    # ── Table ─────────────────────────────────────────────────────────────────
    lines = []
    lines.append("")
    lines.append("fold | trees_only   acc / brier | trees+resMLP acc / brier | full5way    acc / brier")
    lines.append("-----+--------------------------+--------------------------+------------------------")
    for r in fold_results:
        lines.append(
            f"  {r['fold']}  |  {r['trees_acc']:.4f} / {r['trees_brier']:.4f}     "
            f"|  {r['resmlp_acc']:.4f} / {r['resmlp_brier']:.4f}     "
            f"|  {r['full5_acc']:.4f} / {r['full5_brier']:.4f}"
        )

    def _agg(key):
        arr = np.array([r[key] for r in fold_results])
        return arr.mean(), arr.std()

    ta_m, ta_s = _agg("trees_acc");    tb_m, tb_s = _agg("trees_brier")
    ra_m, ra_s = _agg("resmlp_acc");   rb_m, rb_s = _agg("resmlp_brier")
    fa_m, fa_s = _agg("full5_acc");    fb_m, fb_s = _agg("full5_brier")

    lines.append("")
    lines.append("4-fold mean ± std:")
    lines.append(f"  trees_only    acc={ta_m:.4f}±{ta_s:.4f}  brier={tb_m:.4f}±{tb_s:.4f}")
    lines.append(f"  trees+resMLP  acc={ra_m:.4f}±{ra_s:.4f}  brier={rb_m:.4f}±{rb_s:.4f}")
    lines.append(f"  full5way      acc={fa_m:.4f}±{fa_s:.4f}  brier={fb_m:.4f}±{fb_s:.4f}")

    # Ship gate: trees+resMLP vs full5way on brier, per-fold
    res_vs_full = np.array([r["resmlp_brier"] - r["full5_brier"] for r in fold_results])
    res_vs_tree = np.array([r["resmlp_brier"] - r["trees_brier"] for r in fold_results])
    lines.append("")
    lines.append("Ship-gate signals:")
    lines.append(
        f"  trees+resMLP vs full5way  brier_delta={res_vs_full.mean():+.4f}  "
        f"folds_brier_lower={(res_vs_full < 0).sum()}/4"
    )
    lines.append(
        f"  trees+resMLP vs trees     brier_delta={res_vs_tree.mean():+.4f}  "
        f"folds_brier_lower={(res_vs_tree < 0).sum()}/4"
    )

    if (res_vs_full < 0).sum() == 4:
        lines.append("  -> SHIP: trees+resMLP beats full5way on brier in 4/4 folds")
    elif (res_vs_tree >= 0).sum() >= 2:
        lines.append("  -> REJECT: residual MLP fails to improve over trees_only baseline")
    else:
        lines.append("  -> INCONCLUSIVE: does not meet 4/4 ship gate")

    out_block = "\n".join(lines)
    print(out_block, flush=True)

    # Persist results
    results_dir = os.path.join(PROJECT_DIR, "scripts", "_results")
    os.makedirs(results_dir, exist_ok=True)
    out_path = os.path.join(results_dir, "probe_winprob_residual_mlp.txt")
    with open(out_path, "w") as f:
        f.write(out_block + "\n")
    print(f"\nWrote {out_path}", flush=True)


if __name__ == "__main__":
    main()
