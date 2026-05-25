"""retrain_blk_stratified_by_position.py — cycle 102d (loop 5).

BLK LGB-q50 STRATIFIED-by-position retrain. Background:

Cycles 97b (flat center scale), 98b (opp-conditional center scale), 99a/100b/
101b (BLK retrain with position one-hot baked into the SHARED model) all
REJECTED. The lesson: position interactions don't show through a SHARED model
because the loss is dominated by the bulk of the data (Guards/Forwards) and the
Centers' very different distribution is averaged out.

Natural alternative: train SEPARATE LGB-q50 models per position bucket, then
dispatch by position at inference. Per cycle 96e:
  * (C, blk)   MAE = 0.8154 = 1.854x global (n=2882) — far the worst bucket
  * (F, blk)   MAE = 0.5000 = 1.137x global (n=6957)
  * (G, blk)   MAE = 0.2914 = 0.663x global (n=10125)

Buckets used (coarse, hybrid-friendly):
  * "Big":     position contains "Center"   (C, C-F, F-C)
  * "Forward": position contains "Forward"  but NOT "Center" (pure F, F-G, G-F)
  * "Guard":   position contains "Guard"    but NOT "Forward" and NOT "Center"
  * "Unknown": no position (~0% on 2024-25 holdout per cycle 96e — falls back
               to the existing cycle-29 global LGB-q50 model at inference).

Per spec, HYPERPARAMETERS stay identical to cycle 27/29 — this cycle is purely
a stratification experiment. NO new features, no HP tuning.

Cycle 27 baseline (XGB-q50 on the 85-col global feature set):
    BLK holdout MAE = 0.4398 (canonical anchor).

Ship gate (BOTH required):
  * single-split COMBINED BLK MAE strictly DOWN (< 0.4398) when dispatching
    by position
  * walk-forward 4/4 folds positive on COMBINED holdout (not per-bucket —
    combined matters for production dispatch)

When passing: persist as data/models/blk_q50_big.pkl, blk_q50_forward.pkl,
blk_q50_guard.pkl + metrics JSON. Production wire-in: flip
_USE_BLK_STRATIFIED = True in prop_pergame.py with graceful fallback to the
existing global model when any bucket artifact is missing or position is
unknown.

Reject when single-split or WF fails: write metrics JSON with reason but no
.pkl files (back-compat preserved).

Coordination:
  * Sibling to cycles 101b/c/d/f — those tested feature-set retrains, all
    REJECTed. This cycle changes MODEL STRUCTURE not features.
  * Does NOT touch any other stat's heads.
  * Does NOT modify the global blk_q50 model (preserved as fallback).
"""
from __future__ import annotations

import json
import os
import sys
import time
import warnings
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import numpy as np

warnings.filterwarnings("ignore")

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from src.prediction.prop_pergame import (  # noqa: E402
    _LOG_TRANSFORM_STATS, build_pergame_dataset, feature_columns,
)


MODEL_DIR = os.path.join(PROJECT_DIR, "data", "models")
BASELINE_MAE = 0.4398          # cycle 27 (XGB-q50) reference anchor
MIN_ROWS_PER_BUCKET = 1000     # spec floor — q50 fit too unstable below this

# Position buckets — coarse, hyphen-tolerant. Order matters for dispatch
# precedence (Big > Forward > Guard) so a "C-F" row goes to Big.
BUCKET_BIG = "big"
BUCKET_FORWARD = "forward"
BUCKET_GUARD = "guard"
ALL_BUCKETS = (BUCKET_BIG, BUCKET_FORWARD, BUCKET_GUARD)
BUCKET_ARTIFACT = {
    BUCKET_BIG:     "blk_q50_big.pkl",
    BUCKET_FORWARD: "blk_q50_forward.pkl",
    BUCKET_GUARD:   "blk_q50_guard.pkl",
}


def position_bucket(pos: Optional[str]) -> Optional[str]:
    """Map a raw position string to one of {big, forward, guard, None}.

    Precedence ensures hybrid positions get exactly one bucket:
      * Any "Center" component  -> "big"        (C, C-F, F-C)
      * Else any "Forward"      -> "forward"    (pure F, F-G, G-F)
      * Else any "Guard"        -> "guard"      (pure G)
      * Empty / unknown         -> None         (caller dispatches to global)
    """
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


