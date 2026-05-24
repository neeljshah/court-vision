"""measure_bbref_playtype_leak.py — quantify the bbref + playtype leak in prop_pergame.

Trains prop_pergame twice:
  A) baseline: all 85 features (incl. season-final bbref + playtype) — current.
  B) zeroed:   bbref_* and pt_*_freq forced to 0.0 across all rows — kills the
     leak channel entirely (also kills any legitimate signal those carry).

The Δ between A and B bounds the magnitude of the leak. If the gap is small
(<0.005 R² across all stats), the features are mostly noise and removing them
costs little. If large (e.g. >0.02 R² on PTS), there's substantial signal —
some legitimate (player skill), some leaked (knowing the player's eventual
full-season USG/TS).
"""
from __future__ import annotations

import json
import os
import sys
import time

import numpy as np

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from src.prediction.prop_pergame import (  # noqa: E402
    STATS, build_pergame_dataset, feature_columns, train_pergame_models,
)


def main():
    rows, feature_cols = build_pergame_dataset(min_prior=0)
    print(f"[measure] dataset: {len(rows)} rows × {len(feature_cols)} features")

    leak_keys = [c for c in feature_cols if c.startswith("bbref_") or c.startswith("pt_")]
    print(f"[measure] candidate leak cols: {len(leak_keys)}")

    # Baseline metrics file — what we have on disk now.
    base_path = os.path.join(PROJECT_DIR, "data", "models", "props_pergame_metrics.json")
    with open(base_path) as f:
        baseline = json.load(f)
    print("\n=== A) BASELINE (current, leaky) ===")
    for s in STATS:
        m = baseline["stats"][s]
        print(f"  {s.upper():4s} R²={m['holdout_r2']:.4f} MAE={m['holdout_mae']:.4f}")

    # Build a zeroed dataset and inject it via gamelog_dir trick — actually
    # simpler: monkey-patch _get_bbref / _get_playtypes / _get_contracts to
    # return all-zero defaults. Restart by re-running train_pergame_models
    # with a manipulated dataset is hard, so we just zero in place.
    import src.prediction.prop_pergame as ppg

    # Save originals
    orig_get_bbref = ppg._get_bbref
    orig_get_pt = ppg._get_playtypes

    class _NullBBRef:
        def features(self, player_id, season):
            return dict.fromkeys([f"bbref_{k}" for k in ppg._BBREF_KEYS], 0.0)

    class _NullPT:
        def features(self, player_id, season):
            return dict.fromkeys([f"pt_{pt}_freq" for pt in ppg._PLAY_TYPES], 0.0)

    ppg._get_bbref = lambda: _NullBBRef()
    ppg._get_playtypes = lambda: _NullPT()
    # also bust their lazy caches
    ppg._BBREF_CACHE = None
    ppg._PLAYTYPES_CACHE = None

    try:
        t0 = time.time()
        zeroed = ppg.train_pergame_models()
        wall = time.time() - t0
    finally:
        ppg._get_bbref = orig_get_bbref
        ppg._get_playtypes = orig_get_pt

    print(f"\n=== B) ZEROED bbref + playtype ({wall:.0f}s) ===")
    print(" stat | baseline R² | zeroed R² | ΔR² | baseline MAE | zeroed MAE | ΔMAE")
    print("------+-------------+-----------+-----+--------------+------------+------")
    for s in STATS:
        b = baseline["stats"][s]
        z = zeroed["stats"][s]
        dr2 = z["holdout_r2"] - b["holdout_r2"]
        dmae = z["holdout_mae"] - b["holdout_mae"]
        print(f"  {s.upper():4s} | {b['holdout_r2']:.4f}      | "
              f"{z['holdout_r2']:.4f}    | {dr2:+.4f} | "
              f"{b['holdout_mae']:.4f}       | {z['holdout_mae']:.4f}     | {dmae:+.4f}")

    out = {"baseline": baseline["stats"], "zeroed": zeroed["stats"], "wall_s": round(wall, 1)}
    out_path = os.path.join(PROJECT_DIR, "data", "models", "bbref_playtype_leak_measure.json")
    with open(out_path, "w") as f:
        json.dump(out, f, indent=2)
    print(f"\n[measure] wrote {out_path}")


if __name__ == "__main__":
    main()
