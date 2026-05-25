"""probe_center_blk_residual.py -- cycle 106d (loop 5).

Validate the trained CenterBlkResidualModel as a POST-PREDICTION BLK
adjustment on the canonical 80/20 chronological holdout. Reports:

    - factor distribution on holdout (mean / min / max / pct above 1.0)
    - Center BLK MAE before / after
    - non-Center BLK MAE before / after (must be unchanged at 1e-12)
    - 4-fold walk-forward Center-BLK delta

Ship gate (RELAXED per workday spec, since cycles 97b/98b/100b/101b/102d
all rejected):

    Center BLK MAE delta <= -0.05      (single-split)
    non-Center BLK delta == 0 (exact)  (gate fired only on Center stratum)
    WF Center-BLK 4/4 folds negative
"""
from __future__ import annotations

import argparse
import os
import sys
import warnings
from typing import Dict, List

warnings.filterwarnings("ignore")

import numpy as np  # noqa: E402

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from src.prediction.prop_pergame import (  # noqa: E402
    build_pergame_dataset, feature_columns,
)
from src.prediction.center_blk_residual import (  # noqa: E402
    CENTER_POSITIONS,
    CenterBlkResidualModel,
    center_blk_shrinkage_factor,
    apply_center_blk_shrinkage,
)
from scripts.validate_adjustment import _bulk_predict  # noqa: E402


_RESULTS_DIR = os.path.join(PROJECT_DIR, "scripts", "_results")
os.makedirs(_RESULTS_DIR, exist_ok=True)


def _apply_residual(pred: np.ndarray, rows: List[dict],
                    residual: CenterBlkResidualModel) -> tuple:
    """Return (adjusted_pred, per_row_factors)."""
    out = pred.copy()
    factors = np.ones(len(pred), dtype=float)
    for i, r in enumerate(rows):
        f = center_blk_shrinkage_factor(
            residual_model=residual,
            stat="blk",
            position=r.get("position"),
            feature_row=r,
        )
        factors[i] = f
        if f != 1.0:
            out[i] = apply_center_blk_shrinkage(pred[i], f)
    return out, factors


def _blk_mae(pred: np.ndarray, rows: List[dict]) -> tuple:
    y = np.array([
        np.nan if r.get("target_blk") is None else float(r["target_blk"])
        for r in rows
    ], dtype=float)
    mask = ~np.isnan(y)
    if not mask.any():
        return float("nan"), 0
    return float(np.mean(np.abs(pred[mask] - y[mask]))), int(mask.sum())