def _blk_params() -> dict:
    """Match prop_quantiles._per_stat_xgb_params('blk') — DO NOT tune per spec."""
    return dict(n_estimators=800, max_depth=3, learning_rate=0.06,
                subsample=0.8, colsample_bytree=1.0,
                min_child_weight=25, reg_lambda=4.0, reg_alpha=0.5,
                gamma=0.4, random_state=42)


def _train_lgb_q50(X_tr, yt_tr, X_val, yt_val, sw):
    import lightgbm as lgb
    p = _blk_params()
    m = lgb.LGBMRegressor(
        n_estimators=p["n_estimators"], max_depth=p["max_depth"],
        learning_rate=p["learning_rate"],
        subsample=p["subsample"], subsample_freq=1,
        colsample_bytree=p["colsample_bytree"],
        min_child_samples=max(20, p["min_child_weight"] * 2),
        reg_lambda=p["reg_lambda"], reg_alpha=p["reg_alpha"],
        random_state=42, objective="quantile", alpha=0.5,
        n_jobs=-1, verbosity=-1,
    )
    m.fit(X_tr, yt_tr, eval_set=[(X_val, yt_val)],
          sample_weight=sw,
          callbacks=[lgb.early_stopping(40, verbose=False)])
    return m


def _build_X(rows: List[dict], cols: List[str]) -> np.ndarray:
    return np.array([[float(r.get(c, 0.0) or 0.0) for c in cols] for r in rows],
                    dtype=float)


def _bucket_counts(rows: List[dict]) -> Dict[str, int]:
    counts: Dict[str, int] = {b: 0 for b in ALL_BUCKETS}
    counts["unknown"] = 0
    for r in rows:
        b = position_bucket(r.get("position"))
        if b is None:
            counts["unknown"] += 1
        else:
            counts[b] += 1
    return counts


def _bucket_indices(rows: List[dict], bucket: str) -> List[int]:
    return [i for i, r in enumerate(rows) if position_bucket(r.get("position")) == bucket]


def _train_bucket_on_split(rows: List[dict], cols: List[str],
                           tr_idx_global: List[int],
                           val_idx_global: List[int],
                           bucket: str,
                           sw_global: np.ndarray):
    """Train one bucket's LGB-q50 on the slice of (tr+val) belonging to it.

    Returns (model, n_bucket_train, n_bucket_val) or (None, 0, 0) when there
    aren't enough rows.
    """
    tr_b = [i for i in tr_idx_global if position_bucket(rows[i].get("position")) == bucket]
    val_b = [i for i in val_idx_global if position_bucket(rows[i].get("position")) == bucket]
    if len(tr_b) < MIN_ROWS_PER_BUCKET or len(val_b) < 50:
        return None, len(tr_b), len(val_b)
    X = _build_X([rows[i] for i in tr_b], cols)
    y = np.array([rows[i]["target_blk"] for i in tr_b], dtype=float)
    Xv = _build_X([rows[i] for i in val_b], cols)
    yv = np.array([rows[i]["target_blk"] for i in val_b], dtype=float)
    assert "blk" in _LOG_TRANSFORM_STATS
    yt = np.log1p(y)
    ytv = np.log1p(yv)
    # Subset the recency weights to the bucket's training rows. sw_global is
    # already in chronological order matching tr_idx_global; pick out by
    # position within tr_idx_global.
    pos_lookup = {idx: pos for pos, idx in enumerate(tr_idx_global)}
    sw_b = np.array([sw_global[pos_lookup[i]] for i in tr_b], dtype=float)
    m = _train_lgb_q50(X, yt, Xv, ytv, sw_b)
    return m, len(tr_b), len(val_b)


