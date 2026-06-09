"""retrain_iter45_reb_player_id_cat.py

Iter-45: Add player_id as a native LGB categorical feature for the REB
LGB-q50 model. LGB's native categorical handler learns per-player
splits directly rather than relying solely on rolling form features
to represent inter-player variance.

Steps:
  1. Backup current OOS artifact (quantile_pergame_lgb_reb_q50.pkl).
  2. Build dataset via build_pergame_dataset, inject player_id col.
  3. Train LGB-q50 with categorical_feature=['player_id'].
  4. Write candidate artifact to data/models/_candidate_iter45_reb_pid_cat/.
  5. Record val MAE pre/post; print top-10 player_id importances.
  6. SWAP candidate into oos_pre_playoffs/ and run OOS backtest.
  7. SHIP or REVERT based on ROI >= baseline +1pp AND MAE down.

Usage:
    python scripts/retrain_iter45_reb_player_id_cat.py
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
import warnings
from datetime import datetime

warnings.filterwarnings("ignore")

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

import numpy as np

from src.prediction.prop_quantiles import _transform, _inverse, _per_stat_xgb_params
from src.prediction.prop_pergame import build_pergame_dataset, feature_columns_for

STAT = "reb"
CUTOFF_DATE = "2024-04-21"
OOS_DIR = os.path.join(PROJECT_DIR, "data", "models", "oos_pre_playoffs")
CANDIDATE_DIR = os.path.join(PROJECT_DIR, "data", "models", "_candidate_iter45_reb_pid_cat")
BACKUP_DIR = os.path.join(OOS_DIR, "_backup_pre_iter45")

BASELINE_ROI = 14.2045  # __global__["reb"]["roi_pct"] from holdout_baseline.json
BASELINE_VAL_MAE = 1.956284  # from _meta.json reb entry


def _backup_artifact():
    """Copy current OOS REB artifact to backup dir (idempotent)."""
    os.makedirs(BACKUP_DIR, exist_ok=True)
    src = os.path.join(OOS_DIR, "quantile_pergame_lgb_reb_q50.pkl")
    dst = os.path.join(BACKUP_DIR, "quantile_pergame_lgb_reb_q50.pkl")
    if not os.path.exists(dst):
        shutil.copy2(src, dst)
        print(f"  [backup] {src} -> {dst}", flush=True)
    else:
        print(f"  [backup] already exists: {dst}", flush=True)

    # Backup _meta.json reb section
    meta_src = os.path.join(OOS_DIR, "_meta.json")
    meta_dst = os.path.join(BACKUP_DIR, "_meta.json")
    if not os.path.exists(meta_dst) and os.path.exists(meta_src):
        shutil.copy2(meta_src, meta_dst)
        print(f"  [backup] meta -> {meta_dst}", flush=True)


def _build_dataset_with_player_id():
    """Build dataset and inject player_id as int64 column."""
    print("  [data] building pergame dataset ...", flush=True)
    t0 = time.time()
    rows, fcols = build_pergame_dataset(None)
    print(f"  [data] {len(rows)} total rows in {time.time()-t0:.1f}s", flush=True)

    # Inject player_id — each row must have 'player_id' in the gamelog dict.
    # build_pergame_dataset populates it from the gamelog JSON.
    n_missing = sum(1 for r in rows if not r.get("player_id"))
    if n_missing > len(rows) * 0.5:
        raise RuntimeError(
            f"player_id missing from {n_missing}/{len(rows)} rows — "
            "gamelog dataset may predate the player_id field. Aborting."
        )
    print(f"  [data] player_id missing: {n_missing}/{len(rows)}", flush=True)

    # Cast to int (LGB requires int for categorical; 0 sentinel for missing)
    for r in rows:
        try:
            r["player_id_cat"] = int(r["player_id"]) if r.get("player_id") else 0
        except (TypeError, ValueError):
            r["player_id_cat"] = 0

    return rows, fcols


def _filter_and_split(rows, fcols, cutoff_str, val_frac=0.15):
    """Filter to pre-cutoff, sort, train/val split."""
    cutoff = datetime.fromisoformat(cutoff_str)
    pre = [r for r in rows if datetime.fromisoformat(r["date"]) < cutoff]
    pre.sort(key=lambda r: r["date"])
    n_pre = len(pre)
    if n_pre < 200:
        raise RuntimeError(f"only {n_pre} pre-cutoff rows")

    train_end = int(n_pre * (1.0 - val_frac))

    # Build X without player_id (baseline cols)
    X_base = np.array([[r[c] for c in fcols] for r in pre], dtype=float)

    # Build player_id column (int64)
    pid_col = np.array([r["player_id_cat"] for r in pre], dtype=np.int64).reshape(-1, 1)

    # Augmented feature matrix: baseline cols + player_id_cat at the end
    X_aug = np.hstack([X_base, pid_col])

    train_dates = [datetime.fromisoformat(pre[i]["date"]) for i in range(train_end)]
    max_d = max(train_dates)
    age = np.array([(max_d - d).days / 365.0 for d in train_dates], dtype=float)
    sw = np.exp(-0.5 * age)

    y = np.array([r[f"target_{STAT}"] for r in pre], dtype=float)

    return (
        X_aug[:train_end], X_aug[train_end:],
        y[:train_end], y[train_end:],
        sw,
        X_base[:train_end], X_base[train_end:],
        n_pre, len(pre) - train_end,
    )


def _train_lgb_baseline(X_tr, X_val, yt_tr, yt_val, sw, params, seed=42):
    """Train LGB WITHOUT player_id cat to get pre-iter-45 val MAE."""
    import lightgbm as lgb
    m = lgb.LGBMRegressor(
        n_estimators=params["n_estimators"], max_depth=params["max_depth"],
        learning_rate=params["learning_rate"],
        subsample=params["subsample"], subsample_freq=1,
        colsample_bytree=params["colsample_bytree"],
        min_child_samples=max(20, params["min_child_weight"] * 2),
        reg_lambda=params["reg_lambda"], reg_alpha=params["reg_alpha"],
        random_state=seed, objective="quantile", alpha=0.5,
        n_jobs=-1, verbosity=-1,
    )
    import lightgbm as lgb
    t0 = time.time()
    m.fit(X_tr, yt_tr, eval_set=[(X_val, yt_val)], sample_weight=sw,
          callbacks=[lgb.early_stopping(40, verbose=False)])
    return m, time.time() - t0


def _train_lgb_with_pid_cat(X_tr_aug, X_val_aug, yt_tr, yt_val, sw, params,
                             pid_col_idx, seed=42):
    """Train LGB WITH player_id as native categorical at pid_col_idx."""
    import lightgbm as lgb
    m = lgb.LGBMRegressor(
        n_estimators=params["n_estimators"], max_depth=params["max_depth"],
        learning_rate=params["learning_rate"],
        subsample=params["subsample"], subsample_freq=1,
        colsample_bytree=params["colsample_bytree"],
        min_child_samples=max(20, params["min_child_weight"] * 2),
        reg_lambda=params["reg_lambda"], reg_alpha=params["reg_alpha"],
        random_state=seed, objective="quantile", alpha=0.5,
        n_jobs=-1, verbosity=-1,
        max_cat_threshold=64,  # limit splits per categorical value
    )
    t0 = time.time()
    m.fit(X_tr_aug, yt_tr, eval_set=[(X_val_aug, yt_val)],
          sample_weight=sw,
          categorical_feature=[pid_col_idx],
          callbacks=[lgb.early_stopping(40, verbose=False)])
    return m, time.time() - t0


def _val_mae(model, X_val, y_val):
    from sklearn.metrics import mean_absolute_error
    pred_t = model.predict(X_val)
    pred = _inverse(STAT, np.array(pred_t, dtype=float))
    return float(mean_absolute_error(y_val, pred))


def _top_player_importances(model, pid_col_idx, n=10):
    """Return list of (col_index, importance) sorted descending for player_id."""
    imps = model.feature_importances_  # shape (n_features,)
    # The player_id column is at pid_col_idx — but we want the top features
    # overall AND specifically flag how player_id ranks.
    ranked = sorted(enumerate(imps), key=lambda x: x[1], reverse=True)
    return ranked[:n]


def _get_feature_names(fcols):
    """Return augmented feature name list (baseline + player_id_cat)."""
    return list(fcols) + ["player_id_cat"]


def _run_oos_backtest():
    """Run backtest_qstat_oos.py --stat reb and parse ROI/MAE."""
    import re
    script = os.path.join(PROJECT_DIR, "scripts", "backtest_qstat_oos.py")
    env = os.environ.copy()
    env["NBA_INJURY_WIRE_DISABLE"] = "1"
    t0 = time.time()
    result = subprocess.run(
        [sys.executable, script, "--stat", STAT],
        cwd=PROJECT_DIR, env=env, capture_output=True, text=True, timeout=300,
    )
    out = (result.stdout or "") + "\n" + (result.stderr or "")
    elapsed = time.time() - t0

    roi_m = re.search(r"ROI=([+-]?\d+\.\d+)%", out)
    hit_m = re.search(r"hit=([+-]?\d+\.\d+)%", out)
    nb_m  = re.search(r"n_bets=(\d+)", out)
    mae_m = re.search(r"mae_actual=([+-]?\d+\.\d+)", out, re.IGNORECASE)

    roi  = float(roi_m.group(1))  if roi_m  else None
    hit  = float(hit_m.group(1))  if hit_m  else None
    nb   = int(nb_m.group(1))     if nb_m   else None
    mae  = float(mae_m.group(1))  if mae_m  else None

    return {
        "roi_pct": roi, "hit_rate": hit, "n_bets": nb, "mae_actual": mae,
        "elapsed_s": elapsed, "stdout_tail": "\n".join(out.splitlines()[-30:]),
        "exit_code": result.returncode,
    }


def main():
    print("\n" + "="*60, flush=True)
    print(" Iter-45: player_id as LGB categorical — REB only", flush=True)
    print("="*60, flush=True)

    # 1. Backup
    _backup_artifact()

    # 2. Build dataset
    rows, fcols = _build_dataset_with_player_id()
    pid_col_idx = len(fcols)  # last column in augmented matrix
    feat_names = _get_feature_names(fcols)

    # 3. Split
    (X_tr_aug, X_val_aug, y_tr, y_val, sw,
     X_tr_base, X_val_base,
     n_train, n_val) = _filter_and_split(rows, fcols, CUTOFF_DATE)

    yt_tr = _transform(STAT, y_tr)
    yt_val = _transform(STAT, y_val)

    params = _per_stat_xgb_params(STAT)
    print(f"  HPs: {params}", flush=True)
    print(f"  Train: {n_train} | Val: {n_val} | pid_col_idx: {pid_col_idx}", flush=True)

    # 4. Train baseline (no player_id) to get reference val MAE in this run
    print("\n  [phase-A] training baseline LGB (no player_id) ...", flush=True)
    m_base, t_base = _train_lgb_baseline(
        X_tr_base, X_val_base, yt_tr, yt_val, sw, params)
    mae_base = _val_mae(m_base, X_val_base, y_val)
    print(f"  Baseline val MAE: {mae_base:.6f}  (fit={t_base:.1f}s)", flush=True)
    print(f"  Reference val MAE from _meta.json: {BASELINE_VAL_MAE:.6f}", flush=True)

    # 5. Train with player_id categorical
    print("\n  [phase-B] training LGB + player_id categorical ...", flush=True)
    m_cat, t_cat = _train_lgb_with_pid_cat(
        X_tr_aug, X_val_aug, yt_tr, yt_val, sw, params, pid_col_idx)
    mae_cat = _val_mae(m_cat, X_val_aug, y_val)
    delta_mae = mae_cat - mae_base
    print(f"  Categorical val MAE: {mae_cat:.6f}  (fit={t_cat:.1f}s)", flush=True)
    print(f"  Delta vs baseline:   {delta_mae:+.6f}", flush=True)

    # 6. Feature importances — top 10 overall
    print("\n  [importance] top-10 features (iter-45 model):", flush=True)
    top10 = _top_player_importances(m_cat, pid_col_idx, n=10)
    pid_rank = None
    for rank, (idx, imp) in enumerate(top10, 1):
        fname = feat_names[idx] if idx < len(feat_names) else f"col_{idx}"
        marker = " <-- player_id_cat" if idx == pid_col_idx else ""
        print(f"    #{rank:2d}  {fname:40s}  imp={imp:.1f}{marker}", flush=True)
        if idx == pid_col_idx:
            pid_rank = rank

    # Also report player_id_cat importance even if not in top-10
    pid_imp = m_cat.feature_importances_[pid_col_idx] if pid_col_idx < len(m_cat.feature_importances_) else 0
    print(f"\n  player_id_cat importance: {pid_imp:.1f}  (rank: {pid_rank or '>10'})", flush=True)

    # 7. Save candidate artifact
    os.makedirs(CANDIDATE_DIR, exist_ok=True)
    import joblib
    cand_pkl = os.path.join(CANDIDATE_DIR, "quantile_pergame_lgb_reb_q50.pkl")
    joblib.dump(m_cat, cand_pkl)
    print(f"\n  [candidate] saved -> {cand_pkl}", flush=True)

    # Save candidate _meta.json with updated feature_columns (includes player_id_cat)
    meta_cand = {
        "stats": {
            STAT: {
                "cutoff_date": CUTOFF_DATE,
                "stat": STAT,
                "method": "lgb_player_id_cat",
                "iter": "iter45",
                "n_train": n_train, "n_val": n_val,
                "val_mae_baseline_run": mae_base,
                "val_mae_cat": mae_cat,
                "delta_mae": delta_mae,
                "player_id_cat_importance": float(pid_imp),
                "player_id_cat_rank_top10": pid_rank,
                "pid_col_idx": pid_col_idx,
                "model_filename": "quantile_pergame_lgb_reb_q50.pkl",
                "training_timestamp": datetime.now().isoformat(),
                "fit_seconds": t_cat,
                "best_iteration": int(getattr(m_cat, "best_iteration_", -1) or -1),
                "n_features": len(feat_names),
                "hps": params,
                "feature_columns": feat_names,
            }
        }
    }
    meta_cand_path = os.path.join(CANDIDATE_DIR, "_meta.json")
    with open(meta_cand_path, "w", encoding="utf-8") as fh:
        json.dump(meta_cand, fh, indent=2)
    print(f"  [candidate] meta -> {meta_cand_path}", flush=True)

    # 8. SWAP candidate into OOS dir and run backtest
    print("\n  [swap] installing candidate into oos_pre_playoffs/ ...", flush=True)
    oos_pkl = os.path.join(OOS_DIR, "quantile_pergame_lgb_reb_q50.pkl")
    shutil.copy2(cand_pkl, oos_pkl)

    # Update _meta.json in OOS dir so backtest_qstat_oos sees the new feature_columns
    oos_meta_path = os.path.join(OOS_DIR, "_meta.json")
    oos_meta: dict = {}
    if os.path.exists(oos_meta_path):
        try:
            with open(oos_meta_path, encoding="utf-8") as fh:
                oos_meta = json.load(fh)
        except Exception:
            oos_meta = {}
    if "stats" not in oos_meta:
        oos_meta["stats"] = {}
    oos_meta["stats"][STAT] = meta_cand["stats"][STAT]
    with open(oos_meta_path, "w", encoding="utf-8") as fh:
        json.dump(oos_meta, fh, indent=2)
    print(f"  [swap] _meta.json updated.", flush=True)

    # 9. Run OOS backtest
    print("\n  [backtest] running backtest_qstat_oos.py --stat reb ...", flush=True)
    bt = _run_oos_backtest()
    print(bt["stdout_tail"], flush=True)

    roi_cat  = bt["roi_pct"]
    mae_oos  = bt["mae_actual"]
    n_bets   = bt["n_bets"]
    hit_rate = bt["hit_rate"]

    print(f"\n  OOS results: roi={roi_cat}%  hit={hit_rate}%  n_bets={n_bets}"
          f"  mae={mae_oos}", flush=True)

    # 10. Decision
    delta_roi = (roi_cat - BASELINE_ROI) if roi_cat is not None else None
    mae_improved = (delta_mae <= 0)  # val MAE on training split went down

    ship = (
        roi_cat is not None
        and delta_roi >= 1.0
        and mae_improved
        and n_bets is not None
        and n_bets >= 30
    )

    print("\n" + "="*60, flush=True)
    print(f"  DECISION: {'SHIP' if ship else 'REVERT'}", flush=True)
    print(f"  REB ROI  baseline={BASELINE_ROI:+.2f}%  candidate={roi_cat:+.2f}%  "
          f"delta={delta_roi:+.2f}pp", flush=True)
    print(f"  val MAE  baseline_run={mae_base:.6f}  candidate={mae_cat:.6f}  "
          f"delta={delta_mae:+.6f}", flush=True)
    print(f"  player_id_cat importance: {pid_imp:.1f} (rank {pid_rank or '>10'}/10)", flush=True)

    if not ship:
        # REVERT — restore backup
        print("\n  [revert] restoring backup artifact ...", flush=True)
        backup_pkl = os.path.join(BACKUP_DIR, "quantile_pergame_lgb_reb_q50.pkl")
        if os.path.exists(backup_pkl):
            shutil.copy2(backup_pkl, oos_pkl)
            print(f"  [revert] restored {oos_pkl}", flush=True)
        backup_meta = os.path.join(BACKUP_DIR, "_meta.json")
        if os.path.exists(backup_meta):
            shutil.copy2(backup_meta, oos_meta_path)
            print(f"  [revert] restored _meta.json", flush=True)
        print("  [revert] DONE — candidate rejected.", flush=True)

    # 11. Emit machine-readable summary
    summary = {
        "iter": "iter45",
        "stat": STAT,
        "decision": "SHIP" if ship else "REVERT",
        "baseline_roi_pct": BASELINE_ROI,
        "candidate_roi_pct": roi_cat,
        "delta_roi_pp": delta_roi,
        "val_mae_baseline_run": mae_base,
        "val_mae_candidate": mae_cat,
        "delta_mae": delta_mae,
        "n_bets": n_bets,
        "hit_rate": hit_rate,
        "player_id_cat_importance": float(pid_imp),
        "player_id_cat_rank_top10": pid_rank,
        "top10_features": [
            {"rank": rank, "col_idx": idx, "name": feat_names[idx] if idx < len(feat_names) else f"col_{idx}", "importance": float(imp)}
            for rank, (idx, imp) in enumerate(top10, 1)
        ],
        "generated_at": datetime.now().isoformat(),
    }
    summary_path = os.path.join(PROJECT_DIR, "data", "cache",
                                "iter45_player_id_cat_summary.json")
    os.makedirs(os.path.dirname(summary_path), exist_ok=True)
    with open(summary_path, "w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=2)
    print(f"\n  Summary -> {summary_path}", flush=True)
    print("="*60, flush=True)

    return 0 if ship else 1


if __name__ == "__main__":
    sys.exit(main())
