"""oof_pts_minmodel.py — Leak-free OOF A/B for the PTS two-stage minutes model.

Replicates cache_pergame_oof.py's walk-forward fold structure EXACTLY for
stat="pts" only.  For each fold, on IDENTICAL holdout rows, computes:

  baseline  = _train_and_predict_stat("pts", ...) from cache_pergame_oof.py
  new       = train_pts_minmodel(rows[:tr_end]) + predict on ho_rows

Both predictions are derived from the SAME training slice (rows[:tr_end]) and
evaluated on the SAME holdout slice (rows[va_end:te_end]).

Output
------
  data/cache/pregame_oof_pts_minmodel.parquet
  Columns: game_id, player_id, stat, oof_pred_base, oof_pred_new,
           actual, target_min, game_date, fold, season

Also prints:
  - Overall baseline vs new MAE (delta + %)
  - Per-fold MAE table for both
  - Bias-by-actual-minutes table (<12 / 12-24 / 24-32 / 32+) for both
  - Shrinkage slopes (actual ~ a + b*pred) for both

Usage
-----
    python scripts/oof_pts_minmodel.py [--max-rows N]
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
    build_pergame_dataset, feature_columns,
)
from src.prediction.pts_minutes_model import (  # noqa: E402
    train_pts_minmodel, predict_pts_minmodel,
)

# Import the baseline trainer from cache_pergame_oof.py
sys.path.insert(0, os.path.join(PROJECT_DIR, "scripts"))
from cache_pergame_oof import _train_and_predict_stat  # noqa: E402


_OUT_PATH = os.path.join(
    PROJECT_DIR, "data", "cache", "pregame_oof_pts_minmodel.parquet"
)
_N_SPLITS = 4


# ---------------------------------------------------------------------------
# Shrinkage slope helper
# ---------------------------------------------------------------------------

def _shrinkage_slope(actuals: np.ndarray, preds: np.ndarray) -> tuple[float, float]:
    """OLS: actual = a + b * pred.  Returns (a, b)."""
    if len(preds) < 10:
        return (float("nan"), float("nan"))
    X = np.column_stack([np.ones_like(preds), preds])
    coef, *_ = np.linalg.lstsq(X, actuals, rcond=None)
    return float(coef[0]), float(coef[1])


# ---------------------------------------------------------------------------
# Main OOF loop
# ---------------------------------------------------------------------------

def run_oof(n_splits: int = _N_SPLITS, max_rows: Optional[int] = None) -> str:
    """Run the A/B OOF and write the parquet.  Returns the output path."""
    import pandas as pd  # noqa: PLC0415

    print(f"Loading dataset (n_splits={n_splits}, max_rows={max_rows}) ...")
    rows, fc = build_pergame_dataset(min_prior=0)
    rows.sort(key=lambda r: r["date"])
    n = len(rows)
    print(f"  total rows={n}")

    if max_rows is not None and max_rows < n:
        rows = rows[:max_rows]
        n = len(rows)
        print(f"  truncated to {n} rows (--max-rows)")

    # Feature matrix for the baseline (uses feature_columns("pts"))
    fc_pts = feature_columns(stat="pts")
    X_all = np.array([[r.get(c, 0.0) or 0.0 for c in fc_pts] for r in rows], dtype=float)

    records: List[dict] = []
    fold_ends = [(i + 1) / (n_splits + 1) for i in range(n_splits)]

    for fold_idx, train_end_frac in enumerate(fold_ends):
        tr_end = int(n * train_end_frac)
        if fold_idx == n_splits - 1:
            te_end = n
        else:
            te_end = int(n * fold_ends[fold_idx + 1])
        va_end = int(tr_end + (te_end - tr_end) * 0.4)

        min_tr = max(500, int(n * 0.05))
        min_ho = max(50, int(n * 0.02))
        if tr_end < min_tr or (te_end - va_end) < min_ho:
            print(f"  fold {fold_idx+1}: too small (tr={tr_end}, ho={te_end-va_end}) — skip")
            continue

        ho_rows = rows[va_end:te_end]

        # ── Recency sample weights (identical to cache_pergame_oof) ─────────
        tr_dates = [datetime.fromisoformat(rows[i]["date"]) for i in range(tr_end)]
        max_d = max(tr_dates)
        age = np.array([(max_d - d).days / 365.0 for d in tr_dates], dtype=float)
        sw = np.exp(-0.5 * age)

        print(
            f"\n[fold {fold_idx+1}/{n_splits}] tr={tr_end} val={va_end-tr_end} "
            f"ho={te_end-va_end}  {ho_rows[0]['date']}..{ho_rows[-1]['date']}",
            flush=True,
        )
        t0 = time.time()

        # ── Baseline prediction ──────────────────────────────────────────────
        X_tr_b  = X_all[:tr_end]
        X_val_b = X_all[tr_end:va_end]
        X_ho_b  = X_all[va_end:te_end]

        y_all  = np.array([r["target_pts"] for r in rows], dtype=float)
        y_tr   = y_all[:tr_end]
        y_val  = y_all[tr_end:va_end]
        y_ho   = y_all[va_end:te_end]

        print("  Training baseline stack ...", flush=True)
        base_preds = _train_and_predict_stat(
            "pts", X_tr_b, y_tr, X_val_b, y_val, X_ho_b, sw,
        )

        # ── New two-stage model ──────────────────────────────────────────────
        print("  Training two-stage minutes model ...", flush=True)
        artifact = train_pts_minmodel(rows[:tr_end])
        new_preds = np.array(
            [predict_pts_minmodel(artifact, r) for r in ho_rows],
            dtype=float,
        )

        mae_base = float(np.mean(np.abs(base_preds - y_ho)))
        mae_new  = float(np.mean(np.abs(new_preds  - y_ho)))
        print(
            f"  PTS ho_mae  baseline={mae_base:.4f}  new={mae_new:.4f}  "
            f"delta={mae_new - mae_base:+.4f}  ({(mae_new-mae_base)/mae_base*100:+.2f}%)",
            flush=True,
        )
        print(f"  fold {fold_idx+1} wall: {time.time()-t0:.0f}s", flush=True)

        # ── Collect records ──────────────────────────────────────────────────
        for i, row in enumerate(ho_rows):
            records.append({
                "game_id":      str(row.get("game_id", "")),
                "player_id":    int(row.get("player_id", 0)),
                "stat":         "pts",
                "oof_pred_base": float(base_preds[i]),
                "oof_pred_new":  float(new_preds[i]),
                "actual":        float(y_ho[i]),
                "target_min":    float(row.get("target_min", 0.0) or 0.0),
                "game_date":     str(row["date"])[:10],
                "fold":          fold_idx + 1,
                "season":        str(row.get("season", "")),
            })

    if not records:
        raise RuntimeError("No OOF records generated — all folds skipped.")

    df = pd.DataFrame(records)
    df = df[[
        "game_id", "player_id", "stat",
        "oof_pred_base", "oof_pred_new",
        "actual", "target_min",
        "game_date", "fold", "season",
    ]]

    os.makedirs(os.path.dirname(_OUT_PATH), exist_ok=True)
    df.to_parquet(_OUT_PATH, index=False)

    # ── Report ───────────────────────────────────────────────────────────────
    _print_report(df)

    print(f"\nWrote: {_OUT_PATH}  ({os.path.getsize(_OUT_PATH) // 1024} KB)")
    return _OUT_PATH


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def _print_report(df) -> None:
    """Print the full numeric A/B report."""
    import numpy as np  # noqa: PLC0415

    actual     = df["actual"].values
    base_preds = df["oof_pred_base"].values
    new_preds  = df["oof_pred_new"].values
    t_min      = df["target_min"].values

    mae_base = float(np.mean(np.abs(base_preds - actual)))
    mae_new  = float(np.mean(np.abs(new_preds  - actual)))
    delta    = mae_new - mae_base
    delta_pct = delta / mae_base * 100.0

    print("\n" + "=" * 70)
    print("  PTS TWO-STAGE MINUTES MODEL  —  OOF A/B REPORT")
    print("=" * 70)
    print(f"  n holdout rows  : {len(df):,}")
    print(f"  Baseline MAE    : {mae_base:.4f}")
    print(f"  New MAE         : {mae_new:.4f}")
    print(f"  Delta           : {delta:+.4f}  ({delta_pct:+.2f}%)")
    if mae_new < mae_base:
        print("  Gate A: PASS — new < baseline")
    else:
        print("  Gate A: FAIL — new >= baseline")

    # Per-fold table
    print("\n  --- Per-fold MAE ---")
    print(f"  {'Fold':>4}  {'n':>6}  {'Base MAE':>10}  {'New MAE':>10}  {'Delta':>10}")
    for fold in sorted(df["fold"].unique()):
        sub = df[df["fold"] == fold]
        a   = sub["actual"].values
        b   = sub["oof_pred_base"].values
        nw  = sub["oof_pred_new"].values
        mb  = float(np.mean(np.abs(b - a)))
        mn  = float(np.mean(np.abs(nw - a)))
        print(f"  {fold:>4}  {len(sub):>6}  {mb:>10.4f}  {mn:>10.4f}  {mn-mb:>+10.4f}")

    # Bias-by-actual-minutes table
    print("\n  --- Bias (pred − actual) by actual minutes played ---")
    print(f"  {'Bucket':>10}  {'n':>6}  {'Base bias':>10}  {'New bias':>10}  {'Base |bias|':>12}  {'New |bias|':>11}")
    buckets = [
        ("<12",  t_min < 12),
        ("12-24", (t_min >= 12) & (t_min < 24)),
        ("24-32", (t_min >= 24) & (t_min < 32)),
        ("32+",   t_min >= 32),
    ]
    low_base_abs = high_base_abs = low_new_abs = high_new_abs = float("nan")
    for label, mask in buckets:
        if mask.sum() == 0:
            print(f"  {label:>10}  {'0':>6}")
            continue
        b_bias = float(np.mean(base_preds[mask] - actual[mask]))
        n_bias = float(np.mean(new_preds[mask]  - actual[mask]))
        b_abs  = float(np.mean(np.abs(base_preds[mask] - actual[mask])))
        n_abs  = float(np.mean(np.abs(new_preds[mask]  - actual[mask])))
        print(
            f"  {label:>10}  {mask.sum():>6}  {b_bias:>+10.3f}  {n_bias:>+10.3f}"
            f"  {b_abs:>12.3f}  {n_abs:>11.3f}"
        )
        if label == "<12":
            low_base_abs,  low_new_abs  = b_abs, n_abs
        elif label == "32+":
            high_base_abs, high_new_abs = b_abs, n_abs

    # Gate B verdict
    print()
    if not (np.isnan(low_base_abs) or np.isnan(high_base_abs)):
        low_ok  = low_new_abs  < low_base_abs
        high_ok = high_new_abs < high_base_abs
        if low_ok and high_ok:
            print(f"  Gate B: PASS — fan compresses at both tails")
            print(f"           |bias(<12)| : {low_base_abs:.3f} → {low_new_abs:.3f}")
            print(f"           |bias(32+)| : {high_base_abs:.3f} → {high_new_abs:.3f}")
        else:
            print(f"  Gate B: FAIL — fan does NOT fully compress")
            print(f"           |bias(<12)| : {low_base_abs:.3f} → {low_new_abs:.3f}  {'OK' if low_ok else 'WORSE'}")
            print(f"           |bias(32+)| : {high_base_abs:.3f} → {high_new_abs:.3f}  {'OK' if high_ok else 'WORSE'}")

    # Shrinkage slopes
    print("\n  --- Shrinkage slope (actual = a + b*pred) ---")
    a_base, b_base = _shrinkage_slope(actual, base_preds)
    a_new,  b_new  = _shrinkage_slope(actual, new_preds)
    print(f"  Baseline : actual = {a_base:.3f} + {b_base:.3f} * pred")
    print(f"  New      : actual = {a_new:.3f} + {b_new:.3f} * pred")
    print(f"  (b closer to 1.0 = less shrinkage = better calibrated spread)")

    # Gate C — sanity / degeneracy check
    print("\n  --- Gate C: degeneracy check ---")
    nan_count = int(np.sum(~np.isfinite(new_preds)))
    pred_range = float(np.max(new_preds) - np.min(new_preds))
    pred_std   = float(np.std(new_preds))
    print(f"  NaN/inf in new preds : {nan_count}")
    print(f"  New pred range       : {float(np.min(new_preds)):.2f} – {float(np.max(new_preds)):.2f}  (span {pred_range:.2f})")
    print(f"  New pred std         : {pred_std:.3f}")
    if nan_count == 0 and pred_range > 5.0 and pred_std > 1.0:
        print("  Gate C: PASS")
    else:
        print("  Gate C: FAIL")

    # Overall summary
    print("\n" + "=" * 70)
    print("  FINAL VERDICT")
    gate_a = mae_new < mae_base
    gate_b = (not np.isnan(low_base_abs)) and (low_new_abs < low_base_abs) and (high_new_abs < high_base_abs)
    gate_c = (nan_count == 0) and (pred_range > 5.0) and (pred_std > 1.0)
    all_pass = gate_a and gate_b and gate_c
    print(f"  Gate A (MAE < baseline)           : {'PASS' if gate_a else 'FAIL'}")
    print(f"  Gate B (minute-fan compresses)    : {'PASS' if gate_b else 'FAIL'}")
    print(f"  Gate C (no degeneracy)            : {'PASS' if gate_c else 'FAIL'}")
    print()
    if all_pass:
        print("  RECOMMENDATION: SHIP (all gates pass)")
    else:
        print("  RECOMMENDATION: REJECT (one or more gates fail)")
    print("=" * 70)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    ap = argparse.ArgumentParser(
        description="Leak-free OOF A/B for PTS two-stage minutes model."
    )
    ap.add_argument(
        "--max-rows", type=int, default=None, metavar="N",
        help="Truncate dataset to first N rows (dev/smoke run).",
    )
    ap.add_argument(
        "--splits", type=int, default=_N_SPLITS,
        help=f"Number of WF splits (default {_N_SPLITS}).",
    )
    args = ap.parse_args()
    run_oof(n_splits=args.splits, max_rows=args.max_rows)
