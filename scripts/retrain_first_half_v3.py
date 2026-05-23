"""
retrain_first_half_v3.py — Entrypoint for training FirstHalfPredictorV3.

Usage:
    python scripts/retrain_first_half_v3.py [--seasons 2022-23 2023-24 2024-25]

Fetches Q1+Q2 period scores from linescores_all.json cache (pre-built by
scripts/_fetch_linescores.py).  Falls back to 0.47×game_total proxy for
any missing games.
"""
import argparse, json, os, sys, time

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)


def main() -> None:
    parser = argparse.ArgumentParser(description="Train FirstHalfPredictorV3")
    parser.add_argument(
        "--seasons", nargs="+",
        default=["2022-23", "2023-24", "2024-25"],
        help="Seasons to include (space-separated, e.g. 2022-23 2023-24 2024-25)",
    )
    parser.add_argument(
        "--model-dir", default=os.path.join(PROJECT_DIR, "data", "models"),
        help="Directory to write model files",
    )
    args = parser.parse_args()

    linescore_path = os.path.join(PROJECT_DIR, "data", "nba", "linescores_all.json")
    if os.path.exists(linescore_path):
        with open(linescore_path) as f:
            ls = json.load(f)
        print(f"[retrain] Linescore cache: {len(ls)} games loaded")
    else:
        print("[retrain] WARNING: linescores_all.json not found — "
              "all labels will use 0.47×game_total proxy.\n"
              "Run scripts/_fetch_linescores.py first for real period scores.")

    from src.prediction.first_half_v3 import FirstHalfPredictorV3

    t0 = time.time()
    predictor = FirstHalfPredictorV3(model_dir=args.model_dir)
    metrics   = predictor.train(seasons=args.seasons)

    elapsed = time.time() - t0
    if metrics:
        v2_mae  = metrics.get("v2_proxy_holdout_mae", 6.96)
        v3_mae  = metrics.get("holdout_mae")
        real_pct= metrics.get("real_pct", 0)
        print(f"\n{'='*55}")
        print(f"  v2 proxy holdout MAE : {v2_mae:.2f}")
        print(f"  v3 real  holdout MAE : {v3_mae}")
        if v3_mae:
            delta = v2_mae - v3_mae
            sign  = "improvement" if delta > 0 else "regression"
            print(f"  Delta                : {delta:+.2f}  ({sign})")
        print(f"  Real period score %  : {real_pct:.1f}%")
        print(f"  Training time        : {elapsed:.1f}s")
        print(f"{'='*55}")
    else:
        print("[retrain] Training returned no metrics — check data availability.")


if __name__ == "__main__":
    main()
