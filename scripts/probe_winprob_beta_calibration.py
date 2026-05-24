"""probe_winprob_beta_calibration.py — does Beta calibration tighten WinProb Brier?

WinProb walk-forward sits at ~0.7094 acc / 0.193 Brier. Model may be well-
discriminating but poorly CALIBRATED. Beta calibration (Kull et al. 2017) is
strictly more expressive than Platt and less overfit-prone than isotonic.

The 2-parameter Beta(a, b) calibrator reduces to:
    logistic_regression(x = [log(p), log(1 - p)], y = label)

Protocol per fold (4 expanding walk-forward folds, mirroring
scripts/winprob_walk_forward.py):
  - Train the full production 5-way stack (XGB + LGB + LR + 5-seed MLP + NB).
  - Use a 70/30 split on the val window so we can fit the calibrator on the
    first 70% and evaluate the 3 variants on the held-out 30%. This avoids
    fitting the calibrator on the same rows we score it on.
  - Variants scored on holdout:
      * uncalibrated (NNLS-blended stack probs as-is)
      * Platt   = LogisticRegression on val_probs
      * Beta    = LogisticRegression on [log(p), log(1-p)] of val_probs
  - Report acc + brier per variant per fold + 4-fold mean +/- std.

Chose the full 5-way stack (not XGB+LGB alone) because the calibration target
is whatever ships in production — the NNLS-blended ensemble. If calibration
helps the minimal stack but not the ensemble, that's a misleading signal.

Constraints: <= 4 retrains end-to-end, <25 min wall, do NOT modify
win_probability.py, do NOT commit.
"""
from __future__ import annotations

import os
import sys
import time
import warnings

warnings.filterwarnings("ignore")

import numpy as np

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from src.data import nba_api_headers_patch  # noqa: F401, E402
from src.prediction.win_probability import (  # noqa: E402
    _MODEL_FEATURE_COLS, _available_feature_cols, _fetch_season_games,
)


def _train_5way_blend(X_tr, y_tr, X_val, y_val):
    """Train production 5-way stack, return NNLS-blended val probs."""
    from xgboost import XGBClassifier
    import lightgbm as lgb
    from sklearn.linear_model import LogisticRegression, LinearRegression
    from sklearn.neural_network import MLPClassifier
    from sklearn.naive_bayes import GaussianNB
    from sklearn.preprocessing import StandardScaler

    xgb = XGBClassifier(n_estimators=300, learning_rate=0.035, max_depth=5,
                        subsample=0.8, colsample_bytree=0.5, gamma=0.4,
                        eval_metric="logloss", random_state=42, n_jobs=-1,
                        early_stopping_rounds=20)
    xgb.fit(X_tr, y_tr, eval_set=[(X_val, y_val)], verbose=False)
    xp = xgb.predict_proba(X_val)[:, 1]

    lc = lgb.LGBMClassifier(n_estimators=300, learning_rate=0.035, max_depth=4,
                            num_leaves=15, subsample=0.8, subsample_freq=1,
                            colsample_bytree=0.5, min_gain_to_split=0.4,
                            objective="binary", random_state=42, n_jobs=-1,
                            verbose=-1)
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
        w = np.array([0.2] * 5)
    blend = np.clip(w[0]*xp + w[1]*lp + w[2]*rp + w[3]*mp + w[4]*np_,
                    0.0, 1.0)
    return blend


def _fit_platt(val_probs, y_val):
    """Standard Platt scaling: LR on raw prob."""
    from sklearn.linear_model import LogisticRegression
    cal = LogisticRegression(max_iter=1000)
    cal.fit(val_probs.reshape(-1, 1), y_val)
    return cal


def _fit_beta(val_probs, y_val):
    """2-param Beta calibration via Kull et al. log-odds reparameterization."""
    from sklearn.linear_model import LogisticRegression
    eps = 1e-6
    p = np.clip(val_probs, eps, 1.0 - eps)
    X = np.column_stack([np.log(p), np.log(1.0 - p)])
    cal = LogisticRegression(max_iter=1000)
    cal.fit(X, y_val)
    return cal


def _apply_platt(cal, probs):
    return cal.predict_proba(probs.reshape(-1, 1))[:, 1]


def _apply_beta(cal, probs):
    eps = 1e-6
    p = np.clip(probs, eps, 1.0 - eps)
    X = np.column_stack([np.log(p), np.log(1.0 - p)])
    return cal.predict_proba(X)[:, 1]


