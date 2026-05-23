"""
retrain_blowout_ot.py — CLI entrypoint for BlowoutOTPredictorV2 training.

Usage:
    conda run -n basketball_ai python scripts/retrain_blowout_ot.py
    conda run -n basketball_ai python scripts/retrain_blowout_ot.py --seasons 2022-23 2023-24 2024-25
    conda run -n basketball_ai python scripts/retrain_blowout_ot.py --model-dir data/models
"""

from __future__ import annotations

import argparse
import json
import os
import sys

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from src.prediction.blowout_ot_v2 import BlowoutOTPredictorV2


def main() -> None:
    ap = argparse.ArgumentParser(description="Retrain blowout + OT classifiers v2")
    ap.add_argument(
        "--seasons", nargs="+",
        default=["2022-23", "2023-24", "2024-25"],
        help="Seasons to include (default: 2022-23 2023-24 2024-25)",
    )
    ap.add_argument(
        "--model-dir", default="data/models",
        help="Model output directory (default: data/models)",
    )
    args = ap.parse_args()

    print(f"[retrain_blowout_ot] Seasons: {args.seasons}")
    print(f"[retrain_blowout_ot] Model dir: {args.model_dir}")

    predictor = BlowoutOTPredictorV2(model_dir=args.model_dir)
    results = predictor.train(seasons=args.seasons)

    print("\n" + "=" * 60)
    print("RESULTS SUMMARY")
    print("=" * 60)

    for key in ("blowout", "ot"):
        m = results.get(key, {})
        print(f"\n[{key.upper()}]")
        for field in ("acc", "brier", "auc", "logloss", "n", "pos", "ot_rate", "blowout_rate"):
            if field in m:
                print(f"  {field:<14} {m[field]}")
        holdout = m.get("holdout", {})
        if holdout:
            print(f"  --- Holdout ---")
            for field in ("acc", "brier", "auc", "logloss"):
                if field in holdout:
                    print(f"  holdout_{field:<8} {holdout[field]}")
        top_feats = m.get("top_features", [])
        if top_feats:
            print(f"  Top-8 features:")
            for i, ft in enumerate(top_feats[:8], 1):
                print(f"    {i}. {ft['feature']} ({ft['importance']:.0f})")
        cal_bins = m.get("calibration_bins", [])
        if cal_bins:
            print(f"  Calibration bins (predicted → actual):")
            for b in cal_bins:
                print(f"    {b['predicted_mid']:.2f} → {b['actual_rate']:.3f} "
                      f"(n={b['count']})")

    print("\n[retrain_blowout_ot] Done.")


if __name__ == "__main__":
    main()
