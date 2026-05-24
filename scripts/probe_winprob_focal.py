"""probe_winprob_focal.py — focal-loss XGB variant inside the WinProb 5-way stack.

Two probes already rejected this loop have tightened the picture of where
WinProb gains might live:
  - residual MLP (predict y - mean(xgb,lgb))         REJECTED (brier +0.058)
  - beta calibration of NNLS output                  REJECTED (brier +0.001)

This probe targets a third angle: the cross-entropy XGB sees treats every
mispredicted game equally. Focal loss (Lin et al. 2017) downweights
easy/confident examples and upweights hard/uncertain ones. The hypothesis:
the model already does well on lopsided matchups; the marginal information
is in coin-flip games. Focal loss may push XGB to pay more attention to
those without hurting the easy wins.

Implementation: XGBoost custom objective via `obj` callback. Gradient and
hessian for binary focal loss with focusing parameter gamma:
  L = -alpha * (1-p)^gamma * y * log(p) - (1-alpha) * p^gamma * (1-y) * log(1-p)
Use alpha=0.5 (balanced), gamma in {1.0, 2.0}.

Variants compared on 4-fold expanding walk-forward (mirrors winprob_walk_forward.py):
  baseline      — full 5-way NNLS stack (current production)
  focal_g1      — replace XGB inner objective with focal(gamma=1)
  focal_g2      — replace XGB inner objective with focal(gamma=2)

Ship gate: brier strictly down on 4/4 folds vs baseline AND no accuracy loss > 1pp.

Run:
    python scripts/probe_winprob_focal.py
"""
from __future__ import annotations

import os
import sys
import time
import warnings
from typing import List

warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from src.data import nba_api_headers_patch  # noqa: F401, E402
from src.prediction.win_probability import (  # noqa: E402
    _MODEL_FEATURE_COLS,
    _available_feature_cols,
    _fetch_season_games,
)

# Focal binary cross-entropy custom objective for XGBoost.
# Sklearn-wrapped XGBClassifier calls obj(labels, preds) with numpy arrays
# (not the legacy DMatrix-form (preds, dmat)). The label-first signature
# matches xgboost/sklearn.py:164: `inner(preds, labels) -> fn(labels, preds)`.
def _make_focal_obj(gamma: float, alpha: float = 0.5):
    def obj(labels: np.ndarray, raw_pred: np.ndarray) -> tuple:
        y = np.asarray(labels, dtype=np.float64)
        raw_pred = np.asarray(raw_pred, dtype=np.float64)
        p = 1.0 / (1.0 + np.exp(-raw_pred))
        # Numerical guards
        p = np.clip(p, 1e-6, 1 - 1e-6)
        # alpha weighting: pos class -> alpha, neg class -> 1-alpha
        a = np.where(y == 1, alpha, 1.0 - alpha)
        # Hard-example weight (1-p_t)^gamma where p_t is p if y=1 else 1-p
        pt = np.where(y == 1, p, 1.0 - p)
        w_focal = (1.0 - pt) ** gamma
        # Derivatives of focal BCE wrt raw_pred (logit). Use the simplification
        # from Lin et al. for stable gradients:
        # dL/dz = a * w_focal * [gamma * pt * log(pt) * (1 - pt) + (pt - y)]
        # (where z = raw_pred). Hess approximated as |grad|*(1-|grad|) like
        # XGBoost's logistic — safe enough for tree update steps.
        log_pt = np.log(pt)
        grad = a * w_focal * (gamma * pt * log_pt * (1.0 - pt) + (p - y))
        # Hessian: use the diagonal logistic surrogate p*(1-p) scaled by focal weight.
        hess = a * w_focal * p * (1.0 - p)
        # Avoid zero hess so XGB doesn't reject the split.
        hess = np.clip(hess, 1e-6, None)
        return grad, hess
    return obj


