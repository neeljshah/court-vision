"""oof_reb_oppmodel.py — Leak-free A/B OOF: REB opportunity model vs baseline.

Replicates cache_pergame_oof.py's EXACT walk-forward fold structure for stat="reb"
only.  In each fold BOTH models are evaluated on IDENTICAL holdout rows:

  baseline  — _train_and_predict_stat("reb", ...) from cache_pergame_oof
  new       — train_reb_oppmodel(rows[:tr_end]) + predict_reb_oppmodel per row

Output: data/cache/pregame_oof_reb_oppmodel.parquet
Schema:
    game_id, player_id, stat, oof_pred_base, oof_pred_new, actual,
    target_min, game_date, fold, season

Usage
-----
    # Fast dev smoke (6 000 rows)
    python scripts/oof_reb_oppmodel.py --max-rows 6000

    # Full run
    python scripts/oof_reb_oppmodel.py
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
from scripts.cache_pergame_oof import _train_and_predict_stat  # noqa: E402
from src.prediction.reb_opportunity_model import (  # noqa: E402
    train_reb_oppmodel, predict_reb_oppmodel,
)

_OUT_PATH = os.path.join(
    PROJECT_DIR, "data", "cache", "pregame_oof_reb_oppmodel.parquet"
)
_N_SPLITS = 4


# ── bias-by-minutes table ─────────────────────────────────────────────────────

def _bias_table(preds: np.ndarray, actuals: np.ndarray, mins: np.ndarray) -> str:
    """Return a formatted bias-by-actual-minutes table."""
    buckets = [
        ("<12",  mins < 12),
        ("12-24", (mins >= 12) & (mins < 24)),
        ("24-32", (mins >= 24) & (mins < 32)),
        ("32+",  mins >= 32),
    ]
    lines = []
    lines.append(f"  {'Bucket':8s}  {'n':>6s}  {'MAE':>7s}  {'bias(pred-act)':>14s}")
    lines.append(f"  {'-'*8}  {'-'*6}  {'-'*7}  {'-'*14}")
    for label, mask in buckets:
        if mask.sum() == 0:
            lines.append(f"  {label:8s}  {'0':>6s}  {'N/A':>7s}  {'N/A':>14s}")
            continue
        p, a = preds[mask], actuals[mask]
        mae = float(np.mean(np.abs(p - a)))
        bias = float(np.mean(p - a))
        lines.append(f"  {label:8s}  {mask.sum():>6d}  {mae:>7.4f}  {bias:>+14.4f}")
    return "\n".join(lines)


def _shrinkage_slope(preds: np.ndarray, actuals: np.ndarray) -> str:
    """OLS slope of actual ~ a + b·pred."""
    try:
        from numpy.polynomial.polynomial import polyfit  # noqa: PLC0415
        # Use numpy lstsq for clarity
        A = np.column_stack([np.ones_like(preds), preds])
        coef, *_ = np.linalg.lstsq(A, actuals, rcond=None)
        a, b = coef
        corr = float(np.corrcoef(preds, actuals)[0, 1])
        return f"actual = {a:+.3f} + {b:.3f}·pred  (corr={corr:.3f})"
    except Exception as exc:
        return f"(slope computation failed: {exc})"


# ── main OOF loop ─────────────────────────────────────────────────────────────

def run_oof_reb(
    n_splits: int = _N_SPLITS,
    max_rows: Optional[int] = None,
) -> str:
    """Run walk-forward OOF for REB: baseline vs opportunity model.

    Returns the path to the written parquet.
    """
    import pandas as pd

    print("Loading dataset …")
    rows, fc = build_pergame_dataset(min_prior=0)
    rows.sort(key=lambda r: r["date"])
    n = len(rows)
    print(f"  total rows={n}")

    if max_rows is not None and max_rows < n:
        rows = rows[:max_rows]
        n = len(rows)
        print(f"  truncated to {n} rows (--max-rows)")

    fc_reb = feature_columns(stat="reb")   # 132 cols — baseline's exact feature set

    oof_records: List[dict] = []
    fold_ends = [(i + 1) / (n_splits + 1) for i in range(n_splits)]

    for fold_idx, train_end_frac in enumerate(fold_ends):
        tr_end = int(n * train_end_frac)
        if fold_idx == n_splits - 1:
            te_end = n
        else:
            te_end = int(n * fold_ends[fold_idx + 1])
        va_end = int(tr_end + (te_end - tr_end) * 0.4)

        min_tr = max(500, int(n * 0.05))
        min_ho = max(50,  int(n * 0.02))
        if tr_end < min_tr or (te_end - va_end) < min_ho:
            print(f"  fold {fold_idx+1}: too small (tr={tr_end}, ho={te_end-va_end}) -- skip")
            continue

        ho_rows = rows[va_end:te_end]

        # ---- recency sample weights ----------------------------------------
        tr_dates = [datetime.fromisoformat(rows[i]["date"]) for i in range(tr_end)]
        max_d = max(tr_dates)
        age = np.array([(max_d - d).days / 365.0 for d in tr_dates], dtype=float)
        sw = np.exp(-0.5 * age)

        print(
            f"\n[fold {fold_idx+1}/{n_splits}] tr={tr_end} val={va_end-tr_end} "
            f"ho={te_end-va_end}  "
            f"date_range={ho_rows[0]['date']}..{ho_rows[-1]['date']}",
            flush=True,
        )
        t0 = time.time()

        # ---- baseline: identical feature matrix as cache_pergame_oof --------
        X_tr_base  = np.array([[r[c] for c in fc_reb] for r in rows[:tr_end]],     dtype=float)
        X_val_base = np.array([[r[c] for c in fc_reb] for r in rows[tr_end:va_end]], dtype=float)
        X_ho_base  = np.array([[r[c] for c in fc_reb] for r in ho_rows],           dtype=float)

        y_all   = np.array([r["target_reb"] for r in rows], dtype=float)
        y_tr    = y_all[:tr_end]
        y_val   = y_all[tr_end:va_end]
        y_ho    = y_all[va_end:te_end]

        preds_base = _train_and_predict_stat(
            "reb", X_tr_base, y_tr, X_val_base, y_val, X_ho_base, sw
        )
        mae_base = float(np.mean(np.abs(preds_base - y_ho)))
        print(f"  baseline  ho_mae={mae_base:.4f}  n={len(ho_rows)}", flush=True)

        # ---- new: opportunity model ----------------------------------------
        artifact = train_reb_oppmodel(rows[:tr_end])
        preds_new = np.array(
            [predict_reb_oppmodel(artifact, row) for row in ho_rows],
            dtype=float,
        )
        mae_new = float(np.mean(np.abs(preds_new - y_ho)))
        delta = mae_new - mae_base
        pct = delta / mae_base * 100
        print(
            f"  new model ho_mae={mae_new:.4f}  delta={delta:+.4f} ({pct:+.1f}%)",
            flush=True,
        )
        print(f"  fold {fold_idx+1} wall: {time.time()-t0:.0f}s", flush=True)

        mins_ho = np.array([float(r.get("target_min") or 0.0) for r in ho_rows], dtype=float)

        for i, row in enumerate(ho_rows):
            oof_records.append({
                "game_id":      str(row.get("game_id", "")),
                "player_id":    int(row.get("player_id", 0)),
                "stat":         "reb",
                "oof_pred_base": float(preds_base[i]),
                "oof_pred_new":  float(preds_new[i]),
                "actual":        float(y_ho[i]),
                "target_min":    float(mins_ho[i]),
                "game_date":    str(row["date"])[:10],
                "fold":          fold_idx + 1,
                "season":        str(row.get("season", "")),
            })

    if not oof_records:
        raise RuntimeError("No OOF records generated — all folds skipped (dataset too small?).")

    df = pd.DataFrame(oof_records)
    df = df[[
        "game_id", "player_id", "stat",
        "oof_pred_base", "oof_pred_new", "actual",
        "target_min", "game_date", "fold", "season",
    ]]

    os.makedirs(os.path.dirname(_OUT_PATH), exist_ok=True)
    df.to_parquet(_OUT_PATH, index=False)

    # ── full report ──────────────────────────────────────────────────────────
    preds_base_all = df["oof_pred_base"].values
    preds_new_all  = df["oof_pred_new"].values
    actuals_all    = df["actual"].values
    mins_all       = df["target_min"].values

    mae_base_all = float(np.mean(np.abs(preds_base_all - actuals_all)))
    mae_new_all  = float(np.mean(np.abs(preds_new_all  - actuals_all)))
    delta_all    = mae_new_all - mae_base_all
    pct_all      = delta_all / mae_base_all * 100

    print("\n" + "=" * 70)
    print("  REB OPPORTUNITY MODEL -- LEAK-FREE OOF REPORT")
    print("=" * 70)
    print(f"  Total holdout rows : {len(df):,}")
    print(f"  Folds evaluated    : {df['fold'].nunique()}")
    print()
    print(f"  Overall baseline MAE : {mae_base_all:.4f}")
    print(f"  Overall new MAE      : {mae_new_all:.4f}")
    print(f"  Delta (new-base)     : {delta_all:+.4f}  ({pct_all:+.2f}%)")
    print()

    # Per-fold table
    print("  Per-fold MAE:")
    print(f"  {'fold':>4s}  {'n':>6s}  {'baseline':>9s}  {'new':>9s}  {'delta':>8s}  {'%':>7s}")
    print(f"  {'-'*4}  {'-'*6}  {'-'*9}  {'-'*9}  {'-'*8}  {'-'*7}")
    for fold in sorted(df["fold"].unique()):
        fdf = df[df["fold"] == fold]
        pb = fdf["oof_pred_base"].values
        pn = fdf["oof_pred_new"].values
        a  = fdf["actual"].values
        mb = float(np.mean(np.abs(pb - a)))
        mn = float(np.mean(np.abs(pn - a)))
        d  = mn - mb
        pp = d / mb * 100 if mb > 0 else 0.0
        print(f"  {fold:>4d}  {len(fdf):>6d}  {mb:>9.4f}  {mn:>9.4f}  {d:>+8.4f}  {pp:>+6.1f}%")

    # Bias-by-minutes tables
    print()
    print("  Bias-by-ACTUAL-minutes (pred - actual):")
    print()
    print("  --- BASELINE ---")
    print(_bias_table(preds_base_all, actuals_all, mins_all))
    print()
    print("  --- NEW MODEL ---")
    print(_bias_table(preds_new_all, actuals_all, mins_all))

    # Shrinkage slopes
    print()
    print("  Shrinkage slope  actual ~ a + b·pred:")
    print(f"    baseline : {_shrinkage_slope(preds_base_all, actuals_all)}")
    print(f"    new      : {_shrinkage_slope(preds_new_all,  actuals_all)}")

    # Validation gate
    print()
    print("  VALIDATION GATES:")
    # Gate A: overall new MAE < baseline
    pass_a = mae_new_all < mae_base_all
    print(f"  (A) Overall MAE < baseline ({mae_base_all:.4f}):  "
          f"{'PASS' if pass_a else 'FAIL'}  new={mae_new_all:.4f}")

    # Gate B: bias-by-minutes fan compresses
    # Compute per-bucket biases for both models
    def _bucket_bias(preds, actuals, mins, lo, hi):
        mask = (mins >= lo) & (mins < hi)
        if mask.sum() == 0:
            return None
        return float(np.mean(preds[mask] - actuals[mask]))

    bias_base_low  = _bucket_bias(preds_base_all, actuals_all, mins_all, 0, 12)
    bias_base_high = _bucket_bias(preds_base_all, actuals_all, mins_all, 32, 999)
    bias_new_low   = _bucket_bias(preds_new_all,  actuals_all, mins_all, 0, 12)
    bias_new_high  = _bucket_bias(preds_new_all,  actuals_all, mins_all, 32, 999)

    pass_b = (
        bias_base_low is not None and bias_new_low is not None
        and bias_base_high is not None and bias_new_high is not None
        and abs(bias_new_low)  < abs(bias_base_low)
        and abs(bias_new_high) < abs(bias_base_high)
    )
    print(
        f"  (B) Bias fan compresses (<12 and 32+ both shrink):  "
        f"{'PASS' if pass_b else 'FAIL'}  "
        f"<12: base={bias_base_low:+.3f} new={bias_new_low:+.3f}  "
        f"32+: base={bias_base_high:+.3f} new={bias_new_high:+.3f}"
    )

    # Gate C: no degenerate behaviour (finite, non-negative, not constant)
    preds_finite = np.all(np.isfinite(preds_new_all))
    preds_nonneg = np.all(preds_new_all >= 0.0)
    preds_varied = float(np.std(preds_new_all)) > 0.05
    pass_c = preds_finite and preds_nonneg and preds_varied
    print(
        f"  (C) No degenerate behaviour (finite/non-neg/varied):  "
        f"{'PASS' if pass_c else 'FAIL'}  "
        f"finite={preds_finite} non_neg={preds_nonneg} "
        f"std={float(np.std(preds_new_all)):.3f}"
    )

    print()
    gates_passed = sum([pass_a, pass_b, pass_c])
    if pass_a and pass_c:
        verdict = "SHIP (MAE beats baseline + no degeneracy)"
    else:
        verdict = "REJECT -- does not improve OOF MAE over the baseline"
    print(f"  RECOMMENDATION: {verdict}  [{gates_passed}/3 gates pass]")
    print("=" * 70)

    print(f"\nWrote: {_OUT_PATH}  ({os.path.getsize(_OUT_PATH) // 1024} KB)")
    return _OUT_PATH


# ── entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    ap = argparse.ArgumentParser(
        description="Walk-forward OOF A/B: REB opportunity model vs baseline."
    )
    ap.add_argument(
        "--max-rows", type=int, default=None, metavar="N",
        help="Truncate dataset to first N rows for fast dev runs.",
    )
    ap.add_argument(
        "--splits", type=int, default=_N_SPLITS,
        help=f"Number of WF splits (default {_N_SPLITS}).",
    )
    args = ap.parse_args()
    run_oof_reb(n_splits=args.splits, max_rows=args.max_rows)
