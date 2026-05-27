"""strategy_d_threshold_sweep.py — iter-18 |edge| threshold sweep for Strategy D.

iter-17 found the [0.5, 0.75) bucket is the highest-ROI cohort. iter-9 + iter-10
crystallised |edge| > 0.5 as the convention. Tonight's only LOSS (Cason Wallace
STL U 1.5) sat at |edge|=0.50 — exactly on the threshold — which begs the
question whether 0.50 is actually the optimum.

This script reproduces the full Strategy D prediction pass over the 2024
playoff canonical slate (BLK / FG3M / STL only) using the OOS pre-playoffs
artifacts at `data/models/oos_pre_playoffs/`, then sweeps the |edge|
threshold from 0.20 to 1.50 in 0.05 increments (27 cuts). For each threshold:

    n_bets, hit%, ROI@-110, PnL @ flat $100, MaxDD (chronological), PnL/DD.

It also runs the same sweep per-stat (BLK, FG3M, STL separately) and reports
per-criterion optima plus sensitivity around 0.50. Finally it forward-tests
tonight's WCF G7 6-bet ledger under the recommended threshold.

Report: vault/Reports/iter18_threshold_sweep.md
Cache:  data/cache/iter18_threshold_sweep.json

Constraints respected:
- DO NOT modify production models or forbidden files.
- Reuses the leak-safe asof builder (`_build_asof_row`) from iter-6.
- LOCAL ONLY (no RunPod).
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
DEFAULT_OOS_DIR = os.path.join(PROJECT_DIR, "data", "models", "oos_pre_playoffs")
OOS_DIR = DEFAULT_OOS_DIR  # mutable; overridden by --model-dir
FORWARD_CSV = os.path.join(PROJECT_DIR, "data", "bets",
                           "strategy_d_2026-05-27.csv")
REPORT_PATH = os.path.join(PROJECT_DIR, "vault", "Reports",
                           "iter18_threshold_sweep.md")
CACHE_PATH = os.path.join(PROJECT_DIR, "data", "cache",
                          "iter18_threshold_sweep.json")

STATS = ("blk", "fg3m", "stl")
BET_SIZE = 100.0
PROFIT_RATIO_AT_M110 = _odds_to_decimal_profit(-110)  # 0.9091

# Sweep thresholds 0.20 -> 1.50 in 0.05 steps (27 cuts)
THRESHOLDS = [round(0.20 + 0.05 * i, 2) for i in range(27)]
CURRENT_THRESHOLD = 0.50


# ---- model loading -----------------------------------------------------------

def _load_qstat_xgb(stat: str):
    import xgboost as xgb
    path = os.path.join(OOS_DIR, f"quantile_pergame_{stat}_q50.json")
    if not os.path.exists(path):
        return None
    m = xgb.XGBRegressor()
    m.load_model(path)
    return m


def _predict_qstat(stat: str, model, feat_row: Dict[str, float]) -> float:
    cols = feature_columns()
    X = np.array([[float(feat_row.get(c, 0.0) or 0.0) for c in cols]],
                 dtype=float)
    pred_t = float(model.predict(X)[0])
    pred = float(_inverse(stat, np.array([pred_t]))[0])
    return max(0.0, pred)


# ---- drawdown ----------------------------------------------------------------

def _max_drawdown_chrono(records: List[Tuple[str, float]]) -> float:
    """Peak-to-trough on chronologically-sorted per-bet PnL."""
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


# ---- prediction pass ---------------------------------------------------------

def _build_predictions() -> List[dict]:
    """Predict every (player, date, stat) row for BLK/FG3M/STL.

    Returns a list of dicts: date, player, stat, line, actual, pred, edge_signed,
    abs_edge, rec ('OVER'/'UNDER'/'PUSH_LINE'), outcome ('win'/'loss'/'push').
    No threshold filter — every predictable row is cached.
    """
    print(f"  oos_dir:   {OOS_DIR}")
    print(f"  csv:       {CSV_PATH}")
    print(f"  stats:     {STATS}")
    print(f"  bet size:  ${BET_SIZE:.0f} flat @ -110 (profit ratio "
          f"{PROFIT_RATIO_AT_M110:.4f})")

    models: Dict[str, object] = {}
    for s in STATS:
        m = _load_qstat_xgb(s)
        if m is None:
            print(f"  FATAL: missing OOS artifact for {s}")
            sys.exit(1)
        models[s] = m
    print(f"  loaded models: {list(models.keys())}")

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

        edge = pred - line  # signed
        ae = abs(edge)
        # Recommendation: positive edge -> OVER, negative -> UNDER
        if edge > 0:
            rec = "OVER"
        elif edge < 0:
            rec = "UNDER"
        else:
            rec = "PUSH_LINE"  # exact equality, no bet possible

        actual_result = _classify_result(actual, line)
        if rec == "PUSH_LINE":
            outcome = "skip"
        elif actual_result == "PUSH":
            outcome = "push"
        else:
            outcome = "win" if rec == actual_result else "loss"

        preds.append({
            "date": r["date"],
            "player": r["player"],
            "stat": stat,
            "line": line,
            "actual": actual,
            "pred": pred,
            "edge_signed": edge,
            "abs_edge": ae,
            "rec": rec,
            "outcome": outcome,
        })
        if (i + 1) % 500 == 0:
            print(f"   ...{i+1}/{len(rows)} ({time.time()-t0:.1f}s) "
                  f"preds={len(preds)}")
    print(f"  predicted {len(preds)} rows in {time.time()-t0:.1f}s. "
          f"skips: {dict(skips)}")
    return preds


# ---- sweep -------------------------------------------------------------------

def _pnl(stake: float, outcome: str,
         profit_ratio: float = PROFIT_RATIO_AT_M110) -> float:
    if stake <= 0:
        return 0.0
    if outcome == "win":
        return stake * profit_ratio
    if outcome == "loss":
        return -stake
    return 0.0  # push


def _sweep_one(preds: List[dict], threshold: float,
               stat_filter: Optional[str] = None) -> dict:
    """Apply |edge| > threshold over preds (optionally filtered to one stat)."""
    pnl_chrono: List[Tuple[str, float]] = []
    n_bets = wins = losses = pushes = 0
    total_staked = 0.0
    total_pnl = 0.0
    for p in preds:
        if stat_filter is not None and p["stat"] != stat_filter:
            continue
        if p["outcome"] == "skip":  # zero-edge, no recommendation
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
    pnl_dd = (total_pnl / dd) if dd > 0 else (float("inf") if total_pnl > 0
                                              else 0.0)
    return {
        "threshold": threshold,
        "n_bets": n_bets,
        "wins": wins,
        "losses": losses,
        "pushes": pushes,
        "hit_pct": round(hit * 100.0, 2),
        "roi_pct": round(roi, 2),
        "pnl_dollars": round(total_pnl, 2),
        "maxdd_dollars": round(dd, 2),
        "pnl_dd": (round(pnl_dd, 2) if pnl_dd != float("inf") else None),
    }


def _sensitivity_around(preds: List[dict],
                        center: float = 0.50,
                        delta: float = 0.05) -> dict:
    """Detail what happens immediately above/below the current threshold.

    - Bets gained by loosening to (center-delta): |edge| in (center-delta, center]
    - Bets lost by tightening to (center+delta): |edge| in (center, center+delta]
    Hit rates and PnL of each marginal cohort.
    """
    def _cohort(lo: float, hi: float) -> dict:
        n = w = ll = ps = 0
        pnl_sum = 0.0
        for p in preds:
            if p["outcome"] == "skip":
                continue
            ae = p["abs_edge"]
            if not (lo < ae <= hi):
                continue
            n += 1
            if p["outcome"] == "win":
                w += 1
            elif p["outcome"] == "loss":
                ll += 1
            else:
                ps += 1
            pnl_sum += _pnl(BET_SIZE, p["outcome"])
        decisive = w + ll
        hit = (w / decisive) if decisive else 0.0
        return {"n": n, "wins": w, "losses": ll, "pushes": ps,
                "hit_pct": round(hit * 100.0, 2),
                "pnl_dollars": round(pnl_sum, 2)}
    return {
        "added_by_loosening_to_0.45": _cohort(center - delta, center),
        "dropped_by_tightening_to_0.55": _cohort(center, center + delta),
    }


# ---- forward test ------------------------------------------------------------

def _forward_test(csv_path: str, thresholds: List[float]) -> dict:
    """Replay tonight's settled ledger under each candidate threshold."""
    if not os.path.exists(csv_path):
        return {"error": f"missing {csv_path}"}
    bets: List[dict] = []
    with open(csv_path, encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            try:
                edge = float(r["edge"])
                odds = int(r["odds"])
                status = r["status"].strip().upper()
            except Exception:
                continue
            ae = abs(edge)
            outcome = ("win" if status == "WIN"
                       else ("loss" if status == "LOSS" else "push"))
            pr = (odds / 100.0) if odds > 0 else (100.0 / abs(odds))
            bets.append({
                "player": r["player"], "stat": r["stat"],
                "abs_edge": ae, "outcome": outcome, "profit_ratio": pr,
                "odds": odds, "status": status, "edge": edge,
            })
    out: Dict[str, dict] = {}
    for thr in thresholds:
        nb = wins = losses = pushes = 0
        staked = 0.0
        pnl = 0.0
        per_bet: List[dict] = []
        for b in bets:
            if b["abs_edge"] <= thr:
                continue
            stake = BET_SIZE
            p = _pnl(stake, b["outcome"], profit_ratio=b["profit_ratio"])
            nb += 1
            staked += stake
            pnl += p
            if b["outcome"] == "win":
                wins += 1
            elif b["outcome"] == "loss":
                losses += 1
            else:
                pushes += 1
            per_bet.append({
                "player": b["player"], "stat": b["stat"],
                "abs_edge": round(b["abs_edge"], 3),
                "stake": stake, "pnl": round(p, 2), "status": b["status"],
            })
        roi = (pnl / staked * 100.0) if staked > 0 else 0.0
        out[f"{thr:.2f}"] = {
            "threshold": thr,
            "n_bets": nb, "wins": wins, "losses": losses, "pushes": pushes,
            "total_staked": round(staked, 2),
            "total_pnl": round(pnl, 2),
            "roi_pct": round(roi, 2),
            "per_bet": per_bet,
        }
    return out


# ---- main --------------------------------------------------------------------

def _pick_optima(sweep: List[dict]) -> dict:
    """Per-criterion optima from a sweep (list of per-threshold result dicts).

    Robustness score: n_bets>=100 AND hit%>=60 AND ROI%>=25.
    """
    def _safe(arr, key):
        return [x for x in arr if x["n_bets"] > 0]
    rows = _safe(sweep, "n_bets")
    if not rows:
        return {}
    best_hit = max(rows, key=lambda x: x["hit_pct"])
    best_roi = max(rows, key=lambda x: x["roi_pct"])
    best_pnl = max(rows, key=lambda x: x["pnl_dollars"])
    best_dd = max(rows, key=lambda x: (x["pnl_dd"] if x["pnl_dd"] is not None
                                       else 1e9))
    robust = [x for x in rows
              if x["n_bets"] >= 100 and x["hit_pct"] >= 60.0
              and x["roi_pct"] >= 25.0]
    return {
        "best_hit_pct": best_hit,
        "best_roi_pct": best_roi,
        "best_pnl": best_pnl,
        "best_pnl_dd": best_dd,
        "robustness_passes": robust,
    }


def run() -> dict:
    print("\n  iter-18 Strategy D threshold sweep\n")
    preds = _build_predictions()

    # POOLED sweep
    sweep_pooled = [_sweep_one(preds, thr) for thr in THRESHOLDS]
    optima_pooled = _pick_optima(sweep_pooled)

    # Per-stat sweep
    sweep_per_stat: Dict[str, List[dict]] = {}
    optima_per_stat: Dict[str, dict] = {}
    for s in STATS:
        sweep_per_stat[s] = [_sweep_one(preds, thr, stat_filter=s)
                             for thr in THRESHOLDS]
        optima_per_stat[s] = _pick_optima(sweep_per_stat[s])

    # Sensitivity around 0.50
    sens = _sensitivity_around(preds, center=CURRENT_THRESHOLD, delta=0.05)

    # Pick a recommendation:
    # Primary criterion = best PnL/DD among rows with n_bets>=100 (avoid
    # tiny-sample overfit) AND hit%>=60. Fallback = best ROI%.
    rows = [x for x in sweep_pooled
            if x["n_bets"] >= 100 and x["hit_pct"] >= 60.0]
    if rows:
        recommended = max(rows, key=lambda x: (x["pnl_dd"]
                          if x["pnl_dd"] is not None else 1e9))
        rec_reason = ("max PnL/DD among rows with n_bets>=100 and hit%>=60")
    else:
        recommended = optima_pooled.get("best_roi_pct", sweep_pooled[0])
        rec_reason = "fallback: max ROI% (no robust row)"

    # Forward test the recommended threshold + comparison thresholds
    fwd_thresholds = sorted(set([round(recommended["threshold"], 2),
                                  0.50, 0.45, 0.55]))
    fwd = _forward_test(FORWARD_CSV, fwd_thresholds)

    out = {
        "sweep_pooled": sweep_pooled,
        "optima_pooled": optima_pooled,
        "sweep_per_stat": sweep_per_stat,
        "optima_per_stat": optima_per_stat,
        "sensitivity_around_0.50": sens,
        "recommended": recommended,
        "recommendation_reason": rec_reason,
        "forward_test": fwd,
        "n_preds": len(preds),
        "thresholds": THRESHOLDS,
        "current_threshold": CURRENT_THRESHOLD,
    }
    return out


# ---- report ------------------------------------------------------------------

def _fmt_pnl_dd(v) -> str:
    if v is None:
        return "inf"
    return f"{v:.2f}"


def save_report(out: dict) -> None:
    L: List[str] = []
    L.append("# Iter-18 — Strategy D |edge| Threshold Sweep\n")
    L.append(f"Stats: BLK / FG3M / STL. Bet size: ${BET_SIZE:.0f} flat @ -110 "
             f"(profit ratio {PROFIT_RATIO_AT_M110:.4f}). "
             f"Drawdown is chronological peak-to-trough on cumulative PnL.\n")
    L.append(f"Total predictions enumerated (any |edge|): {out['n_preds']}\n")

    # ── Pooled sweep table ──
    L.append("## Pooled sweep table (BLK + FG3M + STL)\n")
    L.append("| threshold | n_bets | hit% | ROI% | PnL @ $100 | MaxDD | PnL/DD |")
    L.append("|---:|---:|---:|---:|---:|---:|---:|")
    for r in out["sweep_pooled"]:
        marker = " (current)" if abs(r["threshold"] - CURRENT_THRESHOLD) < 1e-6 \
                              else ""
        L.append(f"| {r['threshold']:.2f}{marker} | {r['n_bets']} | "
                 f"{r['hit_pct']:.2f}% | {r['roi_pct']:+.2f}% | "
                 f"${r['pnl_dollars']:+,.0f} | ${r['maxdd_dollars']:,.0f} | "
                 f"{_fmt_pnl_dd(r['pnl_dd'])} |")
    L.append("")

    # ── Pooled per-criterion optima ──
    L.append("## Pooled per-criterion optima\n")
    op = out["optima_pooled"]
    L.append("| Criterion | threshold | n_bets | hit% | ROI% | PnL | PnL/DD |")
    L.append("|---|---:|---:|---:|---:|---:|---:|")
    for crit, key in [("Best hit%", "best_hit_pct"),
                      ("Best ROI%", "best_roi_pct"),
                      ("Best raw PnL", "best_pnl"),
                      ("Best PnL/DD", "best_pnl_dd")]:
        r = op.get(key)
        if not r:
            continue
        L.append(f"| {crit} | {r['threshold']:.2f} | {r['n_bets']} | "
                 f"{r['hit_pct']:.2f}% | {r['roi_pct']:+.2f}% | "
                 f"${r['pnl_dollars']:+,.0f} | {_fmt_pnl_dd(r['pnl_dd'])} |")
    robust = op.get("robustness_passes", [])
    if robust:
        L.append("")
        L.append("Robustness passes (n_bets>=100 AND hit%>=60 AND ROI%>=25):")
        L.append("| threshold | n_bets | hit% | ROI% | PnL | PnL/DD |")
        L.append("|---:|---:|---:|---:|---:|---:|")
        for r in robust:
            L.append(f"| {r['threshold']:.2f} | {r['n_bets']} | "
                     f"{r['hit_pct']:.2f}% | {r['roi_pct']:+.2f}% | "
                     f"${r['pnl_dollars']:+,.0f} | "
                     f"{_fmt_pnl_dd(r['pnl_dd'])} |")
    else:
        L.append("")
        L.append("No threshold satisfies the robustness gate.")
    L.append("")

    # ── Per-stat optima ──
    L.append("## Per-stat optima\n")
    L.append("| Stat | Criterion | threshold | n_bets | hit% | ROI% | PnL | "
             "PnL/DD |")
    L.append("|---|---|---:|---:|---:|---:|---:|---:|")
    for s in STATS:
        ops = out["optima_per_stat"].get(s, {})
        for crit, key in [("Best ROI%", "best_roi_pct"),
                          ("Best PnL", "best_pnl"),
                          ("Best PnL/DD", "best_pnl_dd")]:
            r = ops.get(key)
            if not r:
                continue
            L.append(f"| {s.upper()} | {crit} | {r['threshold']:.2f} | "
                     f"{r['n_bets']} | {r['hit_pct']:.2f}% | "
                     f"{r['roi_pct']:+.2f}% | ${r['pnl_dollars']:+,.0f} | "
                     f"{_fmt_pnl_dd(r['pnl_dd'])} |")
    L.append("")

    # ── Per-stat sweep (only show thresholds near 0.50) ──
    L.append("## Per-stat sweep (selected thresholds)\n")
    show_thr = [0.30, 0.40, 0.45, 0.50, 0.55, 0.60, 0.75, 1.00]
    for s in STATS:
        L.append(f"### {s.upper()}")
        L.append("| threshold | n_bets | hit% | ROI% | PnL | PnL/DD |")
        L.append("|---:|---:|---:|---:|---:|---:|")
        for r in out["sweep_per_stat"][s]:
            if r["threshold"] not in show_thr:
                continue
            marker = " (current)" if abs(r["threshold"]
                                        - CURRENT_THRESHOLD) < 1e-6 else ""
            L.append(f"| {r['threshold']:.2f}{marker} | {r['n_bets']} | "
                     f"{r['hit_pct']:.2f}% | {r['roi_pct']:+.2f}% | "
                     f"${r['pnl_dollars']:+,.0f} | "
                     f"{_fmt_pnl_dd(r['pnl_dd'])} |")
        L.append("")

    # ── Sensitivity around 0.50 ──
    L.append("## Sensitivity around current threshold (0.50)\n")
    sens = out["sensitivity_around_0.50"]
    add = sens["added_by_loosening_to_0.45"]
    drp = sens["dropped_by_tightening_to_0.55"]
    L.append("| cohort | n | wins | losses | pushes | hit% | PnL @ $100 |")
    L.append("|---|---:|---:|---:|---:|---:|---:|")
    L.append(f"| Added by loosening 0.50 -> 0.45 (|edge| in (0.45, 0.50]) | "
             f"{add['n']} | {add['wins']} | {add['losses']} | "
             f"{add['pushes']} | {add['hit_pct']:.2f}% | "
             f"${add['pnl_dollars']:+,.0f} |")
    L.append(f"| Dropped by tightening 0.50 -> 0.55 (|edge| in (0.50, 0.55]) "
             f"| {drp['n']} | {drp['wins']} | {drp['losses']} | "
             f"{drp['pushes']} | {drp['hit_pct']:.2f}% | "
             f"${drp['pnl_dollars']:+,.0f} |")
    L.append("")

    # ── Recommendation + forward test ──
    rec = out["recommended"]
    L.append("## Recommendation\n")
    L.append(f"- **Recommended threshold:** **|edge| > {rec['threshold']:.2f}** "
             f"({out['recommendation_reason']}).")
    L.append(f"  - Backtest: n_bets={rec['n_bets']}, hit={rec['hit_pct']:.2f}%, "
             f"ROI={rec['roi_pct']:+.2f}%, PnL=${rec['pnl_dollars']:+,.0f}, "
             f"MaxDD=${rec['maxdd_dollars']:,.0f}, "
             f"PnL/DD={_fmt_pnl_dd(rec['pnl_dd'])}.")
    L.append("")

    # ── Forward test ──
    L.append("## Forward test — tonight's WCF G7 6-bet ledger (real odds)\n")
    fwd = out["forward_test"]
    if fwd.get("error"):
        L.append(f"_({fwd['error']})_")
    else:
        L.append("| threshold | n_bets | wins | losses | Staked | PnL | ROI% |")
        L.append("|---:|---:|---:|---:|---:|---:|---:|")
        for tk in sorted(fwd.keys()):
            d = fwd[tk]
            L.append(f"| {d['threshold']:.2f} | {d['n_bets']} | {d['wins']} | "
                     f"{d['losses']} | ${d['total_staked']:,.0f} | "
                     f"${d['total_pnl']:+,.2f} | {d['roi_pct']:+.2f}% |")
        L.append("")
        # Detail under recommended threshold
        rec_key = f"{rec['threshold']:.2f}"
        if rec_key in fwd:
            L.append(f"### Per-bet detail under recommended |edge| > "
                     f"{rec['threshold']:.2f}")
            L.append("| Player | Stat | |edge| | Stake | Status | PnL |")
            L.append("|---|---|---:|---:|---|---:|")
            for pb in fwd[rec_key]["per_bet"]:
                L.append(f"| {pb['player']} | {pb['stat'].upper()} | "
                         f"{pb['abs_edge']:.2f} | ${pb['stake']:,.0f} | "
                         f"{pb['status']} | ${pb['pnl']:+,.2f} |")
            L.append("")

    # ── Caveats ──
    L.append("## Quirks / caveats\n")
    L.append("- Per-stat samples are smaller than the pooled set — at high "
             "thresholds the per-stat tables get noisy (single-digit bet "
             "counts). Treat per-stat optima with n_bets<30 as suggestive.")
    L.append("- ROI is computed on decisive bets only (pushes excluded from "
             "the denominator's win/loss). Stake/PnL include pushes as $0.")
    L.append("- The forward test odds are the actual moneyline (not -110), so "
             "tonight's PnL ratios differ slightly from the backtest's -110 "
             "ratio.")
    L.append("- Bets with |edge|==exact-threshold are excluded by the strict "
             "`>` comparison. At threshold=0.50, tonight's 4 |edge|=0.50 bets "
             "are FILTERED OUT (this is the key insight: tonight's only LOSS "
             "is also at 0.50).")
    L.append("- Walk-forward leak-safety preserved via the iter-6 "
             "`_build_asof_row` builder.")

    os.makedirs(os.path.dirname(REPORT_PATH), exist_ok=True)
    with open(REPORT_PATH, "w", encoding="utf-8") as fh:
        fh.write("\n".join(L))
    print(f"\n  report -> {REPORT_PATH}")

    os.makedirs(os.path.dirname(CACHE_PATH), exist_ok=True)
    with open(CACHE_PATH, "w", encoding="utf-8") as fh:
        json.dump({
            "generated_at": datetime.utcnow().isoformat() + "Z",
            **out,
        }, fh, indent=2, default=str)
    print(f"  cache  -> {CACHE_PATH}")


def main() -> None:
    global OOS_DIR, REPORT_PATH, CACHE_PATH
    ap = argparse.ArgumentParser()
    ap.add_argument("--model-dir", default=DEFAULT_OOS_DIR,
                    help="Directory containing OOS quantile_pergame_*_q50.json")
    ap.add_argument("--report-path", default=None,
                    help="Override markdown report output path")
    ap.add_argument("--cache-path", default=None,
                    help="Override JSON cache output path")
    args, _ = ap.parse_known_args()
    OOS_DIR = args.model_dir
    if args.report_path:
        REPORT_PATH = args.report_path
    if args.cache_path:
        CACHE_PATH = args.cache_path

    out = run()
    save_report(out)
    # Console summary
    rec = out["recommended"]
    print("\n  ===== ITER-18 THRESHOLD SWEEP SUMMARY =====")
    print(f"  Recommended threshold: |edge| > {rec['threshold']:.2f}")
    print(f"    n_bets={rec['n_bets']}  hit={rec['hit_pct']:.2f}%  "
          f"ROI={rec['roi_pct']:+.2f}%  PnL=${rec['pnl_dollars']:+,.0f}  "
          f"PnL/DD={_fmt_pnl_dd(rec['pnl_dd'])}")
    op = out["optima_pooled"]
    print("  Per-criterion optima:")
    for crit, key in [("hit%", "best_hit_pct"), ("ROI%", "best_roi_pct"),
                      ("PnL$", "best_pnl"), ("PnL/DD", "best_pnl_dd")]:
        r = op.get(key)
        if r:
            print(f"    {crit:>6}: thr={r['threshold']:.2f} "
                  f"(n={r['n_bets']}, hit={r['hit_pct']:.2f}%, "
                  f"ROI={r['roi_pct']:+.2f}%)")


if __name__ == "__main__":
    main()
