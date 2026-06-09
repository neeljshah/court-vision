"""cache_pergame_oof_faithful.py — FAITHFUL per-row OOF that mirrors the
SERVED predict_pergame dispatch (PREDICTION_FIDELITY plumbing fix, 2026-06-04).

Why this exists
---------------
The legacy OOF builder (scripts/cache_pergame_oof.py) records the 3-way NNLS
BLEND for ALL 7 stats. But production src.prediction.prop_pergame.predict_pergame
serves the **q50 median** for _USE_Q50_STATS = {reb, fg3m, stl, blk, tov}
(pts/ast stay on the blend), then applies the garbage-time haircut (pts/reb/ast)
and the R3-F residual heads (reb/ast/fg3m/stl/blk/tov). So for 5 of 7 stats the
legacy OOF VALIDATES a different model than we SERVE. The fidelity audit
(docs/_audits/PREDICTION_FIDELITY.md) showed direction transfers (corr 0.93-0.98)
but the level/point-MAE does not — blend-OOF gains do not reliably reach the
served q50 head.

What this does
--------------
For each WF fold it trains the per-stat SERVED head and records the SERVED
prediction (matching predict_pergame's dispatch exactly):

  * pts, ast (NOT in _USE_Q50_STATS): 3-way XGB+LGB+MLP NNLS blend  (served_head='blend')
  * reb, fg3m, stl, blk, tov (in _USE_Q50_STATS): q50 quantile head  (served_head='q50')
      - reb uses the LGB-q50 backend (matches _Q50_LGB_BACKEND_STATS)
      - the rest use the XGB-q50 backend
      - q50 HPs mirror prop_quantiles._per_stat_xgb_params + the
        reg:quantileerror / objective='quantile' alpha=0.5 recipe

then, on the raw-count point estimate, applies (identical order to predict_pergame):
  1. apply_garbage_time_haircut(pred, stat, home_spread)   [pts/reb/ast only]
  2. apply_residual_correction(pred, feature_row, stat)     [reb/ast/fg3m/stl/blk/tov]

Feature space: trains on the FROZEN served 85-col aligned order
(feature_columns_for(stat)[:85]) — the same column set + order the production
artifacts were trained on (props_pergame_metrics.json["feature_cols"]). The
legacy OOF trained on 129/132 cols, which the served 85-feature artifacts never
saw — another fidelity gap closed here.

Walk-forward integrity is unchanged from the legacy builder: oof_pred for a row
uses ONLY rows strictly before it for training.

Output
------
data/cache/pregame_oof_faithful.parquet (NEW file — does NOT overwrite
pregame_oof.parquet). Schema = legacy schema + a `served_head` column. When
--with-old-blend is set (default), also records `oof_pred_oldblend` (the legacy
3-way blend on the SAME 85-col feature space) so OLD-vs-FAITHFUL re-baselining
is computed on identical rows in one pass.

    game_id            str
    player_id          int
    stat               str    (one of STATS)
    oof_pred           float  (SERVED head, raw-count, + haircut + residual)
    oof_pred_oldblend  float  (legacy 3-way blend, raw-count; NaN if --no-old-blend)
    actual             float  (realised box score)
    game_date          str    (ISO date)
    fold               int    (1-indexed WF fold)
    season             str
    served_head        str    ('q50' | 'blend')

Usage
-----
    # Fast dev run (first N rows)
    python scripts/cache_pergame_oof_faithful.py --max-rows 8000
    # Full run (background, ~45-90 min)
    python scripts/cache_pergame_oof_faithful.py
"""
from __future__ import annotations

import argparse
import os
import sys
import time
import warnings
from datetime import datetime
from typing import Dict, List, Optional, Tuple

warnings.filterwarnings("ignore")

import numpy as np

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from src.prediction.prop_pergame import (  # noqa: E402
    STATS, build_pergame_dataset, feature_columns_for,
    _USE_Q50_STATS, _Q50_LGB_BACKEND_STATS,
    _LOG_TRANSFORM_STATS, _SQRT_HUBER_STATS,
    _MLPSeedEnsemble,
    apply_garbage_time_haircut,
)
from src.prediction.pregame_residual_heads import apply_residual_correction  # noqa: E402
from src.prediction.prop_quantiles import _per_stat_xgb_params  # noqa: E402

_OUT_PATH = os.path.join(PROJECT_DIR, "data", "cache", "pregame_oof_faithful.parquet")
_MODEL_DIR = os.path.join(PROJECT_DIR, "data", "models")
_N_SPLITS = 4
_SERVED_N_FEATURES = 85  # production base/q50/quantile artifacts are 85-feature


# ── label transforms (mirror prop_pergame / prop_quantiles) ───────────────────

