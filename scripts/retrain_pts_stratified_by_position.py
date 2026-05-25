"""retrain_pts_stratified_by_position.py — cycle 104e (loop 5).

PTS sqrt+Huber STRATIFIED-by-position retrain. Mirrors cycle 102d's BLK probe
but applies to PTS — the highest-MAE stat (production 4.6104, pre-haircut
anchor 4.6210). PTS is sqrt+Huber XGB+LGB+MLP blend, not q50.

Hypothesis: PTS distribution properties differ from BLK (continuous, less
position-bimodal). Per-position stratification may work for PTS even though
it didn't for BLK (102d REJECT — Big bucket BLK is genuinely high-variance
bimodal).

Buckets (Big > Forward > Guard precedence; hyphen-tolerant):
  * Big      — "Center" in position  (C, C-F, F-C)
  * Forward  — "Forward" in pos, no "Center"   (F, F-G, G-F)
  * Guard    — "Guard"   in pos, no above      (G)
  * Unknown  — no position → falls back to existing global cycle-18 PTS heads.

Ship gate (BOTH):
  * single-split COMBINED dispatched PTS MAE strictly DOWN vs pre-haircut
    anchor 4.6210
  * walk-forward 4/4 folds negative (combined dispatched MAE < same-recipe
    global baseline on each fold)

If passing: persist data/models/pts_<bucket>_xgb.json + _lgb.pkl + _mlp.pkl
+ _mlp_scaler.pkl per bucket, plus pts_stratified_meta.json with NNLS weights.
Production wire-in (separate step): flip _USE_PTS_STRATIFIED = True with
graceful fallback to cycle-18 global heads on missing artifact / unknown pos.

Spec floor: any sub-bucket < 5000 training rows → REJECT preflight (sqrt+Huber
blend with 3 heads + NNLS needs more samples than q50).
"""
from __future__ import annotations

import json
import os
import sys
import time
import warnings
from datetime import datetime
from typing import Dict, List, Optional

import numpy as np

warnings.filterwarnings("ignore")

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from src.prediction.prop_pergame import (  # noqa: E402
    _MODEL_DIR, _RECENCY_DECAY, _SQRT_HUBER_STATS,
    build_pergame_dataset, feature_columns,
)


BASELINE_MAE = 4.6210          # cycle-18 sqrt+Huber pre-haircut anchor
BASELINE_POST_HAIRCUT = 4.6104
MIN_ROWS_PER_BUCKET = 5000     # spec floor — sqrt+Huber blend with 3 heads

BUCKET_BIG = "big"
BUCKET_FORWARD = "forward"
BUCKET_GUARD = "guard"
ALL_BUCKETS = (BUCKET_BIG, BUCKET_FORWARD, BUCKET_GUARD)
BUCKET_ARTIFACTS = {
    b: {
        "xgb":        f"pts_{b}_xgb.json",
        "lgb":        f"pts_{b}_lgb.pkl",
        "mlp":        f"pts_{b}_mlp.pkl",
        "mlp_scaler": f"pts_{b}_mlp_scaler.pkl",
    }
    for b in ALL_BUCKETS
}


def position_bucket(pos: Optional[str]) -> Optional[str]:
    if not pos:
        return None
    p = str(pos)
    if "Center" in p:
        return BUCKET_BIG
    if "Forward" in p:
        return BUCKET_FORWARD
    if "Guard" in p:
        return BUCKET_GUARD
    return None


def _pts_params() -> dict:
    """Mirror prop_pergame._STAT_PARAMS['pts']. DO NOT tune per spec."""
    return {
        "max_depth": 6, "min_child_weight": 20, "reg_lambda": 4.0,
        "gamma": 0.2, "n_estimators": 800, "learning_rate": 0.025,
        "subsample": 0.8, "colsample_bytree": 0.9, "reg_alpha": 2.0,
    }


def _inv_sqrt(v: np.ndarray) -> np.ndarray:
    return np.clip(v, 0.0, None) ** 2


def _build_X(rows: List[dict], cols: List[str]) -> np.ndarray:
    n = len(rows)
    X = np.zeros((n, len(cols)), dtype=float)
    for i, r in enumerate(rows):
        for j, c in enumerate(cols):
            v = r.get(c)
            X[i, j] = float(v) if v is not None else 0.0
    return X


