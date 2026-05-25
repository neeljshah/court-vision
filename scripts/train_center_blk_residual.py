"""train_center_blk_residual.py -- cycle 106d (loop 5).

Train :class:`src.prediction.center_blk_residual.CenterBlkResidualModel` on the
Center stratum of the pergame dataset. Target is actual_blk / predicted_blk,
clipped to [FACTOR_FLOOR, FACTOR_CEIL]. Chronological 80/20 train/val split.

Usage:
    python scripts/train_center_blk_residual.py
"""
from __future__ import annotations

import os
import sys
from typing import List

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

import numpy as np  # noqa: E402

from src.prediction.prop_pergame import (  # noqa: E402
    build_pergame_dataset, feature_columns,
)
from src.prediction.center_blk_residual import (  # noqa: E402
    CENTER_POSITIONS,
    FACTOR_CEIL,
    FACTOR_FLOOR,
    CenterBlkResidualModel,
    build_feature_row,
)
from scripts.validate_adjustment import _bulk_predict  # noqa: E402


def main() -> int:
    print("Loading pergame dataset (with position join)...", flush=True)
    rows, _ = build_pergame_dataset(min_prior=0)
    rows.sort(key=lambda r: r["date"])
    cols = feature_columns()

    # Filter to Center stratum AND rows that actually played (target_blk present)
    stratum_rows = [
        r for r in rows
        if r.get("position") in CENTER_POSITIONS and r.get("target_blk") is not None
    ]
    print(f"  total rows: {len(rows)}", flush=True)
    print(f"  center-stratum rows: {len(stratum_rows)}", flush=True)
    if not stratum_rows:
        print("  ERROR: empty stratum, abort")
        return 2

    # Bulk-predict BLK for stratum rows.
    X_full = np.array([[float(r.get(c, 0.0) or 0.0) for c in cols]
                       for r in stratum_rows], dtype=float)
    pred = _bulk_predict("blk", X_full)
    if pred is None:
        print("  ERROR: BLK model missing, cannot compute ratios")
        return 2

    # Build training corpus: ratio = actual / pred (skip when pred ~= 0).
    X_rows: List[List[float]] = []
    y_ratios: List[float] = []
    dates = []
    eps = 1e-3
    for r, p in zip(stratum_rows, pred):
        if p < eps:
            continue
        actual = float(r["target_blk"])
        ratio = actual / float(p)
        feats = build_feature_row(
            l5_blk=r.get("l5_blk"),
            l10_blk=r.get("l10_blk"),
            l5_min=r.get("l5_min"),
            l10_min=r.get("l10_min"),
            opp_def_blk=r.get("opp_def_blk"),
            opp_team_pace_l5=r.get("opp_team_pace_l5"),
            opp_team_oreb_pct_l5=r.get("opp_team_oreb_pct_l5"),
            home_spread=r.get("home_spread"),
        )
        X_rows.append(feats)
        y_ratios.append(ratio)
        dates.append(r["date"])

    n = len(X_rows)
    print(f"  training rows after pred>{eps} filter: {n}", flush=True)
    if n < 200:
        print("  ERROR: too few rows for a robust fit")
        return 2

    # Diagnostics
    raw = np.asarray(y_ratios)
    clipped = np.clip(raw, FACTOR_FLOOR, FACTOR_CEIL)
    print(f"  raw ratio: mean={raw.mean():.3f}  median={np.median(raw):.3f}  "
          f"p10={np.percentile(raw,10):.3f}  p90={np.percentile(raw,90):.3f}  "
          f"min={raw.min():.3f}  max={raw.max():.3f}", flush=True)
    print(f"  clipped[{FACTOR_FLOOR},{FACTOR_CEIL}] mean={clipped.mean():.3f}  "
          f"min={clipped.min():.3f}  max={clipped.max():.3f}", flush=True)
    print(f"  frac below floor: {float(np.mean(raw < FACTOR_FLOOR)):.2%}  "
          f"above ceil: {float(np.mean(raw > FACTOR_CEIL)):.2%}", flush=True)

    # Chronological 80/20 split on dates.
    order = np.argsort(dates)
    X_arr = np.asarray(X_rows)[order]
    y_arr = np.asarray(y_ratios)[order]
    cutoff = int(n * 0.80)
    X_tr, y_tr = X_arr[:cutoff], y_arr[:cutoff]
    X_val, y_val = X_arr[cutoff:], y_arr[cutoff:]
    print(f"  split: train={len(X_tr)}  val={len(X_val)}", flush=True)

    model = CenterBlkResidualModel()
    model.fit(X_tr.tolist(), y_tr.tolist(),
              X_val=X_val.tolist(), y_val=y_val.tolist(),
              num_boost_round=300, learning_rate=0.04,
              num_leaves=15, min_data_in_leaf=15, seed=42)

    if len(X_val):
        pred_val = model.predict(X_val.tolist())
        y_val_c = np.clip(y_val, FACTOR_FLOOR, FACTOR_CEIL)
        val_mae = float(np.mean(np.abs(pred_val - y_val_c)))
        baseline = float(np.mean(np.abs(y_val_c - np.mean(np.clip(y_tr, FACTOR_FLOOR, FACTOR_CEIL)))))
        print(f"  val RATIO MAE: {val_mae:.4f}  baseline (mean-pred): {baseline:.4f}  "
              f"(improvement: {baseline - val_mae:+.4f})", flush=True)
        print(f"  val pred dist: mean={pred_val.mean():.3f}  "
              f"min={pred_val.min():.3f}  max={pred_val.max():.3f}", flush=True)

    print(f"  fallback (mean clipped ratio): {model.fallback_mean:.4f}", flush=True)
    model.save()
    print(f"  saved -> data/models/center_blk_residual.lgb", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
