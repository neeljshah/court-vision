"""iter-25: Strategy-D (BLK + FG3M + STL, |edge|>0.5 strict) on EXTENDED OOS.

Iter-24 produced the extended OOS canonical CSV
(data/external/historical_lines/extended_oos_canonical.csv, 10,927 rows)
and re-ran the POOLED aggregate (all 6 stats). We never computed
Strategy-D's specific 3-stat-filtered performance on the extended pool.

This script:
  1. Reads the extended canonical CSV.
  2. Restricts rows to stat in {blk, fg3m, stl}.
  3. Predicts via the leak-clean OOS q50 artifacts at
     data/models/oos_pre_playoffs/quantile_pergame_{blk,fg3m,stl}_q50.json.
  4. Applies the Strategy-D filter (|edge| > 0.50 strict).
  5. Computes flat-$100 PnL @ -110, hit%, ROI%, chronological max drawdown,
     and PnL/DD ratio.
  6. Slices PnL/hit% by stat x era (2024 playoffs vs 2026 reg-season) so we
     can see if the +$12K headline holds.
  7. Writes a markdown report and prints a concise summary.

Reuses iter-6 `_build_asof_row` for leak safety (training cutoff 2024-04-21).
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
from src.prediction.prop_pergame import feature_columns  # noqa: E402
from src.prediction.prop_quantiles import _inverse  # noqa: E402


# ----------------------------------------------------------------------
# Config
# ----------------------------------------------------------------------

EXT_CSV = os.path.join(
    PROJECT_DIR, "data", "external", "historical_lines",
    "extended_oos_canonical.csv",
)
CANON_CSV = os.path.join(
    PROJECT_DIR, "data", "external", "historical_lines",
    "playoffs_2024_canonical.csv",
)
GAMELOG_DIR = os.path.join(PROJECT_DIR, "data", "nba")
OOS_DIR = os.path.join(PROJECT_DIR, "data", "models", "oos_pre_playoffs")
REPORT_PATH = os.path.join(
    PROJECT_DIR, "vault", "Reports",
    "iter25_strategy_d_extended_aggregate.md",
)

STRATEGY_D_STATS = ("blk", "fg3m", "stl")
THRESHOLD = 0.5     # strict |edge| > 0.5
BET_SIZE = 100.0    # flat $100 @ -110

# Canonical (iter-10) headline Strategy-D numbers — used for the comparison row.
CANON_REF_TOTAL = {
    "n_bets": 418, "hit_rate": 0.6746, "roi_pct": 28.80,
    "pnl_dollars": 12036.0, "max_dd": 609.0, "pnl_dd": 19.76,
}
CANON_REF_PER_STAT = {
    "blk":  {"period": "2024 playoffs", "n_bets": 33,  "hit": 0.6970, "roi": 33.06},
    "fg3m": {"period": "2024 playoffs", "n_bets": 358, "hit": 0.6648, "roi": 23.14},
    "stl":  {"period": "2024 playoffs", "n_bets": 27,  "hit": 0.9259, "roi": 36.36},
}


# ----------------------------------------------------------------------
# Era partitioning
# ----------------------------------------------------------------------

def _era_for_date(date_str: str) -> str:
    """Bucket rows into eras to slice extended vs canonical contribution."""
    d = datetime.fromisoformat(date_str)
    if d.year == 2024 and d.month in (4, 5, 6):
        return "2024 playoffs"
    if d.year >= 2025 or (d.year == 2024 and d.month >= 10):
        return "2026 reg season"
    return "other"


# ----------------------------------------------------------------------
# Model loading + prediction
# ----------------------------------------------------------------------

def _load_q50_xgb(stat: str):
    import xgboost as xgb
    path = os.path.join(OOS_DIR, f"quantile_pergame_{stat}_q50.json")
    if not os.path.exists(path):
        return None, path
    m = xgb.XGBRegressor()
    m.load_model(path)
    return m, path


def _predict_q50(stat: str, model, feat_row: Dict[str, float]) -> float:
    cols = feature_columns()
    X = np.array(
        [[float(feat_row.get(c, 0.0) or 0.0) for c in cols]], dtype=float
    )
    pred_t = float(model.predict(X)[0])
    pred = float(_inverse(stat, np.array([pred_t]))[0])
    return max(0.0, pred)


# ----------------------------------------------------------------------
# Main aggregation
# ----------------------------------------------------------------------

def run() -> dict:
    print("\n  iter-25 Strategy-D on EXTENDED OOS")
    print(f"  csv:       {EXT_CSV}")
    print(f"  stats:     {STRATEGY_D_STATS}")
    print(f"  threshold: |edge| > {THRESHOLD}")
    print(f"  bet size:  ${BET_SIZE:.0f} @ -110")

    models: Dict[str, object] = {}
    for s in STRATEGY_D_STATS:
        m, path = _load_q50_xgb(s)
        if m is None:
            print(f"  MISSING {s} at {path} - aborting")
            sys.exit(1)
        models[s] = m
        print(f"  loaded {s} from {os.path.basename(path)}")

    # Load all Strategy-D rows from extended CSV.
    rows: List[dict] = []
    with open(EXT_CSV, encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            stat = r.get("stat", "").lower()
            if stat in STRATEGY_D_STATS:
                rows.append(r)
    print(f"  Strategy-D rows in extended CSV: {len(rows)}")

    # Pre-resolve player ids.
    unique = sorted({r["player"] for r in rows})
    print(f"  resolving {len(unique)} unique players...")
    name2pid: Dict[str, Optional[int]] = {}
    for nm in unique:
        name2pid[nm] = _resolve_player_id(nm)
    n_res = sum(1 for v in name2pid.values() if v is not None)
    print(f"  resolved {n_res}/{len(unique)} players")

    profit_per_win = _odds_to_decimal_profit(-110)

    # Per-stat x era accumulator + chronological PnL series for DD.
    per_stat: Dict[str, dict] = {
        s: {"n_pred": 0, "n_bets": 0, "wins": 0, "losses": 0, "pushes": 0,
            "skip": defaultdict(int),
            "by_era": defaultdict(
                lambda: {"n_bets": 0, "wins": 0, "losses": 0, "pushes": 0}
            )}
        for s in STRATEGY_D_STATS
    }
    settled_bets: List[Tuple[str, str, float]] = []  # (date, stat, profit_per_bet)

    # Build as-of feature row cache.
    row_cache: Dict[Tuple[int, str, str, str], Optional[Dict[str, float]]] = {}

    t0 = time.time()
    for i, r in enumerate(rows):
        stat = r["stat"].lower()
        acc = per_stat[stat]
        try:
            line = float(r["closing_line"])
            actual = float(r["actual_value"])
            d = datetime.fromisoformat(r["date"])
        except Exception:
            acc["skip"]["bad_row"] += 1
            continue
        pid = name2pid.get(r["player"])
        if pid is None:
            acc["skip"]["no_pid"] += 1
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
            acc["skip"]["no_history"] += 1
            continue

        try:
            pred = _predict_q50(stat, models[stat], feat)
        except Exception as e:
            acc["skip"][f"err:{type(e).__name__}"] += 1
            continue

        edge = pred - line
        rec = _recommend(edge, THRESHOLD)
        acc["n_pred"] += 1

        if rec == "NO_BET":
            continue

        era = _era_for_date(r["date"])
        result = _classify_result(actual, line)
        if result == "PUSH":
            acc["pushes"] += 1
            acc["by_era"][era]["pushes"] += 1
            settled_bets.append((r["date"], stat, 0.0))
        else:
            acc["n_bets"] += 1
            acc["by_era"][era]["n_bets"] += 1
            win = (rec == result)
            if win:
                acc["wins"] += 1
                acc["by_era"][era]["wins"] += 1
                profit = profit_per_win * BET_SIZE
            else:
                acc["losses"] += 1
                acc["by_era"][era]["losses"] += 1
                profit = -BET_SIZE
            settled_bets.append((r["date"], stat, profit))

        if (i + 1) % 1000 == 0:
            print(f"   ...{i+1}/{len(rows)} ({time.time()-t0:.1f}s)")

    elapsed = time.time() - t0
    print(f"\n  Done in {elapsed:.1f}s")

    # Per-stat aggregates.
    per_stat_summary: Dict[str, dict] = {}
    for s, acc in per_stat.items():
        bets = acc["n_bets"]
        wins = acc["wins"]
        roi_u = wins * profit_per_win - (bets - wins) * 1.0
        hit = (wins / bets) if bets else 0.0
        roi_pct = (roi_u / bets * 100.0) if bets else 0.0
        pnl_dollars = roi_u * BET_SIZE
        era_breakdown = {}
        for era, ed in acc["by_era"].items():
            eb = ed["n_bets"]
            ew = ed["wins"]
            e_units = ew * profit_per_win - (eb - ew) * 1.0
            era_breakdown[era] = {
                "n_bets": eb,
                "wins": ew,
                "losses": ed["losses"],
                "pushes": ed["pushes"],
                "hit_rate": (ew / eb) if eb else 0.0,
                "roi_pct": (e_units / eb * 100.0) if eb else 0.0,
                "pnl_dollars": e_units * BET_SIZE,
            }
        per_stat_summary[s] = {
            "n_pred": acc["n_pred"],
            "n_bets": bets,
            "wins": wins,
            "losses": acc["losses"],
            "pushes": acc["pushes"],
            "hit_rate": hit,
            "roi_pct": roi_pct,
            "pnl_dollars": pnl_dollars,
            "by_era": era_breakdown,
            "skip": dict(acc["skip"]),
        }

    # Pooled totals.
    total_bets = sum(d["n_bets"] for d in per_stat_summary.values())
    total_wins = sum(d["wins"] for d in per_stat_summary.values())
    total_pushes = sum(d["pushes"] for d in per_stat_summary.values())
    total_losses = sum(d["losses"] for d in per_stat_summary.values())
    total_pred = sum(d["n_pred"] for d in per_stat_summary.values())
    total_units = total_wins * profit_per_win - (total_bets - total_wins) * 1.0
    total_hit = (total_wins / total_bets) if total_bets else 0.0
    total_roi_pct = (total_units / total_bets * 100.0) if total_bets else 0.0
    total_pnl = total_units * BET_SIZE

    # Chronological PnL series for max drawdown.
    settled_bets.sort(key=lambda x: x[0])
    pnl_series = []
    running = 0.0
    peak = 0.0
    max_dd = 0.0
    for _, _, p in settled_bets:
        running += p
        pnl_series.append(running)
        if running > peak:
            peak = running
        dd = peak - running
        if dd > max_dd:
            max_dd = dd
    pnl_dd = (total_pnl / max_dd) if max_dd > 0 else float("inf")

    return {
        "per_stat": per_stat_summary,
        "totals": {
            "n_pred": total_pred,
            "n_bets": total_bets,
            "wins": total_wins,
            "losses": total_losses,
            "pushes": total_pushes,
            "hit_rate": total_hit,
            "roi_pct": total_roi_pct,
            "pnl_dollars": total_pnl,
            "max_dd": max_dd,
            "pnl_dd": pnl_dd,
        },
        "elapsed_sec": elapsed,
        "n_rows_input": len(rows),
        "n_settled": len(settled_bets),
    }


# ----------------------------------------------------------------------
# Report
# ----------------------------------------------------------------------

def save_report(res: dict) -> None:
    os.makedirs(os.path.dirname(REPORT_PATH), exist_ok=True)
    per = res["per_stat"]
    tot = res["totals"]
    L: List[str] = []

    L.append("# Strategy-D Extended OOS Aggregate - iter-25\n")
    L.append("Runs the EXACT Strategy-D filter (BLK + FG3M + STL only, |edge| > 0.5")
    L.append("strict) on the extended OOS pool produced in iter-24 to give a")
    L.append("gold-standard 2-year external validation of iter-10's +$12K headline.\n")
    L.append(f"- threshold: |edge| > {THRESHOLD}")
    L.append(f"- bet sizing: flat ${BET_SIZE:.0f} per bet @ -110")
    L.append(f"- rows scanned: {res['n_rows_input']}")
    L.append(f"- bets settled: {res['n_settled']}")
    L.append(f"- elapsed: {res['elapsed_sec']:.1f}s\n")

    L.append("## Strategy-D extended vs canonical playoffs")
    L.append("| Pool | n_bets | hit% | ROI% | PnL @ $100 | MaxDD | PnL/DD |")
    L.append("|------|------:|-----:|-----:|----------:|------:|------:|")
    cr = CANON_REF_TOTAL
    L.append(
        f"| Canonical playoffs (iter-10) | {cr['n_bets']} | "
        f"{cr['hit_rate']*100:.2f}% | {cr['roi_pct']:+.2f}% | "
        f"${cr['pnl_dollars']:+,.0f} | ${cr['max_dd']:,.0f} | "
        f"{cr['pnl_dd']:.2f} |"
    )
    pnl_dd_disp = (
        f"{tot['pnl_dd']:.2f}" if tot["pnl_dd"] != float("inf") else "inf"
    )
    L.append(
        f"| Extended (iter-25) | {tot['n_bets']} | "
        f"{tot['hit_rate']*100:.2f}% | {tot['roi_pct']:+.2f}% | "
        f"${tot['pnl_dollars']:+,.0f} | ${tot['max_dd']:,.0f} | "
        f"{pnl_dd_disp} |"
    )
    L.append("")

    L.append("## Per-stat x era breakdown")
    L.append("| Stat | Period | n_bets | hit% | ROI% | PnL @$100 |")
    L.append("|------|--------|------:|-----:|-----:|----------:|")
    eras_order = ["2024 playoffs", "2026 reg season", "other"]
    for s in STRATEGY_D_STATS:
        d = per[s]
        for era in eras_order:
            eb = d["by_era"].get(era)
            if not eb or eb["n_bets"] == 0:
                continue
            L.append(
                f"| {s.upper()} | {era} | {eb['n_bets']} | "
                f"{eb['hit_rate']*100:.2f}% | {eb['roi_pct']:+.2f}% | "
                f"${eb['pnl_dollars']:+,.0f} |"
            )
        # Per-stat total
        L.append(
            f"| **{s.upper()} TOTAL** | all | **{d['n_bets']}** | "
            f"**{d['hit_rate']*100:.2f}%** | **{d['roi_pct']:+.2f}%** | "
            f"**${d['pnl_dollars']:+,.0f}** |"
        )
    L.append("")

    L.append("## Per-stat headlines (extended vs canonical)")
    L.append("| Stat | Extended n_bets | Extended ROI% | Canonical ROI% | Delta pp |")
    L.append("|------|----------------:|--------------:|---------------:|---------:|")
    for s in STRATEGY_D_STATS:
        d = per[s]
        ref = CANON_REF_PER_STAT[s]
        delta = d["roi_pct"] - ref["roi"]
        L.append(
            f"| {s.upper()} | {d['n_bets']} | "
            f"{d['roi_pct']:+.2f}% | {ref['roi']:+.2f}% | "
            f"{delta:+.2f} |"
        )
    L.append("")

    # Verdict
    L.append("## Verdict")
    extended_roi = tot["roi_pct"]
    if extended_roi >= 25.0:
        verdict = "ROBUST"
        verdict_text = (
            f"Strategy-D extended ROI ({extended_roi:+.2f}%) is >= 25% on the "
            "extended pool. The original +$12K headline holds well across two "
            "seasons, and the strategy is validated for live deployment."
        )
    elif extended_roi >= 15.0:
        verdict = "SHIFTED"
        verdict_text = (
            f"Strategy-D extended ROI ({extended_roi:+.2f}%) sits between 15% "
            "and 25%. The strategy still beats vig but is materially below the "
            "iter-10 playoffs headline; expect the live edge to be smaller."
        )
    else:
        verdict = "BROKEN"
        verdict_text = (
            f"Strategy-D extended ROI ({extended_roi:+.2f}%) fell below 15%. "
            "The iter-10 +$12K headline was likely an artifact of the 2024 "
            "playoffs window and does not generalise."
        )
    L.append(f"**{verdict}** - {verdict_text}\n")

    L.append("## Quirks / caveats")
    L.append("- benashkar 2026 data only has PTS/REB/AST/3M (no STL/BLK), so STL "
             "and BLK get extra rows only from reisneriv-extra (+~70 each, still "
             "in the 2024 window). FG3M is the only stat with true 2026 OOS rows.")
    L.append("- BLK and STL date_max in the extended CSV is 2024-05-23 - the "
             "2026 reg-season slice for those stats is empty. Only FG3M tests "
             "true generalisation across seasons.")
    L.append("- Per-era sample sizes for BLK/STL are tiny (<50). Treat era ROI "
             "for those stats as noise; the FG3M 2026 slice is the load-bearing "
             "evidence of generalisation.")
    L.append("- All predictions use the iter-6 `_build_asof_row` (training "
             "cutoff 2024-04-21) so there is no leak.")
    L.append("- MaxDD computed chronologically on flat $100 settled bets "
             "(pushes counted as zero PnL, not as drawdown).")
    L.append("- Skip reasons per stat:")
    for s in STRATEGY_D_STATS:
        d = per[s]
        if d["skip"]:
            L.append(f"  - {s}: {d['skip']}")
    L.append("")

    with open(REPORT_PATH, "w", encoding="utf-8") as fh:
        fh.write("\n".join(L))
    print(f"\n  Report -> {REPORT_PATH}")


def main() -> None:
    res = run()
    tot = res["totals"]
    print("\n  STRATEGY-D EXTENDED:")
    print(f"    n_pred={tot['n_pred']}  n_bets={tot['n_bets']}  "
          f"hit={tot['hit_rate']*100:.2f}%  ROI={tot['roi_pct']:+.2f}%  "
          f"PnL=${tot['pnl_dollars']:+,.0f}  MaxDD=${tot['max_dd']:,.0f}  "
          f"PnL/DD={tot['pnl_dd']:.2f}")
    print(f"    canonical iter-10: 418 bets / 67.46% / +28.80% / +$12,036")
    save_report(res)


if __name__ == "__main__":
    main()
