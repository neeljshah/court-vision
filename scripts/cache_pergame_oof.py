"""cache_pergame_oof.py — Generate per-row OOF pregame predictions for the
prop_pergame 3-way stack and save to data/cache/pregame_oof.parquet.

Walk-forward integrity contract
--------------------------------
oof_pred for game G uses ONLY games before game_date(G) for training.
Each WF fold trains on rows[:tr_end] and predicts on rows[va_end:te_end]
(the held-out holdout slice), mirroring prop_pergame_walk_forward.py exactly.

Output schema
-------------
    game_id     str
    player_id   int
    stat        str   (one of STATS)
    oof_pred    float (3-way blend prediction, raw-count scale)
    actual      float (realised box-score value)
    game_date   str   (ISO date, e.g. "2024-04-13")
    fold        int   (1-indexed WF fold that produced this prediction)
    season      str   (e.g. "2024-25")

Ship gate
---------
  1. data/cache/pregame_oof.parquet exists
  2. Schema matches columns above
  3. Coverage >= 80 % of dataset rows per stat (at least 3 folds contribute)

Usage
-----
    # Fast dev run (first 2000 rows only)
    python scripts/cache_pergame_oof.py --max-rows 2000

    # Full run (30-60 min)
    python scripts/cache_pergame_oof.py
"""
from __future__ import annotations

import argparse
import os
import sys
import time
import warnings
from datetime import datetime
from typing import List, Optional

warnings.filterwarnings("ignore")

import numpy as np

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from src.prediction.prop_pergame import (  # noqa: E402
    STATS, build_pergame_dataset, feature_columns,
)

_OUT_PATH = os.path.join(PROJECT_DIR, "data", "cache", "pregame_oof.parquet")
_N_SPLITS = 4          # mirrors prop_pergame_walk_forward default


# ── model training (mirrors _train_one_stat in walk_forward) ──────────────────

def _train_and_predict_stat(
    stat: str,
    X_tr: np.ndarray, y_tr: np.ndarray,
    X_val: np.ndarray, y_val: np.ndarray,
    X_ho: np.ndarray,
    sw: np.ndarray,
) -> np.ndarray:
    """Train XGB+LGB+MLP for one stat, fit NNLS on val, return 3-way
    holdout predictions on raw-count scale."""
    import xgboost as xgb
    import lightgbm as lgb
    from sklearn.neural_network import MLPRegressor  # noqa: F401 (used via ensemble)
    from sklearn.preprocessing import StandardScaler
    from sklearn.linear_model import LinearRegression

    is_count = stat in ("stl", "blk")
    use_log = stat in {"stl", "blk", "tov", "fg3m", "reb", "ast"}
    use_sqrt_huber = stat in {"pts"}

    # ---- label transform ----
    def _fwd(y: np.ndarray) -> np.ndarray:
        if use_sqrt_huber:
            return np.sqrt(np.maximum(y, 0.0))
        if use_log:
            return np.log1p(np.maximum(y, 0.0))
        return y

    def _inv(y: np.ndarray) -> np.ndarray:
        if use_sqrt_huber:
            return np.square(np.maximum(y, 0.0))
        if use_log:
            return np.expm1(np.maximum(y, 0.0))
        return y

    y_tr_t  = _fwd(y_tr)
    y_val_t = _fwd(y_val)

    # ---- choose objectives ----
    if use_sqrt_huber:
        xgb_obj, lgb_obj = "reg:pseudohubererror", "huber"
    elif use_log or is_count is False:
        xgb_obj, lgb_obj = "reg:squarederror", "regression"
    else:
        # is_count AND not log → poisson (shouldn't reach here with current sets
        # but keep as safety)
        xgb_obj, lgb_obj = "count:poisson", "poisson"

    # Override: log-transform stats always use squared-error learners
    if use_log:
        xgb_obj, lgb_obj = "reg:squarederror", "regression"

    depth = 3 if is_count else 4

    xgb_m = xgb.XGBRegressor(
        n_estimators=600, max_depth=depth,
        learning_rate=0.04, subsample=0.8, colsample_bytree=0.8,
        min_child_weight=10, reg_lambda=2.0, reg_alpha=0.5, gamma=0.2,
        random_state=42, objective=xgb_obj,
        early_stopping_rounds=40, eval_metric="mae",
    )
    xgb_m.fit(X_tr, y_tr_t, eval_set=[(X_val, y_val_t)],
              sample_weight=sw, verbose=False)

    lgb_m = lgb.LGBMRegressor(
        n_estimators=600, max_depth=depth,
        learning_rate=0.04, subsample=0.8, subsample_freq=1,
        colsample_bytree=0.8, min_child_samples=20,
        reg_lambda=2.0, reg_alpha=0.5, random_state=42,
        objective=lgb_obj, n_jobs=-1, verbosity=-1,
    )
    lgb_m.fit(X_tr, y_tr_t, eval_set=[(X_val, y_val_t)],
              sample_weight=sw,
              callbacks=[lgb.early_stopping(40, verbose=False)])

    sc = StandardScaler()
    X_tr_s  = sc.fit_transform(X_tr)
    X_val_s = sc.transform(X_val)
    X_ho_s  = sc.transform(X_ho)

    from src.prediction.prop_pergame import _MLPSeedEnsemble  # noqa: PLC0415
    mlp_m = _MLPSeedEnsemble().fit(X_tr_s, y_tr_t)

    # ---- NNLS blend weights from validation slice ----
    xv = _inv(xgb_m.predict(X_val))
    lv = _inv(lgb_m.predict(X_val))
    mv = _inv(mlp_m.predict(X_val_s))

    st = LinearRegression(positive=True, fit_intercept=False)
    st.fit(np.column_stack([xv, lv, mv]), y_val)
    w = st.coef_
    if not (0.5 <= w.sum() <= 1.5):
        w = np.array([1.0 / 3.0, 1.0 / 3.0, 1.0 / 3.0])

    # ---- 3-way holdout predictions (raw-count scale) ----
    xh = _inv(xgb_m.predict(X_ho))
    lh = _inv(lgb_m.predict(X_ho))
    mh = _inv(mlp_m.predict(X_ho_s))

    preds = w[0] * xh + w[1] * lh + w[2] * mh
    return preds


