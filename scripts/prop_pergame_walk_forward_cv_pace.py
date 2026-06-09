"""prop_pergame_walk_forward_cv_pace.py — INT-118: CV pace sidecar walk-forward test.

Tests cv_pace_team_l5, cv_pace_team_l10, cv_pace_opp_l5, cv_pace_opp_l10,
cv_pace_matchup_z as sidecar features for PTS and FG3M (highest pace-sensitivity).

Gates:
  G1 (coverage):      fold-4 non-null >= 30%      [pre-computed externally]
  G2 (orthogonality): |corr(cv_pace_team_l5, api_pace)| < 0.95  [pre-computed]
  G3 (WF):            >=3/4 folds positive MAE delta on PTS; FG3M secondary
  G4 (null control):  real/null ratio >= 2.0
  G5 (no regression): no stat regresses >0.003 MAE on aggregate

Run:
    python scripts/prop_pergame_walk_forward_cv_pace.py --mode all
    python scripts/prop_pergame_walk_forward_cv_pace.py --mode baseline
    python scripts/prop_pergame_walk_forward_cv_pace.py --mode isolation
    python scripts/prop_pergame_walk_forward_cv_pace.py --mode null
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
    STATS, build_pergame_dataset, feature_columns,
)

# ---------------------------------------------------------------------------
# INT-118 sidecar
# ---------------------------------------------------------------------------
SIDECAR_PATH = os.path.join(PROJECT_DIR, "data", "intelligence",
                            "cv_pace_features_sidecar.parquet")

# INT-118: restrict to PTS and FG3M (highest pace-sensitivity)
EVAL_STATS = ["pts", "fg3m"]

SIGNAL_COLS: List[str] = [
    "cv_pace_team_l5",
    "cv_pace_team_l10",
    "cv_pace_opp_l5",
    "cv_pace_opp_l10",
    "cv_pace_matchup_z",
]


def _load_sidecar() -> pd.DataFrame:
    df = pd.read_parquet(SIDECAR_PATH)
    df["player_id"] = df["player_id"].astype(int)
    df["game_date"] = df["game_date"].astype(str).str[:10]
    return df


def _attach_sidecar(rows: list, sidecar: pd.DataFrame) -> tuple:
    """Attach cv_pace sidecar columns to rows via (player_id, game_date) key."""
    lookup: Dict[tuple, Dict[str, float]] = {}
    for _, row in sidecar[["player_id", "game_date"] + SIGNAL_COLS].iterrows():
        key = (int(row["player_id"]), str(row["game_date"])[:10])
        lookup[key] = {c: row[c] for c in SIGNAL_COLS}

    augmented = []
    for r in rows:
        nr = dict(r)
        key = (int(r["player_id"]), str(r["date"])[:10])
        vals = lookup.get(key, {})
        for c in SIGNAL_COLS:
            nr[c] = vals.get(c, np.nan)
        augmented.append(nr)

    return augmented, SIGNAL_COLS


# ---------------------------------------------------------------------------
# Training helper — XGB + LGB ONLY (no MLP)
# ---------------------------------------------------------------------------
def _train_one_stat(stat, X_tr, y_tr, X_val, y_val, X_ho, y_ho, sw):
    import xgboost as xgb
    import lightgbm as lgb
    from sklearn.linear_model import LinearRegression
    from sklearn.metrics import mean_absolute_error

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
        xgb_m.fit(X_tr, y_tr, eval_set=[(X_val, y_val)],
                  sample_weight=sw, verbose=False)
    except Exception:
        _xgb_kwargs.pop("device", None)
        xgb_m = xgb.XGBRegressor(**_xgb_kwargs)
        xgb_m.fit(X_tr, y_tr, eval_set=[(X_val, y_val)],
                  sample_weight=sw, verbose=False)

    lgb_m = lgb.LGBMRegressor(
        n_estimators=600, max_depth=3 if is_count else 4,
        learning_rate=0.04, subsample=0.8, subsample_freq=1,
        colsample_bytree=0.8, min_child_samples=20,
        reg_lambda=2.0, reg_alpha=0.5, random_state=42,
        objective="poisson" if is_count else "regression",
        n_jobs=-1, verbosity=-1,
    )
    lgb_m.fit(X_tr, y_tr, eval_set=[(X_val, y_val)],
               sample_weight=sw,
               callbacks=[lgb.early_stopping(40, verbose=False)])

    xv, lv = xgb_m.predict(X_val), lgb_m.predict(X_val)
    xh, lh = xgb_m.predict(X_ho), lgb_m.predict(X_ho)

    st = LinearRegression(positive=True, fit_intercept=False)
    st.fit(np.column_stack([xv, lv]), y_val)
    w = st.coef_
    if not (0.5 <= w.sum() <= 1.5):
        w = np.array([0.5, 0.5])

    pred_ho = w[0] * xh + w[1] * lh
    mae = float(mean_absolute_error(y_ho, pred_ho))

    return {"mae": mae, "w": [float(x) for x in w]}


def _impute_fold(X_tr, X_val, X_ho, base_n_cols):
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
# Walk-forward engine
# ---------------------------------------------------------------------------
def walk_forward(
    n_splits: int = 4,
    use_sidecar: bool = False,
    null_shuffle: bool = False,
    null_seed: int = 0,
    mode_label: str = "baseline",
    restrict_stats: List[str] | None = None,
) -> dict:
    eval_stats = restrict_stats or STATS

    print(f"\n{'='*60}")
    print(f"MODE: {mode_label}  sidecar={use_sidecar}  null={null_shuffle}")
    print(f"Stats: {eval_stats}")
    print(f"{'='*60}")

    print(f"Loading dataset (n_splits={n_splits}) ...")
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

    fold_ends = [(i + 1) / (n_splits + 1) for i in range(n_splits)]
    per_stat_fold_metrics: dict = {s: [] for s in eval_stats}

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

        tr_dates = [datetime.fromisoformat(rows[i]["date"]) for i in range(tr_end)]
        max_d = max(tr_dates)
        age = np.array([(max_d - d).days / 365.0 for d in tr_dates], dtype=float)
        sw = np.exp(-0.5 * age)

        if use_sidecar and not null_shuffle:
            ho_rows = rows[va_end:te_end]
            cov = float(np.mean([
                1 if not np.isnan(r.get("cv_pace_team_l5", np.nan)) else 0
                for r in ho_rows
            ]))
            print(f"\n[fold {fold_idx+1}/{n_splits}] tr={tr_end} val={va_end-tr_end} "
                  f"ho={te_end-va_end} sidecar_cov={cov:.3f}", flush=True)
        else:
            print(f"\n[fold {fold_idx+1}/{n_splits}] tr={tr_end} val={va_end-tr_end} "
                  f"ho={te_end-va_end}", flush=True)

        t0 = time.time()
        for stat in eval_stats:
            y = np.array([r[f"target_{stat}"] for r in rows], dtype=float)
            res = _train_one_stat(stat, X_tr, y[:tr_end],
                                  X_val, y[tr_end:va_end],
                                  X_ho, y[va_end:te_end], sw)
            res["fold"] = fold_idx + 1
            per_stat_fold_metrics[stat].append(res)
            print(f"  {stat.upper():4s} mae={res['mae']:.4f}", flush=True)
        print(f"  fold {fold_idx+1} wall: {time.time()-t0:.0f}s")

    print(f"\n=== SUMMARY [{mode_label}] ===")
    summary: dict = {
        "mode": mode_label,
        "use_sidecar": use_sidecar,
        "null_shuffle": null_shuffle,
        "folds_per_stat": per_stat_fold_metrics,
        "by_stat": {},
    }
    for stat in eval_stats:
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
    ap = argparse.ArgumentParser(description="INT-118: CV pace sidecar WF test")
    ap.add_argument("--splits", type=int, default=4)
    ap.add_argument("--mode", choices=["baseline", "isolation", "null", "all"],
                    default="all")
    ap.add_argument("--device", default="auto",
                    help="XGB device: 'cuda', 'cpu', or 'auto' (default: auto-detect)")
    args = ap.parse_args()

    global _XGB_DEVICE
    _XGB_DEVICE = _resolve_device(args.device)
    print(f"[INT-118] XGB device: {_XGB_DEVICE}")

    results: Dict[str, Any] = {}

    if args.mode in ("baseline", "all"):
        results["baseline"] = walk_forward(
            args.splits, use_sidecar=False, mode_label="baseline",
            restrict_stats=EVAL_STATS)

    if args.mode in ("isolation", "all"):
        results["isolation"] = walk_forward(
            args.splits, use_sidecar=True, mode_label="isolation_cv_pace",
            restrict_stats=EVAL_STATS)

    if args.mode in ("null", "all"):
        results["null"] = walk_forward(
            args.splits, use_sidecar=True, null_shuffle=True, null_seed=0,
            mode_label="null_cv_pace", restrict_stats=EVAL_STATS)

    # ---------------------------------------------------------------------------
    # G3: per-stat WF — >=3/4 folds positive on PTS; FG3M secondary
    # ---------------------------------------------------------------------------
    print("\n=== G3: PER-STAT WALK-FORWARD ===")
    g3_detail: dict = {}
    g3_pass_pts = False
    g3_pass_fg3m = False

    if "baseline" in results and "isolation" in results:
        base_by_stat = results["baseline"]["by_stat"]
        aug_by_stat = results["isolation"]["by_stat"]

        for stat in EVAL_STATS:
            if stat not in base_by_stat or stat not in aug_by_stat:
                continue
            base_folds = base_by_stat[stat]["per_fold_mae"]
            aug_folds = aug_by_stat[stat]["per_fold_mae"]
            per_fold_d = [a - b for a, b in zip(aug_folds, base_folds)]
            n_neg = sum(1 for d in per_fold_d if d < 0)
            mean_d = float(np.mean(per_fold_d)) if per_fold_d else float("nan")
            g3_detail[stat] = {"per_fold_delta": per_fold_d, "n_neg": n_neg,
                               "mean_delta": mean_d}
            fold_str = "  ".join(f"F{i+1}:{d:+.4f}" for i, d in enumerate(per_fold_d))
            status = "PASS" if n_neg >= 3 else "FAIL"
            print(f"  {stat.upper():4s}: {fold_str}  neg={n_neg}/4  mean={mean_d:+.4f}  [{status}]")
            if stat == "pts":
                g3_pass_pts = n_neg >= 3
            elif stat == "fg3m":
                g3_pass_fg3m = n_neg >= 3

    g3_pass = g3_pass_pts  # primary gate is PTS
    print(f"\n  G3 result: PTS={'PASS' if g3_pass_pts else 'FAIL'}  "
          f"FG3M={'PASS' if g3_pass_fg3m else 'FAIL'}  "
          f"[Overall {'PASS' if g3_pass else 'FAIL'}]")

    # ---------------------------------------------------------------------------
    # G4: null control — real/null >= 2.0 (tighter than standard)
    # ---------------------------------------------------------------------------
    print("\n=== G4: NULL CONTROL (real/null >= 2.0) ===")
    g4_detail: dict = {}
    g4_pass = True

    if "baseline" in results and "isolation" in results and "null" in results:
        base_by_stat = results["baseline"]["by_stat"]
        aug_by_stat = results["isolation"]["by_stat"]
        null_by_stat = results["null"]["by_stat"]

        for stat in EVAL_STATS:
            if stat not in base_by_stat or stat not in aug_by_stat or stat not in null_by_stat:
                continue
            real_delta = aug_by_stat[stat]["mae_mean"] - base_by_stat[stat]["mae_mean"]
            null_delta = null_by_stat[stat]["mae_mean"] - base_by_stat[stat]["mae_mean"]
            # ratio of |real_improvement| / |null_noise|
            if null_delta >= 0 and real_delta < 0:
                # null is neutral/worse; real improves — good
                ratio = float("inf")
            elif abs(null_delta) < 1e-6:
                ratio = float("inf") if real_delta < 0 else 0.0
            else:
                ratio = abs(real_delta) / abs(null_delta)
            g4_detail[stat] = {"real_delta": real_delta, "null_delta": null_delta,
                               "ratio": ratio}
            stat_pass = ratio >= 2.0 or (real_delta < 0 and null_delta >= 0)
            if not stat_pass:
                g4_pass = False
            print(f"  {stat.upper():4s}: real={real_delta:+.4f}  null={null_delta:+.4f}  "
                  f"ratio={ratio:.2f}  [{'PASS' if stat_pass else 'FAIL'}]")

    print(f"\n  G4 result: {'PASS' if g4_pass else 'FAIL'} (real/null >= 2.0)")

    # ---------------------------------------------------------------------------
    # G5: no regression >0.003 on any stat
    # ---------------------------------------------------------------------------
    print("\n=== G5: NO-REGRESSION ===")
    g5_pass = True
    g5_detail: dict = {}

    if "baseline" in results and "isolation" in results:
        base_by_stat = results["baseline"]["by_stat"]
        aug_by_stat = results["isolation"]["by_stat"]
        for stat in EVAL_STATS:
            if stat not in base_by_stat or stat not in aug_by_stat:
                continue
            b = base_by_stat[stat]["mae_mean"]
            a = aug_by_stat[stat]["mae_mean"]
            delta = a - b
            g5_detail[stat] = {"base": b, "aug": a, "delta": delta}
            flag = "FAIL" if delta > 0.003 else "OK"
            if delta > 0.003:
                g5_pass = False
            print(f"  {stat.upper():4s}: base={b:.4f} aug={a:.4f} delta={delta:+.4f} [{flag}]")

    print(f"\n  G5 result: {'PASS' if g5_pass else 'FAIL'}")

    # ---------------------------------------------------------------------------
    # Overall verdict
    # ---------------------------------------------------------------------------
    print("\n=== GATE SCOREBOARD (INT-118) ===")
    print(f"  G1 (coverage >=30%):     PASS (78.5% fold-4, pre-computed)")
    print(f"  G2 (orthogonality <0.95): PASS (|r|=-0.009, pre-computed)")
    print(f"  G3 (WF PTS >=3/4 neg):   {'PASS' if g3_pass else 'FAIL'}")
    print(f"  G4 (null real/null >=2.0): {'PASS' if g4_pass else 'FAIL'}")
    print(f"  G5 (no >0.003 regression): {'PASS' if g5_pass else 'FAIL'}")

    gates_passed = sum([True, True, g3_pass, g4_pass, g5_pass])
    verdict = "SHIP" if (g3_pass and g4_pass and g5_pass) else "REJECT"
    print(f"\n  VERDICT: {verdict}  ({gates_passed}/5 gates)")

    # ---------------------------------------------------------------------------
    # Save results
    # ---------------------------------------------------------------------------
    out = {
        "int_id": "INT-118",
        "description": "CV pace sidecar (cv_pace_team_l5/l10, opp_l5/l10, matchup_z) for PTS + FG3M",
        "g1_coverage": 0.785,
        "g2_corr": -0.0094,
        "g3_pass": g3_pass,
        "g3_pass_pts": g3_pass_pts,
        "g3_pass_fg3m": g3_pass_fg3m,
        "g4_pass": g4_pass,
        "g5_pass": g5_pass,
        "verdict": verdict,
        "g3_detail": g3_detail,
        "g4_detail": g4_detail,
        "g5_detail": g5_detail,
        "results": results,
    }
    out_path = os.path.join(PROJECT_DIR, "data", "models",
                            "prop_pergame_walk_forward_cv_pace.json")
    with open(out_path, "w") as f:
        json.dump(out, f, indent=2, default=str)
    print(f"\nWrote {out_path}")
    return out


if __name__ == "__main__":
    main()
