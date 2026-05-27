"""backtest_2025_26_rs_oos.py — OOS backtest of production models on 2025-26 RS data.

KEY QUESTION: do the production models (trained through 2024-04-21 cutoff)
generalize to the 2025-26 regular season? Or do they only work on the training era?

Uses data/external/historical_lines/regular_season_2025_26_oddsapi.csv
(1,450 rows, 11 dates, Oct 2025 - Apr 2026).

Compares to 2024-25 RS holdout results (already on disk) for cross-season validation.

Output format:
    stat | n_bets_2025_26 | roi_2025_26 | hit_2025_26
"""
from __future__ import annotations

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
    _recommend,
    _odds_to_decimal_profit,
)
from src.prediction.prop_pergame import (  # noqa: E402
    predict_pergame,
)

# ─── paths ────────────────────────────────────────────────────────────────────

RS_2025_26_CSV = os.path.join(
    PROJECT_DIR, "data", "external", "historical_lines",
    "regular_season_2025_26_oddsapi.csv"
)
RS_2024_25_CSV = os.path.join(
    PROJECT_DIR, "data", "external", "historical_lines",
    "regular_season_2024_25_oddsapi.csv"
)
GAMELOG_DIR = os.path.join(PROJECT_DIR, "data", "nba")
THRESHOLD = 0.5

STATS_TO_EVAL = ["pts", "reb", "ast", "fg3m", "stl", "blk"]


# ─── backtest engine ──────────────────────────────────────────────────────────