def _bucket_counts(rows: List[dict]) -> Dict[str, int]:
    counts: Dict[str, int] = {b: 0 for b in ALL_BUCKETS}
    counts["unknown"] = 0
    for r in rows:
        b = position_bucket(r.get("position"))
        counts["unknown" if b is None else b] += 1
    return counts


def _train_blend(X_tr, y_tr, X_val, y_val, sw):
    """PTS sqrt+Huber 3-way blend (XGB+LGB+MLP) + NNLS. Mirrors cycle-18 recipe."""
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
    return np.clip(w_xgb * xgb_p + w_lgb * lgb_p + w_mlp * mlp_p, 0.0, None)


def _train_bucket_on_split(rows, cols, tr_idx, val_idx, bucket, sw_global):
    tr_b = [i for i in tr_idx if position_bucket(rows[i].get("position")) == bucket]
    val_b = [i for i in val_idx if position_bucket(rows[i].get("position")) == bucket]
    if len(tr_b) < MIN_ROWS_PER_BUCKET or len(val_b) < 200:
        return None, len(tr_b), len(val_b)
    X = _build_X([rows[i] for i in tr_b], cols)
    y = np.array([rows[i]["target_pts"] for i in tr_b], dtype=float)
    Xv = _build_X([rows[i] for i in val_b], cols)
    yv = np.array([rows[i]["target_pts"] for i in val_b], dtype=float)
    pos_lookup = {idx: pos for pos, idx in enumerate(tr_idx)}
    sw_b = np.array([sw_global[pos_lookup[i]] for i in tr_b], dtype=float)
    art = _train_blend(X, y, Xv, yv, sw_b)
    return art, len(tr_b), len(val_b)


def single_split_eval(rows: List[dict], cols: List[str],
                      holdout_frac: float = 0.20,
                      val_frac: float = 0.15) -> dict:
    from sklearn.metrics import mean_absolute_error

    rows = sorted(rows, key=lambda r: r["date"])
    n = len(rows)
    train_end = int(n * (1.0 - holdout_frac - val_frac))
    val_end = int(n * (1.0 - holdout_frac))

    y = np.array([float(r["target_pts"]) for r in rows], dtype=float)
    tr_idx = list(range(train_end))
    val_idx = list(range(train_end, val_end))
    ho_idx = list(range(val_end, n))

    train_dates = [datetime.fromisoformat(rows[i]["date"]) for i in tr_idx]
    max_d = max(train_dates)
    age = np.array([(max_d - d).days / 365.0 for d in train_dates], dtype=float)
    sw_global = np.exp(-_RECENCY_DECAY * age) if _RECENCY_DECAY > 0 else None

    # 1) Global baseline (same recipe).
    X_all = _build_X(rows, cols)
    g_art = _train_blend(X_all[:train_end], y[:train_end],
                         X_all[train_end:val_end], y[train_end:val_end], sw_global)
    gx, gl, gsc, gm, gwx, gwl, gwm = g_art
    pred_g = _predict_blend(X_all[val_end:], gsc.transform(X_all[val_end:]),
                            gx, gl, gm, gwx, gwl, gwm)
    mae_global = float(mean_absolute_error(y[val_end:], pred_g))

    # 2) Per-bucket models.
    per_bucket_meta: Dict[str, dict] = {}
    per_bucket_art: Dict[str, tuple] = {}
    for bucket in ALL_BUCKETS:
        art, n_tr, n_val = _train_bucket_on_split(
            rows, cols, tr_idx, val_idx, bucket, sw_global)
        per_bucket_meta[bucket] = {
            "n_train": n_tr, "n_val": n_val, "trained": art is not None,
            "skip_reason": None if art is not None else
                           f"n_train={n_tr} < {MIN_ROWS_PER_BUCKET}",
        }
        if art is not None:
            per_bucket_art[bucket] = art

    # 3) Dispatch holdout.
    ho_rows = [rows[i] for i in ho_idx]
    dispatched = np.zeros(len(ho_idx), dtype=float)
    dispatch_counts = {b: 0 for b in ALL_BUCKETS}
    dispatch_counts["fallback_global"] = 0
    bucket_ho_idx: Dict[str, List[int]] = {b: [] for b in ALL_BUCKETS}
    unknown_ho: List[int] = []
    for j, r in enumerate(ho_rows):
        b = position_bucket(r.get("position"))
        if b is None or b not in per_bucket_art:
            unknown_ho.append(j)
        else:
            bucket_ho_idx[b].append(j)

    for bucket, idx_list in bucket_ho_idx.items():
        if not idx_list or bucket not in per_bucket_art:
            continue
        bx, bl, bsc, bm, bwx, bwl, bwm = per_bucket_art[bucket]
        Xb = _build_X([ho_rows[j] for j in idx_list], cols)
        pred = _predict_blend(Xb, bsc.transform(Xb), bx, bl, bm, bwx, bwl, bwm)
        for k, j in enumerate(idx_list):
            dispatched[j] = pred[k]
        dispatch_counts[bucket] = len(idx_list)

    if unknown_ho:
        Xu = _build_X([ho_rows[j] for j in unknown_ho], cols)
        pred = _predict_blend(Xu, gsc.transform(Xu), gx, gl, gm, gwx, gwl, gwm)
        for k, j in enumerate(unknown_ho):
            dispatched[j] = pred[k]
        dispatch_counts["fallback_global"] = len(unknown_ho)

    y_ho = y[val_end:]
    mae_disp = float(mean_absolute_error(y_ho, dispatched))

    per_bucket_mae: Dict[str, Optional[float]] = {}
    for bucket in ALL_BUCKETS:
        if not bucket_ho_idx[bucket]:
            per_bucket_mae[bucket] = None
            continue
        y_b = np.array([y_ho[j] for j in bucket_ho_idx[bucket]], dtype=float)
        p_b = np.array([dispatched[j] for j in bucket_ho_idx[bucket]], dtype=float)
        per_bucket_mae[bucket] = float(mean_absolute_error(y_b, p_b))

    return {
        "n_rows": n, "n_train": train_end, "n_val": val_end - train_end,
        "n_holdout": n - val_end,
        "mae_global_baseline": mae_global,
        "mae_dispatched": mae_disp,
        "delta_mae": mae_disp - mae_global,
        "mae_vs_anchor": mae_disp - BASELINE_MAE,
        "per_bucket_train_meta": per_bucket_meta,
        "per_bucket_holdout_mae": per_bucket_mae,
        "dispatch_counts": dispatch_counts,
        "per_bucket_artifacts": per_bucket_art,
        "global_artifact": g_art,
    }


