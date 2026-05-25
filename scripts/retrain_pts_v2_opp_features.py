"""retrain_pts_v2_opp_features.py — Cycle 100a (loop 5): PTS retrain with 16 opp_l5 features.

Cycle 99e shipped 16 new opp-context rolling-5 features (additive to row dicts
but NOT wired into feature_columns()):
  * 9 opp_team_<col>_l5   — off_rtg, def_rtg, pace, oreb_pct, dreb_pct,
                             ast_pct, efg_pct, ts_pct, tov_ratio
                             (rolling-5 mean of OPPONENT's last 5 games BEFORE
                              row's date — strictly prior, no leakage)
  * 7 opp_def_<stat>_l5   — rolling-5 mean of opponent's last-5 allowed PTS,
                             REB, AST, FG3M, STL, BLK, TOV (raw counts, also
                             strictly prior). Sibling of opp_def_<stat>
                             (the to-date EXPANDING factor).

All 16 verified at 100% holdout coverage (cycle 99e, re-verified pre-train).

This cycle retrains PTS heads ONLY (sqrt+Huber blend: XGB + LGB + MLP via
NNLS). PTS production MAE is 4.6104 (post cycle-96a haircut) on the cycle-18
sqrt+Huber baseline. Pre-haircut anchor 4.6210.

Hyperparameters: UNCHANGED from production (_STAT_PARAMS["pts"]). Only the
feature set grows by 16 columns. Artifacts persist as data/models/pts_v2_*.pkl
without overwriting v1.

Ship gate (BOTH):
  1. Single-split PTS MAE strictly DOWN vs pre-haircut anchor 4.6210 (recompute
     baseline path matches; this anchor compares apples-to-apples since v2 is
     pre-haircut output as well).
  2. Walk-forward (4 folds) PTS MAE sign 4/4 negative (v2 < v1).

If both pass: persist v2 + update prop_pergame dispatch to load v2 artifacts
for PTS only (other heads untouched). Cycle-96a haircut still applies in prod.

Run:
    python scripts/retrain_pts_v2_opp_features.py
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import warnings
from datetime import datetime
from typing import List, Optional, Tuple

warnings.filterwarnings("ignore")

import numpy as np

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from src.prediction.prop_pergame import (  # noqa: E402
    _MODEL_DIR,
    _RECENCY_DECAY,
    _SQRT_HUBER_STATS,
    _TEAM_ADV_FEATURE_KEYS,
    STATS,
    build_pergame_dataset,
    feature_columns,
)

# 16 new opp_l5 keys: 9 opp_team_<col>_l5 (cycle 99e _TeamAdvancedL5) +
# 7 opp_def_<stat>_l5 (cycle 99e _OpponentDefense.l5_allowed).
_OPP_DEF_L5_KEYS = tuple(f"opp_def_{s}_l5" for s in STATS)
_NEW_OPP_KEYS = tuple(list(_TEAM_ADV_FEATURE_KEYS) + list(_OPP_DEF_L5_KEYS))
assert len(_NEW_OPP_KEYS) == 16, f"expected 16 new keys, got {len(_NEW_OPP_KEYS)}"


def pts_v2_feature_columns() -> List[str]:
    """PTS v2 feature columns: baseline 85 + 16 opp_l5 keys."""
    return list(feature_columns()) + list(_NEW_OPP_KEYS)


def _build_X(rows: List[dict], cols: List[str]) -> np.ndarray:
    n = len(rows)
    X = np.zeros((n, len(cols)), dtype=float)
    for i, r in enumerate(rows):
        for j, c in enumerate(cols):
            v = r.get(c)
            X[i, j] = float(v) if v is not None else 0.0
    return X


# ── coverage check ──────────────────────────────────────────────────────────

def _coverage_check(rows: List[dict]) -> dict:
    n = len(rows)
    train = rows[:int(n * 0.80)]
    holdout = rows[int(n * 0.80):]
    out = {
        "n_train":   len(train),
        "n_holdout": len(holdout),
    }
    for k in _NEW_OPP_KEYS:
        tr = sum(1 for r in train if r.get(k) is not None)
        ho = sum(1 for r in holdout if r.get(k) is not None)
        out[f"{k}_train_cov"]   = tr / max(1, len(train))
        out[f"{k}_holdout_cov"] = ho / max(1, len(holdout))
    return out


# ── training ────────────────────────────────────────────────────────────────

def _pts_params() -> dict:
    """Mirror prop_pergame._STAT_PARAMS['pts'] + _DEFAULT_REG fallbacks."""
    return {
        "max_depth": 6, "min_child_weight": 20, "reg_lambda": 4.0,
        "gamma": 0.2, "n_estimators": 800, "learning_rate": 0.025,
        "subsample": 0.8, "colsample_bytree": 0.9, "reg_alpha": 2.0,
    }


def _inv_sqrt(v: np.ndarray) -> np.ndarray:
    return np.clip(v, 0.0, None) ** 2


def _train_blend(X_tr, y_tr, X_val, y_val, sw):
    """Train PTS sqrt+Huber 3-way blend (xgb + lgb + mlp) + NNLS weights.

    Returns (xgb_model, lgb_model, mlp_scaler, mlp_model, w_xgb, w_lgb, w_mlp).
    Mirrors train_pergame_models for stat='pts' exactly.
    """
    import lightgbm as lgb
    import xgboost as xgb
    from sklearn.linear_model import LinearRegression
    from sklearn.preprocessing import StandardScaler

    from src.prediction.prop_pergame import _MLPSeedEnsemble

    p = _pts_params()
    assert "pts" in _SQRT_HUBER_STATS

    y_tr_t = np.sqrt(y_tr)
    y_val_t = np.sqrt(y_val)

    xgb_m = xgb.XGBRegressor(
        n_estimators=p["n_estimators"], max_depth=p["max_depth"],
        learning_rate=p["learning_rate"], subsample=p["subsample"],
        colsample_bytree=p["colsample_bytree"],
        min_child_weight=p["min_child_weight"], reg_lambda=p["reg_lambda"],
        reg_alpha=p["reg_alpha"], gamma=p["gamma"], random_state=42,
        objective="reg:pseudohubererror",
        early_stopping_rounds=40, eval_metric="mae",
    )
    xgb_m.fit(X_tr, y_tr_t, eval_set=[(X_val, y_val_t)],
              sample_weight=sw, verbose=False)

    lgb_m = lgb.LGBMRegressor(
        n_estimators=p["n_estimators"], max_depth=p["max_depth"],
        learning_rate=p["learning_rate"], subsample=p["subsample"],
        subsample_freq=1, colsample_bytree=p["colsample_bytree"],
        min_child_samples=max(20, p["min_child_weight"] * 2),
        reg_lambda=p["reg_lambda"], reg_alpha=p["reg_alpha"],
        random_state=42, objective="huber", n_jobs=-1, verbosity=-1,
    )
    lgb_m.fit(X_tr, y_tr_t, eval_set=[(X_val, y_val_t)],
              sample_weight=sw,
              callbacks=[lgb.early_stopping(40, verbose=False)])

    scaler = StandardScaler()
    X_tr_s = scaler.fit_transform(X_tr)
    X_val_s = scaler.transform(X_val)
    mlp_m = _MLPSeedEnsemble().fit(X_tr_s, y_tr_t)

    # NNLS on val (raw-y target after inverse).
    xgb_val = _inv_sqrt(xgb_m.predict(X_val))
    lgb_val = _inv_sqrt(lgb_m.predict(X_val))
    mlp_val = _inv_sqrt(mlp_m.predict(X_val_s))
    st = LinearRegression(positive=True, fit_intercept=False)
    st.fit(np.column_stack([xgb_val, lgb_val, mlp_val]), y_val)
    w_xgb, w_lgb, w_mlp = (float(st.coef_[0]), float(st.coef_[1]),
                           float(st.coef_[2]))
    w_sum = w_xgb + w_lgb + w_mlp
    if not (0.5 <= w_sum <= 1.5):
        w_xgb = w_lgb = w_mlp = 1.0 / 3.0

    return xgb_m, lgb_m, scaler, mlp_m, w_xgb, w_lgb, w_mlp


def _predict_blend(X, X_s, xgb_m, lgb_m, mlp_m, w_xgb, w_lgb, w_mlp):
    xgb_p = _inv_sqrt(xgb_m.predict(X))
    lgb_p = _inv_sqrt(lgb_m.predict(X))
    mlp_p = _inv_sqrt(mlp_m.predict(X_s))
    return w_xgb * xgb_p + w_lgb * lgb_p + w_mlp * mlp_p


# ── single-split & WF evals ─────────────────────────────────────────────────

def single_split_eval(rows: List[dict], holdout_frac: float = 0.20,
                      val_frac: float = 0.15) -> Tuple[dict, dict, tuple]:
    """Train PTS v1 (85 cols) and v2 (101 cols) on a 65/15/20 chrono split.
    Returns (v1_info, v2_info, v2_artifacts) where v2_artifacts holds the
    fitted models + scaler + weights for ship persistence.
    """
    from sklearn.metrics import mean_absolute_error, r2_score

    cols_v1 = feature_columns()
    cols_v2 = pts_v2_feature_columns()

    rows.sort(key=lambda r: r["date"])
    n = len(rows)
    train_end = int(n * (1.0 - holdout_frac - val_frac))
    val_end = int(n * (1.0 - holdout_frac))

    X_v1 = _build_X(rows, cols_v1)
    X_v2 = _build_X(rows, cols_v2)
    y = np.array([float(r["target_pts"]) for r in rows], dtype=float)

    X_tr_v1, X_val_v1, X_ho_v1 = (X_v1[:train_end],
                                  X_v1[train_end:val_end],
                                  X_v1[val_end:])
    X_tr_v2, X_val_v2, X_ho_v2 = (X_v2[:train_end],
                                  X_v2[train_end:val_end],
                                  X_v2[val_end:])
    y_tr, y_val, y_ho = y[:train_end], y[train_end:val_end], y[val_end:]

    train_dates = [datetime.fromisoformat(rows[i]["date"]) for i in range(train_end)]
    max_d = max(train_dates)
    age = np.array([(max_d - d).days / 365.0 for d in train_dates], dtype=float)
    sw = np.exp(-_RECENCY_DECAY * age) if _RECENCY_DECAY > 0 else None

    # v1 recomputed baseline (sanity vs cycle-18 anchor 4.6210).
    xgb1, lgb1, sc1, mlp1, wx1, wl1, wm1 = _train_blend(
        X_tr_v1, y_tr, X_val_v1, y_val, sw,
    )
    X_ho_v1_s = sc1.transform(X_ho_v1)
    pred_v1 = _predict_blend(X_ho_v1, X_ho_v1_s, xgb1, lgb1, mlp1, wx1, wl1, wm1)
    pred_v1 = np.clip(pred_v1, 0.0, None)
    mae_v1 = float(mean_absolute_error(y_ho, pred_v1))
    r2_v1 = float(r2_score(y_ho, pred_v1))

    # v2 with new opp features.
    xgb2, lgb2, sc2, mlp2, wx2, wl2, wm2 = _train_blend(
        X_tr_v2, y_tr, X_val_v2, y_val, sw,
    )
    X_ho_v2_s = sc2.transform(X_ho_v2)
    pred_v2 = _predict_blend(X_ho_v2, X_ho_v2_s, xgb2, lgb2, mlp2, wx2, wl2, wm2)
    pred_v2 = np.clip(pred_v2, 0.0, None)
    mae_v2 = float(mean_absolute_error(y_ho, pred_v2))
    r2_v2 = float(r2_score(y_ho, pred_v2))

    v1_info = {"mae": mae_v1, "r2": r2_v1, "w": (wx1, wl1, wm1)}
    v2_info = {"mae": mae_v2, "r2": r2_v2, "w": (wx2, wl2, wm2)}
    v2_artifacts = (xgb2, lgb2, sc2, mlp2, wx2, wl2, wm2)
    return v1_info, v2_info, v2_artifacts


def walk_forward_eval(rows: List[dict], n_splits: int = 4) -> List[dict]:
    """Walk-forward 4-fold MAE delta (v2 - v1) for PTS."""
    from sklearn.metrics import mean_absolute_error

    cols_v1 = feature_columns()
    cols_v2 = pts_v2_feature_columns()

    rows.sort(key=lambda r: r["date"])
    n = len(rows)
    X_v1 = _build_X(rows, cols_v1)
    X_v2 = _build_X(rows, cols_v2)
    y = np.array([float(r["target_pts"]) for r in rows], dtype=float)

    fold_ends = [(i + 1) / (n_splits + 1) for i in range(n_splits)]
    folds = []
    for fold_idx, train_end_frac in enumerate(fold_ends):
        tr_end = int(n * train_end_frac)
        if fold_idx == n_splits - 1:
            te_end = n
        else:
            te_end = int(n * fold_ends[fold_idx + 1])
        va_end = int(tr_end + (te_end - tr_end) * 0.4)
        if tr_end < 5000 or (te_end - va_end) < 2000:
            continue

        y_tr, y_val, y_ho = (y[:tr_end], y[tr_end:va_end], y[va_end:te_end])
        train_dates = [datetime.fromisoformat(rows[i]["date"]) for i in range(tr_end)]
        max_d = max(train_dates)
        age = np.array([(max_d - d).days / 365.0 for d in train_dates], dtype=float)
        sw = np.exp(-_RECENCY_DECAY * age) if _RECENCY_DECAY > 0 else None

        # v1
        xgb1, lgb1, sc1, mlp1, wx1, wl1, wm1 = _train_blend(
            X_v1[:tr_end], y_tr, X_v1[tr_end:va_end], y_val, sw,
        )
        X_ho1 = X_v1[va_end:te_end]
        pred_v1 = _predict_blend(X_ho1, sc1.transform(X_ho1),
                                 xgb1, lgb1, mlp1, wx1, wl1, wm1)
        mae_v1 = float(mean_absolute_error(y_ho, np.clip(pred_v1, 0.0, None)))

        # v2
        xgb2, lgb2, sc2, mlp2, wx2, wl2, wm2 = _train_blend(
            X_v2[:tr_end], y_tr, X_v2[tr_end:va_end], y_val, sw,
        )
        X_ho2 = X_v2[va_end:te_end]
        pred_v2 = _predict_blend(X_ho2, sc2.transform(X_ho2),
                                 xgb2, lgb2, mlp2, wx2, wl2, wm2)
        mae_v2 = float(mean_absolute_error(y_ho, np.clip(pred_v2, 0.0, None)))

        folds.append({
            "fold": fold_idx + 1,
            "n_tr": tr_end, "n_val": va_end - tr_end, "n_ho": te_end - va_end,
            "mae_v1": mae_v1, "mae_v2": mae_v2, "delta": mae_v2 - mae_v1,
        })
    return folds


# ── persistence ─────────────────────────────────────────────────────────────

def _persist_v2(xgb_m, lgb_m, scaler, mlp_m, w_xgb, w_lgb, w_mlp,
                mae_v2: float) -> dict:
    """Persist PTS v2 artifacts to data/models/pts_v2_*. Returns paths."""
    import joblib

    paths = {
        "xgb":        os.path.join(_MODEL_DIR, "pts_v2_xgb.json"),
        "lgb":        os.path.join(_MODEL_DIR, "pts_v2_lgb.pkl"),
        "mlp":        os.path.join(_MODEL_DIR, "pts_v2_mlp.pkl"),
        "mlp_scaler": os.path.join(_MODEL_DIR, "pts_v2_mlp_scaler.pkl"),
        "meta":       os.path.join(_MODEL_DIR, "pts_v2_meta.json"),
    }
    xgb_m.save_model(paths["xgb"])
    joblib.dump(lgb_m, paths["lgb"])
    joblib.dump(mlp_m, paths["mlp"])
    joblib.dump(scaler, paths["mlp_scaler"])
    meta = {
        "cycle": "100a",
        "feature_set": "baseline_85 + 16 opp_l5 (9 opp_team_<col>_l5 + 7 opp_def_<stat>_l5)",
        "n_features": int(len(pts_v2_feature_columns())),
        "new_keys":   list(_NEW_OPP_KEYS),
        "weights":    {"w_xgb": w_xgb, "w_lgb": w_lgb, "w_mlp": w_mlp},
        "holdout_mae": mae_v2,
    }
    with open(paths["meta"], "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)
    return paths


# ── main ────────────────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--splits", type=int, default=4)
    ap.add_argument("--write-anyway", action="store_true")
    args = ap.parse_args()

    print("[cycle 100a] PTS sqrt+Huber retrain v2 — 16 opp_l5 features", flush=True)
    print("=" * 72, flush=True)
    print("Loading pergame dataset...", flush=True)
    rows, _fc = build_pergame_dataset(min_prior=0)
    if not rows:
        print("REJECT: no rows built — gamelog cache empty.")
        return 1
    print(f"  rows={len(rows)}", flush=True)

    print("\nCoverage check (16 new opp_l5 keys, holdout slice):", flush=True)
    cov = _coverage_check(rows)
    coverage_fail = []
    for k in _NEW_OPP_KEYS:
        c = cov[f"{k}_holdout_cov"]
        print(f"  {k:30s} holdout {c:.4f}")
        if c < 0.80:
            coverage_fail.append((k, c))
    if coverage_fail:
        print("\nREJECT: coverage below 80% on:")
        for k, c in coverage_fail:
            print(f"  {k}: {c:.4f}")
        return 1

    print("\nSingle-split eval (65/15/20 chronological)...", flush=True)
    v1, v2, v2_art = single_split_eval(rows)
    delta_single = v2["mae"] - v1["mae"]
    print(f"  v1 (baseline 85-col recompute) MAE = {v1['mae']:.4f}  R2={v1['r2']:.4f}  "
          f"w=[{v1['w'][0]:.2f}/{v1['w'][1]:.2f}/{v1['w'][2]:.2f}]")
    print(f"  v2 (+16 opp_l5)              MAE = {v2['mae']:.4f}  R2={v2['r2']:.4f}  "
          f"w=[{v2['w'][0]:.2f}/{v2['w'][1]:.2f}/{v2['w'][2]:.2f}]")
    print(f"  single-split delta = {delta_single:+.4f}")
    anchor_pre_haircut = 4.6210
    anchor_post_haircut = 4.6104
    print(f"  vs cycle-18 PRE-haircut anchor {anchor_pre_haircut:.4f}: "
          f"d = {v2['mae'] - anchor_pre_haircut:+.4f}")
    print(f"  (post-haircut anchor {anchor_post_haircut:.4f} for reference)")

    print(f"\nWalk-forward eval ({args.splits} folds)...", flush=True)
    folds = walk_forward_eval(rows, n_splits=args.splits)
    if not folds:
        print("REJECT: no walk-forward folds produced.")
        return 1
    for f in folds:
        print(f"  fold {f['fold']}: tr={f['n_tr']} val={f['n_val']} ho={f['n_ho']}  "
              f"v1={f['mae_v1']:.4f}  v2={f['mae_v2']:.4f}  d={f['delta']:+.4f}")
    n_neg = sum(1 for f in folds if f["delta"] < 0.0)
    wf_mean = float(np.mean([f["delta"] for f in folds]))
    wf_std = float(np.std([f["delta"] for f in folds]))
    print(f"  WF mean delta = {wf_mean:+.4f} +- {wf_std:.4f}   "
          f"folds_negative = {n_neg}/{len(folds)}")

    # Ship gate: BOTH single-split < anchor AND 4/4 WF folds negative.
    single_ok = v2["mae"] < anchor_pre_haircut
    wf_ok = (n_neg == len(folds))
    print("\n" + "=" * 72)
    print(f"  single-split MAE < pre-haircut anchor ({anchor_pre_haircut:.4f}) ? "
          f"{single_ok}  ({v2['mae']:.4f} vs {anchor_pre_haircut:.4f})")
    print(f"  walk-forward {len(folds)}/{len(folds)} folds negative ? "
          f"{wf_ok}  ({n_neg}/{len(folds)})")
    print("=" * 72)

    metrics = {
        "cycle": "100a",
        "feature_set": "baseline_85 + 16 opp_l5",
        "n_features": int(len(pts_v2_feature_columns())),
        "new_keys": list(_NEW_OPP_KEYS),
        "coverage": cov,
        "single_split": {
            "mae_v1_recompute":  v1["mae"],
            "r2_v1_recompute":   v1["r2"],
            "mae_v2_new":        v2["mae"],
            "r2_v2_new":         v2["r2"],
            "delta":             delta_single,
            "anchor_pre_haircut":  anchor_pre_haircut,
            "anchor_post_haircut": anchor_post_haircut,
            "delta_vs_pre_anchor": v2["mae"] - anchor_pre_haircut,
            "weights_v2": {"w_xgb": v2["w"][0], "w_lgb": v2["w"][1],
                           "w_mlp": v2["w"][2]},
        },
        "walk_forward": {
            "folds": folds, "mean_delta": wf_mean, "std_delta": wf_std,
            "n_negative": n_neg, "n_folds": len(folds),
        },
        "ship_gate": {
            "single_split_ok": single_ok,
            "walk_forward_ok": wf_ok,
            "shipped":         (single_ok and wf_ok),
        },
    }
    meta_path = os.path.join(_MODEL_DIR, "pts_v2_metrics.json")
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(metrics, f, indent=2, default=str)
    print(f"Wrote metrics -> {meta_path}")

    if single_ok and wf_ok:
        xgb_m, lgb_m, scaler, mlp_m, wx, wl, wm = v2_art
        paths = _persist_v2(xgb_m, lgb_m, scaler, mlp_m, wx, wl, wm, v2["mae"])
        print(f"SHIP: wrote v2 artifacts ->")
        for k, p in paths.items():
            print(f"    {k:11s}: {p}")
        print("\nNext: wire prop_pergame.feature_columns(stat='pts') to append "
              "_NEW_OPP_KEYS, and update predict_pergame's blend dispatch to "
              "load pts_v2_* artifacts for stat='pts' (other stats unchanged).")
        return 0

    if args.write_anyway:
        xgb_m, lgb_m, scaler, mlp_m, wx, wl, wm = v2_art
        paths = _persist_v2(xgb_m, lgb_m, scaler, mlp_m, wx, wl, wm, v2["mae"])
        print(f"(--write-anyway) wrote v2 artifacts: {paths}")
    reason = []
    if not single_ok:
        reason.append(f"single d={delta_single:+.4f} (v2={v2['mae']:.4f})")
    if not wf_ok:
        reason.append(f"WF {n_neg}/{len(folds)} (mean {wf_mean:+.4f})")
    print(f"REJECT cycle 100a: {' | '.join(reason)}. Cycle-18 v1 stays in "
          f"production. New features remain available for future cycles.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