def _split_by_position(rows: List[dict]) -> tuple:
    center_idx = [i for i, r in enumerate(rows) if r.get("position") in CENTER_POSITIONS]
    other_idx = [i for i in range(len(rows)) if i not in set(center_idx)]
    return center_idx, other_idx


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-wf", action="store_true")
    args = ap.parse_args()

    print("Loading pergame dataset...", flush=True)
    rows, _ = build_pergame_dataset(min_prior=0)
    rows.sort(key=lambda r: r["date"])
    cols = feature_columns()

    n_total = len(rows)
    holdout = rows[int(n_total * 0.80):]
    X = np.array([[float(r.get(c, 0.0) or 0.0) for c in cols]
                  for r in holdout], dtype=float)
    print(f"  n_total={n_total}  holdout={len(holdout)}", flush=True)

    residual = CenterBlkResidualModel.load()
    if residual is None:
        print("  ERROR: residual artifact missing -- run train_center_blk_residual.py first")
        return 2

    pred = _bulk_predict("blk", X)
    if pred is None:
        print("  ERROR: BLK model missing")
        return 2

    adj, factors = _apply_residual(pred, holdout, residual)

    # Factor distribution
    fired = factors[factors != 1.0]
    print()
    print("Factor distribution (rows where gate fired):")
    if len(fired):
        print(f"  n_fired={len(fired)}  mean={fired.mean():.3f}  "
              f"min={fired.min():.3f}  max={fired.max():.3f}  "
              f"frac>1.0={(fired > 1.0).mean():.2%}", flush=True)
    else:
        print("  GATE NEVER FIRED -- no Center rows in holdout?")

    center_idx, other_idx = _split_by_position(holdout)
    print(f"  center holdout rows: {len(center_idx)}  "
          f"non-center: {len(other_idx)}", flush=True)

    # Per-bucket MAE
    c_rows = [holdout[i] for i in center_idx]
    o_rows = [holdout[i] for i in other_idx]
    c_pred_b = pred[center_idx]; c_pred_a = adj[center_idx]
    o_pred_b = pred[other_idx]; o_pred_a = adj[other_idx]
    c_mae_b, c_n = _blk_mae(c_pred_b, c_rows)
    c_mae_a, _ = _blk_mae(c_pred_a, c_rows)
    o_mae_b, o_n = _blk_mae(o_pred_b, o_rows)
    o_mae_a, _ = _blk_mae(o_pred_a, o_rows)

    print()
    print("=" * 70)
    print(f"  {'bucket':<14} {'n':>6} {'base_MAE':>10} {'adj_MAE':>10} {'delta':>10}")
    print("-" * 70)
    print(f"  {'CENTER':<14} {c_n:>6d} {c_mae_b:>10.4f} {c_mae_a:>10.4f} "
          f"{c_mae_a - c_mae_b:>+10.4f}")
    print(f"  {'non-CENTER':<14} {o_n:>6d} {o_mae_b:>10.4f} {o_mae_a:>10.4f} "
          f"{o_mae_a - o_mae_b:>+10.4f}")
    print("=" * 70)

    c_delta = c_mae_a - c_mae_b
    o_delta = o_mae_a - o_mae_b
    ss_pass = (c_delta <= -0.05) and (abs(o_delta) < 1e-12)

    # Walk-forward 4 folds on Center subset
    wf_pass = True
    wf_deltas: List[float] = []
    if not args.skip_wf and len(center_idx) >= 80:
        # Fold over holdout chronologically; report on Center rows per fold.
        print()
        print("WALK-FORWARD 4-fold (Center subset)")
        n_h = len(holdout)
        fold_size = n_h // 4
        for k in range(4):
            lo = k * fold_size
            hi = n_h if k == 3 else (k + 1) * fold_size
            sub_rows = holdout[lo:hi]
            sub_X = X[lo:hi]
            sub_pred = _bulk_predict("blk", sub_X)
            sub_adj, _ = _apply_residual(sub_pred, sub_rows, residual)
            c_idx, _ = _split_by_position(sub_rows)
            if not c_idx:
                wf_deltas.append(float("nan"))
                continue
            cr = [sub_rows[i] for i in c_idx]
            b, _ = _blk_mae(sub_pred[c_idx], cr)
            a, _ = _blk_mae(sub_adj[c_idx], cr)
            wf_deltas.append(a - b)
            print(f"  fold {k+1}: n_center={len(c_idx)}  "
                  f"base={b:.4f}  adj={a:.4f}  delta={a-b:+.4f}", flush=True)
        n_neg = sum(1 for d in wf_deltas if (d == d and d < -0.0001))
        wf_pass = (n_neg == 4)
        print(f"  WF: {n_neg}/4 folds negative on Center BLK")

    print()
    print("=" * 70)
    print(f"SHIP GATE:")
    print(f"  Center BLK delta <= -0.05    : {c_delta:+.4f}  "
          f"{'PASS' if c_delta <= -0.05 else 'FAIL'}")
    print(f"  non-Center BLK delta == 0    : {o_delta:+.2e}  "
          f"{'PASS' if abs(o_delta) < 1e-12 else 'FAIL'}")
    if not args.skip_wf:
        print(f"  WF 4/4 negative on Center    : "
              f"{sum(1 for d in wf_deltas if (d==d and d<-0.0001))}/4  "
              f"{'PASS' if wf_pass else 'FAIL'}")
    final = ss_pass and wf_pass
    print(f"  VERDICT: {'SHIP' if final else 'REJECT'}")
    print("=" * 70)

    # Report file
    out_path = os.path.join(_RESULTS_DIR, "center_blk_residual_v1.md")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("# Cycle 106d (loop 5) -- center-BLK opp-aware shrinkage residual\n\n")
        f.write("## Pattern\n")
        f.write("Heat-check pattern: stratified residual outputs a bounded factor "
                "applied multiplicatively to BLK predictions, ONLY for Center "
                "positions. Clamp [0.80, 1.50].\n\n")
        f.write(f"- holdout rows: {len(holdout)}\n")
        f.write(f"- center rows : {len(center_idx)}\n")
        f.write(f"- gate fired  : {len(fired)} rows\n")
        if len(fired):
            f.write(f"- factor mean : {fired.mean():.3f}  "
                    f"min {fired.min():.3f}  max {fired.max():.3f}\n")
        f.write("\n## Holdout BLK MAE\n\n")
        f.write("| bucket | n | base | adj | delta |\n")
        f.write("|---|---|---|---|---|\n")
        f.write(f"| CENTER | {c_n} | {c_mae_b:.4f} | {c_mae_a:.4f} | {c_delta:+.4f} |\n")
        f.write(f"| non-CENTER | {o_n} | {o_mae_b:.4f} | {o_mae_a:.4f} | {o_delta:+.4f} |\n")
        if not args.skip_wf:
            f.write("\n## Walk-forward Center BLK delta\n\n")
            f.write("| fold1 | fold2 | fold3 | fold4 |\n|---|---|---|---|\n|")
            for d in wf_deltas:
                f.write(f" {d:+.4f} |")
            f.write("\n")
        f.write(f"\n**VERDICT: {'SHIP' if final else 'REJECT'}**\n")
    print(f"\nReport written: {out_path}")

    print(f"\n__CENTER_DELTA__={c_delta:+.4f}")
    print(f"__NONCENTER_DELTA__={o_delta:+.2e}")
    print(f"__FINAL__={'SHIP' if final else 'REJECT'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