def _score(y, p):
    from sklearn.metrics import accuracy_score, brier_score_loss
    return (float(accuracy_score(y, (p >= 0.5).astype(int))),
            float(brier_score_loss(y, p)))


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
    print(f"  total n={n} games, features={X.shape[1]}/{len(_MODEL_FEATURE_COLS)}, "
          f"home_win_rate={y.mean():.1%}\n", flush=True)

    fold_ends = [(i + 1) / 5 for i in range(4)]
    results = {"uncal": {"acc": [], "brier": []},
               "platt": {"acc": [], "brier": []},
               "beta":  {"acc": [], "brier": []}}

    for fi, train_end_frac in enumerate(fold_ends):
        tr_end = int(n * train_end_frac)
        te_end = n if fi == 3 else int(n * fold_ends[fi + 1])
        if tr_end < 500 or (te_end - tr_end) < 200:
            print(f"  fold {fi+1}: too small — skip")
            continue
        X_tr, y_tr = X[:tr_end], y[:tr_end]
        X_val, y_val = X[tr_end:te_end], y[tr_end:te_end]
        # 70/30 split of val window: fit calibrator on first 70%, score on last 30%
        cut = int(0.7 * len(X_val))
        X_cal, y_cal = X_val[:cut], y_val[:cut]
        X_ho, y_ho = X_val[cut:], y_val[cut:]

        t0 = time.time()
        # train stack ONCE on X_tr; predict on the full val window so we have
        # probs for both the cal slice and the holdout slice.
        # The NNLS blend inside _train_5way_blend fits on (X_val, y_val) — to
        # avoid leaking holdout labels into the blend weights, fit the stack
        # with the cal slice as the NNLS-fitting val set, then re-predict on
        # holdout via the same trained learners.
        # Implementation note: simplest correct path is to make the val set =
        # cal slice during NNLS fitting, and predict holdout via re-calling
        # the same fitted learners. We restructure _train_5way_blend to expose
        # both predictions.
        blend_cal, blend_ho = _train_and_predict(X_tr, y_tr, X_cal, y_cal, X_ho)

        # Score uncalibrated on holdout
        acc_u, br_u = _score(y_ho, blend_ho)
        # Fit calibrators on cal slice probs vs y_cal
        platt = _fit_platt(blend_cal, y_cal)
        beta = _fit_beta(blend_cal, y_cal)
        platt_ho = _apply_platt(platt, blend_ho)
        beta_ho = _apply_beta(beta, blend_ho)
        acc_p, br_p = _score(y_ho, platt_ho)
        acc_b, br_b = _score(y_ho, beta_ho)

        results["uncal"]["acc"].append(acc_u); results["uncal"]["brier"].append(br_u)
        results["platt"]["acc"].append(acc_p); results["platt"]["brier"].append(br_p)
        results["beta"]["acc"].append(acc_b);  results["beta"]["brier"].append(br_b)

        elapsed = time.time() - t0
        print(f"  fold {fi+1}/4  n_tr={len(X_tr)} n_cal={len(X_cal)} n_ho={len(X_ho)} "
              f"({elapsed:.1f}s)", flush=True)
        print(f"    uncal: acc={acc_u:.4f}  brier={br_u:.4f}")
        print(f"    platt: acc={acc_p:.4f}  brier={br_p:.4f}  "
              f"(d_brier={br_p - br_u:+.4f})")
        print(f"    beta : acc={acc_b:.4f}  brier={br_b:.4f}  "
              f"(d_brier={br_b - br_u:+.4f})", flush=True)
        print()

    def _stats(key, metric):
        arr = np.array(results[key][metric])
        return arr.mean(), arr.std(), arr

    print("=" * 70)
    print("4-FOLD SUMMARY")
    print("=" * 70)
    for variant in ["uncal", "platt", "beta"]:
        a_m, a_s, a = _stats(variant, "acc")
        b_m, b_s, b = _stats(variant, "brier")
        print(f"  {variant:6s} acc={a_m:.4f}+-{a_s:.4f}  "
              f"brier={b_m:.4f}+-{b_s:.4f}")

    u_b = np.array(results["uncal"]["brier"])
    p_b = np.array(results["platt"]["brier"])
    b_b = np.array(results["beta"]["brier"])
    u_a = np.array(results["uncal"]["acc"])
    b_a = np.array(results["beta"]["acc"])

    print()
    print("SHIP GATE")
    print(f"  beta brier < uncal brier in {int((b_b < u_b).sum())}/4 folds  "
          f"(need 4/4)")
    print(f"  beta brier < platt brier in {int((b_b < p_b).sum())}/4 folds  "
          f"(need 3/4)")
    print(f"  beta vs uncal mean brier delta: {(b_b - u_b).mean():+.5f}")
    print(f"  beta vs uncal mean acc   delta: {(b_a - u_a).mean():+.5f}  "
          f"(near-zero = healthy)")


