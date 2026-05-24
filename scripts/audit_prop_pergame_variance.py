"""audit_prop_pergame_variance.py — zero/near-zero variance audit (loop 5 cycle 1, track A1).

Mirrors WinProb cycle 17 audit. Builds the prop_pergame dataset, then reports:
  * Constant features (variance == 0).
  * Near-constant features (top-1 value covers > 99% of rows).
  * Per-feature variance + non-zero counts.

Output is JSON at data/models/prop_pergame_feature_audit.json plus a console summary.
"""
from __future__ import annotations

import json
import os
import sys
from collections import Counter

import numpy as np

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from src.prediction.prop_pergame import build_pergame_dataset  # noqa: E402


def main() -> None:
    rows, feature_cols = build_pergame_dataset(min_prior=0)
    n = len(rows)
    print(f"[audit] rows={n} features={len(feature_cols)}")
    if n == 0:
        print("[audit] no rows — abort")
        return

    X = np.array([[r[c] for c in feature_cols] for r in rows], dtype=float)
    summary = {"n_rows": n, "n_features": len(feature_cols),
               "constant": [], "near_constant": [], "low_signal": [],
               "all": {}}

    for j, name in enumerate(feature_cols):
        col = X[:, j]
        var = float(np.var(col))
        nz  = int(np.count_nonzero(col))
        unique = np.unique(col)
        top_share = 0.0
        if unique.size > 0:
            counts = Counter(col.tolist())
            top_val, top_cnt = counts.most_common(1)[0]
            top_share = top_cnt / n
        summary["all"][name] = {
            "var": round(var, 6),
            "nonzero_count": nz,
            "nonzero_frac": round(nz / n, 4),
            "n_unique": int(unique.size),
            "top_value_share": round(top_share, 4),
        }
        if var == 0.0:
            summary["constant"].append(name)
        elif top_share > 0.99:
            summary["near_constant"].append(name)
        elif top_share > 0.95:
            summary["low_signal"].append(name)

    out_path = os.path.join(PROJECT_DIR, "data", "models", "prop_pergame_feature_audit.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print("\n=== constant features (variance == 0) ===")
    for name in summary["constant"]:
        print(f"  {name}")
    print(f"  total: {len(summary['constant'])}")

    print("\n=== near-constant (>99% one value) ===")
    for name in summary["near_constant"]:
        info = summary["all"][name]
        print(f"  {name}: top_share={info['top_value_share']:.4f} n_unique={info['n_unique']}")
    print(f"  total: {len(summary['near_constant'])}")

    print("\n=== low-signal (95-99% one value) ===")
    for name in summary["low_signal"]:
        info = summary["all"][name]
        print(f"  {name}: top_share={info['top_value_share']:.4f} n_unique={info['n_unique']}")
    print(f"  total: {len(summary['low_signal'])}")

    print(f"\n[audit] wrote {out_path}")


if __name__ == "__main__":
    main()
