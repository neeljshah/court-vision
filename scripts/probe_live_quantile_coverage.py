"""probe_live_quantile_coverage.py -- Cycle 105c (loop 5).

Validate that the calibrated live quantile bands hit ~80% empirical coverage
on the held-out half of the cycle-91a retro.

For each (snap_period, stat):
    bands = bands_for(stat, projected, snapshot_point)
    coverage = mean( q10 <= actual <= q90 )

Ship gate: >=5/7 stats per snapshot_point fall in [0.75, 0.85].

Run:
    python scripts/probe_live_quantile_coverage.py
    python scripts/probe_live_quantile_coverage.py --max-games 100
"""
from __future__ import annotations

import argparse
import os
import sys
from typing import Dict, List, Tuple

import numpy as np

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)
SCRIPTS_DIR = os.path.join(PROJECT_DIR, "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

from src.prediction.live_quantile_bands import (  # noqa: E402
    bands_for, load_calibration, reset_cache,
)
import calibrate_live_quantiles as clq  # noqa: E402

STATS = ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov")
SNAPSHOT_POINTS = ("endQ2", "endQ3")
_COVERAGE_LO = 0.75
_COVERAGE_HI = 0.85
_TARGET = 0.80
_SHIP_MIN_OK = 5   # >=5/7 stats per point inside [0.75, 0.85]


def probe(max_games: int = 0, val_frac: float = 0.5) -> dict:
    reset_cache()
    cal = load_calibration()
    if not cal:
        print("[fail] no calibration artifact -- run "
              "scripts/calibrate_live_quantiles.py first", flush=True)
        return {}

    pairs = clq._collect_residuals(max_games=max_games)

    results: Dict[str, Dict[str, dict]] = {}
    for point in SNAPSHOT_POINTS:
        results[point] = {}
        n_ok = 0
        for stat in STATS:
            pts = pairs[point].get(stat) or []
            if len(pts) < 30:
                print(f"  [skip] {point}/{stat}: n={len(pts)}", flush=True)
                continue
            arr = np.asarray(pts, dtype=float)
            n = len(arr)
            # Interleaved opposite slice from the calibrator.
            held = arr[1::2] if val_frac == 0.5 else arr[int(n * val_frac):]
            if len(held) == 0:
                continue
            covered = 0
            for proj, actual in held:
                b = bands_for(stat, proj, point, calibration=cal)
                if b["q10"] <= actual <= b["q90"]:
                    covered += 1
            cov = covered / len(held)
            ok = _COVERAGE_LO <= cov <= _COVERAGE_HI
            if ok:
                n_ok += 1
            results[point][stat] = {
                "n_held": int(len(held)),
                "coverage_held": round(cov, 4),
                "ok": bool(ok),
            }
            print(f"  {point}/{stat:4s}  n={len(held):4d}  "
                  f"cov={cov:.3f}  {'OK' if ok else 'OUT'}",
                  flush=True)
        results[point]["_n_ok"] = n_ok
        results[point]["_ship"] = n_ok >= _SHIP_MIN_OK
        print(f"  {point}: {n_ok}/7 in [{_COVERAGE_LO}, {_COVERAGE_HI}] -- "
              f"{'SHIP' if n_ok >= _SHIP_MIN_OK else 'REJECT'}",
              flush=True)

    return results


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-games", type=int, default=0)
    ap.add_argument("--val-frac", type=float, default=0.5)
    args = ap.parse_args()
    probe(max_games=args.max_games, val_frac=args.val_frac)


if __name__ == "__main__":
    import warnings
    warnings.filterwarnings("ignore")
    main()