def _train_variant(X_tr, y_tr, X_val, y_val, *, focal_gamma=None):
    """Train the 5-way stack. If focal_gamma given, replace XGB with focal-loss XGB."""
    from xgboost import XGBClassifier
    import lightgbm as lgb
    from sklearn.linear_model import LogisticRegression, LinearRegression
    from sklearn.neural_network import MLPClassifier
    from sklearn.naive_bayes import GaussianNB
    from sklearn.preprocessing import StandardScaler
    from sklearn.metrics import accuracy_score, brier_score_loss

    if focal_gamma is None:
        xgb_m = XGBClassifier(
            n_estimators=300, learning_rate=0.035, max_depth=5,
            subsample=0.8, colsample_bytree=0.5, gamma=0.4,
            eval_metric="logloss", random_state=42, n_jobs=-1,
            early_stopping_rounds=20,
        )
        xgb_m.fit(X_tr, y_tr, eval_set=[(X_val, y_val)], verbose=False)
    else:
        # Train with focal custom objective. No early stopping since custom
        # objective + classifier eval is awkward; rely on n_estimators=300
        # which is the production value.
        xgb_m = XGBClassifier(
            n_estimators=300, learning_rate=0.035, max_depth=5,
            subsample=0.8, colsample_bytree=0.5, gamma=0.4,
            objective=_make_focal_obj(focal_gamma, alpha=0.5),
            base_score=0.5, random_state=42, n_jobs=-1,
        )
        xgb_m.fit(X_tr, y_tr, verbose=False)
    xp = xgb_m.predict_proba(X_val)[:, 1]

    lc = lgb.LGBMClassifier(
        n_estimators=300, learning_rate=0.035, max_depth=4, num_leaves=15,
        subsample=0.8, subsample_freq=1, colsample_bytree=0.5,
        min_gain_to_split=0.4, objective="binary",
        random_state=42, n_jobs=-1, verbose=-1,
    )
    lc.fit(X_tr, y_tr, eval_set=[(X_val, y_val)],
           callbacks=[lgb.early_stopping(20, verbose=False)])
    lp = lc.predict_proba(X_val)[:, 1]

    sc = StandardScaler().fit(X_tr)
    Xts = sc.transform(X_tr); Xvs = sc.transform(X_val)

    lr = LogisticRegression(max_iter=1000, C=1.0, random_state=42, n_jobs=-1)
    lr.fit(Xts, y_tr); rp = lr.predict_proba(Xvs)[:, 1]

    mps = []
    for seed in (1, 7, 42, 100, 2024):
        m = MLPClassifier(hidden_layer_sizes=(64,), alpha=0.001,
                          early_stopping=True, validation_fraction=0.15,
                          n_iter_no_change=20, max_iter=500, random_state=seed)
        m.fit(Xts, y_tr); mps.append(m.predict_proba(Xvs)[:, 1])
    mp = np.mean(mps, axis=0)

    nb = GaussianNB().fit(Xts, y_tr); np_ = nb.predict_proba(Xvs)[:, 1]

    st = LinearRegression(positive=True, fit_intercept=False).fit(
        np.column_stack([xp, lp, rp, mp, np_]), y_val)
    w = st.coef_
    if not (0.5 <= w.sum() <= 1.5):
        w = np.array([0.2, 0.2, 0.2, 0.2, 0.2])
    blend = np.clip(w[0]*xp + w[1]*lp + w[2]*rp + w[3]*mp + w[4]*np_, 0.0, 1.0)
    return {
        "acc":   float(accuracy_score(y_val, (blend >= 0.5).astype(int))),
        "brier": float(brier_score_loss(y_val, blend)),
        "xgb_brier_solo": float(brier_score_loss(y_val, xp)),
        "w_xgb": float(w[0]),
    }


def _load(seasons: List[str]):
    rows: list = []
    for s in seasons:
        rs = _fetch_season_games(s)
        rows.extend(rs)
        print(f"  {s}: {len(rs)} games", flush=True)
    df = pd.DataFrame(rows).dropna(subset=["home_win"])
    if "game_date" in df.columns:
        df = df.sort_values("game_date").reset_index(drop=True)
    cols = _available_feature_cols(df.to_dict("records") if len(df) else [])
    X = df[cols].values.astype(np.float32)
    y = df["home_win"].values.astype(int)
    return X, y


def main():
    seasons = ["2023-24", "2024-25"]
    print(f"WinProb focal loss probe | seasons={seasons}", flush=True)
    X, y = _load(seasons)
    n = len(X)
    print(f"  n={n} home_win_rate={y.mean():.3f}", flush=True)

    n_splits = 4
    fold_ends = [(i + 1) / (n_splits + 1) for i in range(n_splits)]

    out = {v: {"acc": [], "brier": [], "xgb_brier": []}
           for v in ["baseline", "focal_g1", "focal_g2"]}

    for fi, frac in enumerate(fold_ends):
        tr_end = int(n * frac)
        te_end = n if fi == n_splits - 1 else int(n * fold_ends[fi+1])
        if tr_end < 500 or (te_end - tr_end) < 100:
            print(f"  fold {fi+1}: too small — skip", flush=True)
            continue
        X_tr, y_tr = X[:tr_end], y[:tr_end]
        X_val, y_val = X[tr_end:te_end], y[tr_end:te_end]
        t0 = time.time()
        rb = _train_variant(X_tr, y_tr, X_val, y_val, focal_gamma=None)
        r1 = _train_variant(X_tr, y_tr, X_val, y_val, focal_gamma=1.0)
        r2 = _train_variant(X_tr, y_tr, X_val, y_val, focal_gamma=2.0)
        for v, r in (("baseline", rb), ("focal_g1", r1), ("focal_g2", r2)):
            out[v]["acc"].append(r["acc"])
            out[v]["brier"].append(r["brier"])
            out[v]["xgb_brier"].append(r["xgb_brier_solo"])
        elapsed = time.time() - t0
        print(f"  fold {fi+1}: baseline brier={rb['brier']:.4f}  "
              f"focal_g1 brier={r1['brier']:.4f} (d={r1['brier']-rb['brier']:+.4f})  "
              f"focal_g2 brier={r2['brier']:.4f} (d={r2['brier']-rb['brier']:+.4f})  "
              f"({elapsed:.1f}s)", flush=True)

    print("\n=== Summary (lower brier better) ===")
    for v in ("baseline", "focal_g1", "focal_g2"):
        a = np.array(out[v]["acc"]); b = np.array(out[v]["brier"])
        xb = np.array(out[v]["xgb_brier"])
        print(f"  {v:10s}: acc={a.mean():.4f}+-{a.std():.4f}  "
              f"brier={b.mean():.4f}+-{b.std():.4f}  "
              f"xgb_solo_brier={xb.mean():.4f}+-{xb.std():.4f}")
    print("\n=== Ship gate (brier strictly down 4/4 AND acc not down > 0.01) ===")
    bb = np.array(out["baseline"]["brier"]); ba = np.array(out["baseline"]["acc"])
    for v in ("focal_g1", "focal_g2"):
        vb = np.array(out[v]["brier"]); va = np.array(out[v]["acc"])
        gate_b = int((vb < bb).sum()) == len(bb)
        gate_a = (ba - va).max() <= 0.01
        verdict = "SHIP" if (gate_b and gate_a) else "REJECT"
        print(f"  {v}: brier 4/4 down = {gate_b}, acc loss <= 1pp = {gate_a} -> {verdict}")


if __name__ == "__main__":
    main()
