"""strategy_d_threshold_sweep_seeded.py — iter-20 seed-stability sweep.

Adapted from iter-18's strategy_d_threshold_sweep.py to accept --model-dir,
so we can re-run the threshold sweep against alternative-seed OOS artifacts
and check whether iter-18's |edge|=0.35 PnL optimum is seed-robust.

Slim version: pooled (BLK+FG3M+STL) sweep + per-stat sweep, no report write,
no forward-test. Output goes to data/cache/iter20_threshold_sweep_seed<N>.json.

Usage:
    python scripts/strategy_d_threshold_sweep_seeded.py \
        --model-dir data/models/oos_pre_playoffs_seed7 \
        --tag seed7
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from collections import defaultdict
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import numpy as np

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)
os.environ.setdefault("NBA_INJURY_WIRE_DISABLE", "1")

from scripts.backtest_closing_lines_2024_playoffs import (  # noqa: E402
    _build_asof_row,
    _resolve_player_id,
    _season_for_date,
    _classify_result,
    _odds_to_decimal_profit,
)
from src.prediction.prop_pergame import feature_columns  # noqa: E402
from src.prediction.prop_quantiles import _inverse  # noqa: E402


CSV_PATH = os.path.join(PROJECT_DIR, "data", "external", "historical_lines",
                        "playoffs_2024_canonical.csv")
GAMELOG_DIR = os.path.join(PROJECT_DIR, "data", "nba")

STATS = ("blk", "fg3m", "stl")
BET_SIZE = 100.0
PROFIT_RATIO_AT_M110 = _odds_to_decimal_profit(-110)

THRESHOLDS = [round(0.20 + 0.05 * i, 2) for i in range(27)]
CURRENT_THRESHOLD = 0.50
ITER18_OPT_THRESHOLD = 0.35


def _load_qstat_xgb(stat: str, oos_dir: str):
    import xgboost as xgb
    path = os.path.join(oos_dir, f"quantile_pergame_{stat}_q50.json")
    if not os.path.exists(path):
        return None
    m = xgb.XGBRegressor()
    m.load_model(path)
    return m


def _predict_qstat(stat: str, model, feat_row: Dict[str, float]) -> float:
    cols = feature_columns()
    X = np.array([[float(feat_row.get(c, 0.0) or 0.0) for c in cols]], dtype=float)
    pred_t = float(model.predict(X)[0])
    pred = float(_inverse(stat, np.array([pred_t]))[0])
    return max(0.0, pred)


def _max_drawdown_chrono(records: List[Tuple[str, float]]) -> float:
    if not records:
        return 0.0
    records = sorted(records, key=lambda x: x[0])
    cum = 0.0
    peak = 0.0
    dd = 0.0
    for _d, pnl in records:
        cum += pnl
        if cum > peak:
            peak = cum
        dd = min(dd, cum - peak)
    return float(-dd)


def _build_predictions(oos_dir: str) -> List[dict]:
    models: Dict[str, object] = {}
    for s in STATS:
        m = _load_qstat_xgb(s, oos_dir)
        if m is None:
            print(f"  FATAL: missing OOS artifact for {s} in {oos_dir}")
            sys.exit(1)
        models[s] = m
    print(f"  loaded models from {oos_dir}: {list(models.keys())}")

    rows: List[dict] = []
    with open(CSV_PATH, encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if r.get("stat", "").lower() in STATS:
                rows.append(r)
    print(f"  CSV rows for BLK/FG3M/STL: {len(rows)}")

    names = sorted({r["player"] for r in rows})
    name2pid: Dict[str, Optional[int]] = {}
    for nm in names:
        name2pid[nm] = _resolve_player_id(nm)
    n_resolved = sum(1 for v in name2pid.values() if v is not None)
    print(f"  resolved {n_resolved}/{len(names)} players")

    preds: List[dict] = []
    skips = defaultdict(int)
    row_cache: Dict[Tuple, Optional[Dict[str, float]]] = {}
    t0 = time.time()
    for i, r in enumerate(rows):
        stat = r["stat"].lower()
        try:
            line = float(r["closing_line"])
            actual = float(r["actual_value"])
            d = datetime.fromisoformat(r["date"])
        except Exception:
            skips["bad_row"] += 1
            continue
        pid = name2pid.get(r["player"])
        if pid is None:
            skips["no_pid"] += 1
            continue
        season = _season_for_date(d)
        is_home = (r["venue"] == "home")
        key = (pid, r["date"], r["venue"], r["opp"])
        if key not in row_cache:
            row_cache[key] = _build_asof_row(
                pid, r["opp"], d, season, is_home=is_home,
                rest_days=2.0, gamelog_dir=GAMELOG_DIR,
            )
        feat = row_cache[key]
        if feat is None:
            skips["no_history"] += 1
            continue
        try:
            pred = _predict_qstat(stat, models[stat], feat)
        except Exception as e:
            skips[f"err:{type(e).__name__}"] += 1
            continue

        edge = pred - line
        ae = abs(edge)
        if edge > 0:
            rec = "OVER"
        elif edge < 0:
            rec = "UNDER"
        else:
            rec = "PUSH_LINE"

        actual_result = _classify_result(actual, line)
        if rec == "PUSH_LINE":
            outcome = "skip"
        elif actual_result == "PUSH":
            outcome = "push"
        else:
            outcome = "win" if rec == actual_result else "loss"

        preds.append({
            "date": r["date"], "player": r["player"], "stat": stat,
            "line": line, "actual": actual, "pred": pred,
            "edge_signed": edge, "abs_edge": ae,
            "rec": rec, "outcome": outcome,
        })
        if (i + 1) % 500 == 0:
            print(f"   ...{i+1}/{len(rows)} ({time.time()-t0:.1f}s) preds={len(preds)}")
    print(f"  predicted {len(preds)} rows in {time.time()-t0:.1f}s. skips: {dict(skips)}")
    return preds


def _pnl(stake: float, outcome: str,
         profit_ratio: float = PROFIT_RATIO_AT_M110) -> float:
    if stake <= 0:
        return 0.0
    if outcome == "win":
        return stake * profit_ratio
    if outcome == "loss":
        return -stake
    return 0.0


def _sweep_one(preds: List[dict], threshold: float,
               stat_filter: Optional[str] = None) -> dict:
    pnl_chrono: List[Tuple[str, float]] = []
    n_bets = wins = losses = pushes = 0
    total_staked = 0.0
    total_pnl = 0.0
    for p in preds:
        if stat_filter is not None and p["stat"] != stat_filter:
            continue
        if p["outcome"] == "skip":
            continue
        if p["abs_edge"] <= threshold:
            continue
        n_bets += 1
        total_staked += BET_SIZE
        pnl = _pnl(BET_SIZE, p["outcome"])
        total_pnl += pnl
        if p["outcome"] == "win":
            wins += 1
        elif p["outcome"] == "loss":
            losses += 1
        else:
            pushes += 1
        pnl_chrono.append((p["date"], pnl))
    decisive = wins + losses
    hit = (wins / decisive) if decisive else 0.0
    roi = (total_pnl / total_staked * 100.0) if total_staked > 0 else 0.0
    dd = _max_drawdown_chrono(pnl_chrono)
    pnl_dd = (total_pnl / dd) if dd > 0 else (float("inf") if total_pnl > 0 else 0.0)
    return {
        "threshold": threshold, "n_bets": n_bets,
        "wins": wins, "losses": losses, "pushes": pushes,
        "hit_pct": round(hit * 100.0, 2), "roi_pct": round(roi, 2),
        "pnl_dollars": round(total_pnl, 2),
        "maxdd_dollars": round(dd, 2),
        "pnl_dd": (round(pnl_dd, 2) if pnl_dd != float("inf") else None),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model-dir", required=True,
                    help="Directory containing OOS XGB q50 models (relative to project root or absolute)")
    ap.add_argument("--tag", required=True, help="Tag for cache filename (e.g. seed7)")
    args = ap.parse_args()

    oos_dir = args.model_dir
    if not os.path.isabs(oos_dir):
        oos_dir = os.path.join(PROJECT_DIR, oos_dir)

    print(f"\n  iter-20 seeded threshold sweep — {args.tag}\n")
    preds = _build_predictions(oos_dir)

    sweep_pooled = [_sweep_one(preds, thr) for thr in THRESHOLDS]
    sweep_per_stat: Dict[str, List[dict]] = {}
    for s in STATS:
        sweep_per_stat[s] = [_sweep_one(preds, thr, stat_filter=s) for thr in THRESHOLDS]

    # Best PnL threshold (any n_bets)
    best_pnl_row = max(sweep_pooled, key=lambda x: x["pnl_dollars"])
    # Best PnL/DD with n_bets>=100 (robustness gate from iter-18)
    rows100 = [x for x in sweep_pooled if x["n_bets"] >= 100]
    best_pnl_dd_row = max(rows100, key=lambda x: (x["pnl_dd"] if x["pnl_dd"] is not None else 1e9)) if rows100 else None

    out = {
        "tag": args.tag, "model_dir": oos_dir,
        "sweep_pooled": sweep_pooled,
        "sweep_per_stat": sweep_per_stat,
        "best_pnl": best_pnl_row,
        "best_pnl_dd_n100": best_pnl_dd_row,
        "n_preds": len(preds),
        "thresholds": THRESHOLDS,
    }
    cache_path = os.path.join(PROJECT_DIR, "data", "cache",
                              f"iter20_threshold_sweep_{args.tag}.json")
    os.makedirs(os.path.dirname(cache_path), exist_ok=True)
    with open(cache_path, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=2, default=str)
    print(f"\n  cache -> {cache_path}")

    # Console summary
    print(f"\n  ===== {args.tag.upper()} SUMMARY =====")
    print(f"  Best PnL:    thr={best_pnl_row['threshold']:.2f}  "
          f"n={best_pnl_row['n_bets']}  hit={best_pnl_row['hit_pct']:.2f}%  "
          f"PnL=${best_pnl_row['pnl_dollars']:+,.0f}")
    if best_pnl_dd_row:
        print(f"  Best PnL/DD (n>=100):  thr={best_pnl_dd_row['threshold']:.2f}  "
              f"n={best_pnl_dd_row['n_bets']}  PnL=${best_pnl_dd_row['pnl_dollars']:+,.0f}  "
              f"PnL/DD={best_pnl_dd_row['pnl_dd']}")
    for thr in (0.35, 0.50):
        r = next((x for x in sweep_pooled if abs(x["threshold"] - thr) < 1e-6), None)
        if r:
            print(f"  @ {thr:.2f}:  n={r['n_bets']}  hit={r['hit_pct']:.2f}%  "
                  f"ROI={r['roi_pct']:+.2f}%  PnL=${r['pnl_dollars']:+,.0f}")


if __name__ == "__main__":
    main()
