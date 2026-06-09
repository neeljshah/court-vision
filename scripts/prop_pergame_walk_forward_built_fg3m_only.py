"""prop_pergame_walk_forward_built_fg3m_only.py — INT-107: FG3M-ONLY ft_rate sidecar re-test.

Hypothesis: ft_rate is a stat-specific signal for FG3M only (confirmed 4/4 folds in INT-102).
This driver restricts STATS=["fg3m"] and uses 2-way XGB+LGB (same architecture as INT-102
baseline), making the architecture-parity kill switch inapplicable.

Gates evaluated:
  G1 (coverage):            PRE-RESOLVED (INT-94 confirmed 91% fold-4 coverage)
  G2 (FG3M WF >=3/4 neg):  tested here — target 4/4 to confirm INT-102
  G3 (null ratio >=1.5):    tested here — INT-102 had 3.43, expect similar
  G4 (no regression >=0.001 improvement): tested here on FG3M aggregate
  G5 (prod-arch cost):      no-MLP 2-way baseline vs 3-way prod on FG3M only

Run:
    python scripts/prop_pergame_walk_forward_built_fg3m_only.py --mode all
    python scripts/prop_pergame_walk_forward_built_fg3m_only.py --mode baseline
    python scripts/prop_pergame_walk_forward_built_fg3m_only.py --mode isolation
    python scripts/prop_pergame_walk_forward_built_fg3m_only.py --mode null
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
# INT-107: FG3M ONLY — stat restriction
# ---------------------------------------------------------------------------
STATS_FG3M = ["fg3m"]

# INT-83 ft_rate columns only — INT-79 excluded per spec
SIDECAR_PATH = os.path.join(PROJECT_DIR, "data", "intelligence", "built_signals_sidecar.parquet")
FT_RATE_COLS = ["ft_rate_q50", "ft_rate_spread", "ft_n_prior"]


def _load_sidecar() -> pd.DataFrame:
    """Load sidecar parquet keyed on (player_id, game_date). Only ft_rate cols."""
    df = pd.read_parquet(SIDECAR_PATH)
    df["player_id"] = df["player_id"].astype(int)
    df["game_date"] = df["game_date"].astype(str).str[:10]
    # Only keep ft_rate columns that exist (ft_n_prior may be absent)
    keep = ["player_id", "game_date"] + [c for c in FT_RATE_COLS if c in df.columns]
    return df[keep]


def _attach_sidecar(rows: list, sidecar: pd.DataFrame) -> tuple:
    """Attach ft_rate sidecar columns to rows. Returns (augmented rows, extra_cols list)."""
    avail_cols = [c for c in FT_RATE_COLS if c in sidecar.columns]
    lookup: Dict[tuple, Dict[str, float]] = {}
    for _, row in sidecar[["player_id", "game_date"] + avail_cols].iterrows():
        key = (int(row["player_id"]), str(row["game_date"])[:10])
        lookup[key] = {c: row[c] for c in avail_cols}

    augmented = []
    for r in rows:
        nr = dict(r)
        key = (int(r["player_id"]), str(r["date"])[:10])
        vals = lookup.get(key, {})
        for c in avail_cols:
            nr[c] = vals.get(c, np.nan)
        augmented.append(nr)

    return augmented, avail_cols


# ---------------------------------------------------------------------------
# Training helper — XGB + LGB ONLY (no MLP) — identical to INT-102
# ---------------------------------------------------------------------------
def _train_fg3m_no_mlp(X_tr, y_tr, X_val, y_val, X_ho, y_ho, sw):
    """Train XGB + LGB for fg3m (not a count stat); return 2-way holdout metrics."""
    import xgboost as xgb
    import lightgbm as lgb
    from sklearn.linear_model import LinearRegression
    from sklearn.metrics import mean_absolute_error, r2_score

    _xgb_kwargs = dict(
        n_estimators=600, max_depth=4,
        learning_rate=0.04, subsample=0.8, colsample_bytree=0.8,
        min_child_weight=10, reg_lambda=2.0, reg_alpha=0.5, gamma=0.2,
        random_state=42,
        objective="reg:squarederror",
        early_stopping_rounds=40, eval_metric="mae",
    )
    if _XGB_DEVICE == "cuda":
        _xgb_kwargs["device"] = "cuda"
    try:
        xgb_m = xgb.XGBRegressor(**_xgb_kwargs)
        xgb_m.fit(X_tr, y_tr, eval_set=[(X_val, y_val)],
                  sample_weight=sw, verbose=False)
    except Exception:
        _xgb_kwargs.pop("device", None)
        xgb_m = xgb.XGBRegressor(**_xgb_kwargs)
        xgb_m.fit(X_tr, y_tr, eval_set=[(X_val, y_val)],
                  sample_weight=sw, verbose=False)

    lgb_m = lgb.LGBMRegressor(
        n_estimators=600, max_depth=4,
        learning_rate=0.04, subsample=0.8, subsample_freq=1,
        colsample_bytree=0.8, min_child_samples=20,
        reg_lambda=2.0, reg_alpha=0.5, random_state=42,
        objective="regression",
        n_jobs=-1, verbosity=-1,
    )
    lgb_m.fit(X_tr, y_tr, eval_set=[(X_val, y_val)],
              sample_weight=sw,
              callbacks=[lgb.early_stopping(40, verbose=False)])

    xv = xgb_m.predict(X_val)
    lv = lgb_m.predict(X_val)
    xh = xgb_m.predict(X_ho)
    lh = lgb_m.predict(X_ho)

    st = LinearRegression(positive=True, fit_intercept=False)
    st.fit(np.column_stack([xv, lv]), y_val)
    w = st.coef_
    if not (0.5 <= w.sum() <= 1.5):
        w = np.array([0.5, 0.5])

    blend_ho = w[0] * xh + w[1] * lh
    mae = float(mean_absolute_error(y_ho, blend_ho))
    r2 = float(r2_score(y_ho, blend_ho))

    return {"mae": mae, "r2": r2, "w": [float(x) for x in w]}


# ---------------------------------------------------------------------------
# Per-fold NaN imputation (training medians — no leakage)
# ---------------------------------------------------------------------------
def _impute_fold(X_tr: np.ndarray, X_val: np.ndarray, X_ho: np.ndarray,
                 base_n_cols: int) -> tuple:
    """Fill NaN in sidecar columns using training-fold median only."""
    if X_tr.shape[1] == base_n_cols:
        return X_tr, X_val, X_ho
    for col_i in range(base_n_cols, X_tr.shape[1]):
        train_col = X_tr[:, col_i]
        non_nan = train_col[~np.isnan(train_col)]
        median = float(np.median(non_nan)) if len(non_nan) > 0 else 0.0
        for arr in (X_tr, X_val, X_ho):
            mask = np.isnan(arr[:, col_i])
            arr[mask, col_i] = median
    return X_tr, X_val, X_ho


# ---------------------------------------------------------------------------
# Walk-forward engine (FG3M ONLY, 2-way XGB+LGB)
# ---------------------------------------------------------------------------
def walk_forward(
    n_splits: int = 4,
    use_sidecar: bool = False,
    null_shuffle: bool = False,
    null_seed: int = 0,
    mode_label: str = "baseline",
) -> dict:
    print(f"\n{'='*60}")
    print(f"MODE: {mode_label}  sidecar={use_sidecar}  null={null_shuffle}  [FG3M-ONLY, NO-MLP]")
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
        rows, extra_cols = _attach_sidecar(rows, sidecar)
        print(f"  extra sidecar cols: {extra_cols}")

    all_cols = fc + extra_cols
    X_all = np.array([[r.get(c, np.nan) for c in all_cols] for r in rows], dtype=float)
    y_all = np.array([r["target_fg3m"] for r in rows], dtype=float)

    fold_ends = [(i + 1) / (n_splits + 1) for i in range(n_splits)]
    per_fold_results = []

    for fold_idx, train_end_frac in enumerate(fold_ends):
        tr_end = int(n * train_end_frac)
        if fold_idx == n_splits - 1:
            te_end = n
        else:
            te_end = int(n * fold_ends[fold_idx + 1])
        va_end = int(tr_end + (te_end - tr_end) * 0.4)

        if tr_end < 5000 or (te_end - va_end) < 2000:
            print(f"  fold {fold_idx+1}: too small — skip")
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

        # Compute sidecar coverage on holdout (for reporting)
        cov_str = ""
        if use_sidecar and extra_cols and not null_shuffle:
            ho_rows = rows[va_end:te_end]
            cov = np.mean([1 if not np.isnan(r.get(extra_cols[0], np.nan)) else 0 for r in ho_rows])
            cov_str = f" sidecar_cov={cov:.3f}"

        print(f"\n[fold {fold_idx+1}/{n_splits}] tr={tr_end} val={va_end-tr_end} "
              f"ho={te_end-va_end}{cov_str}", flush=True)

        tr_dates = [datetime.fromisoformat(rows[i]["date"]) for i in range(tr_end)]
        max_d = max(tr_dates)
        age = np.array([(max_d - d).days / 365.0 for d in tr_dates], dtype=float)
        sw = np.exp(-0.5 * age)

        t0 = time.time()
        res = _train_fg3m_no_mlp(
            X_tr, y_all[:tr_end],
            X_val, y_all[tr_end:va_end],
            X_ho, y_all[va_end:te_end],
            sw,
        )
        res["fold"] = fold_idx + 1
        per_fold_results.append(res)
        print(f"  FG3M mae={res['mae']:.4f} r2={res['r2']:.4f} w={res['w']}  {time.time()-t0:.0f}s")

    print(f"\n=== SUMMARY [{mode_label}] ===")
    maes = [r["mae"] for r in per_fold_results]
    mean_mae = float(np.mean(maes)) if maes else float("nan")
    std_mae = float(np.std(maes)) if maes else float("nan")
    print(f"  FG3M mae={mean_mae:.4f}±{std_mae:.4f}  per_fold={[f'{m:.4f}' for m in maes]}")

    return {
        "mode": mode_label,
        "use_sidecar": use_sidecar,
        "null_shuffle": null_shuffle,
        "architecture": "XGB+LGB_2way_fg3m_only",
        "per_fold": per_fold_results,
        "mae_mean": mean_mae,
        "mae_std": std_mae,
        "per_fold_mae": maes,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description="INT-107: FG3M-only ft_rate sidecar WF test")
    ap.add_argument("--splits", type=int, default=4)
    ap.add_argument("--mode", choices=["baseline", "isolation", "null", "all"],
                    default="all")
    ap.add_argument("--device", default="auto",
                    help="XGB device: 'cuda', 'cpu', or 'auto' (default: auto-detect)")
    args = ap.parse_args()

    global _XGB_DEVICE
    _XGB_DEVICE = _resolve_device(args.device)
    print(f"[INT-107] XGB device: {_XGB_DEVICE}")

    results: Dict[str, Any] = {}

    if args.mode in ("baseline", "all"):
        results["baseline"] = walk_forward(args.splits, use_sidecar=False,
                                           mode_label="baseline_fg3m_only")

    if args.mode in ("isolation", "all"):
        results["isolation"] = walk_forward(args.splits, use_sidecar=True,
                                            mode_label="isolation_ft_rate_fg3m_only")

    if args.mode in ("null", "all"):
        results["null"] = walk_forward(args.splits, use_sidecar=True,
                                       null_shuffle=True, null_seed=0,
                                       mode_label="null_ft_rate_fg3m_only")

    # ---------------------------------------------------------------------------
    # G2: Per-fold MAE delta (aug vs baseline)
    # ---------------------------------------------------------------------------
    print("\n=== G2: FG3M WF FOLD DELTAS (aug - baseline) ===")
    g2_pass = False
    g2_detail: dict = {}
    if "baseline" in results and "isolation" in results:
        base_folds = results["baseline"]["per_fold_mae"]
        aug_folds = results["isolation"]["per_fold_mae"]
        per_fold_delta = [a - b for a, b in zip(aug_folds, base_folds)]
        n_neg = sum(1 for d in per_fold_delta if d < 0)
        mean_delta = float(np.mean(per_fold_delta)) if per_fold_delta else float("nan")
        g2_detail = {"per_fold_delta": per_fold_delta, "n_neg": n_neg, "mean_delta": mean_delta}
        fold_str = "  ".join(f"F{i+1}:{d:+.4f}" for i, d in enumerate(per_fold_delta))
        print(f"  FG3M: {fold_str}")
        print(f"  n_neg={n_neg}/4  mean_delta={mean_delta:+.4f}")
        g2_pass = n_neg >= 3
    print(f"\n  G2 result: {'PASS' if g2_pass else 'FAIL'} (need >=3/4 negative folds)")

    # ---------------------------------------------------------------------------
    # G3: Null control
    # ---------------------------------------------------------------------------
    print("\n=== G3: NULL CONTROL ===")
    g3_pass = False
    g3_detail: dict = {}
    if "baseline" in results and "isolation" in results and "null" in results:
        real_delta = results["isolation"]["mae_mean"] - results["baseline"]["mae_mean"]
        null_delta = results["null"]["mae_mean"] - results["baseline"]["mae_mean"]
        if abs(null_delta) > 1e-6:
            ratio = abs(real_delta) / abs(null_delta)
        else:
            ratio = float("inf") if real_delta < 0 else 0.0
        g3_detail = {"real_delta": real_delta, "null_delta": null_delta, "ratio": ratio}
        print(f"  FG3M: real_delta={real_delta:+.4f}  null_delta={null_delta:+.4f}  ratio={ratio:.2f}")
        g3_pass = ratio >= 1.5
    print(f"\n  G3 result: {'PASS' if g3_pass else 'FAIL'} (need ratio>=1.5)")

    # ---------------------------------------------------------------------------
    # G4: Aggregate improvement >=0.001
    # ---------------------------------------------------------------------------
    print("\n=== G4: AGGREGATE IMPROVEMENT (aug must beat baseline by >=0.001) ===")
    g4_pass = False
    g4_detail: dict = {}
    if "baseline" in results and "isolation" in results:
        base_mae = results["baseline"]["mae_mean"]
        aug_mae = results["isolation"]["mae_mean"]
        improvement = base_mae - aug_mae  # positive = improvement
        g4_detail = {"base_mae": base_mae, "aug_mae": aug_mae, "improvement": improvement}
        print(f"  base={base_mae:.4f}  aug={aug_mae:.4f}  improvement={improvement:+.4f}")
        g4_pass = improvement >= 0.001
    print(f"\n  G4 result: {'PASS' if g4_pass else 'FAIL'} (need improvement>=0.001)")

    # ---------------------------------------------------------------------------
    # G5: Production architecture cost (no-MLP 2-way vs 3-way prod on FG3M)
    # ---------------------------------------------------------------------------
    print("\n=== G5: PRODUCTION ARCHITECTURE COST (2-way no-MLP vs 3-way prod) ===")
    g5_detail: dict = {}
    prod_fg3m_3way: float = float("nan")
    arch_cost: float = float("nan")
    g5_flag = "UNKNOWN"

    prod_json = os.path.join(PROJECT_DIR, "data", "models", "prop_pergame_walk_forward.json")
    if os.path.exists(prod_json):
        with open(prod_json) as f:
            prod = json.load(f)
        prod_fg3m = prod.get("by_stat", {}).get("fg3m", {})
        prod_fg3m_3way = prod_fg3m.get("mae_3way_mean", float("nan"))
        prod_fg3m_2way = prod_fg3m.get("mae_2way_mean", float("nan"))
        if "baseline" in results:
            no_mlp_2way = results["baseline"]["mae_mean"]
            arch_cost = no_mlp_2way - prod_fg3m_3way  # positive = no-MLP is worse
            g5_detail = {
                "prod_3way_mae": prod_fg3m_3way,
                "prod_2way_mae": prod_fg3m_2way,
                "no_mlp_2way_mae": no_mlp_2way,
                "arch_cost_vs_3way": arch_cost,
            }
            print(f"  prod_3way_mae={prod_fg3m_3way:.4f}")
            print(f"  prod_2way_mae={prod_fg3m_2way:.4f}  (from same prod JSON)")
            print(f"  no_mlp_2way_mae (INT-107 baseline)={no_mlp_2way:.4f}")
            print(f"  arch_cost (no-mlp vs 3way) = {arch_cost:+.4f}")
            if arch_cost <= 0.005:
                g5_flag = "SAFE"
                print("  [SAFE] arch_cost <=0.005 — wire-in is clean")
            elif arch_cost <= 0.01:
                g5_flag = "BORDERLINE"
                print("  [BORDERLINE] 0.005<arch_cost<=0.01 — marginal cost, signal may still net out")
            else:
                g5_flag = "BLOCKED"
                print("  [BLOCKED] arch_cost >0.01 — ft_rate cannot ship to production without MLP restructure")
    else:
        print("  prod JSON not found — G5 skipped")
    print(f"\n  G5 flag: {g5_flag}")

    # ---------------------------------------------------------------------------
    # Overall verdict
    # ---------------------------------------------------------------------------
    print("\n=== INT-107 GATE SCOREBOARD ===")
    print(f"  G1 (coverage >=10%):          PRE-PASS (INT-94 confirmed 91% fold-4)")
    print(f"  G2 (FG3M >=3/4 neg folds):    {'PASS' if g2_pass else 'FAIL'}  "
          f"n_neg={g2_detail.get('n_neg','?')}/4  mean={g2_detail.get('mean_delta', float('nan')):+.4f}")
    print(f"  G3 (null ratio >=1.5):         {'PASS' if g3_pass else 'FAIL'}  "
          f"ratio={g3_detail.get('ratio', float('nan')):.2f}")
    print(f"  G4 (improvement >=0.001):      {'PASS' if g4_pass else 'FAIL'}  "
          f"improvement={g4_detail.get('improvement', float('nan')):+.4f}")
    print(f"  G5 (prod-arch cost):           {g5_flag}  "
          f"cost={arch_cost:+.4f}")

    if g2_pass and g3_pass:
        if g4_pass and g5_flag == "SAFE":
            verdict = "SHIP"
        elif g4_pass and g5_flag == "BORDERLINE":
            verdict = "SCOPED-SHIP"
        elif g5_flag == "BLOCKED":
            verdict = "SCOPED-SHIP"  # signal real, no production path yet
        else:
            verdict = "SCOPED-SHIP"
    else:
        verdict = "REJECT"

    print(f"\n  VERDICT: {verdict}")
    if verdict == "SHIP":
        print("  Wire-in: add ft_rate_q50/ft_rate_spread/ft_n_prior to FG3M-branch of production model.")
    elif verdict == "SCOPED-SHIP":
        print("  Signal is real but production wire-in requires architecture change (add ft_rate sidecar")
        print("  to FG3M only; either restructure 3-way to accept per-stat extra features, or promote")
        print("  FG3M to a 4-way ensemble with ft_rate-augmented XGB as the 4th learner).")
    else:
        print("  REJECT: INT-102 FG3M finding was sample-specific or fold-specific noise.")

    # ---------------------------------------------------------------------------
    # Save results
    # ---------------------------------------------------------------------------
    out = {
        "int_id": "INT-107",
        "description": "INT-83 ft_rate sidecar — FG3M-only 2-way XGB+LGB re-test",
        "g1_pass": True,
        "g2_pass": g2_pass,
        "g3_pass": g3_pass,
        "g4_pass": g4_pass,
        "g5_flag": g5_flag,
        "verdict": verdict,
        "g2_detail": g2_detail,
        "g3_detail": g3_detail,
        "g4_detail": g4_detail,
        "g5_detail": g5_detail,
        "results": results,
    }
    out_path = os.path.join(PROJECT_DIR, "data", "models",
                            "prop_pergame_walk_forward_fg3m_only.json")
    with open(out_path, "w") as f:
        json.dump(out, f, indent=2, default=str)
    print(f"\nWrote {out_path}")
    return out


if __name__ == "__main__":
    main()