def _fwd(stat: str, y: np.ndarray) -> np.ndarray:
    if stat in _SQRT_HUBER_STATS:
        return np.sqrt(np.maximum(y, 0.0))
    if stat in _LOG_TRANSFORM_STATS:
        return np.log1p(np.maximum(y, 0.0))
    return y


def _inv(stat: str, v: np.ndarray) -> np.ndarray:
    if stat in _SQRT_HUBER_STATS:
        return np.square(np.maximum(v, 0.0))
    if stat in _LOG_TRANSFORM_STATS:
        return np.expm1(np.maximum(v, 0.0))
    return np.maximum(v, 0.0)


# ── served-head trainers ──────────────────────────────────────────────────────

def _train_blend(
    stat: str,
    X_tr: np.ndarray, y_tr: np.ndarray,
    X_val: np.ndarray, y_val: np.ndarray,
    X_ho: np.ndarray,
    sw: np.ndarray,
) -> np.ndarray:
    """3-way XGB+LGB+MLP NNLS blend (raw-count). Mirrors the legacy OOF builder
    and the cycle-23 production blend that predict_pergame serves for pts/ast."""
    import xgboost as xgb
    import lightgbm as lgb
    from sklearn.preprocessing import StandardScaler
    from sklearn.linear_model import LinearRegression

    is_count = stat in ("stl", "blk")
    use_log = stat in _LOG_TRANSFORM_STATS
    use_sqrt_huber = stat in _SQRT_HUBER_STATS

    if use_sqrt_huber:
        xgb_obj, lgb_obj = "reg:pseudohubererror", "huber"
    elif use_log or is_count is False:
        xgb_obj, lgb_obj = "reg:squarederror", "regression"
    else:
        xgb_obj, lgb_obj = "count:poisson", "poisson"
    if use_log:
        xgb_obj, lgb_obj = "reg:squarederror", "regression"

    depth = 3 if is_count else 4
    y_tr_t, y_val_t = _fwd(stat, y_tr), _fwd(stat, y_val)

    xgb_m = xgb.XGBRegressor(
        n_estimators=600, max_depth=depth, learning_rate=0.04,
        subsample=0.8, colsample_bytree=0.8, min_child_weight=10,
        reg_lambda=2.0, reg_alpha=0.5, gamma=0.2, random_state=42,
        objective=xgb_obj, early_stopping_rounds=40, eval_metric="mae",
    )
    xgb_m.fit(X_tr, y_tr_t, eval_set=[(X_val, y_val_t)], sample_weight=sw, verbose=False)

    lgb_m = lgb.LGBMRegressor(
        n_estimators=600, max_depth=depth, learning_rate=0.04,
        subsample=0.8, subsample_freq=1, colsample_bytree=0.8,
        min_child_samples=20, reg_lambda=2.0, reg_alpha=0.5,
        random_state=42, objective=lgb_obj, n_jobs=-1, verbosity=-1,
    )
    lgb_m.fit(X_tr, y_tr_t, eval_set=[(X_val, y_val_t)], sample_weight=sw,
              callbacks=[lgb.early_stopping(40, verbose=False)])

    sc = StandardScaler()
    X_tr_s, X_val_s, X_ho_s = sc.fit_transform(X_tr), sc.transform(X_val), sc.transform(X_ho)
    mlp_m = _MLPSeedEnsemble().fit(X_tr_s, y_tr_t)

    xv = _inv(stat, xgb_m.predict(X_val))
    lv = _inv(stat, lgb_m.predict(X_val))
    mv = _inv(stat, mlp_m.predict(X_val_s))
    st = LinearRegression(positive=True, fit_intercept=False)
    st.fit(np.column_stack([xv, lv, mv]), y_val)
    w = st.coef_
    if not (0.5 <= w.sum() <= 1.5):
        w = np.array([1.0 / 3.0, 1.0 / 3.0, 1.0 / 3.0])

    xh = _inv(stat, xgb_m.predict(X_ho))
    lh = _inv(stat, lgb_m.predict(X_ho))
    mh = _inv(stat, mlp_m.predict(X_ho_s))
    return np.maximum(w[0] * xh + w[1] * lh + w[2] * mh, 0.0)


