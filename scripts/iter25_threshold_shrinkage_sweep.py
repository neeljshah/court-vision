"""iter25_threshold_shrinkage_sweep.py — Iter-25 recalibration on Iter-22 model.

Runs on 2025-26 only eval (RS + playoffs) which is true OOS post Iter-22 cutoff.
Baseline: commit 2688cd41 (+19.37% on 1,337 2025-26 bets — from holdout_baseline.json).

Steps:
  1. Build eval CSV (RS + playoffs 2025-26).
  2. Generate per-row predictions + edges, cached in memory.
  3. Edge-shrinkage fit on 2024-25 RS data (fit set), apply to 2025-26 eval.
  4. Threshold sweep [0.1..1.5] on 2025-26 eval with 4 calendar folds.
  5. Combined test: shrinkage + optimal thresholds.
  6. SHIP if +1pp aggregate ROI improvement.
"""
from __future__ import annotations

import csv
import json
import os
import sys
import time
from collections import defaultdict
from datetime import datetime, date as _date
from typing import Dict, List, Optional, Tuple

import numpy as np

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)
os.environ.setdefault("NBA_INJURY_WIRE_DISABLE", "1")

from scripts.backtest_closing_lines_2024_playoffs import (
    _build_asof_row,
    _resolve_player_id,
    _season_for_date,
    _classify_result,
    _recommend,
    _odds_to_decimal_profit,
)
from src.prediction.prop_pergame import predict_pergame

# ─── paths ─────────────────────────────────────────────────────────────────────

RS_2025_26   = os.path.join(PROJECT_DIR, "data", "external", "historical_lines",
                            "regular_season_2025_26_oddsapi.csv")
PO_2025_26   = os.path.join(PROJECT_DIR, "data", "external", "historical_lines",
                            "playoffs_2025_26_oddsapi.csv")
RS_2024_25   = os.path.join(PROJECT_DIR, "data", "external", "historical_lines",
                            "regular_season_2024_25_oddsapi.csv")
EVAL_COMBINED = os.path.join(PROJECT_DIR, "data", "cache", "eval_2025_26_combined.csv")
GAMELOG_DIR  = os.path.join(PROJECT_DIR, "data", "nba")
HOLDOUT_JSON = os.path.join(PROJECT_DIR, "data", "cache", "holdout_baseline.json")
THRESHOLDS_PY = os.path.join(PROJECT_DIR, "src", "prediction", "bet_thresholds.py")
SHRINKAGE_PY  = os.path.join(PROJECT_DIR, "src", "prediction", "edge_shrinkage.py")

STATS = ["pts", "reb", "ast", "fg3m", "stl", "blk", "tov"]
THRESHOLD_CANDIDATES = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 1.0, 1.5]

# Current production thresholds (from bet_thresholds.py as of Iter-15)
CURRENT_THRESHOLDS = {
    "pts": 0.5, "ast": 0.5, "reb": 0.5, "fg3m": 0.5,
    "stl": 0.10, "blk": 0.40, "tov": 0.5,
}

MIN_BETS_FOR_RECOMMENDATION = 30
SHIP_THRESHOLD_PP = 1.0  # aggregate ROI lift required to ship

# ─── calendar fold boundaries (4 folds for 2025-26) ──────────────────────────
# Fold 1: Oct 2025 – Dec 2025 (regular season start)
# Fold 2: Jan 2026 – Mar 2026 (mid-season)
# Fold 3: Apr 2026 – May 2026 RS games
# Fold 4: May 2026 – Jun 2026 playoffs
FOLD_CUTOFFS = [
    ("2025-10-01", "2025-12-31"),   # fold 0
    ("2026-01-01", "2026-03-31"),   # fold 1
    ("2026-04-01", "2026-04-30"),   # fold 2
    ("2026-05-01", "2026-12-31"),   # fold 3 (playoffs)
]


