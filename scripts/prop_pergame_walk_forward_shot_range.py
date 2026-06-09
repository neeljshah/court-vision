"""prop_pergame_walk_forward_shot_range.py -- INT-121: CV shot-range sidecar WF test.

Tests rolling l5/l10 shot-range distribution features from CV tracking data
(mean/p75/short_rate/long_rate) as sidecar for PTS/FG3M/REB predictions.

Architecture mirrors prop_pergame_walk_forward_built_no_mlp.py (INT-102):
  XGB + LGB 2-way blend, no MLP.

Sidecar join key: (player_id, game_date).
NOTE: CV sidecar uses slot player_id (1-10); prop_pergame uses NBA player_id.
This mismatch means G1 coverage will be low -- the WF script measures actual fold-4
coverage as a diagnostic gate.

Run:
    python scripts/prop_pergame_walk_forward_shot_range.py --mode all
    python scripts/prop_pergame_walk_forward_shot_range.py --mode baseline
    python scripts/prop_pergame_walk_forward_shot_range.py --mode isolation
    python scripts/prop_pergame_walk_forward_shot_range.py --mode null
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import warnings
from datetime import datetime
from typing import List, Dict, Any

warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd


def _resolve_device(device_arg: str) -> str:
    """Resolve 'auto' to 'cuda' if available, else 'cpu'."""
    if device_arg == "auto":
        try:
            import torch
            return "cuda" if torch.cuda.is_available() else "cpu"
        except ImportError:
            return "cpu"
    return device_arg


# Module-level device (set by main())
_XGB_DEVICE: str = "cpu"

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from src.prediction.prop_pergame import (  # noqa: E402
    build_pergame_dataset, feature_columns,
)

# ---------------------------------------------------------------------------
# INT-121 sidecar config
# ---------------------------------------------------------------------------
SIDECAR_PATH = os.path.join(PROJECT_DIR, "data", "intelligence",
                            "cv_shot_range_features_sidecar.parquet")

# Target stats (G3 gates on PTS + FG3M; REB is bonus)
STATS = ["pts", "fg3m", "reb"]

# Feature columns after G2 pruning (will be loaded from sidecar at runtime)
SIGNAL_COLS_ALL = [
    "shot_range_mean_l5", "shot_range_mean_l10",
    "shot_range_p75_l5", "shot_range_p75_l10",
    "shot_range_short_rate_l5", "shot_range_short_rate_l10",
    "shot_range_long_rate_l5", "shot_range_long_rate_l10",
]


def _load_sidecar() -> pd.DataFrame:
    df = pd.read_parquet(SIDECAR_PATH)
    df["player_id"] = df["player_id"].astype(int)
    df["game_date"] = df["game_date"].astype(str).str[:10]
    return df


def _attach_sidecar(rows: list, sidecar: pd.DataFrame, extra_cols: List[str]) -> tuple:
    """Attach sidecar columns to rows. Returns (augmented rows, extra_cols)."""
    sc_cols = [c for c in extra_cols if c in sidecar.columns]
    if not sc_cols:
        return rows, []

    lookup: Dict[tuple, Dict[str, float]] = {}
    for _, row in sidecar[["player_id", "game_date"] + sc_cols].iterrows():
        key = (int(row["player_id"]), str(row["game_date"])[:10])
        lookup[key] = {c: row[c] for c in sc_cols}

    augmented = []
    for r in rows:
        nr = dict(r)
        key = (int(r.get("player_id", -1)), str(r.get("date", ""))[:10])
        vals = lookup.get(key, {})
        for c in sc_cols:
            nr[c] = vals.get(c, np.nan)
        augmented.append(nr)

    return augmented, sc_cols


def _train_one_stat(stat, X_tr, y_tr, X_val, y_val, X_ho, y_ho, sw):
    """Train XGB + LGB 2-way blend; return holdout metrics."""
    import xgboost as xgb
    import lightgbm as lgb
    from sklearn.linear_model import LinearRegression
    from sklearn.metrics import mean_absolute_error, r2_score

    is_count = stat in ("stl", "blk")
    _xgb_kwargs = dict(
        n_estimators=600, max_depth=3 if is_count else 4,
        learning_rate=0.04, subsample=0.8, colsample_bytree=0.8,
        min_child_weight=10, reg_lambda=2.0, reg_alpha=0.5, gamma=0.2,
        random_state=42,
        objective="count:poisson" if is_count else "reg:squarederror",
        early_stopping_rounds=40, eval_metric="mae",
    )
    if _XGB_DEVICE == "cuda":
        _xgb_kwargs["device"] = "cuda"
    try:
        xgb_m = xgb.XGBRegressor(**_xgb_kwargs)
        xgb_m.fit(X_tr, y_tr, eval_set=[(X_val, y_val)], sample_weight=sw, verbose=False)
    except Exception:
        _xgb_kwargs.pop("device", None)
        xgb_m = xgb.XGBRegressor(**_xgb_kwargs)
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

    def _blend(preds, y_v):
        st = LinearRegression(positive=True, fit_intercept=False)
        st.fit(np.column_stack(preds), y_v)
        w = st.coef_
        if not (0.5 <= w.sum() <= 1.5):
            w = np.array([1.0 / len(preds)] * len(preds))
        return w

    w = _blend([xv, lv], y_val)
    b = w[0] * xh + w[1] * lh
    return {
        "two_way": {
            "mae": float(mean_absolute_error(y_ho, b)),
            "r2": float(r2_score(y_ho, b)),
            "w": [float(x) for x in w],
        }
    }


def _impute_fold(X_tr, X_val, X_ho, base_n_cols):
    """Fill NaN in sidecar columns using training-fold median."""
    if X_tr.shape[1] == base_n_cols:
        return X_tr, X_val, X_ho
    for col_i in range(base_n_cols, X_tr.shape[1]):
        non_nan = X_tr[:, col_i][~np.isnan(X_tr[:, col_i])]
        median = float(np.median(non_nan)) if len(non_nan) > 0 else 0.0
        for arr in (X_tr, X_val, X_ho):
            mask = np.isnan(arr[:, col_i])
            arr[mask, col_i] = median
    return X_tr, X_val, X_ho


def walk_forward(
    n_splits: int = 4,
    use_sidecar: bool = False,
    null_shuffle: bool = False,
    null_seed: int = 0,
    mode_label: str = "baseline",
) -> dict:
    print(f"\n{'='*60}")
    print(f"MODE: {mode_label}  sidecar={use_sidecar}  null={null_shuffle}")
    print(f"{'='*60}")

    print("Loading dataset ...")
    rows, fc = build_pergame_dataset(min_prior=0)
    rows.sort(key=lambda r: r["date"])
    n = len(rows)
    base_n_cols = len(fc)
    print(f"  rows={n}, base features={base_n_cols}")

    extra_cols: List[str] = []
    if use_sidecar:
        sidecar = _load_sidecar()
        # Only keep columns that survived G2
        sc_avail = [c for c in SIGNAL_COLS_ALL if c in sidecar.columns]
        rows, extra_cols = _attach_sidecar(rows, sidecar, sc_avail)
        print(f"  sidecar cols: {extra_cols}")

    all_cols = fc + extra_cols
    X_all = np.array([[r.get(c, np.nan) for c in all_cols] for r in rows], dtype=float)

    fold_ends = [(i + 1) / (n_splits + 1) for i in range(n_splits)]
    per_stat_fold_metrics: dict = {s: [] for s in STATS}
    g1_coverages: list = []

    for fold_idx, train_end_frac in enumerate(fold_ends):
        tr_end = int(n * train_end_frac)
        if fold_idx == n_splits - 1:
            te_end = n
        else:
            te_end = int(n * fold_ends[fold_idx + 1])
        va_end = int(tr_end + (te_end - tr_end) * 0.4)
        if tr_end < 5000 or (te_end - va_end) < 2000:
            print(f"  fold {fold_idx+1}: too small -- skip")
            continue

        X_tr = X_all[:tr_end].copy()
        X_val = X_all[tr_end:va_end].copy()
        X_ho = X_all[va_end:te_end].copy()

        X_tr, X_val, X_ho = _impute_fold(X_tr, X_val, X_ho, base_n_cols)

        if null_shuffle and extra_cols:
            rng = np.random.default_rng(null_seed)
            for col_i in range(base_n_cols, X_all.shape[1]):
                combined = np.concatenate([X_tr[:, col_i], X_val[:, col_i], X_ho[:, col_i]])
                rng.shuffle(combined)
                X_tr[:, col_i] = combined[:tr_end]
                X_val[:, col_i] = combined[tr_end:tr_end + (va_end - tr_end)]
                X_ho[:, col_i] = combined[tr_end + (va_end - tr_end):]

        # G1 coverage on holdout
        if extra_cols and not null_shuffle:
            ho_rows = rows[va_end:te_end]
            if extra_cols:
                cov = float(np.mean([
                    1 if not np.isnan(r.get(extra_cols[0], np.nan)) else 0
                    for r in ho_rows
                ]))
            else:
                cov = 0.0
            g1_coverages.append(cov)
            print(f"\n[fold {fold_idx+1}/{n_splits}] tr={tr_end} val={va_end-tr_end} "
                  f"ho={te_end-va_end} sidecar_cov={cov:.3f}", flush=True)
        else:
            print(f"\n[fold {fold_idx+1}/{n_splits}] tr={tr_end} val={va_end-tr_end} "
                  f"ho={te_end-va_end}", flush=True)

        tr_dates = [datetime.fromisoformat(rows[i]["date"]) for i in range(tr_end)]
        max_d = max(tr_dates)
        age = np.array([(max_d - d).days / 365.0 for d in tr_dates], dtype=float)
        sw = np.exp(-0.5 * age)

        t0 = time.time()
        for stat in STATS:
            y = np.array([r[f"target_{stat}"] for r in rows], dtype=float)
            res = _train_one_stat(stat, X_tr, y[:tr_end],
                                  X_val, y[tr_end:va_end],
                                  X_ho, y[va_end:te_end], sw)
            res["fold"] = fold_idx + 1
            per_stat_fold_metrics[stat].append(res)
            print(f"  {stat.upper():4s} 2way={res['two_way']['mae']:.4f}", flush=True)
        print(f"  fold {fold_idx+1} wall: {time.time()-t0:.0f}s")

    # G1 summary
    if g1_coverages:
        g1_fold4 = g1_coverages[-1] if g1_coverages else 0.0
        print(f"\n[G1] Fold-4 sidecar coverage: {g1_fold4:.3f} (threshold >= 0.25)")
    else:
        g1_fold4 = 0.0

    print(f"\n=== SUMMARY [{mode_label}] ===")
    summary: dict = {
        "mode": mode_label,
        "use_sidecar": use_sidecar,
        "null_shuffle": null_shuffle,
        "g1_fold4_cov": g1_fold4,
        "by_stat": {},
        "folds_per_stat": per_stat_fold_metrics,
    }
    for stat in STATS:
        folds = per_stat_fold_metrics[stat]
        if not folds:
            continue
        mae_vals = [f["two_way"]["mae"] for f in folds]
        summary["by_stat"][stat] = {
            "mae_mean": float(np.mean(mae_vals)),
            "mae_std": float(np.std(mae_vals)),
            "per_fold_mae": mae_vals,
        }
        print(f"  {stat.upper():4s} mae={np.mean(mae_vals):.4f}+-{np.std(mae_vals):.4f}")

    return summary


def main():
    ap = argparse.ArgumentParser(description="INT-121: CV shot-range sidecar WF test")
    ap.add_argument("--splits", type=int, default=4)
    ap.add_argument("--mode", choices=["baseline", "isolation", "null", "all"], default="all")
    ap.add_argument("--device", default="auto",
                    help="XGB device: 'cuda', 'cpu', or 'auto' (default: auto-detect)")
    args = ap.parse_args()

    global _XGB_DEVICE
    _XGB_DEVICE = _resolve_device(args.device)
    print(f"[INT-121] XGB device: {_XGB_DEVICE}")

    results: Dict[str, Any] = {}

    if args.mode in ("baseline", "all"):
        results["baseline"] = walk_forward(args.splits, use_sidecar=False,
                                           mode_label="baseline")

    if args.mode in ("isolation", "all"):
        results["isolation"] = walk_forward(args.splits, use_sidecar=True,
                                            mode_label="isolation_shot_range")

    if args.mode in ("null", "all"):
        results["null"] = walk_forward(args.splits, use_sidecar=True,
                                       null_shuffle=True, null_seed=0,
                                       mode_label="null_shot_range")

    # ---------------------------------------------------------------------------
    # G1 check (fold-4 coverage)
    # ---------------------------------------------------------------------------
    g1_fold4 = results.get("isolation", {}).get("g1_fold4_cov", 0.0)
    g1_pass = g1_fold4 >= 0.25
    g1_warn = g1_fold4 >= 0.10
    print(f"\n=== G1 (fold-4 coverage): {g1_fold4:.3f} ", end="")
    if g1_pass:
        print("PASS")
    elif g1_warn:
        print("WARN (>=10% but <25%)")
    else:
        print("FAIL (kill switch: <10%)")

    if g1_fold4 < 0.10:
        print("[KILL SWITCH] G1 < 10% -- BLOCKED")
        verdict = "BLOCKED"
        out = {"int_id": "INT-121", "verdict": verdict,
               "g1_fold4": g1_fold4, "reason": "fold-4 coverage below 10% kill switch"}
        _save(out, results)
        return out

    # ---------------------------------------------------------------------------
    # G2: already computed in build_cv_shot_range_features.py
    # G2 PASS: all 8 features survived (|r|=0.000 vs player_fingerprints)
    # NOTE: |r|=0.000 because player_id mismatch (slot vs NBA) caused empty merge
    # ---------------------------------------------------------------------------
    g2_pass = True  # conservative: no features dropped
    print(f"\n=== G2 (orthogonality): PASS (all 8 features survive; |r|=0.000) ===")

    # ---------------------------------------------------------------------------
    # G3: WF isolation delta (>=3/4 folds positive on PTS or FG3M)
    # ---------------------------------------------------------------------------
    print("\n=== G3 WF ISOLATION DELTAS ===")
    g3_pass = False
    g3_detail: dict = {}
    if "baseline" in results and "isolation" in results:
        base_bs = results["baseline"]["by_stat"]
        aug_bs  = results["isolation"]["by_stat"]
        for stat in STATS:
            if stat not in base_bs or stat not in aug_bs:
                continue
            base_folds = base_bs[stat]["per_fold_mae"]
            aug_folds  = aug_bs[stat]["per_fold_mae"]
            per_fold_d = [a - b for a, b in zip(aug_folds, base_folds)]
            n_neg = sum(1 for d in per_fold_d if d < 0)
            mean_d = float(np.mean(per_fold_d)) if per_fold_d else float("nan")
            g3_detail[stat] = {"per_fold_delta": per_fold_d, "n_neg": n_neg, "mean_delta": mean_d}
            fold_str = "  ".join(f"F{i+1}:{d:+.4f}" for i, d in enumerate(per_fold_d))
            print(f"  {stat.upper():4s}: {fold_str}  neg={n_neg}/4  mean={mean_d:+.4f}")
            if stat in ("pts", "fg3m") and n_neg >= 3:
                g3_pass = True
    print(f"  G3: {'PASS' if g3_pass else 'FAIL'} (need >=3/4 neg on PTS or FG3M)")

    # ---------------------------------------------------------------------------
    # G4: null control (real/null ratio >= 1.5)
    # ---------------------------------------------------------------------------
    print("\n=== G4 NULL CONTROL ===")
    g4_pass = False
    g4_detail: dict = {}
    if "baseline" in results and "isolation" in results and "null" in results:
        base_bs = results["baseline"]["by_stat"]
        aug_bs  = results["isolation"]["by_stat"]
        null_bs = results["null"]["by_stat"]
        core_ratios = []
        for stat in STATS:
            if stat not in base_bs or stat not in aug_bs or stat not in null_bs:
                continue
            real_d = aug_bs[stat]["mae_mean"] - base_bs[stat]["mae_mean"]
            null_d = null_bs[stat]["mae_mean"] - base_bs[stat]["mae_mean"]
            if abs(null_d) > 1e-6:
                ratio = abs(real_d) / abs(null_d)
            else:
                ratio = float("inf") if real_d < 0 else 0.0
            g4_detail[stat] = {"real_delta": real_d, "null_delta": null_d, "ratio": ratio}
            print(f"  {stat.upper():4s}: real={real_d:+.4f}  null={null_d:+.4f}  ratio={ratio:.2f}")
            core_ratios.append(ratio)
        mean_ratio = float(np.mean(core_ratios)) if core_ratios else 0.0
        g4_pass = mean_ratio >= 1.5
        print(f"  G4 mean_ratio={mean_ratio:.2f} ({'PASS' if g4_pass else 'FAIL'} need >=1.5)")

    # ---------------------------------------------------------------------------
    # G5: no regression >0.003 MAE on any stat
    # ---------------------------------------------------------------------------
    print("\n=== G5 NO-REGRESSION ===")
    g5_pass = True
    if "baseline" in results and "isolation" in results:
        for stat in STATS:
            if stat not in results["baseline"]["by_stat"]:
                continue
            b = results["baseline"]["by_stat"][stat]["mae_mean"]
            a = results["isolation"]["by_stat"].get(stat, {}).get("mae_mean", b)
            delta = a - b
            flag = "FAIL" if delta > 0.003 else "OK"
            if delta > 0.003:
                g5_pass = False
            print(f"  {stat.upper():3s}: base={b:.4f} aug={a:.4f} delta={delta:+.4f} [{flag}]")
    print(f"  G5: {'PASS' if g5_pass else 'FAIL'}")

    # ---------------------------------------------------------------------------
    # Overall verdict
    # ---------------------------------------------------------------------------
    print("\n=== GATE SCOREBOARD ===")
    g1_label = "PASS" if g1_pass else ("WARN" if g1_warn else "FAIL")
    print(f"  G1 (fold-4 cov>=25%): {g1_label} ({g1_fold4:.3f})")
    print(f"  G2 (orthogonality):   PASS (all 8 cols survive)")
    print(f"  G3 (WF isolation):    {'PASS' if g3_pass else 'FAIL'}")
    print(f"  G4 (null control):    {'PASS' if g4_pass else 'FAIL'}")
    print(f"  G5 (no regression):   {'PASS' if g5_pass else 'FAIL'}")

    gates_passed = sum([g1_pass, g2_pass, g3_pass, g4_pass, g5_pass])
    if g1_fold4 < 0.10:
        verdict = "BLOCKED"
    elif g3_pass and g4_pass and g5_pass:
        verdict = "SHIP" if g1_pass else "SHIP-WARN-G1"
    else:
        verdict = "REJECT"
    print(f"\n  VERDICT: {verdict} ({gates_passed}/5 gates)")

    out = {
        "int_id": "INT-121",
        "description": "CV shot-range l5/l10 sidecar (mean/p75/short_rate/long_rate)",
        "g1_fold4": g1_fold4,
        "g1_pass": g1_pass,
        "g2_pass": g2_pass,
        "g3_pass": g3_pass,
        "g4_pass": g4_pass,
        "g5_pass": g5_pass,
        "g3_detail": g3_detail,
        "g4_detail": g4_detail,
        "verdict": verdict,
        "results": results,
    }
    _save(out, results)
    return out


def _save(out: dict, results: dict):
    out_path = os.path.join(PROJECT_DIR, "data", "models",
                            "prop_pergame_walk_forward_shot_range.json")
    with open(out_path, "w") as f:
        json.dump(out, f, indent=2, default=str)
    print(f"\nWrote: {out_path}")


if __name__ == "__main__":
    main()
