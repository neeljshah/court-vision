"""
retrain_props_now.py — Retrain the prop ensemble on locally-cached seasons.

Banks the code-level prediction fixes into actual model files:
  * PRED-08 — count-stat regularisation (xgb_params_for_stat)
  * PRED-12 — grid-searched hyperparameters
  * PRED-10 — LightGBM base learner + the multi-model stacker

Uses only the locally-cached seasons so it never blocks on the NBA API.

Usage:
    python scripts/retrain_props_now.py [--seasons 2024-25 2025-26]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import traceback

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)


def main() -> int:
    ap = argparse.ArgumentParser(description="Retrain the prop ensemble")
    ap.add_argument("--seasons", nargs="+", default=["2024-25", "2025-26"])
    args = ap.parse_args()
    seasons = args.seasons

    summary: dict = {"seasons": seasons}
    try:
        from src.prediction.player_props import train_props, train_props_lightgbm

        print(f"=== XGBoost prop retrain — seasons={seasons} ===", flush=True)
        summary["xgb"] = train_props(seasons=seasons, force=True)
        print("XGB_RESULT=" + json.dumps(summary["xgb"]), flush=True)

        print("=== LightGBM prop retrain (ensemble base learner #2) ===", flush=True)
        summary["lgb"] = train_props_lightgbm(seasons=seasons, force=True)
        print("LGB_RESULT=" + json.dumps(summary["lgb"]), flush=True)

        print("=== Multi-model stacker retrain (PRED-10) ===", flush=True)
        from src.prediction.prop_stacker import train_stacker_all
        stack = train_stacker_all(seasons=seasons, force=True)
        summary["stacker"] = {k: str(v) for k, v in (stack or {}).items()}
        print("STACKER_DONE", flush=True)

        out = os.path.join(PROJECT_DIR, "data", "output", "retrain_summary.json")
        os.makedirs(os.path.dirname(out), exist_ok=True)
        with open(out, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2)
        print(f"RETRAIN_COMPLETE -> {out}", flush=True)
        return 0
    except Exception as exc:  # noqa: BLE001
        print("RETRAIN_FAILED: " + repr(exc), flush=True)
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