def _train_q50(
    stat: str,
    X_tr: np.ndarray, y_tr: np.ndarray,
    X_val: np.ndarray, y_val: np.ndarray,
    X_ho: np.ndarray,
    sw: np.ndarray,
) -> np.ndarray:
    """q=0.5 quantile head (raw-count). Mirrors prop_quantiles.train_quantile_models'
    q50 recipe + _load_q50_model's backend dispatch (LGB for reb, XGB otherwise)
    — i.e. exactly the head predict_pergame serves for _USE_Q50_STATS."""
    import xgboost as xgb
    import lightgbm as lgb

    params = _per_stat_xgb_params(stat)
    y_tr_t, y_val_t = _fwd(stat, y_tr), _fwd(stat, y_val)

    if stat in _Q50_LGB_BACKEND_STATS:
        lgb_m = lgb.LGBMRegressor(
            n_estimators=params["n_estimators"], max_depth=params["max_depth"],
            learning_rate=params["learning_rate"],
            subsample=params["subsample"], subsample_freq=1,
            colsample_bytree=params["colsample_bytree"],
            min_child_samples=max(20, params["min_child_weight"] * 2),
            reg_lambda=params["reg_lambda"], reg_alpha=params["reg_alpha"],
            random_state=42, objective="quantile", alpha=0.5,
            n_jobs=-1, verbosity=-1,
        )
        lgb_m.fit(X_tr, y_tr_t, eval_set=[(X_val, y_val_t)], sample_weight=sw,
                  callbacks=[lgb.early_stopping(40, verbose=False)])
        return _inv(stat, lgb_m.predict(X_ho))

    # Default XGB-q50 backend.
    m = xgb.XGBRegressor(
        **{k: v for k, v in params.items() if k != "random_state"},
        random_state=42, objective="reg:quantileerror", quantile_alpha=0.5,
        early_stopping_rounds=40, eval_metric="mae",
    )
    m.fit(X_tr, y_tr_t, eval_set=[(X_val, y_val_t)], sample_weight=sw, verbose=False)
    return _inv(stat, m.predict(X_ho))


# ── post-prediction transforms (mirror predict_pergame, EXACT order) ──────────

def _apply_served_post(pred: float, stat: str, row: dict) -> float:
    """Apply the garbage-time haircut then residual correction to a raw-count
    point estimate — the exact tail predict_pergame runs after the head dispatch.

    predict_pergame:
        pred = apply_garbage_time_haircut(pred, stat, home_spread)
        pred = apply_residual_correction(pred, feature_row, stat, model_dir=...)
        return round(pred, 2)
    """
    hs_raw = row.get("home_spread")
    pred = apply_garbage_time_haircut(pred, stat, hs_raw)
    pred = apply_residual_correction(pred, row, stat, model_dir=_MODEL_DIR)
    return round(pred, 2)


# ── main OOF loop ─────────────────────────────────────────────────────────────