def single_split_eval(rows: List[dict],
                      cols: List[str],
                      holdout_frac: float = 0.2,
                      val_frac: float = 0.15) -> dict:
    """Train per-bucket LGB-q50 + global LGB-q50, then evaluate by dispatching
    each holdout row to its bucket's model (or the global model when bucket
    has no fit or position is unknown). Compare to a same-recipe baseline
    GLOBAL LGB-q50 trained on the same train slice."""
    from sklearn.metrics import mean_absolute_error

    rows = sorted(rows, key=lambda r: r["date"])
    n = len(rows)
    train_end = int(n * (1.0 - holdout_frac - val_frac))
    val_end = int(n * (1.0 - holdout_frac))

    y = np.array([r["target_blk"] for r in rows], dtype=float)
    yt = np.log1p(y)

    tr_idx = list(range(train_end))
    val_idx = list(range(train_end, val_end))
    ho_idx = list(range(val_end, n))

    # Recency weights (mirror production train_quantile_models).
    train_dates = [datetime.fromisoformat(rows[i]["date"]) for i in tr_idx]
    max_d = max(train_dates)
    age = np.array([(max_d - d).days / 365.0 for d in train_dates], dtype=float)
    sw_global = np.exp(-0.5 * age)

    # 1) GLOBAL baseline — same recipe, all rows.
    X_all = _build_X(rows, cols)
    m_global = _train_lgb_q50(
        X_all[:train_end], yt[:train_end],
        X_all[train_end:val_end], yt[train_end:val_end], sw_global)
    base_pred = np.clip(np.expm1(m_global.predict(X_all[val_end:])), 0.0, None)
    mae_global = float(mean_absolute_error(y[val_end:], base_pred))

    # 2) Per-bucket models.
    per_bucket_meta: Dict[str, dict] = {}
    per_bucket_models: Dict[str, object] = {}
    for bucket in ALL_BUCKETS:
        mdl, n_tr, n_val = _train_bucket_on_split(
            rows, cols, tr_idx, val_idx, bucket, sw_global)
        per_bucket_meta[bucket] = {
            "n_train": n_tr, "n_val": n_val,
            "trained": mdl is not None,
            "skip_reason": None if mdl is not None else
                           f"n_train={n_tr} < {MIN_ROWS_PER_BUCKET}",
        }
        if mdl is not None:
            per_bucket_models[bucket] = mdl

    # 3) Dispatch over holdout: per-row pick bucket model, else global.
    dispatched = np.zeros(len(ho_idx), dtype=float)
    dispatch_counts = {b: 0 for b in ALL_BUCKETS}
    dispatch_counts["fallback_global"] = 0

    # Build per-bucket holdout X and predictions in batch (faster than per-row).
    ho_rows = [rows[i] for i in ho_idx]
    bucket_ho_idx: Dict[str, List[int]] = {b: [] for b in ALL_BUCKETS}
    unknown_ho_idx: List[int] = []
    for j, r in enumerate(ho_rows):
        b = position_bucket(r.get("position"))
        if b is None or b not in per_bucket_models:
            unknown_ho_idx.append(j)
        else:
            bucket_ho_idx[b].append(j)

    for bucket, idx_list in bucket_ho_idx.items():
        if not idx_list or bucket not in per_bucket_models:
            continue
        Xb = _build_X([ho_rows[j] for j in idx_list], cols)
        pred_t = per_bucket_models[bucket].predict(Xb)
        pred = np.clip(np.expm1(pred_t), 0.0, None)
        for k, j in enumerate(idx_list):
            dispatched[j] = pred[k]
        dispatch_counts[bucket] = len(idx_list)

    if unknown_ho_idx:
        Xu = _build_X([ho_rows[j] for j in unknown_ho_idx], cols)
        pred_t = m_global.predict(Xu)
        pred = np.clip(np.expm1(pred_t), 0.0, None)
        for k, j in enumerate(unknown_ho_idx):
            dispatched[j] = pred[k]
        dispatch_counts["fallback_global"] = len(unknown_ho_idx)

    y_ho = y[val_end:]
    mae_dispatched = float(mean_absolute_error(y_ho, dispatched))

    # 4) Per-bucket MAE on holdout slice for diagnostics.
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
        "mae_dispatched":      mae_dispatched,
        "delta_mae":           mae_dispatched - mae_global,
        "mae_vs_cycle27":      mae_dispatched - BASELINE_MAE,
        "per_bucket_train_meta": per_bucket_meta,
        "per_bucket_holdout_mae": per_bucket_mae,
        "dispatch_counts": dispatch_counts,
        "per_bucket_models": per_bucket_models,
        "global_model": m_global,
    }


