"""r12_predict_game_cli.py - drop-in CLI for R12 game predictions.

Usage:
    python -m src.prediction.r12_predict_game_cli --game-id <id> [--snap-q N]
    python -m src.prediction.r12_predict_game_cli --tail N           [--snap-q N]

Loads season_games + linescores, augments with R12 features + interactions,
runs predict_all_pregame_markets (and predict_all_inplay_markets when --snap-q),
prints tabular per-market predictions for each requested game.

For binary markets, prints P(yes) and a breakeven decimal-odds column (1/p).
"""
from __future__ import annotations
import argparse
import importlib.util
import os
import sys

import numpy as np
import pandas as pd

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_DIR)

from src.prediction.r12_canonical_predictor import (  # noqa: E402
    build_r12_features, predict_all_pregame_markets, predict_all_inplay_markets,
    list_available_bundles,
)


# Stat metadata for nice output
MARKET_META = {
    "total_pts_box":  {"label": "Total points",     "kind": "reg"},
    "score_diff":     {"label": "Spread (h-a)",     "kind": "reg"},
    "home_score":     {"label": "Home points",      "kind": "reg"},
    "away_score":     {"label": "Away points",      "kind": "reg"},
    "over_230":       {"label": "P(total > 230)",   "kind": "bin"},
    "home_cover_AH3": {"label": "P(home -3 cover)", "kind": "bin"},
}

SNAP_FEATURES = ["cum_home_score", "cum_away_score", "cum_score_diff",
                 "cum_total", "score_margin_abs", "q_remaining", "cum_pace_proxy"]


def _load_data_with_linescores():
    """Import via the B10 probe script (consistent with B30/B32 callers)."""
    scripts_dir = os.path.join(PROJECT_DIR, "scripts")
    b10_path = os.path.join(scripts_dir, "probe_R12_batch10_inplay_winprob.py")
    spec = importlib.util.spec_from_file_location("probe_R12_batch10_inplay_winprob", b10_path)
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    return mod.load_data_with_linescores(), mod.add_snapshot_features


def _add_interactions(merged):
    scripts_dir = os.path.join(PROJECT_DIR, "scripts")
    b9_path = os.path.join(scripts_dir, "probe_R12_batch9_rest_travel_halflife2.py")
    spec = importlib.util.spec_from_file_location("probe_R12_batch9_rest_travel_halflife2", b9_path)
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    return mod.add_interactions(merged)


def _format_row(target, pred):
    meta = MARKET_META[target]
    label = meta["label"]
    if meta["kind"] == "reg":
        return f"  {label:<22} {pred:>8.2f}"
    p = float(np.clip(pred, 1e-6, 1 - 1e-6))
    odds = 1.0 / p
    return f"  {label:<22} P={p:>6.3f}  breakeven {odds:>6.2f}"


def predict_for_dataframe(df_subset, snap_q=None):
    """Run all-markets prediction on df_subset (already augmented with R12 features
    + interactions). If snap_q given, df_subset must already have snapshot features
    for that snap_q.

    Returns list of dicts: one per row, with all market predictions.
    """
    pregame = predict_all_pregame_markets(df_subset)
    rows = []
    for i in range(len(df_subset)):
        row = {"index": i,
               "game_id": df_subset.iloc[i].get("game_id"),
               "home_team": df_subset.iloc[i].get("home_team"),
               "away_team": df_subset.iloc[i].get("away_team"),
               "game_date": df_subset.iloc[i].get("game_date")}
        for market, preds in pregame.items():
            row[market] = float(preds[i])
        rows.append(row)
    if snap_q is not None:
        inplay = predict_all_inplay_markets(df_subset, snap_q)
        for i in range(len(df_subset)):
            for market, preds in inplay.items():
                rows[i][market] = float(preds[i])
    return rows


def main(argv=None):
    parser = argparse.ArgumentParser()
    grp = parser.add_mutually_exclusive_group(required=True)
    grp.add_argument("--game-id", help="Predict a specific game by game_id")
    grp.add_argument("--tail", type=int, help="Predict the last N games in the dataset")
    parser.add_argument("--snap-q", type=int, choices=[1, 2, 3], default=None,
                        help="If set, also produce in-play predictions at end of quarter N")
    args = parser.parse_args(argv)

    print("r12_predict_game_cli")
    print("=" * 70)
    avail = list_available_bundles()
    missing = [t for t, ok in avail.items() if not ok]
    if missing:
        print(f"WARNING: missing canonical bundles: {missing}")
        print("Run scripts/probe_R12_batch24_serialize_models.py + "
              "scripts/probe_R12_batch26_serialize_ensembles.py first.")
        return 2

    merged, add_snapshot_features = _load_data_with_linescores()
    merged = build_r12_features(merged)
    merged = _add_interactions(merged)

    if args.game_id:
        df_sub = merged[merged["game_id"].astype(str) == str(args.game_id)].reset_index(drop=True)
        if len(df_sub) == 0:
            print(f"ERROR: game_id {args.game_id!r} not found in dataset")
            return 1
        scope_label = f"game_id={args.game_id}"
    else:
        df_sub = merged.iloc[-args.tail:].reset_index(drop=True)
        scope_label = f"last {args.tail} games"

    if args.snap_q is not None:
        df_sub = add_snapshot_features(df_sub, args.snap_q)
        df_sub[SNAP_FEATURES] = df_sub[SNAP_FEATURES].fillna(0.0)

    print(f"Dataset: {len(merged)} games loaded; predicting {scope_label}")
    if args.snap_q:
        print(f"In-play snapshot: end of Q{args.snap_q}")
    print("")

    rows = predict_for_dataframe(df_sub, args.snap_q)
    for row in rows:
        gid = row["game_id"]; date = row["game_date"]
        ht = row["home_team"]; at = row["away_team"]
        print(f"--- {gid} | {date} | {at} @ {ht} ---")
        for market in MARKET_META:
            print(_format_row(market, row[market]))
        if args.snap_q:
            wp_key = f"home_wins_endQ{args.snap_q}"
            if wp_key in row:
                p = float(np.clip(row[wp_key], 1e-6, 1 - 1e-6))
                print(f"  {'P(home wins) endQ' + str(args.snap_q):<22} "
                      f"P={p:>6.3f}  breakeven {1.0/p:>6.2f}")
            if args.snap_q == 2 and "remaining_total_endQ2" in row:
                rt = row["remaining_total_endQ2"]
                print(f"  {'Remaining total Q2':<22} {rt:>8.2f}")
        print("")

    print(f"Done. Predicted {len(rows)} game(s) across {len(MARKET_META)} pregame markets"
          + (f" + {args.snap_q + 1 if args.snap_q == 2 else 1} in-play market(s)"
             if args.snap_q else "."))
    return 0


if __name__ == "__main__":
    sys.exit(main())
