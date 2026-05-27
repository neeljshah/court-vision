"""audit_model_prob_calibration.py — iter-8 model_prob calibration audit.

Issue #19: WCF G7 dry-run produced Wemby BLK U 3.5 @ model_prob=0.999. Audit
whether model_prob (q10/q50/q90 → Normal CDF → P(over)) is calibrated to
reality across 5108 rows of the 2024 NBA playoffs.

Pipeline per row:
    (player, date, stat) -> _build_asof_row (leak-free, iter-7 reuse)
                          -> predict_pergame_quantiles(stat, row, model_dir)
                          -> apply_quantile_calibration (cycle-40)
                          -> sigma = (cal_q90 - cal_q10) / (2 * 1.2816)
                          -> z = (line - q50) / sigma  (note: q50 used as mu,
                             same as compare_to_lines._model_hit_prob)
                          -> p_over = 1 - Phi(z)
                          -> bucket by p_over -> empirical OVER rate

Outputs:
    * Calibration table (10 buckets, all stats) -> stdout + JSON
    * Per-stat calibration of the 0.9-1.0 + 0.0-0.1 buckets (most aggressive bets)
    * Isotonic regression mapping model_prob_raw -> calibrated_prob
        - Train on first 70% of dates (time-sorted), eval on remaining 30%
        - Save to data/models/calibration/model_prob_isotonic.pkl
        - Brier-score improvement reported

Sanity: Wemby (Victor Wembanyama, player_id=1641705) BLK U 3.5 — print
the production model_prob the system would emit *today*.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import pickle
import sys
import time
from collections import defaultdict
from datetime import datetime
from typing import Dict, List, Optional, Tuple

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

os.environ.setdefault("NBA_INJURY_WIRE_DISABLE", "1")

# Reuse iter-7 backtest helpers.
from scripts.backtest_closing_lines_2024_playoffs import (  # noqa: E402
    _build_asof_row,
    _resolve_player_id,
    _season_for_date,
)
from src.prediction.prop_pergame import predict_pergame  # noqa: E402
from src.prediction.prop_quantiles import predict_pergame_quantiles  # noqa: E402
from src.prediction.quantile_calibration import apply as apply_quantile_calibration  # noqa: E402

try:
    from sklearn.isotonic import IsotonicRegression  # noqa: E402
    HAVE_SKLEARN = True
except Exception as exc:
    print(f"  [warn] sklearn isotonic unavailable: {exc}")
    HAVE_SKLEARN = False


STATS_AUDIT = ["reb", "ast", "fg3m", "stl", "blk", "tov", "pts"]
NUM_BUCKETS = 10  # 0.0-0.1, 0.1-0.2, ..., 0.9-1.0


def _normal_cdf(z: float) -> float:
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def _model_prob_over(stat: str, q10: float, q50: float, q90: float,
                     line: float) -> Optional[float]:
    """Replica of compare_to_lines._model_hit_prob (OVER side) — cycle-40 cal."""
    if q10 is None or q50 is None or q90 is None:
        return None
    cal_q10, cal_q90 = apply_quantile_calibration(stat, q10, q50, q90)
    sigma = max((cal_q90 - cal_q10) / (2 * 1.2816), 1e-6)
    z = (line - q50) / sigma
    return float(1.0 - _normal_cdf(z))


def _bucket_idx(p: float) -> int:
    """0.0 → 0; 1.0 → 9; clip to [0, NUM_BUCKETS-1]."""
    return min(max(int(p * NUM_BUCKETS), 0), NUM_BUCKETS - 1)


def _brier(probs: List[float], hits: List[int]) -> float:
    if not probs:
        return float("nan")
    return float(sum((p - y) ** 2 for p, y in zip(probs, hits)) / len(probs))


# ──────────────────────────────────────────────────────── per-row audit ──

def collect_rows(csv_path: str, gamelog_dir: str,
                 max_rows: Optional[int] = None) -> List[dict]:
    """Compute model_prob_over for every line in the canonical playoffs CSV."""
    rows = []
    with open(csv_path, encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for r in reader:
            rows.append(r)
    if max_rows:
        rows = rows[:max_rows]
    print(f"  Loaded {len(rows)} rows from {os.path.basename(csv_path)}")

    unique_names = sorted({r["player"] for r in rows})
    name2pid = {nm: _resolve_player_id(nm) for nm in unique_names}
    resolved = sum(1 for v in name2pid.values() if v is not None)
    print(f"  Resolved {resolved}/{len(unique_names)} player names")

    feat_cache: Dict[Tuple, Optional[dict]] = {}
    out: List[dict] = []
    skip_reasons: defaultdict = defaultdict(int)
    t0 = time.time()
    for idx, r in enumerate(rows):
        stat = r["stat"].lower()
        if stat not in STATS_AUDIT:
            skip_reasons["stat_excluded"] += 1
            continue
        try:
            line = float(r["closing_line"])
            actual = float(r["actual_value"])
        except (TypeError, ValueError):
            skip_reasons["bad_numeric"] += 1
            continue
        try:
            d = datetime.fromisoformat(r["date"])
        except Exception:
            skip_reasons["bad_date"] += 1
            continue
        pid = name2pid.get(r["player"])
        if pid is None:
            skip_reasons["no_pid"] += 1
            continue
        venue = r["venue"]
        opp = r["opp"]
        season = _season_for_date(d)
        is_home = (venue == "home")

        key = (pid, r["date"], venue, opp)
        if key not in feat_cache:
            try:
                feat_cache[key] = _build_asof_row(
                    pid, opp, d, season, is_home=is_home, rest_days=2.0,
                    gamelog_dir=gamelog_dir,
                )
            except Exception as exc:
                feat_cache[key] = None
                skip_reasons[f"feat_err:{type(exc).__name__}"] += 1
        feat = feat_cache[key]
        if feat is None:
            skip_reasons["no_features"] += 1
            continue

        try:
            point = predict_pergame(stat, feat)
            qint = predict_pergame_quantiles(stat, feat)
        except Exception as exc:
            skip_reasons[f"pred_err:{type(exc).__name__}"] += 1
            continue
        if point is None or qint is None:
            skip_reasons["no_model"] += 1
            continue
        prob_over = _model_prob_over(stat,
                                     qint.get("q10"), qint.get("q50"),
                                     qint.get("q90"), line)
        if prob_over is None:
            skip_reasons["no_prob"] += 1
            continue

        hit_over = int(actual > line)
        is_push = abs(actual - line) < 1e-9
        if is_push:
            skip_reasons["push"] += 1
            continue
        out.append({
            "date": r["date"],
            "player": r["player"],
            "stat": stat,
            "line": line,
            "actual": actual,
            "q10": qint["q10"], "q50": qint["q50"], "q90": qint["q90"],
            "point": float(point),
            "model_prob_over": prob_over,
            "hit_over": hit_over,
        })

        if (idx + 1) % 500 == 0:
            print(f"  ...{idx+1}/{len(rows)} processed in {time.time()-t0:.1f}s, "
                  f"kept {len(out)}")

    print(f"  Done collecting: {len(out)} usable rows in {time.time()-t0:.1f}s")
    print(f"  Skip reasons: {dict(skip_reasons)}")
    return out


# ──────────────────────────────────────────────────── calibration table ──

def calibration_table(records: List[dict],
                      stat_filter: Optional[str] = None) -> List[dict]:
    """Bucket records by model_prob_over -> empirical OVER rate."""
    buckets = [[] for _ in range(NUM_BUCKETS)]
    for rec in records:
        if stat_filter and rec["stat"] != stat_filter:
            continue
        b = _bucket_idx(rec["model_prob_over"])
        buckets[b].append(rec)
    table = []
    for i, b in enumerate(buckets):
        if not b:
            table.append({
                "bin": f"{i/NUM_BUCKETS:.1f}-{(i+1)/NUM_BUCKETS:.1f}",
                "n_rows": 0, "model_prob_mean": None,
                "empirical_over_rate": None, "gap": None,
            })
            continue
        n = len(b)
        mp = sum(r["model_prob_over"] for r in b) / n
        eo = sum(r["hit_over"] for r in b) / n
        table.append({
            "bin": f"{i/NUM_BUCKETS:.1f}-{(i+1)/NUM_BUCKETS:.1f}",
            "n_rows": n,
            "model_prob_mean": round(mp, 4),
            "empirical_over_rate": round(eo, 4),
            "gap": round(mp - eo, 4),
        })
    return table


def print_table(table: List[dict], header: str) -> None:
    print(f"\n  {header}")
    print(f"  {'bin':>9s} | {'n':>5s} | {'model_p':>8s} | {'emp_over':>8s} | {'gap':>7s}")
    print(f"  {'-'*9} | {'-'*5} | {'-'*8} | {'-'*8} | {'-'*7}")
    for row in table:
        if row["n_rows"] == 0:
            print(f"  {row['bin']:>9s} | {0:>5d} | {'-':>8s} | {'-':>8s} | {'-':>7s}")
            continue
        print(f"  {row['bin']:>9s} | {row['n_rows']:>5d} | "
              f"{row['model_prob_mean']:>8.4f} | {row['empirical_over_rate']:>8.4f} | "
              f"{row['gap']:>+7.4f}")


# ────────────────────────────────────────────────────── isotonic fit ──────

def fit_isotonic(records: List[dict], train_frac: float = 0.70) -> dict:
    """Time-sorted 70/30 split. Returns {brier_raw, brier_cal, model, n_train, n_test}."""
    if not HAVE_SKLEARN:
        return {"error": "sklearn unavailable"}
    sorted_rec = sorted(records, key=lambda r: r["date"])
    n = len(sorted_rec)
    cut = int(n * train_frac)
    train = sorted_rec[:cut]
    test = sorted_rec[cut:]
    if not train or not test:
        return {"error": "empty split"}

    iso = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
    iso.fit([r["model_prob_over"] for r in train],
            [r["hit_over"] for r in train])

    raw_test = [r["model_prob_over"] for r in test]
    hits_test = [r["hit_over"] for r in test]
    cal_test = [float(p) for p in iso.predict(raw_test)]

    brier_raw = _brier(raw_test, hits_test)
    brier_cal = _brier(cal_test, hits_test)

    # Distribution shift of tail (>=0.9) and head (<=0.1)
    tail_raw = [p for p in raw_test if p >= 0.9]
    tail_cal_for_those = [iso.predict([p])[0] for p in tail_raw]
    head_raw = [p for p in raw_test if p <= 0.1]
    head_cal_for_those = [iso.predict([p])[0] for p in head_raw]

    return {
        "n_train": len(train), "n_test": len(test),
        "train_date_max": train[-1]["date"], "test_date_min": test[0]["date"],
        "brier_raw": round(brier_raw, 5),
        "brier_cal": round(brier_cal, 5),
        "brier_delta": round(brier_raw - brier_cal, 5),
        "tail_n": len(tail_raw),
        "tail_raw_mean": (round(sum(tail_raw)/len(tail_raw), 4) if tail_raw else None),
        "tail_cal_mean": (round(float(sum(tail_cal_for_those))/len(tail_cal_for_those), 4)
                          if tail_cal_for_those else None),
        "head_n": len(head_raw),
        "head_raw_mean": (round(sum(head_raw)/len(head_raw), 4) if head_raw else None),
        "head_cal_mean": (round(float(sum(head_cal_for_those))/len(head_cal_for_those), 4)
                          if head_cal_for_those else None),
        "model": iso,
    }


# ─────────────────────────────────────────────────────── Wemby sanity ───

def wemby_sanity(gamelog_dir: str, line: float = 3.5) -> dict:
    """Compute the production model_prob for Wemby BLK U <line> today."""
    pid = 1641705  # Victor Wembanyama
    today = datetime.now()
    season = _season_for_date(today)
    feat = None
    try:
        feat = _build_asof_row(pid, "DAL", today, season,
                               is_home=True, rest_days=2.0,
                               gamelog_dir=gamelog_dir)
    except Exception as exc:
        return {"error": f"feat build: {exc}"}
    if feat is None:
        return {"error": "no gamelog/features available for Wemby today"}
    try:
        point = predict_pergame("blk", feat)
        qint = predict_pergame_quantiles("blk", feat)
    except Exception as exc:
        return {"error": f"predict: {exc}"}
    if point is None or qint is None:
        return {"error": "no model output"}
    p_over = _model_prob_over("blk",
                              qint.get("q10"), qint.get("q50"),
                              qint.get("q90"), line)
    p_under = 1.0 - p_over if p_over is not None else None
    return {
        "player_id": pid,
        "stat": "blk", "line": line,
        "point": round(float(point), 4),
        "q10": round(qint["q10"], 4),
        "q50": round(qint["q50"], 4),
        "q90": round(qint["q90"], 4),
        "p_over": round(p_over, 6) if p_over is not None else None,
        "p_under": round(p_under, 6) if p_under is not None else None,
    }


# ─────────────────────────────────────────────────────────── main ───────

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default=os.path.join(
        PROJECT_DIR, "data", "external", "historical_lines",
        "playoffs_2024_canonical.csv"))
    ap.add_argument("--gamelog-dir", default=os.path.join(PROJECT_DIR, "data", "nba"))
    ap.add_argument("--max-rows", type=int, default=None)
    ap.add_argument("--out-json", default=os.path.join(
        PROJECT_DIR, "data", "cache",
        "audit_model_prob_calibration.json"))
    ap.add_argument("--isotonic-out", default=os.path.join(
        PROJECT_DIR, "data", "models", "calibration",
        "model_prob_isotonic.pkl"))
    ap.add_argument("--skip-wemby", action="store_true",
                    help="Skip Wemby sanity (slow if NBA static index missing).")
    args = ap.parse_args()

    print(f"\n  csv          : {args.csv}")
    print(f"  gamelog dir  : {args.gamelog_dir}")
    print(f"  max_rows     : {args.max_rows or 'ALL'}\n")

    records = collect_rows(args.csv, args.gamelog_dir, max_rows=args.max_rows)
    if not records:
        print("  [fail] no usable rows collected. Exiting.")
        return

    # All-stats table
    overall = calibration_table(records)
    print_table(overall, "Calibration table (all stats combined)")

    # Per-stat tables — focus on stats that include BLK (the Wemby issue).
    per_stat = {}
    for st in ["blk", "stl", "fg3m", "tov", "reb", "ast", "pts"]:
        sub = [r for r in records if r["stat"] == st]
        if not sub:
            continue
        per_stat[st] = calibration_table(records, stat_filter=st)
        print_table(per_stat[st], f"Calibration — stat={st} ({len(sub)} rows)")

    # Isotonic fit
    iso_res = fit_isotonic(records)
    iso_model = iso_res.pop("model", None) if isinstance(iso_res, dict) else None
    print("\n  Isotonic regression (time-sorted 70/30 split):")
    print(f"    {json.dumps(iso_res, indent=4, default=str)}")

    if iso_model is not None:
        os.makedirs(os.path.dirname(args.isotonic_out), exist_ok=True)
        with open(args.isotonic_out, "wb") as fh:
            pickle.dump(iso_model, fh)
        print(f"  Isotonic calibrator saved -> {args.isotonic_out}")

    # Wemby sanity
    wemby = {}
    if not args.skip_wemby:
        print("\n  Wemby BLK U 3.5 sanity (today):")
        wemby = wemby_sanity(args.gamelog_dir, line=3.5)
        print(f"    {json.dumps(wemby, indent=4, default=str)}")

    # Distribution of high-confidence BLK rows in the audit set
    blk_high = [r for r in records if r["stat"] == "blk" and
                (r["model_prob_over"] >= 0.95 or r["model_prob_over"] <= 0.05)]
    blk_extreme_summary = {
        "n_blk_total": sum(1 for r in records if r["stat"] == "blk"),
        "n_blk_extreme": len(blk_high),
        "n_p_le_001": sum(1 for r in records if r["stat"] == "blk"
                          and r["model_prob_over"] <= 0.001),
        "n_p_ge_999": sum(1 for r in records if r["stat"] == "blk"
                          and r["model_prob_over"] >= 0.999),
    }
    if blk_high:
        emp_over = sum(r["hit_over"] for r in blk_high) / len(blk_high)
        mp = sum(r["model_prob_over"] for r in blk_high) / len(blk_high)
        blk_extreme_summary["model_prob_mean"] = round(mp, 4)
        blk_extreme_summary["empirical_over_rate"] = round(emp_over, 4)
    print(f"\n  BLK extreme-confidence rows (p<=0.05 or p>=0.95): "
          f"{json.dumps(blk_extreme_summary, indent=4)}")

    # Dump everything
    os.makedirs(os.path.dirname(args.out_json), exist_ok=True)
    payload = {
        "n_records": len(records),
        "calibration_overall": overall,
        "calibration_per_stat": per_stat,
        "isotonic": iso_res,
        "wemby_sanity": wemby,
        "blk_extreme_summary": blk_extreme_summary,
    }
    with open(args.out_json, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, default=str)
    print(f"\n  Audit JSON saved -> {args.out_json}")


if __name__ == "__main__":
    main()
