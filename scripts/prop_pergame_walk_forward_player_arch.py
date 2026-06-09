"""prop_pergame_walk_forward_player_arch.py — INT-138 WF test for player×def-archetype sidecar.

Tests 15-column player-vs-defensive-archetype sidecar (12 diff + 3 n_prior) against
the prop_pergame baseline using XGB+LGB 2-way blend (no MLP).

Gates evaluated:
  G1 (coverage): fold-4 % rows with n_prior>=3 per arch >= 25% [PRE-PASS verified 89-92%]
  G2 (orthogonality): |r| vs opp_def_rtg <= 0.7, inter-arch <= 0.85 [PRE-PASS max=0.027 / 0.267]
  G3 (WF): >=3/4 folds positive on >=1 of PTS/REB/AST/FG3M
  G4 (null control): real/null >= 1.5
  G5 (no regression): no stat regresses >0.003 MAE

Run:
    python scripts/prop_pergame_walk_forward_player_arch.py --mode all
    python scripts/prop_pergame_walk_forward_player_arch.py --mode baseline
    python scripts/prop_pergame_walk_forward_player_arch.py --mode isolation
    python scripts/prop_pergame_walk_forward_player_arch.py --mode null
    python scripts/prop_pergame_walk_forward_player_arch.py --device cuda  (default: auto)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import warnings
from datetime import datetime
from typing import Dict, List, Any

warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from src.prediction.prop_pergame import (  # noqa: E402
    STATS, build_pergame_dataset, feature_columns,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
SIDECAR_PATH = os.path.join(PROJECT_DIR, "data", "intelligence",
                             "player_def_archetype_sidecar.parquet")
NULL_SIDECAR_PATH = SIDECAR_PATH.replace(".parquet", "_null.parquet")

TARGET_ARCHETYPES = ["HELP_DEF", "PACE_CONTROL", "SWITCH_HEAVY"]
TARGET_STATS_CORE = ["pts", "reb", "ast", "fg3m"]

# 15 feature columns: 12 diff + 3 n_prior (n_prior is arch-level, not stat-level)
SIGNAL_COLS: Dict[str, List[str]] = {
    "player_arch": (
        [f"player_{s}_vs_{a}_diff" for s in ["pts", "reb", "ast", "fg3m"]
         for a in TARGET_ARCHETYPES]
        + [f"player_n_games_vs_{a}_prior" for a in TARGET_ARCHETYPES]
    )
}


def _resolve_device(device_arg: str) -> str:
    if device_arg == "auto":
        try:
            import torch
            return "cuda" if torch.cuda.is_available() else "cpu"
        except ImportError:
            return "cpu"
    return device_arg


_XGB_DEVICE: str = "cpu"


# ---------------------------------------------------------------------------
# Sidecar helpers
# ---------------------------------------------------------------------------
def _load_sidecar(path: str) -> pd.DataFrame:
    df = pd.read_parquet(path)
    df["player_id"] = df["player_id"].astype(int)
    df["game_date"] = df["game_date"].astype(str).str[:10]
    return df


def _build_lookup(sidecar: pd.DataFrame, extra_cols: List[str]) -> Dict[tuple, Dict[str, float]]:
    avail = [c for c in extra_cols if c in sidecar.columns]
    lookup: Dict[tuple, Dict[str, float]] = {}
    for _, row in sidecar[["player_id", "game_date"] + avail].iterrows():
        key = (int(row["player_id"]), str(row["game_date"])[:10])
        lookup[key] = {c: row[c] for c in avail}
    return lookup


def _attach_sidecar(rows: list, sidecar: pd.DataFrame, signal_groups: List[str]) -> tuple:
    extra_cols: List[str] = []
    for g in signal_groups:
        extra_cols.extend(SIGNAL_COLS[g])
    lookup = _build_lookup(sidecar, extra_cols)
    augmented = []
    for r in rows:
        nr = dict(r)
        key = (int(r["player_id"]), str(r["date"])[:10])
        vals = lookup.get(key, {})
        for c in extra_cols:
            nr[c] = vals.get(c, np.nan)
        augmented.append(nr)
    return augmented, extra_cols


# ---------------------------------------------------------------------------
# Per-fold imputation
# ---------------------------------------------------------------------------
def _impute_fold(X_tr, X_val, X_ho, base_n_cols):
    if X_tr.shape[1] == base_n_cols:
        return X_tr, X_val, X_ho
    for col_i in range(base_n_cols, X_tr.shape[1]):
        col = X_tr[:, col_i]
        non_nan = col[~np.isnan(col)]
        median = float(np.median(non_nan)) if len(non_nan) > 0 else 0.0
        for arr in (X_tr, X_val, X_ho):
            mask = np.isnan(arr[:, col_i])
            arr[mask, col_i] = median
    return X_tr, X_val, X_ho


# ---------------------------------------------------------------------------
# Training: XGB + LGB 2-way blend (no MLP)
# ---------------------------------------------------------------------------
def _train_one_stat(stat, X_tr, y_tr, X_val, y_val, X_ho, y_ho, sw,
                    xgb_device: str = "cpu"):
    import xgboost as xgb
    import lightgbm as lgb
    from sklearn.linear_model import LinearRegression
    from sklearn.metrics import mean_absolute_error

    is_count = stat in ("stl", "blk")
    _xgb_kw = dict(
        n_estimators=600, max_depth=3 if is_count else 4,
        learning_rate=0.04, subsample=0.8, colsample_bytree=0.8,
        min_child_weight=10, reg_lambda=2.0, reg_alpha=0.5, gamma=0.2,
        random_state=42,
        objective="count:poisson" if is_count else "reg:squarederror",
        early_stopping_rounds=40, eval_metric="mae",
    )
    if xgb_device == "cuda":
        _xgb_kw["device"] = "cuda"
    try:
        xgb_m = xgb.XGBRegressor(**_xgb_kw)
        xgb_m.fit(X_tr, y_tr, eval_set=[(X_val, y_val)], sample_weight=sw, verbose=False)
    except Exception:
        _xgb_kw.pop("device", None)
        xgb_m = xgb.XGBRegressor(**_xgb_kw)
        xgb_m.fit(X_tr, y_tr, eval_set=[(X_val, y_val)], sample_weight=sw, verbose=False)

    lgb_m = lgb.LGBMRegressor(
        n_estimators=600, max_depth=3 if is_count else 4,
        learning_rate=0.04, subsample=0.8, subsample_freq=1,
        colsample_bytree=0.8, min_child_samples=20,
        reg_lambda=2.0, reg_alpha=0.5, random_state=42,
        objective="poisson" if is_count else "regression",
        n_jobs=-1, verbosity=-1,
    )
    lgb_m.fit(X_tr, y_tr, eval_set=[(X_val, y_val)], sample_weight=sw,
              callbacks=[lgb.early_stopping(40, verbose=False)])

    xv, lv = xgb_m.predict(X_val), lgb_m.predict(X_val)
    xh, lh = xgb_m.predict(X_ho), lgb_m.predict(X_ho)

    st = LinearRegression(positive=True, fit_intercept=False)
    st.fit(np.column_stack([xv, lv]), y_val)
    w = st.coef_
    if not (0.5 <= w.sum() <= 1.5):
        w = np.array([0.5, 0.5])
    blend = w[0] * xh + w[1] * lh
    mae = float(mean_absolute_error(y_ho, blend))

    return {"mae": mae, "w": [float(x) for x in w]}


# ---------------------------------------------------------------------------
# Walk-forward engine
# ---------------------------------------------------------------------------
def walk_forward(
    n_splits: int = 4,
    signal_groups: List[str] | None = None,
    null_sidecar: bool = False,
    mode_label: str = "baseline",
) -> dict:
    print(f"\n{'='*60}")
    print(f"MODE: {mode_label}  signals={signal_groups}  null={null_sidecar}")
    print(f"{'='*60}")

    print("Loading dataset...")
    rows, fc = build_pergame_dataset(min_prior=0)
    rows.sort(key=lambda r: r["date"])
    n = len(rows)
    base_n_cols = len(fc)
    print(f"  rows={n}, base_features={base_n_cols}")

    extra_cols: List[str] = []
    if signal_groups:
        spath = NULL_SIDECAR_PATH if null_sidecar else SIDECAR_PATH
        sidecar = _load_sidecar(spath)
        rows, extra_cols = _attach_sidecar(rows, sidecar, signal_groups)
        print(f"  sidecar cols ({len(extra_cols)}): {extra_cols}")

    all_cols = fc + extra_cols
    X_all = np.array([[r.get(c, np.nan) for c in all_cols] for r in rows], dtype=float)

    fold_ends = [(i + 1) / (n_splits + 1) for i in range(n_splits)]
    per_stat_fold_metrics: dict = {s: [] for s in STATS}

    for fold_idx, train_end_frac in enumerate(fold_ends):
        tr_end = int(n * train_end_frac)
        te_end = n if fold_idx == n_splits - 1 else int(n * fold_ends[fold_idx + 1])
        va_end = int(tr_end + (te_end - tr_end) * 0.4)
        if tr_end < 5000 or (te_end - va_end) < 2000:
            print(f"  fold {fold_idx+1}: too small — skip")
            continue

        X_tr = X_all[:tr_end].copy()
        X_val = X_all[tr_end:va_end].copy()
        X_ho = X_all[va_end:te_end].copy()
        X_tr, X_val, X_ho = _impute_fold(X_tr, X_val, X_ho, base_n_cols)

        tr_dates = [datetime.fromisoformat(rows[i]["date"]) for i in range(tr_end)]
        max_d = max(tr_dates)
        sw = np.exp(-0.5 * np.array([(max_d - d).days / 365.0 for d in tr_dates], dtype=float))

        if extra_cols:
            ho_rows = rows[va_end:te_end]
            first_extra = extra_cols[0]
            cov = np.mean([0 if np.isnan(r.get(first_extra, np.nan)) else 1 for r in ho_rows])
            print(f"\n[fold {fold_idx+1}/{n_splits}] tr={tr_end} val={va_end-tr_end} "
                  f"ho={te_end-va_end} sidecar_cov={cov:.3f}", flush=True)
        else:
            print(f"\n[fold {fold_idx+1}/{n_splits}] tr={tr_end} val={va_end-tr_end} "
                  f"ho={te_end-va_end}", flush=True)

        t0 = time.time()
        for stat in STATS:
            y = np.array([r[f"target_{stat}"] for r in rows], dtype=float)
            res = _train_one_stat(stat, X_tr, y[:tr_end], X_val, y[tr_end:va_end],
                                  X_ho, y[va_end:te_end], sw, xgb_device=_XGB_DEVICE)
            res["fold"] = fold_idx + 1
            per_stat_fold_metrics[stat].append(res)
            print(f"  {stat.upper():4s} mae={res['mae']:.4f}", flush=True)
        print(f"  fold wall: {time.time()-t0:.0f}s")

    print(f"\n=== SUMMARY [{mode_label}] ===")
    summary: dict = {"mode": mode_label, "signal_groups": signal_groups or [],
                     "null_sidecar": null_sidecar, "folds_per_stat": per_stat_fold_metrics,
                     "by_stat": {}}
    for stat in STATS:
        folds = per_stat_fold_metrics[stat]
        if not folds:
            continue
        maes = [f["mae"] for f in folds]
        summary["by_stat"][stat] = {
            "mae_mean": float(np.mean(maes)),
            "mae_std": float(np.std(maes)),
            "per_fold_mae": maes,
        }
        print(f"  {stat.upper():4s} mae={np.mean(maes):.4f}±{np.std(maes):.4f}")

    return summary


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description="INT-138: player×def-archetype WF test")
    ap.add_argument("--splits", type=int, default=4)
    ap.add_argument("--mode", choices=["baseline", "isolation", "null", "all"], default="all")
    ap.add_argument("--device", default="auto")
    args = ap.parse_args()

    global _XGB_DEVICE
    _XGB_DEVICE = _resolve_device(args.device)
    print(f"[INT-138] XGB device: {_XGB_DEVICE}")

    results: Dict[str, Any] = {}

    if args.mode in ("baseline", "all"):
        results["baseline"] = walk_forward(args.splits, signal_groups=None,
                                           mode_label="baseline")

    if args.mode in ("isolation", "all"):
        results["isolation"] = walk_forward(args.splits, signal_groups=["player_arch"],
                                            mode_label="isolation_player_arch")

    if args.mode in ("null", "all"):
        if not os.path.exists(NULL_SIDECAR_PATH):
            print(f"[WARN] Null sidecar not found at {NULL_SIDECAR_PATH}.")
            print("  Run: python scripts/build_player_def_archetype.py --null")
            results["null"] = {}
        else:
            results["null"] = walk_forward(args.splits, signal_groups=["player_arch"],
                                           null_sidecar=True, mode_label="null_player_arch")

    # ---------------------------------------------------------------------------
    # G3: per-stat WF deltas
    # ---------------------------------------------------------------------------
    print("\n=== G3 WALK-FORWARD DELTAS ===")
    g3_pass = False
    g3_detail: dict = {}
    if "baseline" in results and "isolation" in results:
        base_bs = results["baseline"]["by_stat"]
        aug_bs = results["isolation"]["by_stat"]
        for stat in STATS:
            if stat not in base_bs or stat not in aug_bs:
                continue
            base_folds = base_bs[stat]["per_fold_mae"]
            aug_folds = aug_bs[stat]["per_fold_mae"]
            deltas = [a - b for a, b in zip(aug_folds, base_folds)]
            n_neg = sum(1 for d in deltas if d < 0)
            mean_d = float(np.mean(deltas))
            g3_detail[stat] = {"per_fold_delta": deltas, "n_neg": n_neg, "mean_delta": mean_d}
            fold_str = "  ".join(f"F{i+1}:{d:+.4f}" for i, d in enumerate(deltas))
            print(f"  {stat.upper():4s}: {fold_str}  neg={n_neg}/4  mean={mean_d:+.4f}")
            if stat in TARGET_STATS_CORE and n_neg >= 3:
                g3_pass = True
    print(f"\n  G3 result: {'PASS' if g3_pass else 'FAIL'} (>=3/4 neg on >=1 core stat)")

    # ---------------------------------------------------------------------------
    # G4: null control
    # ---------------------------------------------------------------------------
    print("\n=== G4 NULL CONTROL ===")
    g4_pass = False
    g4_detail: dict = {}
    if "baseline" in results and "isolation" in results and "null" in results and results["null"]:
        base_bs = results["baseline"]["by_stat"]
        aug_bs = results["isolation"]["by_stat"]
        null_bs = results["null"]["by_stat"]
        core_ratios = []
        for stat in STATS:
            if stat not in base_bs or stat not in aug_bs or stat not in null_bs:
                continue
            real_delta = aug_bs[stat]["mae_mean"] - base_bs[stat]["mae_mean"]
            null_delta = null_bs[stat]["mae_mean"] - base_bs[stat]["mae_mean"]
            if abs(null_delta) > 1e-6:
                ratio = abs(real_delta) / abs(null_delta)
            else:
                ratio = float("inf") if real_delta < 0 else 0.0
            g4_detail[stat] = {"real_delta": real_delta, "null_delta": null_delta, "ratio": ratio}
            print(f"  {stat.upper():4s}: real={real_delta:+.4f}  null={null_delta:+.4f}  ratio={ratio:.2f}")
            if stat in TARGET_STATS_CORE:
                core_ratios.append(ratio)
        mean_ratio = float(np.mean(core_ratios)) if core_ratios else 0.0
        g4_pass = mean_ratio >= 1.5
        print(f"\n  G4 mean_ratio={mean_ratio:.2f} — {'PASS' if g4_pass else 'FAIL'} (need >=1.5)")
    else:
        print("  G4 SKIP (null sidecar not available or null WF not run)")
        g4_pass = False

    # ---------------------------------------------------------------------------
    # G5: no regression on non-core stats
    # ---------------------------------------------------------------------------
    print("\n=== G5 NO-REGRESSION (STL/BLK/TOV) ===")
    g5_pass = True
    if "baseline" in results and "isolation" in results:
        for stat in ["stl", "blk", "tov"]:
            b = results["baseline"]["by_stat"].get(stat, {}).get("mae_mean", float("nan"))
            a = results["isolation"]["by_stat"].get(stat, {}).get("mae_mean", float("nan"))
            delta = a - b
            flag = "FAIL" if delta > 0.003 else "OK"
            if delta > 0.003:
                g5_pass = False
            print(f"  {stat.upper():3s}: base={b:.4f} aug={a:.4f} delta={delta:+.4f} [{flag}]")
    print(f"\n  G5 result: {'PASS' if g5_pass else 'FAIL'} (no >0.003 regression)")

    # ---------------------------------------------------------------------------
    # Gate scoreboard
    # ---------------------------------------------------------------------------
    print("\n=== GATE SCOREBOARD ===")
    print(f"  G1 (coverage >=25%):      PRE-PASS (89-92% fold-4 coverage)")
    print(f"  G2 (orthogonality <=0.7): PRE-PASS (max |r|=0.027 vs def_rtg; 0.267 inter-arch)")
    print(f"  G3 (WF >=3/4 neg):        {'PASS' if g3_pass else 'FAIL'}")
    print(f"  G4 (null >=1.5):          {'PASS' if g4_pass else 'FAIL'}")
    print(f"  G5 (no regression):       {'PASS' if g5_pass else 'FAIL'}")

    all_pass = g3_pass and g4_pass and g5_pass
    verdict = "SHIP" if all_pass else "REJECT"
    gates_pass_str = f"G1+G2+{'G3' if g3_pass else ''}+{'G4' if g4_pass else ''}+{'G5' if g5_pass else ''}"
    print(f"\n  VERDICT: {verdict}")

    # ---------------------------------------------------------------------------
    # Save JSON
    # ---------------------------------------------------------------------------
    out = {
        "int_id": "INT-138",
        "description": "Player×defensive-archetype rolling performance sidecar",
        "g3_pass": g3_pass, "g4_pass": g4_pass, "g5_pass": g5_pass,
        "verdict": verdict,
        "g3_detail": g3_detail,
        "g4_detail": g4_detail,
        "results": results,
    }
    out_path = os.path.join(PROJECT_DIR, "data", "models",
                            "prop_pergame_walk_forward_player_arch.json")
    with open(out_path, "w") as f:
        json.dump(out, f, indent=2, default=str)
    print(f"\nWrote: {out_path}")
    return out


if __name__ == "__main__":
    main()