def walk_forward_eval(rows: List[dict], cols: List[str],
                      n_splits: int = 4) -> dict:
    from sklearn.metrics import mean_absolute_error

    rows = sorted(rows, key=lambda r: r["date"])
    n = len(rows)
    y = np.array([float(r["target_pts"]) for r in rows], dtype=float)
    X_all = _build_X(rows, cols)

    fold_ends = [(i + 1) / (n_splits + 1) for i in range(n_splits)]
    folds_metrics = []
    for fi, frac in enumerate(fold_ends):
        tr_end = int(n * frac)
        te_end = n if fi == n_splits - 1 else int(n * fold_ends[fi + 1])
        va_end = int(tr_end + (te_end - tr_end) * 0.4)
        if tr_end < 5000 or (te_end - va_end) < 2000:
            print(f"  fold {fi+1}: too small — skip", flush=True)
            continue
        tr_idx = list(range(tr_end))
        val_idx = list(range(tr_end, va_end))
        ho_idx = list(range(va_end, te_end))
        train_dates = [datetime.fromisoformat(rows[i]["date"]) for i in tr_idx]
        max_d = max(train_dates)
        age = np.array([(max_d - d).days / 365.0 for d in train_dates], dtype=float)
        sw_global = np.exp(-_RECENCY_DECAY * age) if _RECENCY_DECAY > 0 else None

        gx, gl, gsc, gm, gwx, gwl, gwm = _train_blend(
            X_all[:tr_end], y[:tr_end],
            X_all[tr_end:va_end], y[tr_end:va_end], sw_global)
        p_global = _predict_blend(X_all[va_end:te_end],
                                  gsc.transform(X_all[va_end:te_end]),
                                  gx, gl, gm, gwx, gwl, gwm)
        mae_base = float(mean_absolute_error(y[va_end:te_end], p_global))

        per_bucket_art: Dict[str, tuple] = {}
        bucket_train_meta = {}
        for bucket in ALL_BUCKETS:
            art, n_tr, n_val = _train_bucket_on_split(
                rows, cols, tr_idx, val_idx, bucket, sw_global)
            bucket_train_meta[bucket] = {"n_train": n_tr, "n_val": n_val,
                                         "trained": art is not None}
            if art is not None:
                per_bucket_art[bucket] = art

        ho_rows = [rows[i] for i in ho_idx]
        dispatched = np.zeros(len(ho_idx), dtype=float)
        bucket_ho_idx: Dict[str, List[int]] = {b: [] for b in ALL_BUCKETS}
        unknown_ho: List[int] = []
        for j, r in enumerate(ho_rows):
            b = position_bucket(r.get("position"))
            if b is None or b not in per_bucket_art:
                unknown_ho.append(j)
            else:
                bucket_ho_idx[b].append(j)
        for bucket, idx_list in bucket_ho_idx.items():
            if not idx_list or bucket not in per_bucket_art:
                continue
            bx, bl, bsc, bm, bwx, bwl, bwm = per_bucket_art[bucket]
            Xb = _build_X([ho_rows[j] for j in idx_list], cols)
            pred = _predict_blend(Xb, bsc.transform(Xb), bx, bl, bm, bwx, bwl, bwm)
            for k, j in enumerate(idx_list):
                dispatched[j] = pred[k]
        if unknown_ho:
            Xu = _build_X([ho_rows[j] for j in unknown_ho], cols)
            pred = _predict_blend(Xu, gsc.transform(Xu), gx, gl, gm, gwx, gwl, gwm)
            for k, j in enumerate(unknown_ho):
                dispatched[j] = pred[k]

        y_ho = y[va_end:te_end]
        mae_disp = float(mean_absolute_error(y_ho, dispatched))
        d = mae_disp - mae_base
        folds_metrics.append({"fold": fi + 1, "mae_base": mae_base,
                              "mae_dispatched": mae_disp, "delta_mae": d,
                              "bucket_train_meta": bucket_train_meta})
        print(f"  fold {fi+1}: base={mae_base:.4f}  disp={mae_disp:.4f}  d={d:+.4f}",
              flush=True)

    if not folds_metrics:
        return {"folds": [], "wf_4_of_4_negative": False}
    deltas = [f["delta_mae"] for f in folds_metrics]
    n_neg = int(sum(1 for d in deltas if d < 0))
    return {
        "folds": folds_metrics,
        "n_folds": len(folds_metrics),
        "n_folds_negative": n_neg,
        "wf_4_of_4_negative": (n_neg == len(folds_metrics) == 4),
        "delta_mae_mean": float(np.mean(deltas)),
        "delta_mae_std":  float(np.std(deltas)),
    }