def run_oof(n_splits: int = _N_SPLITS, max_rows: Optional[int] = None,
            with_old_blend: bool = True, out_path: Optional[str] = None) -> str:
    import pandas as pd

    out_path = out_path or _OUT_PATH
    print(f"[faithful-oof] n_splits={n_splits} max_rows={max_rows} "
          f"with_old_blend={with_old_blend}", flush=True)
    rows, _fc = build_pergame_dataset(min_prior=0)
    rows.sort(key=lambda r: r["date"])
    n = len(rows)
    print(f"  total rows={n}", flush=True)
    if max_rows is not None and max_rows < n:
        rows = rows[:max_rows]
        n = len(rows)
        print(f"  truncated to {n} rows (--max-rows)", flush=True)

    # Frozen served 85-col aligned feature order (same for every stat — the
    # per-stat extras append after slot 128 and are sliced off at 85). Use
    # feature_columns_for so the order tracks _meta.json (flag-independent).
    served_cols: Dict[str, List[str]] = {
        s: feature_columns_for(s, _MODEL_DIR)[:_SERVED_N_FEATURES] for s in STATS
    }

    oof_records: List[dict] = []
    fold_ends = [(i + 1) / (n_splits + 1) for i in range(n_splits)]

    for fold_idx, train_end_frac in enumerate(fold_ends):
        tr_end = int(n * train_end_frac)
        te_end = n if fold_idx == n_splits - 1 else int(n * fold_ends[fold_idx + 1])
        va_end = int(tr_end + (te_end - tr_end) * 0.4)

        min_tr = max(500, int(n * 0.05))
        min_ho = max(50, int(n * 0.02))
        if tr_end < min_tr or (te_end - va_end) < min_ho:
            print(f"  fold {fold_idx+1}: too small (tr={tr_end}, ho={te_end-va_end}) — skip", flush=True)
            continue

        ho_rows = rows[va_end:te_end]
        tr_dates = [datetime.fromisoformat(rows[i]["date"]) for i in range(tr_end)]
        max_d = max(tr_dates)
        age = np.array([(max_d - d).days / 365.0 for d in tr_dates], dtype=float)
        sw = np.exp(-0.5 * age)

        print(f"\n[fold {fold_idx+1}/{n_splits}] tr={tr_end} val={va_end-tr_end} "
              f"ho={te_end-va_end}  {ho_rows[0]['date']}..{ho_rows[-1]['date']}", flush=True)
        t0 = time.time()

        for stat in STATS:
            cols = served_cols[stat]
            X_tr = np.array([[r[c] for c in cols] for r in rows[:tr_end]], dtype=float)
            X_val = np.array([[r[c] for c in cols] for r in rows[tr_end:va_end]], dtype=float)
            X_ho = np.array([[r[c] for c in cols] for r in rows[va_end:te_end]], dtype=float)

            y = np.array([r[f"target_{stat}"] for r in rows], dtype=float)
            y_tr, y_val = y[:tr_end], y[tr_end:va_end]
            y_ho = y[va_end:te_end]

            served_head = "q50" if stat in _USE_Q50_STATS else "blend"

            # SERVED head dispatch (matches predict_pergame).
            if served_head == "q50":
                raw_served = _train_q50(stat, X_tr, y_tr, X_val, y_val, X_ho, sw)
            else:
                raw_served = _train_blend(stat, X_tr, y_tr, X_val, y_val, X_ho, sw)

            # OLD legacy blend on the SAME 85-col space (for re-baselining).
            if with_old_blend:
                raw_oldblend = _train_blend(stat, X_tr, y_tr, X_val, y_val, X_ho, sw)
            else:
                raw_oldblend = None

            for i, row in enumerate(ho_rows):
                # SERVED tail: haircut + residual on the served head's point est.
                served_pred = _apply_served_post(float(raw_served[i]), stat, row)
                rec = {
                    "game_id": str(row.get("game_id", "")),
                    "player_id": int(row.get("player_id", 0)),
                    "stat": stat,
                    "oof_pred": float(served_pred),
                    "oof_pred_oldblend": (float(raw_oldblend[i])
                                          if raw_oldblend is not None else float("nan")),
                    "actual": float(y_ho[i]),
                    "game_date": str(row["date"])[:10],
                    "fold": fold_idx + 1,
                    "season": str(row.get("season", "")),
                    "served_head": served_head,
                }
                oof_records.append(rec)

            mae_served = float(np.mean(np.abs(
                np.array([r["oof_pred"] for r in oof_records[-len(ho_rows):]]) - y_ho)))
            extra = ""
            if with_old_blend:
                mae_old = float(np.mean(np.abs(raw_oldblend - y_ho)))
                extra = f"  oldblend_mae={mae_old:.4f}"
            print(f"  {stat.upper():4s} [{served_head:5s}] served_mae={mae_served:.4f}{extra}  "
                  f"n={len(ho_rows)}", flush=True)

        print(f"  fold {fold_idx+1} wall: {time.time()-t0:.0f}s", flush=True)

    if not oof_records:
        raise RuntimeError("No OOF records generated — all folds skipped (dataset too small?)")

    df = pd.DataFrame(oof_records)
    df = df[["game_id", "player_id", "stat", "oof_pred", "oof_pred_oldblend",
             "actual", "game_date", "fold", "season", "served_head"]]
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    df.to_parquet(out_path, index=False)

    # ── re-baseline report: per-stat OOF MAE OLD (blend) vs FAITHFUL (served) ──
    print("\n=== FAITHFUL OOF RE-BASELINE (per-stat MAE) ===", flush=True)
    print(f"{'stat':5s} {'head':6s} {'n':>7s} {'MAE_OLD_blend':>14s} "
          f"{'MAE_SERVED':>11s} {'delta':>9s} {'pct':>8s}", flush=True)
    for stat in STATS:
        sub = df[df["stat"] == stat]
        if sub.empty:
            continue
        head = sub["served_head"].iloc[0]
        mae_served = float(np.mean(np.abs(sub["oof_pred"] - sub["actual"])))
        if with_old_blend and sub["oof_pred_oldblend"].notna().any():
            mae_old = float(np.mean(np.abs(sub["oof_pred_oldblend"] - sub["actual"])))
            d = mae_served - mae_old
            pct = 100.0 * d / mae_old if mae_old else 0.0
            print(f"{stat:5s} {head:6s} {len(sub):7d} {mae_old:14.4f} "
                  f"{mae_served:11.4f} {d:+9.4f} {pct:+7.2f}%", flush=True)
        else:
            print(f"{stat:5s} {head:6s} {len(sub):7d} {'n/a':>14s} "
                  f"{mae_served:11.4f} {'n/a':>9s} {'n/a':>8s}", flush=True)

    print(f"\nWrote: {out_path}  ({os.path.getsize(out_path) // 1024} KB)", flush=True)
    return out_path


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Faithful (served-dispatch) OOF builder.")
    ap.add_argument("--max-rows", type=int, default=None, metavar="N")
    ap.add_argument("--splits", type=int, default=_N_SPLITS)
    ap.add_argument("--no-old-blend", action="store_true",
                    help="Skip recomputing the legacy blend (faster; no re-baseline).")
    ap.add_argument("--out", type=str, default=None, help="Override output parquet path.")
    args = ap.parse_args()
    run_oof(n_splits=args.splits, max_rows=args.max_rows,
            with_old_blend=not args.no_old_blend, out_path=args.out)