# ── main OOF loop ─────────────────────────────────────────────────────────────

def run_oof(n_splits: int = _N_SPLITS, max_rows: Optional[int] = None) -> str:
    """Generate OOF predictions and write pregame_oof.parquet.

    Returns the path to the written parquet.
    """
    import pandas as pd

    print(f"Loading dataset (n_splits={n_splits}, max_rows={max_rows}) ...")
    rows, fc = build_pergame_dataset(min_prior=0)
    rows.sort(key=lambda r: r["date"])
    n = len(rows)
    print(f"  total rows={n}, features={len(fc)}")

    if max_rows is not None and max_rows < n:
        rows = rows[:max_rows]
        n = len(rows)
        print(f"  truncated to {n} rows (--max-rows)")

    # Build feature matrix once
    X_all = np.array([[r[c] for c in fc] for r in rows], dtype=float)

    # We collect OOF records as a list of dicts; one entry per (row, stat)
    oof_records: List[dict] = []

    fold_ends = [(i + 1) / (n_splits + 1) for i in range(n_splits)]

    for fold_idx, train_end_frac in enumerate(fold_ends):
        tr_end = int(n * train_end_frac)
        if fold_idx == n_splits - 1:
            te_end = n
        else:
            te_end = int(n * fold_ends[fold_idx + 1])
        va_end = int(tr_end + (te_end - tr_end) * 0.4)

        # For --max-rows dev runs the thresholds scale with dataset size;
        # full runs always have tr>5000 and ho>2000 anyway.
        min_tr = max(500, int(n * 0.05))
        min_ho = max(50,  int(n * 0.02))
        if tr_end < min_tr or (te_end - va_end) < min_ho:
            print(f"  fold {fold_idx+1}: too small (tr={tr_end}, ho={te_end-va_end}) — skip")
            continue

        X_tr  = X_all[:tr_end]
        X_val = X_all[tr_end:va_end]
        X_ho  = X_all[va_end:te_end]

        ho_rows = rows[va_end:te_end]

        # Recency sample weights on training slice
        tr_dates = [datetime.fromisoformat(rows[i]["date"]) for i in range(tr_end)]
        max_d = max(tr_dates)
        age = np.array([(max_d - d).days / 365.0 for d in tr_dates], dtype=float)
        sw = np.exp(-0.5 * age)

        print(f"\n[fold {fold_idx+1}/{n_splits}] tr={tr_end} val={va_end-tr_end} "
              f"ho={te_end-va_end}  date_range={ho_rows[0]['date']}..{ho_rows[-1]['date']}",
              flush=True)
        t0 = time.time()

        for stat in STATS:
            # Use per-stat feature columns (e.g. reb gets extra context cols)
            fc_stat = feature_columns(stat=stat)
            # Rebuild X slices with stat-specific feature set
            X_tr_s   = np.array([[r[c] for c in fc_stat] for r in rows[:tr_end]],  dtype=float)
            X_val_s  = np.array([[r[c] for c in fc_stat] for r in rows[tr_end:va_end]], dtype=float)
            X_ho_s   = np.array([[r[c] for c in fc_stat] for r in rows[va_end:te_end]], dtype=float)

            y = np.array([r[f"target_{stat}"] for r in rows], dtype=float)
            y_tr  = y[:tr_end]
            y_val = y[tr_end:va_end]
            y_ho  = y[va_end:te_end]

            preds = _train_and_predict_stat(
                stat, X_tr_s, y_tr, X_val_s, y_val, X_ho_s, sw,
            )

            for i, row in enumerate(ho_rows):
                oof_records.append({
                    "game_id":   str(row.get("game_id", "")),
                    "player_id": int(row.get("player_id", 0)),
                    "stat":      stat,
                    "oof_pred":  float(preds[i]),
                    "actual":    float(y_ho[i]),
                    "game_date": str(row["date"])[:10],
                    "fold":      fold_idx + 1,
                    "season":    str(row.get("season", "")),
                })

            mae = float(np.mean(np.abs(preds - y_ho)))
            print(f"  {stat.upper():4s} ho_mae={mae:.4f}  n={len(ho_rows)}", flush=True)

        print(f"  fold {fold_idx+1} wall: {time.time()-t0:.0f}s")

    if not oof_records:
        raise RuntimeError("No OOF records generated — all folds were skipped (dataset too small?)")

    df = pd.DataFrame(oof_records)
    # Enforce schema column order
    df = df[["game_id", "player_id", "stat", "oof_pred", "actual",
             "game_date", "fold", "season"]]

    os.makedirs(os.path.dirname(_OUT_PATH), exist_ok=True)
    df.to_parquet(_OUT_PATH, index=False)

    # ── integrity report ──────────────────────────────────────────────────────
    total_rows = n
    print(f"\n=== OOF INTEGRITY REPORT ===")
    print(f"Total dataset rows: {total_rows}")
    print(f"OOF records written: {len(df)}")
    print(f"Unique game_ids: {df['game_id'].nunique()}")
    print(f"Unique player_ids: {df['player_id'].nunique()}")
    print(f"\nCoverage per stat (% of dataset rows with oof_pred):")
    per_stat = df.groupby("stat").size()
    for stat in STATS:
        cnt = per_stat.get(stat, 0)
        pct = cnt / total_rows * 100
        flag = "OK" if pct >= 80.0 else "WARN <80%"
        print(f"  {stat.upper():4s}: {cnt:6d} rows  ({pct:.1f}%)  [{flag}]")

    print(f"\nFolds contributing per stat:")
    fold_coverage = df.groupby(["stat", "fold"]).size().unstack(fill_value=0)
    print(fold_coverage.to_string())

    # Walk-forward integrity check: no oof_pred should use future data.
    # Verify by checking that within each fold, all game_dates are AFTER
    # the latest game_date of the training slice.
    print(f"\nWalk-forward date integrity check:")
    all_dates = sorted(set(r["date"][:10] for r in rows))
    ok = True
    for fold_idx, train_end_frac in enumerate(fold_ends):
        tr_end = int(n * train_end_frac)
        if fold_idx == n_splits - 1:
            te_end = n
        else:
            te_end = int(n * fold_ends[fold_idx + 1])
        va_end = int(tr_end + (te_end - tr_end) * 0.4)
        if tr_end < 2000:
            continue
        max_train_date = rows[tr_end - 1]["date"][:10]
        fold_df = df[df["fold"] == fold_idx + 1]
        if fold_df.empty:
            continue
        min_ho_date = fold_df["game_date"].min()
        if min_ho_date <= max_train_date:
            print(f"  fold {fold_idx+1}: FAIL — holdout min_date={min_ho_date} <= "
                  f"train max_date={max_train_date}")
            ok = False
        else:
            print(f"  fold {fold_idx+1}: OK  — holdout from {min_ho_date} "
                  f"(train through {max_train_date})")
    if ok:
        print("  All folds pass date integrity check.")

    print(f"\nWrote: {_OUT_PATH}  ({os.path.getsize(_OUT_PATH) // 1024} KB)")
    return _OUT_PATH


# ── entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    ap = argparse.ArgumentParser(
        description="Generate per-row OOF predictions for the prop_pergame stack."
    )
    ap.add_argument(
        "--max-rows", type=int, default=None, metavar="N",
        help="Truncate dataset to first N rows for fast dev runs (e.g. 2000).",
    )
    ap.add_argument(
        "--splits", type=int, default=_N_SPLITS,
        help=f"Number of WF splits (default {_N_SPLITS}).",
    )
    args = ap.parse_args()
    run_oof(n_splits=args.splits, max_rows=args.max_rows)
