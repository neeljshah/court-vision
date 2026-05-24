"""verify_winprob.py — sanity check the WinProb claim in PREDICTIONS_QUICKSTART.

PREDICTIONS_QUICKSTART.md claims:
    WinProb walk-forward: 0.71 acc / 0.193 Brier
    Single-split: 0.717 / 0.188

The walk-forward results are cached at data/models/winprob_walk_forward_results.json
(written by scripts/winprob_walk_forward.py). This script reads that file
and compares to the claim — exits 0 if within tolerance, 1 with drift report
otherwise. Same shape as cycle-48 scripts/verify_production_mae.py.

Cheap (file read, no model training) so it's safe to wire into CI later.

Run:
    python scripts/verify_winprob.py
    python scripts/verify_winprob.py --retrain    # also fail if results file is older than 30 days
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_RESULTS_PATH = os.path.join(PROJECT_DIR, "data", "models",
                              "winprob_walk_forward_results.json")

# Claims from PREDICTIONS_QUICKSTART.md cycle 50 refresh.
CLAIM_ACC_WF = 0.71
CLAIM_BRIER_WF = 0.193
ACC_TOLERANCE = 0.01
BRIER_TOLERANCE = 0.005

STALE_DAYS = 30


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--retrain", action="store_true",
                    help="Also fail if results file is older than 30 days.")
    args = ap.parse_args()

    if not os.path.exists(_RESULTS_PATH):
        print(f"[fail] missing {os.path.relpath(_RESULTS_PATH, PROJECT_DIR)}")
        print("       Run scripts/winprob_walk_forward.py first.")
        return 1

    with open(_RESULTS_PATH, encoding="utf-8") as f:
        payload = json.load(f)
    acc = float(payload.get("acc_mean", 0.0))
    brier = float(payload.get("brier_mean", 0.0))
    n_folds = int(payload.get("n_folds", 0))
    file_age_days = (time.time() - os.path.getmtime(_RESULTS_PATH)) / 86400

    d_acc = acc - CLAIM_ACC_WF
    d_brier = brier - CLAIM_BRIER_WF
    acc_ok = abs(d_acc) <= ACC_TOLERANCE
    brier_ok = abs(d_brier) <= BRIER_TOLERANCE

    print("=== WinProb walk-forward verification ===")
    print(f"  results file age: {file_age_days:.1f} days  ({n_folds} folds)")
    print(f"  acc:    claim {CLAIM_ACC_WF:.4f}  live {acc:.4f}  d={d_acc:+.4f}  "
          f"{'OK' if acc_ok else 'DRIFT'}")
    print(f"  brier:  claim {CLAIM_BRIER_WF:.4f}  live {brier:.4f}  d={d_brier:+.4f}  "
          f"{'OK' if brier_ok else 'DRIFT'}")

    stale = args.retrain and file_age_days > STALE_DAYS
    if stale:
        print(f"\n[stale] results are {file_age_days:.0f} days old (>{STALE_DAYS}).")
        print("        Re-run scripts/winprob_walk_forward.py to refresh.")

    if acc_ok and brier_ok and not stale:
        print("\nALL within tolerance. WinProb production matches quickstart.")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
