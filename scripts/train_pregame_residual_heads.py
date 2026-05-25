"""scripts/train_pregame_residual_heads.py -- R3-F pregame residual heads.

Trains one LightGBM head per stat on the residual between the pregame OOF
prediction (data/cache/pregame_oof.parquet) and the realized actual.

Features
--------
The full 85-column pregame feature set returned by feature_columns() — i.e.
the same features the prop_pergame stack saw at train time. For stat="reb",
feature_columns(stat="reb") returns 88 columns (3 extra OREB-context cols).

Walk-forward gate
-----------------
Uses the saved 4-fold ids from the OOF cache (do NOT re-split).
For each stat: train on folds {1..k-1}, validate on fold k, k in {2,3,4}.
Plus fold-1 leave-one-out (train on {2,3,4}, predict on {1}) for completeness.

Effective WF: 4 folds where each fold is held-out exactly once.

Ship gate
---------
Save data/models/pregame_residual_heads/{stat}.lgb ONLY if WF mean MAE
strictly < zero-pred (i.e. trust OOF) on >= 3/4 folds.

Output
------
    data/models/pregame_residual_heads/<stat>.lgb           (per stat, if gate)
    data/models/pregame_residual_heads/training_report.json (per-stat WF deltas)

Usage
-----
    python scripts/train_pregame_residual_heads.py
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from typing import Dict, List, Tuple

import numpy as np

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

from src.prediction.prop_pergame import (  # noqa: E402
    STATS as _STATS_LIST,
    build_pergame_dataset,
    feature_columns,
)

STATS = tuple(_STATS_LIST)  # ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov")
OOF_PATH = os.path.join(PROJECT_DIR, "data", "cache", "pregame_oof.parquet")
OUT_DIR = os.path.join(PROJECT_DIR, "data", "models", "pregame_residual_heads")

LGB_PARAMS = {
    "n_estimators": 200,
    "learning_rate": 0.03,
    "num_leaves": 15,
    "min_child_samples": 80,
    "objective": "regression_l1",
    "random_state": 42,
    "verbosity": -1,
    "n_jobs": -1,
}


def _load_oof():
    """Load OOF parquet."""
    import pandas as pd
    df = pd.read_parquet(OOF_PATH)
    # date short form for join
    df["date_short"] = df["game_date"].astype(str).str[:10]
    return df


def _build_feature_lookup(rows, stat: str) -> Tuple[Dict[Tuple[int, str], np.ndarray], List[str]]:
    """Map (player_id, date_short) -> feature vector for the requested stat.

    Uses feature_columns(stat=stat) so REB picks up its 3 extra OREB cols.
    """
    fc = feature_columns(stat=stat)
    out: Dict[Tuple[int, str], np.ndarray] = {}
    for r in rows:
        pid = r.get("player_id")
        date_full = r.get("date")
        if pid is None or not date_full:
            continue
        date_short = str(date_full)[:10]
        try:
            pid_int = int(pid)
        except (TypeError, ValueError):
            continue
        # Build feature vector; coerce Nones to 0.0
        vec = np.array(
            [float(r.get(c) if r.get(c) is not None else 0.0) for c in fc],
            dtype=np.float32,
        )
        out[(pid_int, date_short)] = vec
    return out, fc


def _train_one_stat(
    stat: str,
    X: np.ndarray,
    y_resid: np.ndarray,
    folds: np.ndarray,
    feature_names: List[str],
) -> Tuple[bool, Dict]:
    """4-fold WF: hold out fold k in {1..4}; train on the other 3.

    Save .lgb only if WF mean MAE strictly < zero-pred on >= 3/4 folds.
    """
    import lightgbm as lgb

    fold_details = []
    fold_wins = 0
    deltas = []

    for k in (1, 2, 3, 4):
        tr_mask = folds != k
        va_mask = folds == k
        if tr_mask.sum() < LGB_PARAMS["min_child_samples"] or va_mask.sum() == 0:
            fold_details.append({"fold": k, "skip": True})
            continue

        model = lgb.LGBMRegressor(**LGB_PARAMS)
        model.fit(X[tr_mask], y_resid[tr_mask], feature_name=feature_names)
        pred = model.predict(X[va_mask])
        y_va = y_resid[va_mask]

        mae_model = float(np.mean(np.abs(pred - y_va)))
        mae_zero = float(np.mean(np.abs(y_va)))
        delta = mae_model - mae_zero
        deltas.append(delta)
        fold_details.append({
            "fold": k,
            "n_val": int(va_mask.sum()),
            "mae_model": round(mae_model, 5),
            "mae_zero": round(mae_zero, 5),
            "delta": round(delta, 5),
        })
        if mae_model < mae_zero:
            fold_wins += 1
        print(f"    [{stat}] fold {k}: model={mae_model:.4f} zero={mae_zero:.4f} "
              f"delta={delta:+.4f} {'WIN' if mae_model < mae_zero else 'loss'}")

    mean_delta = float(np.mean(deltas)) if deltas else 0.0
    gate_passed = fold_wins >= 3
    saved = False

    if gate_passed:
        model_final = lgb.LGBMRegressor(**LGB_PARAMS)
        model_final.fit(X, y_resid, feature_name=feature_names)
        out_path = os.path.join(OUT_DIR, f"{stat}.lgb")
        model_final.booster_.save_model(out_path)
        saved = True
        print(f"  [{stat}] SAVED -> {out_path} ({fold_wins}/4 folds won, mean delta={mean_delta:+.4f})")
    else:
        print(f"  [{stat}] NOT SAVED ({fold_wins}/4 folds beat zero-pred, mean delta={mean_delta:+.4f})")

    return saved, {
        "stat": stat,
        "n_rows": int(len(y_resid)),
        "fold_wins": fold_wins,
        "mean_delta": round(mean_delta, 5),
        "gate_passed": gate_passed,
        "saved": saved,
        "folds": fold_details,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Train R3-F pregame residual heads.")
    ap.add_argument("--max-rows", type=int, default=None,
                    help="Truncate dataset (smoke test).")
    args = ap.parse_args()

    os.makedirs(OUT_DIR, exist_ok=True)

    print("Loading OOF cache ...")
    oof = _load_oof()
    print(f"  OOF rows: {len(oof)}  stats: {oof['stat'].nunique()}  folds: {sorted(oof['fold'].unique())}")

    print("Building pergame dataset (this takes ~70 s) ...")
    t0 = time.time()
    rows, _base_fc = build_pergame_dataset(min_prior=0)
    print(f"  dataset rows: {len(rows)}  base_fc: {len(_base_fc)}  ({time.time()-t0:.1f}s)")

    report = {"trained_stats": [], "skipped_stats": []}

    for stat in STATS:
        print(f"\n=== {stat.upper()} ===")
        sub = oof[oof["stat"] == stat].copy()
        if args.max_rows is not None:
            sub = sub.head(args.max_rows)
        if len(sub) < 500:
            print(f"  too few OOF rows for {stat}: {len(sub)}")
            report["skipped_stats"].append({"stat": stat, "reason": "few_rows"})
            continue

        feat_lookup, fc = _build_feature_lookup(rows, stat)
        print(f"  feature_columns({stat}) -> {len(fc)} cols, lookup size: {len(feat_lookup)}")

        # Join OOF rows to features by (player_id, date_short)
        X_list: List[np.ndarray] = []
        y_resid_list: List[float] = []
        fold_list: List[int] = []
        miss = 0

        for _, r in sub.iterrows():
            key = (int(r["player_id"]), str(r["date_short"]))
            vec = feat_lookup.get(key)
            if vec is None:
                miss += 1
                continue
            X_list.append(vec)
            y_resid_list.append(float(r["actual"]) - float(r["oof_pred"]))
            fold_list.append(int(r["fold"]))

        if not X_list:
            print(f"  no joinable rows for {stat} ({miss} misses)")
            report["skipped_stats"].append({"stat": stat, "reason": "no_join"})
            continue

        X = np.vstack(X_list).astype(np.float32)
        y_resid = np.array(y_resid_list, dtype=np.float32)
        folds = np.array(fold_list, dtype=np.int32)
        print(f"  joined: {len(X)} rows  misses: {miss}  resid_mean={y_resid.mean():+.4f}  resid_mae={np.abs(y_resid).mean():.4f}")

        saved, stat_report = _train_one_stat(stat, X, y_resid, folds, fc)
        if saved:
            report["trained_stats"].append(stat_report)
        else:
            report["skipped_stats"].append(stat_report)

    report_path = os.path.join(OUT_DIR, "training_report.json")
    with open(report_path, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2)

    print(f"\nTraining report -> {report_path}")
    trained = [r["stat"] for r in report["trained_stats"] if isinstance(r, dict)]
    print(f"Heads saved: {trained or 'none'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