def _persist_bucket(bucket: str, art: tuple, model_dir: str) -> dict:
    import joblib
    xgb_m, lgb_m, scaler, mlp_m, wx, wl, wm = art
    paths = {k: os.path.join(model_dir, fname)
             for k, fname in BUCKET_ARTIFACTS[bucket].items()}
    xgb_m.save_model(paths["xgb"])
    joblib.dump(lgb_m, paths["lgb"])
    joblib.dump(mlp_m, paths["mlp"])
    joblib.dump(scaler, paths["mlp_scaler"])
    return {**paths, "w_xgb": wx, "w_lgb": wl, "w_mlp": wm}


def main() -> int:
    t0 = time.time()
    print("[cycle 104e] PTS stratified-by-position sqrt+Huber retrain", flush=True)
    print("Building per-game dataset ...", flush=True)
    rows, _fc = build_pergame_dataset(min_prior=0)
    rows.sort(key=lambda r: r["date"])
    print(f"  rows={len(rows)} wall={time.time()-t0:.0f}s", flush=True)

    counts = _bucket_counts(rows)
    print(f"  bucket counts (all rows): {counts}", flush=True)

    train_floor_n = int(len(rows) * 0.65)
    train_counts = _bucket_counts(rows[:train_floor_n])
    print(f"  bucket counts (single-split train slice): {train_counts}", flush=True)
    os.makedirs(_MODEL_DIR, exist_ok=True)
    metrics_path = os.path.join(_MODEL_DIR, "pts_stratified_metrics.json")

    for bucket in ALL_BUCKETS:
        if train_counts[bucket] < MIN_ROWS_PER_BUCKET:
            reason = (f"bucket={bucket} has {train_counts[bucket]} train rows "
                      f"< floor {MIN_ROWS_PER_BUCKET}")
            print(f"REJECT (preflight): {reason}", flush=True)
            out = {
                "cycle": "104e", "ship": False, "reason": reason,
                "bucket_counts": counts,
                "train_bucket_counts": train_counts,
                "min_rows_per_bucket": MIN_ROWS_PER_BUCKET,
                "baseline_anchor": BASELINE_MAE,
            }
            with open(metrics_path, "w", encoding="utf-8") as f:
                json.dump(out, f, indent=2, default=str)
            return 0

    cols = feature_columns()
    print(f"  cols={len(cols)}", flush=True)

    print("Single-split eval ...", flush=True)
    ss = single_split_eval(rows, cols)
    print(f"  baseline (global sqrt+Huber): MAE={ss['mae_global_baseline']:.4f}",
          flush=True)
    print(f"  dispatched (stratified):      MAE={ss['mae_dispatched']:.4f}",
          flush=True)
    print(f"  delta (disp - base) = {ss['delta_mae']:+.4f}", flush=True)
    print(f"  vs cycle-18 anchor {BASELINE_MAE} = {ss['mae_vs_anchor']:+.4f}",
          flush=True)
    print(f"  per-bucket holdout MAE: {ss['per_bucket_holdout_mae']}", flush=True)
    print(f"  dispatch counts: {ss['dispatch_counts']}", flush=True)

    single_ok = ss["mae_dispatched"] < BASELINE_MAE
    print(f"  single_split_gate (MAE < {BASELINE_MAE}): "
          f"{'PASS' if single_ok else 'FAIL'}", flush=True)

    if not single_ok:
        out = {
            "cycle": "104e", "ship": False, "reason": "single_split_failed",
            "bucket_counts": counts,
            "train_bucket_counts": train_counts,
            "single_split": {k: v for k, v in ss.items()
                             if k not in ("per_bucket_artifacts", "global_artifact")},
            "baseline_anchor": BASELINE_MAE,
        }
        with open(metrics_path, "w", encoding="utf-8") as f:
            json.dump(out, f, indent=2, default=str)
        print(f"REJECT (single-split): wrote {metrics_path}", flush=True)
        return 0

    print("Walk-forward 4-fold ...", flush=True)
    wf = walk_forward_eval(rows, cols, n_splits=4)
    wf_ok = wf.get("wf_4_of_4_negative", False)
    print(f"  WF folds_negative={wf.get('n_folds_negative')}/{wf.get('n_folds')}  "
          f"d_mae={wf.get('delta_mae_mean'):+.4f}+-{wf.get('delta_mae_std'):.4f}",
          flush=True)
    print(f"  wf_gate (4/4 negative): {'PASS' if wf_ok else 'FAIL'}", flush=True)

    out = {
        "cycle": "104e",
        "ship": bool(single_ok and wf_ok),
        "bucket_counts": counts,
        "train_bucket_counts": train_counts,
        "single_split": {k: v for k, v in ss.items()
                         if k not in ("per_bucket_artifacts", "global_artifact")},
        "walk_forward": wf,
        "baseline_anchor": BASELINE_MAE,
        "baseline_post_haircut": BASELINE_POST_HAIRCUT,
    }

    if single_ok and wf_ok:
        artifacts = {}
        for bucket, art in ss["per_bucket_artifacts"].items():
            artifacts[bucket] = _persist_bucket(bucket, art, _MODEL_DIR)
        out["artifacts"] = artifacts
        print(f"SHIP MAE={ss['mae_dispatched']:.4f}: wrote artifacts for "
              f"{list(artifacts.keys())}", flush=True)
        print("Next: set _USE_PTS_STRATIFIED = True in prop_pergame.py.",
              flush=True)
    else:
        out["reason"] = "wf_failed" if single_ok else "single_split_failed"
        print(f"REJECT: single_split={single_ok} wf={wf_ok}", flush=True)

    with open(metrics_path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, default=str)
    print(f"Wrote {metrics_path}  wall={time.time()-t0:.0f}s", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