def walk_forward_eval(rows: List[dict],
                      cols: List[str],
                      n_splits: int = 4) -> dict:
    """4-fold walk-forward — COMBINED dispatched BLK MAE vs same-recipe global.
    Per-fold metrics record per-bucket counts but the ship gate evaluates the
    COMBINED holdout (matches production behaviour)."""
    from sklearn.metrics import mean_absolute_error

    rows = sorted(rows, key=lambda r: r["date"])
    n = len(rows)
    y = np.array([r["target_blk"] for r in rows], dtype=float)
    yt = np.log1p(y)
    X_all = _build_X(rows, cols)

    fold_ends = [(i + 1) / (n_splits + 1) for i in range(n_splits)]
    folds_metrics = []
    for fi, frac in enumerate(fold_ends):
        tr_end = int(n * frac)
        te_end = n if fi == n_splits - 1 else int(n * fold_ends[fi + 1])
        va_end = int(tr_end + (te_end - tr_end) * 0.4)
        if tr_end < 5000 or (te_end - va_end) < 2000:
            print(f"  fold {fi+1}: too small (tr={tr_end}, ho={te_end-va_end}) — skip",
                  flush=True)
            continue
        tr_idx = list(range(tr_end))
        val_idx = list(range(tr_end, va_end))
        ho_idx = list(range(va_end, te_end))
        train_dates = [datetime.fromisoformat(rows[i]["date"]) for i in tr_idx]
        max_d = max(train_dates)
        age = np.array([(max_d - d).days / 365.0 for d in train_dates], dtype=float)
        sw_global = np.exp(-0.5 * age)

        # Global baseline
        m_global = _train_lgb_q50(
            X_all[:tr_end], yt[:tr_end],
            X_all[tr_end:va_end], yt[tr_end:va_end], sw_global)
        p_global = np.clip(np.expm1(m_global.predict(X_all[va_end:te_end])), 0.0, None)
        mae_base = float(mean_absolute_error(y[va_end:te_end], p_global))

        # Per-bucket
        per_bucket_models: Dict[str, object] = {}
        bucket_train_meta = {}
        for bucket in ALL_BUCKETS:
            mdl, n_tr, n_val = _train_bucket_on_split(
                rows, cols, tr_idx, val_idx, bucket, sw_global)
            bucket_train_meta[bucket] = {"n_train": n_tr, "n_val": n_val,
                                         "trained": mdl is not None}
            if mdl is not None:
                per_bucket_models[bucket] = mdl

        ho_rows = [rows[i] for i in ho_idx]
        dispatched = np.zeros(len(ho_idx), dtype=float)
        bucket_ho_idx: Dict[str, List[int]] = {b: [] for b in ALL_BUCKETS}
        unknown_ho_idx: List[int] = []
        for j, r in enumerate(ho_rows):
            b = position_bucket(r.get("position"))
            if b is None or b not in per_bucket_models:
                unknown_ho_idx.append(j)
            else:
                bucket_ho_idx[b].append(j)

        for bucket, idx_list in bucket_ho_idx.items():
            if not idx_list or bucket not in per_bucket_models:
                continue
            Xb = _build_X([ho_rows[j] for j in idx_list], cols)
            pred_t = per_bucket_models[bucket].predict(Xb)
            pred = np.clip(np.expm1(pred_t), 0.0, None)
            for k, j in enumerate(idx_list):
                dispatched[j] = pred[k]
        if unknown_ho_idx:
            Xu = _build_X([ho_rows[j] for j in unknown_ho_idx], cols)
            pred_t = m_global.predict(Xu)
            pred = np.clip(np.expm1(pred_t), 0.0, None)
            for k, j in enumerate(unknown_ho_idx):
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


