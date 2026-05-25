"""probe_multitask_mlp_live.py -- tier3-9 (loop 5).

Empirical comparison of the multitask_mlp_live artifact against:
  1. cycle-48 production predict_pergame (per-stat dispatch)
  2. cycle-23 multitask MLP baseline (zero-live-input pathway of this model)
  3. cycle 9d3 minute_trajectory replacement (where relevant -- minutes only)

For each historical game in the cycle-91a per-quarter parquet we:
  - Reconstruct the endQ3 snapshot for each player
  - Build the 15-dim live vector (current_pts / current_pf / margin / ...)
  - Run the two-input model with both populated and zero live vectors
  - Compute MAE per stat against the actual full-game total

Read-only -- no model writes. Pass --max-games for a quick check.

Usage:
    python scripts/probe_multitask_mlp_live.py
    python scripts/probe_multitask_mlp_live.py --max-games 50
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from collections import defaultdict
from typing import Dict, List, Optional, Tuple

import numpy as np

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)
SCRIPTS_DIR = os.path.join(PROJECT_DIR, "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

from src.prediction.multitask_mlp_live import (  # noqa: E402
    LIVE_DIM,
    LIVE_FEATURE_NAMES,
    MultitaskMLPLive,
    STATS,
    build_live_vector,
)
from src.prediction.live_factors import foul_trouble_factor  # noqa: E402
from src.prediction.prop_pergame import (  # noqa: E402
    build_pergame_dataset,
    feature_columns,
    predict_pergame,
)

_QPARQUET = os.path.join(PROJECT_DIR, "data", "player_quarter_stats.parquet")


def _safe_float(v) -> float:
    if v is None:
        return 0.0
    try:
        f = float(v)
        return 0.0 if f != f else f
    except (TypeError, ValueError):
        return 0.0


def build_endq3_snapshot(player_quarters) -> Optional[Dict[str, float]]:
    """Aggregate Q1+Q2+Q3 rows into a snapshot dict matching LIVE_FEATURE_NAMES.

    player_quarters is a list of per-quarter dicts for ONE player in one game.
    Returns None when the player has no Q1-Q3 data (didn't play any of the
    first three quarters -- no live snapshot is meaningful).
    """
    cur_pts = cur_reb = cur_ast = cur_fg3m = 0.0
    cur_stl = cur_blk = cur_tov = cur_min = cur_pf = 0.0
    has_any_q = False
    for r in player_quarters:
        try:
            p = int(r["period"])
        except (KeyError, TypeError, ValueError):
            continue
        if p < 1 or p > 3:
            continue
        has_any_q = True
        cur_pts += _safe_float(r.get("pts"))
        cur_reb += _safe_float(r.get("reb"))
        cur_ast += _safe_float(r.get("ast"))
        cur_fg3m += _safe_float(r.get("fg3m"))
        cur_stl += _safe_float(r.get("stl"))
        cur_blk += _safe_float(r.get("blk"))
        cur_tov += _safe_float(r.get("tov"))
        cur_min += _safe_float(r.get("min"))
        cur_pf += _safe_float(r.get("pf"))
    if not has_any_q:
        return None
    return {
        "period": 4,
        "clock_min_remaining": 12.0,
        "period_share_played": 0.75,  # endQ3 = 3 of 4 quarters played
        "current_pts": cur_pts,
        "current_reb": cur_reb,
        "current_ast": cur_ast,
        "current_fg3m": cur_fg3m,
        "current_stl": cur_stl,
        "current_blk": cur_blk,
        "current_tov": cur_tov,
        "current_min": cur_min,
        "current_pf": cur_pf,
        "score_margin": 0.0,
        "foul_factor": foul_trouble_factor(cur_pf, 4),
        "blow_factor": 1.0,
    }


def build_actual_totals(player_quarters) -> Dict[str, float]:
    """Sum Q1-Q4 + OT for each stat."""
    out = {s: 0.0 for s in STATS}
    for r in player_quarters:
        for s in STATS:
            out[s] += _safe_float(r.get(s))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-games", type=int, default=None)
    args = ap.parse_args()

    t0 = time.time()
    model = MultitaskMLPLive.load()
    if model is None:
        print("  ERROR: multitask_mlp_live artifact not found at data/models/")
        print("         Run scripts/train_multitask_mlp_live.py first.")
        return 2
    print(f"  loaded multitask_mlp_live: pregame_dim={model.pregame_dim} "
          f"live_dim={model.live_dim}  heads={len(model.stats)}")

    # We use the per-game dataset for pre-game feature row construction --
    # need (player_id, game_date) -> feature_row lookup. build_pergame_dataset
    # returns the same shape used during training.
    print("  loading per-game dataset for pregame feature rows...")
    rows, feature_cols = build_pergame_dataset(min_prior=0)
    by_key: Dict[Tuple[int, str], Dict[str, float]] = {}
    for r in rows:
        try:
            pid = int(r.get("player_id") or 0)
        except (TypeError, ValueError):
            continue
        date_iso = str(r.get("date") or "")[:10]
        if pid and date_iso:
            by_key[(pid, date_iso)] = r
    print(f"  pregame lookup built: {len(by_key)} (player, date) rows")

    print("  loading per-quarter parquet...")
    import pandas as pd
    if not os.path.exists(_QPARQUET):
        print(f"  ERROR: {_QPARQUET} missing")
        return 2
    qdf = pd.read_parquet(_QPARQUET)

    # game_id -> game_date lookup via season_games_*.json (same trick used
    # by build_player_quarter_stats in prop_pergame).
    import json as _json
    gid_to_date: Dict[str, str] = {}
    nba_dir = os.path.join(PROJECT_DIR, "data", "nba")
    for fn in sorted(os.listdir(nba_dir)) if os.path.exists(nba_dir) else []:
        if not fn.startswith("season_games_") or not fn.endswith(".json"):
            continue
        try:
            payload = _json.load(open(os.path.join(nba_dir, fn), encoding="utf-8"))
        except Exception:
            continue
        for g in (payload.get("rows", payload) if isinstance(payload, dict) else payload) or []:
            gid = g.get("game_id") or g.get("GAME_ID")
            gd = g.get("game_date") or g.get("GAME_DATE")
            if gid and gd:
                gid_to_date[str(gid).zfill(10)] = str(gd)[:10]

    games_in_order = sorted(qdf["game_id"].unique().tolist())
    if args.max_games:
        games_in_order = games_in_order[:args.max_games]
    print(f"  probing {len(games_in_order)} games")

    # Accumulators -- per-stat lists of (actual, pred) for each predictor.
    bucket = lambda: defaultdict(list)  # noqa: E731
    abs_err: Dict[str, Dict[str, list]] = {
        "live_on":  bucket(),
        "live_off": bucket(),
        "prod":     bucket(),
    }
    counts = 0

    for gid in games_in_order:
        gdate = gid_to_date.get(str(gid).zfill(10))
        if not gdate:
            continue
        gdf = qdf[qdf["game_id"] == gid]
        if gdf.empty:
            continue
        for pid in gdf["player_id"].unique():
            try:
                pid_i = int(pid)
            except (TypeError, ValueError):
                continue
            pdf = gdf[gdf["player_id"] == pid].to_dict(orient="records")
            snap = build_endq3_snapshot(pdf)
            if snap is None:
                continue
            actual = build_actual_totals(pdf)

            pre_row = by_key.get((pid_i, gdate))
            if pre_row is None:
                continue
            pregame_vec = np.array([float(pre_row.get(c, 0.0) or 0.0)
                                    for c in feature_cols], dtype=np.float32)

            # Live ON
            live_vec = build_live_vector(snap)
            pred_on = model.predict(pregame_vec.reshape(1, -1),
                                     live_vec.reshape(1, -1))[0]
            # Live OFF (zero vector = back-compat)
            pred_off = model.predict(pregame_vec.reshape(1, -1), None)[0]
            # Production predict_pergame per-stat
            prod_pred: Dict[str, float] = {}
            for s in STATS:
                try:
                    v = predict_pergame(s, pre_row)
                except Exception:
                    v = None
                prod_pred[s] = float(v) if v is not None else float("nan")

            for j, s in enumerate(STATS):
                a = float(actual[s])
                abs_err["live_on"][s].append(abs(float(pred_on[j]) - a))
                abs_err["live_off"][s].append(abs(float(pred_off[j]) - a))
                v = prod_pred[s]
                if v == v:  # not NaN
                    abs_err["prod"][s].append(abs(v - a))
            counts += 1

    print(f"  collected {counts} (game, player) endQ3 snapshots")
    print()
    print("  == per-stat MAE comparison ==")
    print(f"    {'stat':5s}  {'live_on':>9s}  {'live_off':>9s}  {'prod':>9s}  "
          f"{'delta_vs_prod':>14s}  {'live_lift':>10s}")
    n_wins_vs_prod = 0
    for s in STATS:
        on = np.mean(abs_err["live_on"][s]) if abs_err["live_on"][s] else float("nan")
        off = np.mean(abs_err["live_off"][s]) if abs_err["live_off"][s] else float("nan")
        # prod accumulator may be empty for some stats if predict_pergame
        # returned None for every row (e.g. stale n_features_in_); guard.
        prod = (np.mean(abs_err["prod"][s])
                if abs_err["prod"][s] else float("nan"))
        d_vs_prod = on - prod if prod == prod else float("nan")
        live_lift = off - on  # positive = live vector helped
        if d_vs_prod == d_vs_prod and d_vs_prod <= -0.02:
            n_wins_vs_prod += 1
        print(f"    {s.upper():5s}  {on:>9.4f}  {off:>9.4f}  {prod:>9.4f}  "
              f"{d_vs_prod:>+14.4f}  {live_lift:>+10.4f}")
    print()
    print(f"  stats with live_on improvement >= 0.02 vs prod: {n_wins_vs_prod}/7")
    print(f"  ship gate (>=3/7): {'PASS' if n_wins_vs_prod >= 3 else 'FAIL'}")
    print(f"  elapsed: {time.time() - t0:.1f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
