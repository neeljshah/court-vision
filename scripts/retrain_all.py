"""
retrain_all.py -- Phase B5: Full model retrain with complete feature set.

Retrains all models in dependency order:
  1. Props (7 models) -- now includes matchup_fg, defender_zone, shot_dashboard, tracking
  2. Matchup model   -- synergy + hustle + on-off already wired
  3. Game models     -- team features updated
  4. Win probability -- updated game features

Run after Phase A data collection is complete.

Usage:
    conda activate basketball_ai
    python scripts/retrain_all.py               # all models
    python scripts/retrain_all.py --model props  # single model
    python scripts/retrain_all.py --check        # show current model metrics
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

_MODEL_DIR = os.path.join(PROJECT_DIR, "data", "models")
_VAULT_DIR = os.path.join(PROJECT_DIR, "vault", "Improvements")


def _log_to_vault(entry: str) -> None:
    """Append retrain entry to Tracker Improvements Log."""
    log_path = os.path.join(_VAULT_DIR, "Tracker Improvements Log.md")
    if not os.path.exists(log_path):
        return
    timestamp = time.strftime("%Y-%m-%d %H:%M")
    try:
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"\n### {timestamp} -- Model Retrain\n{entry}\n")
    except Exception as e:
        print(f"  [WARN] Could not write to vault: {e}")


def check_model_metrics() -> None:
    """Print current model metadata/metrics."""
    print("\n=== Current Model Metrics ===\n")

    # Props
    print("Props models:")
    for stat in ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov"):
        p = os.path.join(_MODEL_DIR, f"props_{stat}.json")
        if os.path.exists(p):
            try:
                meta = json.load(open(os.path.join(_MODEL_DIR, f"props_{stat}_meta.json")))
                print(f"  {stat}: MAE={meta.get('mae', '?'):.3f}  R2={meta.get('r2', '?'):.3f}")
            except Exception:
                print(f"  {stat}: [OK] (no metadata)")
        else:
            print(f"  {stat}: [MISSING]")

    # Matchup
    m_path = os.path.join(_MODEL_DIR, "matchup_model.json")
    if os.path.exists(m_path):
        try:
            meta = json.load(open(os.path.join(_MODEL_DIR, "matchup_model_meta.json")))
            print(f"\nMatchup: R2={meta.get('r2', '?'):.3f}  MAE={meta.get('mae', '?'):.3f}")
        except Exception:
            print("\nMatchup: [OK] (no metadata)")
    else:
        print("\nMatchup: [MISSING]")

    # Win prob
    wp_path = os.path.join(_MODEL_DIR, "win_probability.pkl")
    if os.path.exists(wp_path):
        mtime = time.strftime("%Y-%m-%d", time.localtime(os.path.getmtime(wp_path)))
        print(f"\nWin prob: [OK] (last trained {mtime})")
    else:
        print("\nWin prob: [MISSING]")
    print()


def retrain_props() -> dict:
    """Retrain all 7 prop models with current full feature set."""
    print("\n=== Props Retrain (7 models) ===")
    from src.prediction.player_props import train_props

    start = time.time()
    results = train_props(force=True)
    elapsed = time.time() - start

    if not results:
        print("  [WARN] No results returned from train_props()")
        return {}

    print(f"\n  Done in {elapsed:.1f}s")
    for stat, metrics in results.items():
        mae = metrics.get("mae", 0)
        r2  = metrics.get("r2", 0)
        n   = metrics.get("n_test", 0)
        print(f"  {stat}: MAE={mae:.3f}  R2={r2:.3f}  n={n}")

    _log_to_vault(
        f"Props retrained: {len(results)} models\n"
        + "\n".join(f"  - {s}: MAE={m.get('mae',0):.3f}  R2={m.get('r2',0):.3f}"
                   for s, m in results.items())
    )
    return results


def retrain_matchup() -> dict:
    """Retrain matchup model with synergy + hustle features."""
    print("\n=== Matchup Model Retrain ===")
    from src.prediction.matchup_model import train_matchup_model

    start = time.time()
    try:
        result = train_matchup_model(force=True)
        elapsed = time.time() - start
        r2  = result.get("r2_test",  result.get("r2",  "?"))
        mae = result.get("mae_test", result.get("mae", "?"))
        n   = result.get("n_test",   "?")
        print(f"  Done in {elapsed:.1f}s  |  R2={r2}  MAE={mae}  n={n}")
        _log_to_vault(f"Matchup model retrained: R2={r2}  MAE={mae}")
        return result
    except Exception as e:
        print(f"  [ERR] {e}")
        return {}


def retrain_win_prob() -> dict:
    """Retrain win probability model."""
    print("\n=== Win Probability Retrain ===")
    from src.prediction.win_probability import train as wp_train

    start = time.time()
    try:
        # Train on 3 completed seasons only -- do NOT include 2025-26 because
        # game outcomes are the labels and we're predicting live 2025-26 games.
        model = wp_train(seasons=["2022-23", "2023-24", "2024-25"])
        elapsed = time.time() - start
        acc = getattr(model, "_last_accuracy", None)
        print(f"  Done in {elapsed:.1f}s"
              + (f"  |  accuracy={acc:.1%}" if acc else ""))
        _log_to_vault(f"Win probability retrained"
                      + (f": accuracy={acc:.1%}" if acc else ""))
        return {"trained": True, "accuracy": acc}
    except Exception as e:
        print(f"  [ERR] {e}")
        return {}


def retrain_game_models() -> dict:
    """Retrain game spread/total/blowout models."""
    print("\n=== Game Models Retrain ===")
    from src.prediction.game_models import train as gm_train

    start = time.time()
    try:
        results = gm_train(force=True)
        elapsed = time.time() - start
        print(f"  Done in {elapsed:.1f}s")
        for name, metrics in (results or {}).items():
            print(f"  {name}: MAE={metrics.get('mae_test', metrics.get('mae', '?'))}")
        return results or {}
    except Exception as e:
        print(f"  [ERR] {e}")
        return {}


def main() -> None:
    parser = argparse.ArgumentParser(description="Phase B5 -- Full model retrain")
    parser.add_argument(
        "--model",
        choices=["props", "matchup", "winprob", "game"],
        help="Retrain only a specific model (default: all)",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Show current model metrics without retraining",
    )
    args = parser.parse_args()

    if args.check:
        check_model_metrics()
        return

    print("=" * 60)
    print("Phase B5 -- Full Model Retrain")
    print("=" * 60)

    start = time.time()
    all_results = {}

    if args.model == "props" or args.model is None:
        all_results["props"] = retrain_props()

    if args.model == "matchup" or args.model is None:
        all_results["matchup"] = retrain_matchup()

    if args.model == "game" or args.model is None:
        all_results["game"] = retrain_game_models()

    if args.model == "winprob" or args.model is None:
        all_results["winprob"] = retrain_win_prob()

    elapsed = time.time() - start
    print(f"\n[OK] Retrain complete in {elapsed/60:.1f} min")
    check_model_metrics()


if __name__ == "__main__":
    main()
