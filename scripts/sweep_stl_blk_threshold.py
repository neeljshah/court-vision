"""sweep_stl_blk_threshold.py -- Iter 14a: edge-threshold sweep for STL and BLK.

STL/BLK have STRONG ROI when the model fires (+55%, +90%) but at the default
0.5-unit threshold the model fires on <5 bets per fold, giving noisy / INCONCLUSIVE
results across the 12 RS folds.

This script sweeps the edge threshold across [0.5, 0.4, 0.3, 0.25, 0.2, 0.15, 0.1]
for each stat and reports:
  - total_bets (across all 12 folds)
  - mean_roi, std_roi
  - folds_positive (roi > 0)
  - folds_with_5plus_bets
  - score = mean_roi * folds_positive / 12  (subject to total_bets >= 30)

Outputs:
  - Console sweep table
  - vault/Models/STL_BLK_Threshold_Sweep_<date>.md
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

from scripts.backtest_closing_lines_2024_playoffs import (
    _build_asof_row,
    _resolve_player_id,
    _season_for_date,
    _classify_result,
    _recommend,
    _odds_to_decimal_profit,
)
from src.prediction.prop_quantiles import _inverse

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

RS_CSV = os.path.join(
    PROJECT_DIR, "data", "external", "historical_lines",
    "regular_season_2024_25_oddsapi.csv",
)
GAMELOG_DIR = os.path.join(PROJECT_DIR, "data", "nba")
OOS_DIR = os.path.join(PROJECT_DIR, "data", "models", "oos_pre_playoffs")
VAULT_MODELS_DIR = os.path.join(PROJECT_DIR, "vault", "Models")

THRESHOLDS = [0.5, 0.4, 0.3, 0.25, 0.2, 0.15, 0.1]
STATS = ["stl", "blk"]

# ---------------------------------------------------------------------------
# Model loading (XGB q50 — both STL and BLK are XGB q50)
# ---------------------------------------------------------------------------

_MODEL_CACHE: Dict[str, object] = {}
_META_CACHE: Optional[Dict] = None
_FEAT_COL_CACHE: Dict[str, List[str]] = {}


def _meta() -> Dict:
    global _META_CACHE
    if _META_CACHE is None:
        meta_path = os.path.join(OOS_DIR, "_meta.json")
        _META_CACHE = json.load(open(meta_path, encoding="utf-8")) if os.path.exists(meta_path) else {}
    return _META_CACHE


def _load_model(stat: str):
    if stat in _MODEL_CACHE:
        return _MODEL_CACHE[stat]
    import xgboost as xgb
    path = os.path.join(OOS_DIR, f"quantile_pergame_{stat}_q50.json")
    if not os.path.exists(path):
        raise FileNotFoundError(f"OOS artifact missing: {path}")
    m = xgb.XGBRegressor()
    m.load_model(path)
    _MODEL_CACHE[stat] = m
    print(f"  Loaded {stat.upper()} model: {path}")
    return m


def _feature_columns(stat: str, model) -> List[str]:
    if stat in _FEAT_COL_CACHE:
        return _FEAT_COL_CACHE[stat]
    # Try artifact meta first, then model introspection, then current schema
    from src.prediction.prop_pergame import feature_columns
    current = feature_columns()

    n_expected = getattr(model, "n_features_in_", None) or getattr(model, "n_features_", None)
    if n_expected is not None and n_expected != len(current):
        saved = _meta().get("stats", {}).get(stat, {}).get("feature_columns", [])
        if saved and len(saved) == n_expected:
            _FEAT_COL_CACHE[stat] = saved
            return saved
        _FEAT_COL_CACHE[stat] = current[:n_expected]
        return current[:n_expected]

    _FEAT_COL_CACHE[stat] = current
    return current


def _predict(stat: str, model, feat_row: Dict) -> float:
    cols = _feature_columns(stat, model)
    X = np.array([[float(feat_row.get(c, 0.0) or 0.0) for c in cols]], dtype=float)
    pred_t = float(model.predict(X)[0])
    pred = float(_inverse(stat, np.array([pred_t]))[0])
    return max(0.0, pred)


# ---------------------------------------------------------------------------
# Fold runner — returns raw (pred, line, actual) tuples for post-hoc sweep
# ---------------------------------------------------------------------------

def _collect_fold_predictions(
    stat: str,
    fold_date: str,
    all_csv_rows: List[Dict],
    name2pid: Dict,
    row_cache: Dict,
    model,
) -> List[Tuple[float, float, float]]:
    """Return list of (pred, line, actual) for all valid rows on this fold date."""
    window_rows = [
        r for r in all_csv_rows
        if r.get("stat", "").lower() == stat and r["date"] == fold_date
    ]
    results: List[Tuple[float, float, float]] = []
    skip = defaultdict(int)

    for r in window_rows:
        try:
            line = float(r["closing_line"])
            actual = float(r["actual_value"])
            d = datetime.fromisoformat(r["date"])
        except Exception:
            skip["bad_row"] += 1
            continue
        player = r["player"]
        pid = name2pid.get(player)
        if pid is None:
            pid = _resolve_player_id(player)
            name2pid[player] = pid
        if pid is None:
            skip["no_pid"] += 1
            continue
        season = _season_for_date(d)
        is_home = r["venue"] == "home"
        key = (pid, r["date"], r["venue"], r["opp"])
        if key not in row_cache:
            row_cache[key] = _build_asof_row(
                pid, r["opp"], d, season, is_home=is_home, rest_days=2.0,
                gamelog_dir=GAMELOG_DIR,
            )
        feat = row_cache[key]
        if feat is None:
            skip["no_history"] += 1
            continue
        try:
            pred = _predict(stat, model, feat)
        except Exception as e:
            skip[f"err:{type(e).__name__}"] += 1
            continue
        results.append((pred, line, actual))

    if skip:
        pass  # silent — fold-level skips are expected
    return results


# ---------------------------------------------------------------------------
# Threshold evaluation for a set of fold predictions
# ---------------------------------------------------------------------------

PROFIT_AT_110 = _odds_to_decimal_profit(-110)  # ~0.9091


def _eval_threshold(
    fold_preds: List[Tuple[float, float, float]],
    threshold: float,
) -> Dict:
    """Given (pred, line, actual) tuples, evaluate at the given threshold."""
    n_bets = wins = losses = 0
    for pred, line, actual in fold_preds:
        edge = pred - line
        rec = _recommend(edge, threshold)
        if rec == "NO_BET":
            continue
        result = _classify_result(actual, line)
        if result == "PUSH":
            continue  # skip pushes
        n_bets += 1
        if rec == result:
            wins += 1
        else:
            losses += 1
    roi_units = wins * PROFIT_AT_110 - losses * 1.0
    roi_pct = (roi_units / n_bets * 100.0) if n_bets else None
    hit_rate = (wins / n_bets) if n_bets else None
    return {
        "n_bets": n_bets,
        "wins": wins,
        "losses": losses,
        "roi_pct": roi_pct,
        "hit_rate": hit_rate,
    }


# ---------------------------------------------------------------------------
# Main sweep
# ---------------------------------------------------------------------------

def run_sweep() -> Dict[str, List[Dict]]:
    """Run the full threshold sweep and return results keyed by stat."""
    print("\n" + "=" * 70)
    print("  Iter 14a — STL/BLK Edge-Threshold Sweep")
    print(f"  Thresholds: {THRESHOLDS}")
    print("=" * 70)

    if not os.path.exists(RS_CSV):
        raise SystemExit(f"RS CSV not found: {RS_CSV}")

    with open(RS_CSV, encoding="utf-8") as fh:
        all_rows = list(csv.DictReader(fh))
    print(f"  RS CSV: {len(all_rows)} rows")

    unique_dates = sorted(set(r["date"] for r in all_rows))
    print(f"  Folds: {len(unique_dates)}  ({unique_dates[0]} … {unique_dates[-1]})")

    name2pid: Dict[str, Optional[int]] = {}
    row_cache: Dict = {}

    sweep_results: Dict[str, List[Dict]] = {}

    for stat in STATS:
        print(f"\n{'='*70}")
        print(f"  STAT: {stat.upper()}  (XGB-q50)")
        print(f"{'='*70}")

        try:
            model = _load_model(stat)
        except FileNotFoundError as e:
            print(f"  [SKIP] {e}")
            sweep_results[stat] = []
            continue

        # --- collect all fold predictions ONCE ---
        fold_preds_all: Dict[str, List[Tuple[float, float, float]]] = {}
        for fold_date in unique_dates:
            t0 = time.time()
            preds = _collect_fold_predictions(
                stat, fold_date, all_rows, name2pid, row_cache, model
            )
            elapsed = time.time() - t0
            fold_preds_all[fold_date] = preds
            # Quick check at default threshold to show status
            chk = _eval_threshold(preds, 0.5)
            print(
                f"  {fold_date}  n_preds={len(preds):>3}  "
                f"n_bets@0.5={chk['n_bets']:>3}  ({elapsed:.1f}s)"
            )

        print(f"\n  {'thresh':>8}  {'n_bets':>8}  {'mean_roi':>10}  "
              f"{'std_roi':>9}  {'folds_pos':>11}  {'folds_5+':>10}  {'score':>9}")
        print(f"  {'-'*80}")

        stat_rows: List[Dict] = []
        for thr in THRESHOLDS:
            fold_rois: List[float] = []
            fold_bets: List[int] = []
            total_bets = 0
            for fd in unique_dates:
                ev = _eval_threshold(fold_preds_all[fd], thr)
                fold_bets.append(ev["n_bets"])
                total_bets += ev["n_bets"]
                if ev["roi_pct"] is not None and ev["n_bets"] >= 1:
                    fold_rois.append(ev["roi_pct"])

            n_folds_pos = sum(1 for r in fold_rois if r > 0.0)
            n_folds_5plus = sum(1 for b in fold_bets if b >= 5)
            mean_roi = float(np.mean(fold_rois)) if fold_rois else float("nan")
            std_roi = float(np.std(fold_rois)) if len(fold_rois) > 1 else float("nan")
            # score = mean_roi * (folds_pos / 12), meaningful only if total_bets >= 30
            score = (mean_roi * n_folds_pos / 12.0) if total_bets >= 30 else float("nan")

            row = {
                "stat": stat,
                "threshold": thr,
                "total_bets": total_bets,
                "mean_roi": mean_roi,
                "std_roi": std_roi,
                "folds_positive": n_folds_pos,
                "folds_total": len(fold_rois),  # folds with >= 1 bet
                "folds_with_5plus": n_folds_5plus,
                "score": score,
                "fold_bets": fold_bets,
                "fold_rois": fold_rois,
            }
            stat_rows.append(row)

            sig_flag = "" if total_bets >= 30 else " [insig]"
            mean_str = f"{mean_roi:+.1f}%" if not np.isnan(mean_roi) else "   N/A"
            std_str = f"{std_roi:.1f}%" if not np.isnan(std_roi) else "  N/A"
            score_str = f"{score:+.1f}" if not np.isnan(score) else "    N/A"
            print(
                f"  {thr:>8.2f}  {total_bets:>8}  {mean_str:>10}  "
                f"{std_str:>9}  {n_folds_pos:>4}/{len(fold_rois):<6}  "
                f"{n_folds_5plus:>10}  {score_str:>9}{sig_flag}"
            )

        sweep_results[stat] = stat_rows

    return sweep_results


# ---------------------------------------------------------------------------
# Optimal threshold selection
# ---------------------------------------------------------------------------

def _pick_optimal(stat_rows: List[Dict]) -> Optional[Dict]:
    """Select threshold that maximises score subject to total_bets >= 30."""
    candidates = [r for r in stat_rows if r["total_bets"] >= 30 and not np.isnan(r["score"])]
    if not candidates:
        return None
    return max(candidates, key=lambda r: r["score"])


# ---------------------------------------------------------------------------
# Per-fold breakdown at a given threshold
# ---------------------------------------------------------------------------

def _per_fold_breakdown(
    stat: str,
    threshold: float,
    all_rows: List[Dict],
    unique_dates: List[str],
    name2pid: Dict,
    row_cache: Dict,
    model,
) -> List[Dict]:
    rows_out = []
    for fd in unique_dates:
        preds = _collect_fold_predictions(stat, fd, all_rows, name2pid, row_cache, model)
        ev = _eval_threshold(preds, threshold)
        rows_out.append({
            "date": fd,
            "n_bets": ev["n_bets"],
            "wins": ev["wins"],
            "losses": ev["losses"],
            "hit_rate": ev["hit_rate"],
            "roi_pct": ev["roi_pct"],
        })
    return rows_out


# ---------------------------------------------------------------------------
# Markdown report
# ---------------------------------------------------------------------------

def _write_report(
    sweep_results: Dict[str, List[Dict]],
    recommendations: Dict[str, Optional[Dict]],
    fold_breakdowns: Dict[str, List[Dict]],
    unique_dates: List[str],
) -> str:
    today = datetime.now().strftime("%Y-%m-%d")
    report_path = os.path.join(VAULT_MODELS_DIR, f"STL_BLK_Threshold_Sweep_{today}.md")
    os.makedirs(VAULT_MODELS_DIR, exist_ok=True)

    lines: List[str] = [
        f"# STL/BLK Edge-Threshold Sweep — {today}",
        "",
        "**Goal:** find the edge threshold for STL and BLK that captures more bets "
        "while maintaining positive ROI across the 12 RS folds.  "
        "Current production threshold: **0.5 units**.  "
        "Constraint: total_bets >= 30 for statistical significance.",
        "",
        f"**Data:** `regular_season_2024_25_oddsapi.csv` ({len(unique_dates)} game-night folds)",
        "**Models:** OOS pre-playoffs XGB-q50 artifacts",
        "**Folds:** " + ", ".join(unique_dates),
        "",
        "---",
        "",
    ]

    for stat in STATS:
        stat_rows = sweep_results.get(stat, [])
        rec = recommendations.get(stat)
        lines += [
            f"## {stat.upper()} Threshold Sweep",
            "",
            "| threshold | total_bets | mean_roi | std_roi | folds_pos | folds_5+ | score |",
            "|----------:|-----------:|---------:|--------:|----------:|---------:|------:|",
        ]
        for row in stat_rows:
            sig = "" if row["total_bets"] >= 30 else " †"
            mean_str = f"{row['mean_roi']:+.1f}%" if not np.isnan(row["mean_roi"]) else "N/A"
            std_str = f"{row['std_roi']:.1f}%" if not np.isnan(row["std_roi"]) else "N/A"
            score_str = f"{row['score']:+.2f}" if not np.isnan(row["score"]) else "N/A"
            folds_pos_str = f"{row['folds_positive']}/{row['folds_total']}"
            lines.append(
                f"| {row['threshold']:.2f}{sig} "
                f"| {row['total_bets']} "
                f"| {mean_str} "
                f"| {std_str} "
                f"| {folds_pos_str} "
                f"| {row['folds_with_5plus']} "
                f"| {score_str} |"
            )
        lines += [
            "",
            "_† total_bets < 30 (statistically insignificant — excluded from optimal selection)_",
            "",
        ]

        if rec is not None:
            lines += [
                f"### Recommended threshold: **{rec['threshold']:.2f}**",
                "",
                f"- total_bets: **{rec['total_bets']}** (vs {stat_rows[0]['total_bets']} at 0.5)",
                f"- mean_roi: **{rec['mean_roi']:+.1f}%**",
                f"- folds_positive: **{rec['folds_positive']}/{rec['folds_total']}**",
                f"- folds_with_5+_bets: **{rec['folds_with_5plus']}**",
                f"- score (mean_roi × pos_folds/12): **{rec['score']:+.2f}**",
                "",
            ]
        else:
            lines += [
                f"### No statistically significant threshold found (total_bets < 30 at all levels)",
                "",
            ]

        # Per-fold breakdown at recommended threshold
        fb = fold_breakdowns.get(stat, [])
        if fb and rec is not None:
            lines += [
                f"### Per-fold breakdown at threshold={rec['threshold']:.2f}",
                "",
                "| date | n_bets | wins | losses | hit_rate | roi_pct |",
                "|------|-------:|-----:|-------:|---------:|--------:|",
            ]
            for fr in fb:
                hit_str = f"{fr['hit_rate']*100:.1f}%" if fr["hit_rate"] is not None else "N/A"
                roi_str = f"{fr['roi_pct']:+.1f}%" if fr["roi_pct"] is not None else "N/A"
                lines.append(
                    f"| {fr['date']} | {fr['n_bets']} | {fr['wins']} | "
                    f"{fr['losses']} | {hit_str} | {roi_str} |"
                )
            lines.append("")

        lines.append("---")
        lines.append("")

    # Summary recommendations
    lines += ["## Summary & Recommendations", ""]
    for stat in STATS:
        rec = recommendations.get(stat)
        base_row = next((r for r in sweep_results.get(stat, []) if r["threshold"] == 0.5), None)
        if rec is not None and base_row is not None:
            uplift = rec["total_bets"] - base_row["total_bets"]
            lines.append(
                f"- **{stat.upper()}**: Lower threshold from 0.5 → **{rec['threshold']:.2f}**.  "
                f"Bets: {base_row['total_bets']} → {rec['total_bets']} (+{uplift} total, "
                f"~{uplift/11:.1f}/night uplift).  "
                f"mean_roi: {rec['mean_roi']:+.1f}%  folds_pos: {rec['folds_positive']}/{rec['folds_total']}"
            )
        else:
            lines.append(f"- **{stat.upper()}**: No statistically significant threshold — keep 0.5.")

    lines += [
        "",
        "**Action:** threshold changes are NOT applied here — follow-up task will wire the new values.",
        "",
        "_Generated by `scripts/sweep_stl_blk_threshold.py`_",
    ]

    with open(report_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
    print(f"\n  Report -> {report_path}")
    return report_path


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    t0 = time.time()

    sweep_results = run_sweep()

    # Optimal threshold per stat
    recommendations: Dict[str, Optional[Dict]] = {}
    for stat in STATS:
        rec = _pick_optimal(sweep_results.get(stat, []))
        recommendations[stat] = rec
        if rec is not None:
            print(
                f"\n  {stat.upper()} OPTIMAL threshold: {rec['threshold']:.2f}  "
                f"(total_bets={rec['total_bets']}, mean_roi={rec['mean_roi']:+.1f}%, "
                f"folds_pos={rec['folds_positive']}/{rec['folds_total']}, "
                f"score={rec['score']:+.2f})"
            )
        else:
            print(f"\n  {stat.upper()}: No significant threshold found (total_bets < 30 everywhere).")

    # Detailed per-fold breakdown at recommended thresholds
    print("\n  Computing per-fold breakdowns at recommended thresholds...")
    if not os.path.exists(RS_CSV):
        raise SystemExit(f"RS CSV not found: {RS_CSV}")
    with open(RS_CSV, encoding="utf-8") as fh:
        all_rows = list(csv.DictReader(fh))
    unique_dates = sorted(set(r["date"] for r in all_rows))
    name2pid: Dict[str, Optional[int]] = {}
    row_cache: Dict = {}

    fold_breakdowns: Dict[str, List[Dict]] = {}
    for stat in STATS:
        rec = recommendations.get(stat)
        if rec is None:
            fold_breakdowns[stat] = []
            continue
        model = _MODEL_CACHE.get(stat)
        if model is None:
            try:
                model = _load_model(stat)
            except FileNotFoundError:
                fold_breakdowns[stat] = []
                continue
        fb = _per_fold_breakdown(stat, rec["threshold"], all_rows, unique_dates, name2pid, row_cache, model)
        fold_breakdowns[stat] = fb

        print(f"\n  {stat.upper()} per-fold @ threshold={rec['threshold']:.2f}:")
        print(f"  {'date':<14}  {'n_bets':>7}  {'wins':>5}  {'losses':>7}  {'hit':>8}  {'roi':>10}")
        for fr in fb:
            hit_s = f"{fr['hit_rate']*100:.1f}%" if fr["hit_rate"] is not None else "   N/A"
            roi_s = f"{fr['roi_pct']:+.1f}%" if fr["roi_pct"] is not None else "     N/A"
            print(f"  {fr['date']:<14}  {fr['n_bets']:>7}  {fr['wins']:>5}  {fr['losses']:>7}  {hit_s:>8}  {roi_s:>10}")

    report_path = _write_report(sweep_results, recommendations, fold_breakdowns, unique_dates)

    total_elapsed = time.time() - t0
    print(f"\n  Total elapsed: {total_elapsed:.1f}s")
    print(f"  Report: {report_path}")
    print("\n  DONE.")


if __name__ == "__main__":
    main()