def _train_and_predict(X_tr, y_tr, X_cal, y_cal, X_ho):
    """Train 5-way stack with NNLS fitted on (X_cal, y_cal); return blended
    probs for both X_cal and X_ho. y_ho is never touched here.
    """
    from xgboost import XGBClassifier
    import lightgbm as lgb
    from sklearn.linear_model import LogisticRegression, LinearRegression
    from sklearn.neural_network import MLPClassifier
    from sklearn.naive_bayes import GaussianNB
    from sklearn.preprocessing import StandardScaler

    xgb = XGBClassifier(n_estimators=300, learning_rate=0.035, max_depth=5,
                        subsample=0.8, colsample_bytree=0.5, gamma=0.4,
                        eval_metric="logloss", random_state=42, n_jobs=-1,
                        early_stopping_rounds=20)
    xgb.fit(X_tr, y_tr, eval_set=[(X_cal, y_cal)], verbose=False)
    xp_cal = xgb.predict_proba(X_cal)[:, 1]
    xp_ho = xgb.predict_proba(X_ho)[:, 1]

    lc = lgb.LGBMClassifier(n_estimators=300, learning_rate=0.035, max_depth=4,
                            num_leaves=15, subsample=0.8, subsample_freq=1,
                            colsample_bytree=0.5, min_gain_to_split=0.4,
                            objective="binary", random_state=42, n_jobs=-1,
                            verbose=-1)
    lc.fit(X_tr, y_tr, eval_set=[(X_cal, y_cal)],
           callbacks=[lgb.early_stopping(20, verbose=False)])
    lp_cal = lc.predict_proba(X_cal)[:, 1]
    lp_ho = lc.predict_proba(X_ho)[:, 1]

    scaler = StandardScaler().fit(X_tr)
    X_tr_s = scaler.transform(X_tr)
    X_cal_s = scaler.transform(X_cal)
    X_ho_s = scaler.transform(X_ho)

    lr = LogisticRegression(max_iter=1000, C=1.0, random_state=42, n_jobs=-1)
    lr.fit(X_tr_s, y_tr)
    rp_cal = lr.predict_proba(X_cal_s)[:, 1]
    rp_ho = lr.predict_proba(X_ho_s)[:, 1]

    mps_cal, mps_ho = [], []
    for seed in [1, 7, 42, 100, 2024]:
        m = MLPClassifier(hidden_layer_sizes=(64,), alpha=0.001,
                          early_stopping=True, validation_fraction=0.15,
                          n_iter_no_change=20, max_iter=500, random_state=seed)
        m.fit(X_tr_s, y_tr)
        mps_cal.append(m.predict_proba(X_cal_s)[:, 1])
        mps_ho.append(m.predict_proba(X_ho_s)[:, 1])
    mp_cal = np.mean(mps_cal, axis=0)
    mp_ho = np.mean(mps_ho, axis=0)

    nb = GaussianNB().fit(X_tr_s, y_tr)
    np_cal = nb.predict_proba(X_cal_s)[:, 1]
    np_ho = nb.predict_proba(X_ho_s)[:, 1]

    # NNLS fit on cal slice only
    st = LinearRegression(positive=True, fit_intercept=False)
    st.fit(np.column_stack([xp_cal, lp_cal, rp_cal, mp_cal, np_cal]), y_cal)
    w = st.coef_
    if not (0.5 <= float(w.sum()) <= 1.5):
        w = np.array([0.2] * 5)
    blend_cal = np.clip(w[0]*xp_cal + w[1]*lp_cal + w[2]*rp_cal +
                        w[3]*mp_cal + w[4]*np_cal, 0.0, 1.0)
    blend_ho = np.clip(w[0]*xp_ho + w[1]*lp_ho + w[2]*rp_ho +
                       w[3]*mp_ho + w[4]*np_ho, 0.0, 1.0)
    return blend_cal, blend_ho


if __name__ == "__main__":
    main()
