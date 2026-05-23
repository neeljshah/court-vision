"""
retrain_game_models.py — Retrain all 5 game-level LightGBM models (v2).

Walk-forward splits:
  Train   : 2022-23 + first 70% of 2023-24
  Val     : last 30% of 2023-24
  Holdout : full 2024-25  ← what counts

Usage:
  conda run -n basketball_ai python scripts/retrain_game_models.py
  conda run -n basketball_ai python scripts/retrain_game_models.py --force
"""
import os
import sys
import json
import argparse

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)


def main():
    ap = argparse.ArgumentParser(description="Retrain game-level models v2")
    ap.add_argument("--force", action="store_true",
                    help="Retrain even if models already exist")
    ap.add_argument("--seasons", nargs="+",
                    default=["2022-23", "2023-24", "2024-25"],
                    help="Seasons to include (default: 3-season set)")
    args = ap.parse_args()

    # Verify lightgbm available
    try:
        import lightgbm as lgb
        print(f"[ok] lightgbm {lgb.__version__}")
    except ImportError:
        print("[ERROR] lightgbm not installed.")
        print("  Install: conda run -n basketball_ai pip install lightgbm")
        sys.exit(1)

    from src.prediction.game_models import train

    print(f"\n{'='*60}")
    print(" NBA Game Models v2 — LightGBM + L10 Features + Walk-Forward")
    print(f"{'='*60}\n")

    results = train(seasons=args.seasons, force=args.force)

    if not results:
        print("\n[info] No training performed (models exist or insufficient data).")
        print("       Use --force to retrain.")
        return

    print(f"\n{'='*60}")
    print(" RESULTS SUMMARY")
    print(f"{'='*60}")

    # Before/after comparison
    baseline = {
        "game_total": {"mae": 14.08, "r2": 0.173},
        "spread":     {"mae": 11.23, "r2": 0.239},
        "blowout":    {"acc": 0.6201, "brier": 0.2395},
        "first_half": {"mae": 6.66, "r2": 0.182},
        "pace":       {"mae": 0.02, "r2": 1.0, "note": "LEAKAGE"},
    }

    print(f"\n{'Model':<14} {'Metric':<8} {'Before':>10} {'Val':>10} {'Holdout':>10}")
    print("-" * 58)

    for model, res in results.items():
        if model == "version":
            continue
        base = baseline.get(model, {})
        if model == "blowout":
            b_acc  = base.get("acc",  "?")
            b_bri  = base.get("brier", "?")
            v_acc  = res.get("acc",   "?")
            v_bri  = res.get("brier", "?")
            h_acc  = res.get("holdout_acc",   "N/A")
            h_bri  = res.get("holdout_brier", "N/A")
            print(f"{'blowout':<14} {'acc':<8} {str(b_acc):>10} {str(v_acc):>10} {str(h_acc):>10}")
            print(f"{'':14} {'brier':<8} {str(b_bri):>10} {str(v_bri):>10} {str(h_bri):>10}")
        elif model == "pace":
            b_r2   = base.get("r2",  "?")
            b_note = base.get("note", "")
            v_r2   = res.get("r2",  "?")
            h_r2   = res.get("holdout_r2", "N/A")
            v_mae  = res.get("mae",  "?")
            h_mae  = res.get("holdout_mae", "N/A")
            print(f"{'pace':<14} {'MAE':<8} {str(b_note):>10} {str(v_mae):>10} {str(h_mae):>10}")
            print(f"{'':14} {'R²':<8} {str(b_r2):>10} {str(v_r2):>10} {str(h_r2):>10}")
        else:
            b_mae = base.get("mae", "?")
            b_r2  = base.get("r2",  "?")
            v_mae = res.get("mae", "?")
            v_r2  = res.get("r2",  "?")
            h_mae = res.get("holdout_mae", "N/A")
            h_r2  = res.get("holdout_r2",  "N/A")
            print(f"{model:<14} {'MAE':<8} {str(b_mae):>10} {str(v_mae):>10} {str(h_mae):>10}")
            print(f"{'':14} {'R²':<8} {str(b_r2):>10} {str(v_r2):>10} {str(h_r2):>10}")

    print(f"\nTargets: total≤10.5 | spread≤9.5 | first_half≤5.5 | blowout_acc≥0.66")
    print(f"Metrics saved -> data/models/game_models_metrics.json")
    print(f"Version: {results.get('version', 'v2_l10_features')}")


if __name__ == "__main__":
    main()
