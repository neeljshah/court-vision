"""betting_backtest_smart_line.py — backtest vs a smarter line proxy.

The cycle-30 harness used line = L5 average. Sportsbooks set lines using
MORE than the player's recent form — they incorporate opponent defense,
home/away, rest, lineup. This script uses an opponent-adjusted line:

    line = L5_stat * opp_def_factor_for_this_stat * home_adjustment

Where:
  opp_def_factor — comes from the same _OpponentDefense lookup the model
                   uses internally (per-opp per-stat allowed-rate vs league).
                   Values > 1 mean opp gives up MORE of that stat than avg.
  home_adjustment — small home/away boost: 1.02 for home games, 0.98 away.

This is still a synthetic proxy — real books incorporate much more — but it
narrows the gap and gives a more honest "vs serious-but-naive line" backtest.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import warnings

warnings.filterwarnings("ignore")

import numpy as np

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from src.prediction.prop_pergame import (  # noqa: E402
    STATS, build_pergame_dataset, feature_columns,
)
from scripts.betting_backtest import _batch_predict, backtest_stat  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--thresholds", nargs="+", type=float,
                    default=[0.0, 0.25, 0.5, 0.75, 1.0, 1.5, 2.0])
    ap.add_argument("--holdout-frac", type=float, default=0.2)
    args = ap.parse_args()

    rows, fc = build_pergame_dataset(min_prior=0)
    rows.sort(key=lambda r: r["date"])
    n = len(rows)
    ho_start = int(n * (1.0 - args.holdout_frac))
    ho_rows = rows[ho_start:]
    print(f"holdout size: {len(ho_rows)} games", flush=True)

    X_ho = np.array([[r[c] for c in fc] for r in ho_rows], dtype=float)
    model_dir = os.path.join(PROJECT_DIR, "data", "models")

    print("\n== SMART LINE BACKTEST: line = L5 * opp_def_factor * home_adj ==")
    print("== This narrows the gap to real sportsbook lines (still synthetic). ==")
    summary = {}
    for stat in STATS:
        preds = _batch_predict(stat, X_ho, model_dir)
        if preds is None:
            continue
        actuals = np.array([r[f"target_{stat}"] for r in ho_rows], dtype=float)
        l5 = np.array([r.get(f"l5_{stat}", actuals.mean()) for r in ho_rows], dtype=float)
        opp_def = np.array([r.get(f"opp_def_{stat}", 1.0) for r in ho_rows], dtype=float)
        is_home = np.array([r.get("is_home", 0.5) for r in ho_rows], dtype=float)
        home_adj = np.where(is_home > 0.5, 1.02, 0.98)
        lines = l5 * opp_def * home_adj
        res = backtest_stat(stat, preds, actuals, lines, args.thresholds)
        summary[stat] = res

        print(f"\n  --- {stat.upper()} (pred {preds.mean():.2f}, smart_line {lines.mean():.2f}, actual {actuals.mean():.2f}) ---")
        print(f"    thresh | n_bets | bet%  | hit_rate | EV/unit | ROI%")
        for r in res["by_threshold"]:
            beat = " ***" if (r["hit_rate"] or 0) >= 0.524 and r["n_bets"] > 100 else ""
            hr = f"{r['hit_rate']:.4f}" if r["hit_rate"] is not None else "  n/a"
            print(f"    {r['edge_threshold']:+5.2f}  | {r['n_bets']:6d} | {r['bet_pct']:4.1f} | {hr}  | {r['ev_per_unit']:+.4f} | {r['roi_pct']:+5.2f}{beat}")

    out_path = os.path.join(model_dir, "betting_backtest_smart_line.json")
    with open(out_path, "w") as f:
        json.dump(summary, f, indent=2)
    print(f"\n[done] wrote {out_path}")


if __name__ == "__main__":
    main()