def main() -> int:
    t0 = time.time()
    print("[cycle 102d] BLK stratified-by-position LGB-q50 retrain", flush=True)

    print("Building per-game dataset ...", flush=True)
    rows, _fc = build_pergame_dataset(min_prior=0)
    rows.sort(key=lambda r: r["date"])
    print(f"  rows={len(rows)} wall={time.time()-t0:.0f}s", flush=True)

    counts = _bucket_counts(rows)
    print(f"  bucket counts (all rows): {counts}", flush=True)

    # Spec floor: any sub-bucket below 1000 rows in TRAIN portion -> reject.
    # Approximate the train portion as 65% of rows for the upfront sanity check
    # (single_split uses train_frac = 1 - 0.20 - 0.15 = 0.65).
    train_floor_n = int(len(rows) * 0.65)
    train_slice = rows[:train_floor_n]
    train_counts = _bucket_counts(train_slice)
    print(f"  bucket counts (single-split train slice): {train_counts}",
          flush=True)
    for bucket in ALL_BUCKETS:
        if train_counts[bucket] < MIN_ROWS_PER_BUCKET:
            reason = (f"bucket={bucket} has {train_counts[bucket]} train rows "
                      f"< floor {MIN_ROWS_PER_BUCKET}")
            print(f"REJECT (preflight): {reason}", flush=True)
            out = {
                "cycle": "102d", "ship": False,
                "reason": reason,
                "bucket_counts": counts,
                "train_bucket_counts": train_counts,
                "min_rows_per_bucket": MIN_ROWS_PER_BUCKET,
                "baseline_cycle27": BASELINE_MAE,
            }
            os.makedirs(MODEL_DIR, exist_ok=True)
            path = os.path.join(MODEL_DIR, "blk_q50_stratified_metrics.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump(out, f, indent=2, default=str)
            return 0

    cols = feature_columns()
    print(f"  cols={len(cols)}", flush=True)

    print("Single-split eval ...", flush=True)
    ss = single_split_eval(rows, cols)
    print(f"  baseline (global LGB-q50): MAE={ss['mae_global_baseline']:.4f}",
          flush=True)
    print(f"  dispatched (stratified):   MAE={ss['mae_dispatched']:.4f}",
          flush=True)
    print(f"  delta_mae (disp - base) = {ss['delta_mae']:+.4f}", flush=True)
    print(f"  delta_mae vs cycle27 anchor {BASELINE_MAE} = "
          f"{ss['mae_vs_cycle27']:+.4f}", flush=True)
    print(f"  per-bucket holdout MAE: {ss['per_bucket_holdout_mae']}",
          flush=True)
    print(f"  dispatch counts: {ss['dispatch_counts']}", flush=True)

    single_split_pass = ss["mae_dispatched"] < BASELINE_MAE
    print(f"  single_split_gate (MAE < {BASELINE_MAE}): "
          f"{'PASS' if single_split_pass else 'FAIL'}", flush=True)

    if not single_split_pass:
        out = {
            "cycle": "102d", "ship": False,
            "reason": "single_split_failed",
            "bucket_counts": counts,
            "train_bucket_counts": train_counts,
            "single_split": {k: v for k, v in ss.items()
                             if k not in ("per_bucket_models", "global_model")},
            "baseline_cycle27": BASELINE_MAE,
        }
        os.makedirs(MODEL_DIR, exist_ok=True)
        path = os.path.join(MODEL_DIR, "blk_q50_stratified_metrics.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(out, f, indent=2, default=str)
        print(f"REJECT (single-split): wrote {path}", flush=True)
        return 0

    print("Walk-forward 4-fold ...", flush=True)
    wf = walk_forward_eval(rows, cols, n_splits=4)
    wf_pass = wf.get("wf_4_of_4_negative", False)
    print(f"  WF folds_negative={wf.get('n_folds_negative')}/{wf.get('n_folds')}  "
          f"d_mae={wf.get('delta_mae_mean'):+.4f}+-{wf.get('delta_mae_std'):.4f}",
          flush=True)
    print(f"  wf_gate (4/4 folds negative): {'PASS' if wf_pass else 'FAIL'}",
          flush=True)

    out = {
        "cycle": "102d",
        "ship": bool(single_split_pass and wf_pass),
        "bucket_counts": counts,
        "train_bucket_counts": train_counts,
        "single_split": {k: v for k, v in ss.items()
                         if k not in ("per_bucket_models", "global_model")},
        "walk_forward": wf,
        "baseline_cycle27": BASELINE_MAE,
    }

    if single_split_pass and wf_pass:
        import joblib
        os.makedirs(MODEL_DIR, exist_ok=True)
        artifact_paths = {}
        for bucket, mdl in ss["per_bucket_models"].items():
            path = os.path.join(MODEL_DIR, BUCKET_ARTIFACT[bucket])
            joblib.dump(mdl, path)
            artifact_paths[bucket] = path
        out["artifacts"] = artifact_paths
        print(f"SHIP MAE={ss['mae_dispatched']:.4f}: wrote {artifact_paths}",
              flush=True)
        print("Next step: set _USE_BLK_STRATIFIED = True in prop_pergame.py.",
              flush=True)
    else:
        out["reason"] = "wf_failed" if single_split_pass else "single_split_failed"
        print(f"REJECT: single_split={single_split_pass} wf={wf_pass}", flush=True)

    path = os.path.join(MODEL_DIR, "blk_q50_stratified_metrics.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, default=str)
    print(f"Wrote {path}  wall={time.time()-t0:.0f}s", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