def _fold_for_date(ds: str) -> int:
    d = datetime.fromisoformat(ds)
    for i, (lo, hi) in enumerate(FOLD_CUTOFFS):
        if datetime.fromisoformat(lo) <= d <= datetime.fromisoformat(hi):
            return i
    return -1


# ─── step 1: build combined eval CSV ─────────────────────────────────────────

def build_eval_csv() -> int:
    """Concatenate RS + playoffs 2025-26 into a single CSV. Returns row count."""
    os.makedirs(os.path.dirname(EVAL_COMBINED), exist_ok=True)
    rows_written = 0
    header_written = False
    for src_path in [RS_2025_26, PO_2025_26]:
        with open(src_path, encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            if not header_written:
                fieldnames = reader.fieldnames
            with open(EVAL_COMBINED, "w" if not header_written else "a",
                      newline="", encoding="utf-8") as out:
                w = csv.DictWriter(out, fieldnames=fieldnames)
                if not header_written:
                    w.writeheader()
                    header_written = True
                for r in reader:
                    w.writerow(r)
                    rows_written += 1
    print(f"  [step1] wrote {rows_written} rows -> {EVAL_COMBINED}")
    return rows_written


# ─── step 2: generate predictions for all eval rows ──────────────────────────

def _load_rows(path: str, stats_filter=None) -> List[dict]:
    rows = []
    with open(path, encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if stats_filter and r.get("stat", "").lower() not in stats_filter:
                continue
            rows.append(r)
    return rows


def build_predictions_cache(rows: List[dict], label: str) -> List[dict]:
    """Return list of enriched dicts with pred, edge, actual, line, fold, stat."""
    unique_names = sorted({r["player"] for r in rows})
    name2pid = {}
    for nm in unique_names:
        name2pid[nm] = _resolve_player_id(nm)
    resolved = sum(1 for v in name2pid.values() if v)
    print(f"  [{label}] resolved {resolved}/{len(unique_names)} players")

    row_cache: Dict = {}
    skip = defaultdict(int)
    results = []
    t0 = time.time()

    for idx, r in enumerate(rows):
        stat = r.get("stat", "").lower()
        if stat not in STATS:
            skip["bad_stat"] += 1
            continue
        player = r["player"]
        opp = r["opp"]
        venue = r.get("venue", "home")
        try:
            line = float(r["closing_line"])
            actual = float(r["actual_value"])
            over_odds = int(r.get("over_odds") or -110)
            under_odds = int(r.get("under_odds") or -110)
        except (TypeError, ValueError):
            skip["bad_numeric"] += 1
            continue
        try:
            d = datetime.fromisoformat(r["date"])
        except Exception:
            skip["bad_date"] += 1
            continue

        pid = name2pid.get(player)
        if pid is None:
            skip["no_pid"] += 1
            continue

        season = _season_for_date(d)
        is_home = (venue == "home")
        key = (pid, r["date"], venue, opp)
        if key not in row_cache:
            row_cache[key] = _build_asof_row(
                pid, opp, d, season, is_home=is_home, rest_days=2.0,
                gamelog_dir=GAMELOG_DIR,
            )
        feat = row_cache[key]
        if feat is None:
            skip["no_history"] += 1
            continue

        try:
            pred = predict_pergame(stat, feat)
        except Exception as e:
            skip[f"predict_err"] += 1
            continue
        if pred is None:
            skip["no_model"] += 1
            continue
        pred = float(pred)

        edge = pred - line
        fold = _fold_for_date(r["date"])
        results.append({
            "player": player, "date": r["date"], "stat": stat,
            "pred": pred, "line": line, "actual": actual, "edge": edge,
            "over_odds": over_odds, "under_odds": under_odds,
            "fold": fold,
        })

        if (idx + 1) % 500 == 0:
            print(f"  [{label}] {idx+1}/{len(rows)} processed ({time.time()-t0:.1f}s)")

    elapsed = time.time() - t0
    print(f"  [{label}] done: {len(results)} predictions in {elapsed:.1f}s — skip: {dict(skip)}")
    return results


# ─── ROI calculation utilities ────────────────────────────────────────────────

def _roi_for_preds(preds: List[dict], threshold: float, stat_filter: str = None,
                   shrinkage_slopes: dict = None) -> dict:
    """Compute ROI for a list of prediction dicts at a given threshold.

    shrinkage_slopes: {stat: slope} — multiply raw edge by slope before threshold test.
    """
    profit_per_win = _odds_to_decimal_profit(-110)
    bets = wins = 0
    fold_wins = defaultdict(int)
    fold_bets = defaultdict(int)

    for p in preds:
        if stat_filter and p["stat"] != stat_filter:
            continue
        edge = p["edge"]
        if shrinkage_slopes:
            slope = shrinkage_slopes.get(p["stat"], 1.0)
            edge = edge * slope

        rec = _recommend(edge, threshold)
        if rec == "NO_BET":
            continue

        actual_result = _classify_result(p["actual"], p["line"])
        if actual_result == "PUSH":
            continue

        bets += 1
        fold_bets[p["fold"]] += 1
        if rec == actual_result:
            wins += 1
            fold_wins[p["fold"]] += 1

    if bets == 0:
        return {"n_bets": 0, "roi_pct": 0.0, "hit_rate": 0.0, "folds_positive": 0}

    hit = wins / bets
    roi_units = wins * profit_per_win - (bets - wins) * 1.0
    roi_pct = roi_units / bets * 100.0

    # folds_positive = number of folds with roi > 0
    folds_positive = 0
    for f in range(4):
        fb = fold_bets.get(f, 0)
        fw = fold_wins.get(f, 0)
        if fb > 0:
            fold_roi = (fw * profit_per_win - (fb - fw) * 1.0) / fb * 100
            if fold_roi > 0:
                folds_positive += 1

    return {
        "n_bets": bets, "roi_pct": roi_pct, "hit_rate": hit * 100,
        "folds_positive": folds_positive,
    }


def _score(roi_pct: float, folds_positive: int, total_folds: int = 4) -> float:
    """Optimisation score: mean_roi * (folds_positive / total_folds)."""
    if folds_positive == 0:
        return 0.0
    return roi_pct * (folds_positive / total_folds)


# ─── step 3: edge shrinkage fit ───────────────────────────────────────────────

def fit_shrinkage_slopes(fit_preds: List[dict]) -> dict:
    """Fit slope of actual_margin ~ predicted_edge via OLS per stat.

    actual_margin = actual - line (positive = player went over)
    predicted_edge = pred - line

    We regress actual_margin ON predicted_edge (no intercept) to get shrinkage factor.
    A slope < 1 means the model over-predicts edge; slope > 1 means under-predicts.
    In practice for a well-calibrated model slope ≈ 1.
    """
    slopes = {}
    for stat in STATS:
        stat_preds = [p for p in fit_preds if p["stat"] == stat and abs(p["edge"]) > 1e-9]
        if len(stat_preds) < 20:
            slopes[stat] = 1.0
            print(f"    {stat.upper()}: n={len(stat_preds)} < 20, slope=1.0 (default)")
            continue

        edges = np.array([p["edge"] for p in stat_preds], dtype=float)
        margins = np.array([p["actual"] - p["line"] for p in stat_preds], dtype=float)

        # OLS: slope = cov(edge, margin) / var(edge) — no intercept
        slope = float(np.dot(edges, margins) / np.dot(edges, edges))
        # Clip: slope in [0.2, 2.0] to prevent degenerate calibration
        slope = float(np.clip(slope, 0.2, 2.0))
        slopes[stat] = slope
        corr = float(np.corrcoef(edges, margins)[0, 1]) if len(edges) > 2 else 0.0
        print(f"    {stat.upper()}: n={len(stat_preds)} slope={slope:.4f} corr={corr:.4f}")

    return slopes


# ─── step 4: threshold sweep ─────────────────────────────────────────────────

def run_threshold_sweep(eval_preds: List[dict]) -> dict:
    """For each (stat, threshold), compute metrics on 2025-26 eval."""
    results = {}
    for stat in STATS:
        results[stat] = {}
        stat_preds = [p for p in eval_preds if p["stat"] == stat]
        if not stat_preds:
            continue
        for thr in THRESHOLD_CANDIDATES:
            m = _roi_for_preds(stat_preds, thr, stat_filter=stat)
            m["score"] = _score(m["roi_pct"], m["folds_positive"])
            results[stat][thr] = m
    return results


def _select_optimal_threshold(sweep: dict, stat: str) -> Tuple[float, dict]:
    """Pick threshold maximising score, subject to n_bets >= 30."""
    best_thr = CURRENT_THRESHOLDS.get(stat, 0.5)
    best_score = -999.0
    best_m = {}
    for thr, m in sweep.get(stat, {}).items():
        if m["n_bets"] < MIN_BETS_FOR_RECOMMENDATION:
            continue
        s = _score(m["roi_pct"], m["folds_positive"])
        if s > best_score:
            best_score = s
            best_thr = thr
            best_m = m
    return best_thr, best_m


# ─── step 5: combined test ────────────────────────────────────────────────────

def run_combined_test(eval_preds: List[dict],
                      optimal_thresholds: dict,
                      shrinkage_slopes: dict) -> dict:
    """Apply BOTH shrinkage AND optimal thresholds. Return pooled metrics."""
    profit_per_win = _odds_to_decimal_profit(-110)
    total_bets = total_wins = 0

    per_stat_combined = {}
    for stat in STATS:
        thr = optimal_thresholds.get(stat, CURRENT_THRESHOLDS.get(stat, 0.5))
        stat_preds = [p for p in eval_preds if p["stat"] == stat]
        m = _roi_for_preds(stat_preds, thr, stat_filter=stat,
                           shrinkage_slopes=shrinkage_slopes)
        per_stat_combined[stat] = m
        total_bets += m["n_bets"]
        if m["n_bets"] > 0:
            wins_approx = round(m["hit_rate"] / 100.0 * m["n_bets"])
            total_wins += wins_approx

    if total_bets == 0:
        return {"n_bets": 0, "roi_pct": 0.0}

    roi_units = total_wins * profit_per_win - (total_bets - total_wins) * 1.0
    roi_pct = roi_units / total_bets * 100.0
    return {"n_bets": total_bets, "roi_pct": roi_pct, "per_stat": per_stat_combined}


# ─── baseline metrics from holdout_baseline.json ─────────────────────────────

def load_baseline() -> Tuple[float, int]:
    """Return (baseline_roi_pct, baseline_n_bets) from holdout JSON."""
    if not os.path.exists(HOLDOUT_JSON):
        return 19.37, 1337  # hard-coded fallback
    with open(HOLDOUT_JSON, encoding="utf-8") as fh:
        j = json.load(fh)
    g = j.get("__global__", {})
    total_bets = sum(v.get("n_bets", 0) for v in g.values())
    # Weighted average ROI
    weighted_roi = sum(
        v.get("roi_pct", 0.0) * v.get("n_bets", 0)
        for v in g.values()
    )
    avg_roi = weighted_roi / total_bets if total_bets else 0.0
    return avg_roi, total_bets


# ─── aggregate ROI (pooled, current thresholds, no shrinkage) ────────────────

def eval_baseline_on_preds(eval_preds: List[dict]) -> Tuple[float, int]:
    """Measure the baseline (current thresholds, no shrinkage) on our eval preds."""
    profit_per_win = _odds_to_decimal_profit(-110)
    total_bets = total_wins = 0
    for stat in STATS:
        thr = CURRENT_THRESHOLDS.get(stat, 0.5)
        stat_preds = [p for p in eval_preds if p["stat"] == stat]
        m = _roi_for_preds(stat_preds, thr, stat_filter=stat)
        total_bets += m["n_bets"]
        if m["n_bets"] > 0:
            wins_approx = round(m["hit_rate"] / 100.0 * m["n_bets"])
            total_wins += wins_approx
    if total_bets == 0:
        return 0.0, 0
    roi_units = total_wins * profit_per_win - (total_bets - total_wins) * 1.0
    return roi_units / total_bets * 100.0, total_bets


# ─── main ─────────────────────────────────────────────────────────────────────

def main():
    print("\n" + "=" * 70)
    print("  ITER-25: edge-shrinkage + threshold sweep on Iter-22 model")
    print("=" * 70)

    # ── step 1: build combined eval CSV ──────────────────────────────────────
    print("\n  [step 1] building combined 2025-26 eval CSV...")
    n_eval_rows = build_eval_csv()

    # ── step 2: generate predictions ─────────────────────────────────────────
    print("\n  [step 2] generating predictions for 2025-26 eval...")
    eval_rows = _load_rows(EVAL_COMBINED, stats_filter=set(STATS))
    print(f"    loaded {len(eval_rows)} rows for stats in {STATS}")
    eval_preds = build_predictions_cache(eval_rows, "eval-2025-26")

    if not eval_preds:
        print("  [ABORT] no predictions generated — exiting")
        return

    # ── step 2b: generate predictions for shrinkage FIT set (2024-25 RS) ────
    print("\n  [step 2b] generating predictions for shrinkage fit set (2024-25 RS)...")
    fit_rows = _load_rows(RS_2024_25, stats_filter=set(STATS))
    print(f"    loaded {len(fit_rows)} rows from 2024-25 RS")
    fit_preds = build_predictions_cache(fit_rows, "fit-2024-25")

    # ── step 3: fit shrinkage slopes ──────────────────────────────────────────
    print("\n  [step 3] fitting edge-shrinkage slopes on 2024-25 RS data...")
    slopes = fit_shrinkage_slopes(fit_preds)
    print(f"    slopes: {slopes}")

    # ── step 3b: measure shrinkage-only ROI on eval ───────────────────────────
    print("\n  [step 3b] measuring shrinkage-only ROI on 2025-26 eval...")
    profit_per_win = _odds_to_decimal_profit(-110)
    shrink_bets = shrink_wins = 0
    for stat in STATS:
        thr = CURRENT_THRESHOLDS.get(stat, 0.5)
        stat_preds = [p for p in eval_preds if p["stat"] == stat]
        m = _roi_for_preds(stat_preds, thr, stat_filter=stat,
                           shrinkage_slopes=slopes)
        shrink_bets += m["n_bets"]
        if m["n_bets"] > 0:
            w = round(m["hit_rate"] / 100.0 * m["n_bets"])
            shrink_wins += w
    shrink_roi = 0.0
    if shrink_bets > 0:
        u = shrink_wins * profit_per_win - (shrink_bets - shrink_wins) * 1.0
        shrink_roi = u / shrink_bets * 100.0

    # ── step 4: threshold sweep ───────────────────────────────────────────────
    print("\n  [step 4] running threshold sweep on 2025-26 eval...")
    sweep = run_threshold_sweep(eval_preds)

    # Print sweep table
    print("\n  Threshold sweep results (2025-26 eval):")
    print(f"  {'stat':4s} | {'thr':4s} | {'n_bets':>6s} | {'roi%':>7s} | {'hit%':>6s} | {'folds+':>6s} | {'score':>7s}")
    print("  " + "-" * 65)
    for stat in STATS:
        for thr in THRESHOLD_CANDIDATES:
            m = sweep.get(stat, {}).get(thr, {})
            if not m:
                continue
            print(f"  {stat.upper():4s} | {thr:4.1f} | {m['n_bets']:6d} | "
                  f"{m['roi_pct']:+7.2f}% | {m['hit_rate']:5.1f}% | "
                  f"{m['folds_positive']:6d} | {m['score']:+7.2f}")
        print()

    # Select optimal thresholds
    optimal_thresholds = {}
    print("\n  Recommended thresholds (score = roi * folds_positive/4, n_bets >= 30):")
    print(f"  {'stat':4s} | {'curr':>5s} | {'new':>5s} | {'n_bets':>6s} | {'roi%':>7s} | {'folds+':>6s} | {'score':>7s}")
    print("  " + "-" * 65)
    thresholds_changed = False
    for stat in STATS:
        new_thr, best_m = _select_optimal_threshold(sweep, stat)
        curr_thr = CURRENT_THRESHOLDS.get(stat, 0.5)
        optimal_thresholds[stat] = new_thr
        changed = "*" if abs(new_thr - curr_thr) > 0.001 else " "
        if abs(new_thr - curr_thr) > 0.001:
            thresholds_changed = True
        n = best_m.get("n_bets", 0)
        r = best_m.get("roi_pct", 0.0)
        fp = best_m.get("folds_positive", 0)
        s = best_m.get("score", 0.0)
        print(f"  {stat.upper():4s}{changed}| {curr_thr:5.2f} | {new_thr:5.2f} | {n:6d} | {r:+7.2f}% | {fp:6d} | {s:+7.2f}")

    # ── step 4b: thresholds-only ROI ─────────────────────────────────────────
    thresh_bets = thresh_wins = 0
    for stat in STATS:
        thr = optimal_thresholds.get(stat, 0.5)
        stat_preds = [p for p in eval_preds if p["stat"] == stat]
        m = _roi_for_preds(stat_preds, thr, stat_filter=stat)
        thresh_bets += m["n_bets"]
        if m["n_bets"] > 0:
            w = round(m["hit_rate"] / 100.0 * m["n_bets"])
            thresh_wins += w
    thresh_roi = 0.0
    if thresh_bets > 0:
        u = thresh_wins * profit_per_win - (thresh_bets - thresh_wins) * 1.0
        thresh_roi = u / thresh_bets * 100.0

    # ── step 5: combined test ─────────────────────────────────────────────────
    print("\n  [step 5] combined (shrinkage + optimal thresholds)...")
    combined = run_combined_test(eval_preds, optimal_thresholds, slopes)

    # ── baseline comparison ───────────────────────────────────────────────────
    print("\n  [baseline] measuring current-config on eval predictions...")
    baseline_roi_live, baseline_bets_live = eval_baseline_on_preds(eval_preds)
    baseline_roi_json, baseline_bets_json = load_baseline()

    combined_roi = combined["roi_pct"]
    combined_bets = combined["n_bets"]

    print("\n" + "=" * 70)
    print("  SUMMARY: 2025-26 OOS ROI comparison")
    print("=" * 70)
    print(f"  Holdout JSON baseline (Iter-22 weights, current thresholds): "
          f"{baseline_roi_json:+.2f}% on {baseline_bets_json} bets")
    print(f"  Live baseline (current config, eval set): "
          f"{baseline_roi_live:+.2f}% on {baseline_bets_live} bets")
    print(f"  Shrinkage-only (current thresholds):       "
          f"{shrink_roi:+.2f}% on {shrink_bets} bets")
    print(f"  Thresholds-only (no shrinkage):            "
          f"{thresh_roi:+.2f}% on {thresh_bets} bets")
    print(f"  Combined (shrinkage + opt thresholds):     "
          f"{combined_roi:+.2f}% on {combined_bets} bets")

    # Select best approach
    best_approach = "none"
    best_roi = baseline_roi_live
    if thresh_roi - baseline_roi_live >= SHIP_THRESHOLD_PP and thresh_bets >= 100:
        best_approach = "thresholds"
        best_roi = thresh_roi
    if combined_roi - baseline_roi_live >= SHIP_THRESHOLD_PP and combined_bets >= 100:
        if combined_roi > best_roi:
            best_approach = "combined"
            best_roi = combined_roi
    # Shrinkage standalone: only if it beats combined
    if (shrink_roi - baseline_roi_live >= SHIP_THRESHOLD_PP and
            shrink_bets >= 100 and shrink_roi > best_roi):
        best_approach = "shrinkage"
        best_roi = shrink_roi

    lift = best_roi - baseline_roi_live
    print(f"\n  Best approach: {best_approach.upper()} | lift vs live baseline: {lift:+.2f}pp")
    decision = "SHIP" if best_approach != "none" and lift >= SHIP_THRESHOLD_PP else "REVERT"
    print(f"  DECISION: {decision}")

    if decision == "SHIP":
        # Write bet_thresholds.py
        _ship_thresholds(optimal_thresholds, best_approach, lift, baseline_roi_live)

        # Write edge_shrinkage.py if shrinkage is part of the win
        if best_approach in ("combined", "shrinkage"):
            _ship_shrinkage(slopes, lift)

        # Update holdout_baseline.json
        _update_holdout_baseline(
            eval_preds, optimal_thresholds,
            slopes if best_approach in ("combined", "shrinkage") else {},
            best_roi, combined_bets, best_approach,
        )

        print("\n  Files updated:")
        print(f"    {THRESHOLDS_PY}")
        if best_approach in ("combined", "shrinkage"):
            print(f"    {SHRINKAGE_PY}")
        print(f"    {HOLDOUT_JSON}")
    else:
        print("\n  No files changed — REVERT (lift below +1pp or insufficient volume)")

    return {
        "decision": decision,
        "best_approach": best_approach,
        "baseline_roi": baseline_roi_live,
        "best_roi": best_roi,
        "lift_pp": lift,
        "slopes": slopes,
        "optimal_thresholds": optimal_thresholds,
        "shrink_roi": shrink_roi,
        "thresh_roi": thresh_roi,
        "combined_roi": combined_roi,
    }


def _ship_thresholds(optimal: dict, approach: str, lift: float, baseline_roi: float):
    """Overwrite src/prediction/bet_thresholds.py with new optimal thresholds."""
    lines = [
        '"""src/prediction/bet_thresholds.py — central per-stat edge-threshold config.',
        '',
        'Iter-25 recalibration on Iter-22 model (commit 5fb964f1).',
        f'  Approach: {approach}  |  lift vs baseline: {lift:+.2f}pp',
        f'  Baseline 2025-26 ROI: {baseline_roi:+.2f}%',
        '',
        '  Iter-15 thresholds (prior values):',
        '    STL: 0.5 → 0.10  (Iter 14a sweep)',
        '    BLK: 0.5 → 0.40  (Iter 14a sweep)',
        '',
        'Usage:',
        '    from src.prediction.bet_thresholds import edge_threshold_for',
        '',
        '    thr = edge_threshold_for("stl")',
        '    thr = edge_threshold_for("pts")',
        '    thr = edge_threshold_for("unknown")  # 0.5 (safe fallback)',
        '"""',
        'from __future__ import annotations',
        '',
        '_STAT_THRESHOLDS: dict[str, float] = {',
    ]
    for stat in STATS:
        v = optimal.get(stat, CURRENT_THRESHOLDS.get(stat, 0.5))
        lines.append(f'    "{stat}":  {v},')
    lines += [
        '}',
        '',
        '_DEFAULT_THRESHOLD: float = 0.5',
        '',
        '',
        'def edge_threshold_for(stat: str) -> float:',
        '    """Return the edge threshold for *stat* (case-insensitive).',
        '',
        '    Falls back to ``_DEFAULT_THRESHOLD`` for unknown stat strings so',
        '    existing callers that don\'t specify a stat remain unaffected.',
        '    """',
        '    return _STAT_THRESHOLDS.get(stat.lower(), _DEFAULT_THRESHOLD)',
        '',
    ]
    with open(THRESHOLDS_PY, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
    print(f"  [ship] updated {THRESHOLDS_PY}")


def _ship_shrinkage(slopes: dict, lift: float):
    """Write src/prediction/edge_shrinkage.py."""
    lines = [
        '"""src/prediction/edge_shrinkage.py — per-stat edge shrinkage calibration.',
        '',
        'Iter-25: fit slope of actual_margin ~ predicted_edge (OLS, no intercept)',
        'on 2024-25 RS data. Apply to shrink over-confident edges before threshold.',
        '',
        f'Lift vs baseline: {lift:+.2f}pp on 2025-26 OOS eval.',
        '',
        'Usage:',
        '    from src.prediction.edge_shrinkage import shrink_edge',
        '    adjusted_edge = shrink_edge("pts", raw_edge)',
        '"""',
        'from __future__ import annotations',
        '',
        '_SHRINKAGE_SLOPES: dict[str, float] = {',
    ]
    for stat, slope in slopes.items():
        lines.append(f'    "{stat}":  {slope:.6f},')
    lines += [
        '}',
        '',
        '_DEFAULT_SLOPE: float = 1.0',
        '',
        '',
        'def shrink_edge(stat: str, raw_edge: float) -> float:',
        '    """Apply per-stat shrinkage slope to the raw model edge.',
        '',
        '    A slope < 1 shrinks the edge (model over-confident),',
        '    slope > 1 expands it (model under-confident).',
        '    """',
        '    slope = _SHRINKAGE_SLOPES.get(stat.lower(), _DEFAULT_SLOPE)',
        '    return raw_edge * slope',
        '',
    ]
    with open(SHRINKAGE_PY, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
    print(f"  [ship] wrote {SHRINKAGE_PY}")


def _update_holdout_baseline(eval_preds, optimal_thresholds, shrinkage_slopes,
                              best_roi, best_bets, approach):
    """Update data/cache/holdout_baseline.json with per-stat combined metrics."""
    existing = {}
    if os.path.exists(HOLDOUT_JSON):
        with open(HOLDOUT_JSON, encoding="utf-8") as fh:
            existing = json.load(fh)

    profit_per_win = _odds_to_decimal_profit(-110)
    new_global = {}
    for stat in STATS:
        thr = optimal_thresholds.get(stat, CURRENT_THRESHOLDS.get(stat, 0.5))
        stat_preds = [p for p in eval_preds if p["stat"] == stat]
        m = _roi_for_preds(stat_preds, thr, stat_filter=stat,
                           shrinkage_slopes=shrinkage_slopes if shrinkage_slopes else None)
        if m["n_bets"] == 0:
            continue
        w = round(m["hit_rate"] / 100.0 * m["n_bets"])
        roi_units = w * profit_per_win - (m["n_bets"] - w) * 1.0
        new_global[stat] = {
            "roi_pct": round(m["roi_pct"], 4),
            "hit_rate": round(m["hit_rate"], 4),
            "n_bets": m["n_bets"],
            "roi_units": round(roi_units, 4),
            "threshold": thr,
        }

    existing["__global__"] = new_global
    existing["__updated_at__"] = datetime.utcnow().isoformat() + "+00:00"
    existing["__iter25__"] = {
        "approach": approach,
        "best_roi": round(best_roi, 4),
        "best_bets": best_bets,
        "optimal_thresholds": optimal_thresholds,
        "shrinkage_slopes": shrinkage_slopes,
        "generated_at": datetime.utcnow().isoformat() + "+00:00",
    }

    with open(HOLDOUT_JSON, "w", encoding="utf-8") as fh:
        json.dump(existing, fh, indent=2)
    print(f"  [ship] updated {HOLDOUT_JSON}")


if __name__ == "__main__":
    main()