def run_backtest(csv_path: str, label: str, threshold: float = THRESHOLD) -> Dict:
    rows = []
    with open(csv_path, encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for r in reader:
            rows.append(r)

    print(f"\n{'='*65}")
    print(f"  BACKTEST: {label}  ({len(rows)} rows)")
    print(f"{'='*65}")

    # Resolve player ids
    unique_names = sorted({r["player"] for r in rows})
    name2pid: Dict[str, Optional[int]] = {}
    for nm in unique_names:
        name2pid[nm] = _resolve_player_id(nm)
    resolved = sum(1 for v in name2pid.values() if v is not None)
    print(f"  Player name -> id: {resolved}/{len(unique_names)} resolved")

    # Feature row cache: (pid, date, venue, opp) -> feat_row
    row_cache: Dict[Tuple, Optional[Dict]] = {}
    skip_reasons = defaultdict(int)

    per_stat = defaultdict(lambda: {
        "n_pred": 0, "n_skip": 0,
        "abs_err_actual": [], "abs_err_line": [],
        "n_bets": 0, "wins": 0, "losses": 0, "pushes": 0,
    })

    t0 = time.time()
    for idx, r in enumerate(rows):
        player = r["player"]
        opp = r["opp"]
        venue = r["venue"]
        stat = r["stat"].lower()

        if stat not in STATS_TO_EVAL:
            continue

        try:
            line = float(r["closing_line"])
            actual = float(r["actual_value"])
            over_odds = int(r.get("over_odds", -110) or -110)
            under_odds = int(r.get("under_odds", -110) or -110)
        except (TypeError, ValueError):
            per_stat[stat]["n_skip"] += 1
            skip_reasons["bad_numeric"] += 1
            continue

        try:
            d = datetime.fromisoformat(r["date"])
        except Exception:
            per_stat[stat]["n_skip"] += 1
            skip_reasons["bad_date"] += 1
            continue

        pid = name2pid.get(player)
        if pid is None:
            per_stat[stat]["n_skip"] += 1
            skip_reasons["no_pid"] += 1
            continue

        season = _season_for_date(d)
        is_home = (venue == "home")
        key = (pid, r["date"], venue, opp)

        if key not in row_cache:
            row_cache[key] = _build_asof_row(
                pid, opp, d, season,
                is_home=is_home, rest_days=2.0,
                gamelog_dir=GAMELOG_DIR,
            )

        feat_row = row_cache[key]
        if feat_row is None:
            per_stat[stat]["n_skip"] += 1
            skip_reasons["no_history"] += 1
            continue

        try:
            pred = predict_pergame(stat, feat_row)
        except Exception as e:
            per_stat[stat]["n_skip"] += 1
            skip_reasons[f"predict_err:{type(e).__name__}"] += 1
            continue

        if pred is None:
            per_stat[stat]["n_skip"] += 1
            skip_reasons["model_missing"] += 1
            continue

        pred = float(pred)
        edge = pred - line
        actual_result = _classify_result(actual, line)
        rec = _recommend(edge, threshold)

        s = per_stat[stat]
        s["n_pred"] += 1
        s["abs_err_actual"].append(abs(pred - actual))
        s["abs_err_line"].append(abs(pred - line))

        if rec != "NO_BET":
            if actual_result == "PUSH":
                s["pushes"] += 1
            else:
                s["n_bets"] += 1
                if rec == actual_result:
                    s["wins"] += 1
                else:
                    s["losses"] += 1

        if (idx + 1) % 500 == 0:
            elapsed = time.time() - t0
            print(f"  ...{idx+1}/{len(rows)} ({elapsed:.1f}s)")

    elapsed = time.time() - t0
    print(f"  Completed in {elapsed:.1f}s")
    print(f"  Skip reasons: {dict(skip_reasons)}")

    # Print per-stat table
    print(f"\n  {'stat':4s} | {'n_pred':>6s} | {'n_bets':>6s} | {'hit%':>6s} | {'ROI':>7s} | {'MAE_act':>7s}")
    print(f"  {'-'*60}")

    results = {}
    profit_per_win = _odds_to_decimal_profit(-110)

    for stat in STATS_TO_EVAL:
        s = per_stat.get(stat)
        if not s or s["n_pred"] == 0:
            results[stat] = {"n_pred": 0, "n_bets": 0, "hit_pct": 0.0, "roi_pct": 0.0, "mae_actual": 0.0}
            continue

        mae_a = sum(s["abs_err_actual"]) / len(s["abs_err_actual"])
        nb = s["n_bets"]
        w = s["wins"]
        hit = (w / nb) if nb else 0.0
        roi_units = w * profit_per_win - (nb - w) * 1.0 if nb > 0 else 0.0
        roi_pct = (roi_units / nb * 100.0) if nb else 0.0

        print(f"  {stat.upper():4s} | {s['n_pred']:6d} | {nb:6d} | {hit*100:5.1f}% | {roi_pct:6.2f}% | {mae_a:7.3f}")

        results[stat] = {
            "n_pred": s["n_pred"],
            "n_bets": nb,
            "wins": w,
            "hit_pct": hit * 100,
            "roi_pct": roi_pct,
            "mae_actual": mae_a,
        }

    # Pool totals
    total_bets = sum(results[st]["n_bets"] for st in STATS_TO_EVAL)
    total_wins = sum(results[st].get("wins", 0) for st in STATS_TO_EVAL)
    total_roi = (total_wins * profit_per_win - (total_bets - total_wins)) / total_bets * 100 if total_bets else 0.0
    print(f"\n  POOL | bets={total_bets} | wins={total_wins} | ROI={total_roi:.2f}%")

    return results


def cross_season_comparison(res_2425: Dict, res_2526: Dict) -> None:
    print(f"\n{'='*75}")
    print(f"  CROSS-SEASON COMPARISON: 2024-25 RS vs 2025-26 RS")
    print(f"  (Do production models generalize to 2025-26?)")
    print(f"{'='*75}")
    print(f"  {'stat':4s} | {'n_bets_2425':>11s} | {'roi_2425':>9s} | {'hit_2425':>9s} | {'n_bets_2526':>11s} | {'roi_2526':>9s} | {'hit_2526':>9s} | {'verdict':12s}")
    print(f"  {'-'*105}")

    for stat in STATS_TO_EVAL:
        r24 = res_2425.get(stat, {})
        r25 = res_2526.get(stat, {})
        nb24 = r24.get("n_bets", 0)
        roi24 = r24.get("roi_pct", 0.0)
        hit24 = r24.get("hit_pct", 0.0)
        nb25 = r25.get("n_bets", 0)
        roi25 = r25.get("roi_pct", 0.0)
        hit25 = r25.get("hit_pct", 0.0)

        if nb25 < 5:
            verdict = "TOO_FEW"
        elif roi25 > 0 and roi24 > 0:
            verdict = "GENERALIZES"
        elif roi25 > 0 and roi24 <= 0:
            verdict = "IMPROVES_OOS"
        elif roi25 <= 0 and roi24 > 0:
            verdict = "DEGRADES_OOS"
        else:
            verdict = "BOTH_NEG"

        print(f"  {stat.upper():4s} | {nb24:11d} | {roi24:8.2f}% | {hit24:8.1f}% | {nb25:11d} | {roi25:8.2f}% | {hit25:8.1f}% | {verdict:12s}")

    print()


if __name__ == "__main__":
    # Run 2025-26 backtest
    res_2526 = run_backtest(RS_2025_26_CSV, "2025-26 Regular Season (OOS)")

    # Run 2024-25 backtest for comparison
    res_2425 = {}
    if os.path.exists(RS_2024_25_CSV):
        res_2425 = run_backtest(RS_2024_25_CSV, "2024-25 Regular Season (baseline)")
    else:
        print(f"\n  [WARN] 2024-25 RS CSV not found at {RS_2024_25_CSV}")

    # Cross-season comparison
    cross_season_comparison(res_2425, res_2526)

    print("Done.")
