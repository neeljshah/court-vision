"""audit_model_prob_calibration_per_stat.py — iter-19 per-stat calibration.

Builds on iter-8's `audit_model_prob_calibration.py`. The iter-8 audit fit a
GLOBAL isotonic at `data/models/calibration/model_prob_isotonic.pkl` (Brier
-8.2% on held-out 2024 playoff rows). Per-stat bins in the iter-8 cache
showed VERY different miscalibration shapes per stat (BLK extreme bins were
the worst — model 3.7% confidence vs 26% empirical; PTS asymmetric).

This script:
  1. Reuses iter-8's `collect_rows` to build per-row records (heavy step).
  2. Caches per-row records to data/cache/audit_per_stat_records_iter19.json
     so re-runs are seconds, not 15min.
  3. Fits a GLOBAL iso AND a PER-STAT iso on the same time-sorted 70/30
     split *of each stat's rows* — head-to-head Brier comparison.
  4. Samples raw->cal curves at raw_p = [0.05, 0.10, 0.25, 0.50, 0.75,
     0.90, 0.95] for each stat under both isos.
  5. Saves per-stat artifacts to
     data/models/calibration/model_prob_isotonic_<stat>.pkl
     and a summary JSON to
     data/models/calibration/per_stat_iso_metrics.json
  6. Recommends whether to ship per-stat (Δ > meaningful margin vs global).

Forbidden files NOT touched: ingest_one_game.py, fetch_games.py,
unified_pipeline.py, advanced_tracker.py. Existing global iso pkl is NOT
modified.
"""
from __future__ import annotations

import argparse
import json
import os
import pickle
import sys
import time
from typing import Dict, List, Optional

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

os.environ.setdefault("NBA_INJURY_WIRE_DISABLE", "1")

# Reuse iter-8 audit machinery — collect_rows is the slow path.
from scripts.audit_model_prob_calibration import (  # noqa: E402
    collect_rows,
    _brier,
)

try:
    from sklearn.isotonic import IsotonicRegression  # noqa: E402
    HAVE_SKLEARN = True
except Exception as exc:  # pragma: no cover
    print(f"  [warn] sklearn isotonic unavailable: {exc}")
    HAVE_SKLEARN = False


STATS_PER_STAT = ["pts", "reb", "ast", "fg3m", "stl", "blk"]  # skip TOV per goal
SAMPLE_RAW_PROBS = [0.05, 0.10, 0.25, 0.50, 0.75, 0.90, 0.95]


def _fit_iso(train_records: List[dict]) -> Optional[IsotonicRegression]:
    if not HAVE_SKLEARN or not train_records:
        return None
    iso = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
    iso.fit([r["model_prob_over"] for r in train_records],
            [r["hit_over"] for r in train_records])
    return iso


def _records_to_json(records: List[dict]) -> List[dict]:
    """Strip down to the keys we need for caching."""
    keep = ("date", "stat", "model_prob_over", "hit_over")
    return [{k: r[k] for k in keep} for r in records]


def _load_cached_records(path: str) -> Optional[List[dict]]:
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data, list) and data and "model_prob_over" in data[0]:
            return data
    except Exception:
        return None
    return None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default=os.path.join(
        PROJECT_DIR, "data", "external", "historical_lines",
        "playoffs_2024_canonical.csv"))
    ap.add_argument("--gamelog-dir", default=os.path.join(PROJECT_DIR, "data", "nba"))
    ap.add_argument("--records-cache", default=os.path.join(
        PROJECT_DIR, "data", "cache", "audit_per_stat_records_iter19.json"))
    ap.add_argument("--out-dir", default=os.path.join(
        PROJECT_DIR, "data", "models", "calibration"))
    ap.add_argument("--summary-out", default=os.path.join(
        PROJECT_DIR, "data", "models", "calibration",
        "per_stat_iso_metrics.json"))
    ap.add_argument("--max-rows", type=int, default=None)
    ap.add_argument("--train-frac", type=float, default=0.70)
    args = ap.parse_args()

    t0 = time.time()
    cached = _load_cached_records(args.records_cache)
    if cached:
        print(f"  Reusing cached records: {len(cached)} rows ({args.records_cache})")
        records = cached
    else:
        print(f"  No cache -- running collect_rows (slow, ~15min on 5K rows)")
        records = collect_rows(args.csv, args.gamelog_dir, max_rows=args.max_rows)
        if not records:
            print("  [fail] no usable rows. Exiting.")
            return
        os.makedirs(os.path.dirname(args.records_cache), exist_ok=True)
        with open(args.records_cache, "w", encoding="utf-8") as fh:
            json.dump(_records_to_json(records), fh)
        print(f"  Cached {len(records)} records -> {args.records_cache}")
        records = _records_to_json(records)

    print(f"  Total rows: {len(records)} ({time.time()-t0:.1f}s elapsed)")

    # ── Build per-stat splits (time-sorted 70/30 inside each stat) ──
    by_stat: Dict[str, List[dict]] = {}
    for r in records:
        by_stat.setdefault(r["stat"], []).append(r)
    print("  Rows per stat:")
    for st in sorted(by_stat):
        print(f"    {st:5s}: {len(by_stat[st])}")

    # ── Fit GLOBAL iso on the SAME train split (concat of train halves) ──
    # so the comparison is apples-to-apples: same test rows used for both.
    global_train: List[dict] = []
    splits: Dict[str, dict] = {}
    for st in STATS_PER_STAT:
        rs = by_stat.get(st, [])
        if not rs:
            splits[st] = None
            continue
        rs_sorted = sorted(rs, key=lambda r: r["date"])
        cut = int(len(rs_sorted) * args.train_frac)
        train = rs_sorted[:cut]
        test = rs_sorted[cut:]
        if not train or not test:
            splits[st] = None
            continue
        splits[st] = {"train": train, "test": test}
        global_train.extend(train)

    print(f"  Fitting GLOBAL iso on concat of per-stat train halves "
          f"(n={len(global_train)})...")
    global_iso = _fit_iso(global_train)
    if global_iso is None:
        print("  [fail] global iso fit failed.")
        return

    # ── Per-stat isos, evaluated on the same per-stat test rows ──
    per_stat_table: List[dict] = []
    per_stat_curves: Dict[str, dict] = {}
    per_stat_isos: Dict[str, IsotonicRegression] = {}
    os.makedirs(args.out_dir, exist_ok=True)

    for st in STATS_PER_STAT:
        sp = splits.get(st)
        if sp is None:
            per_stat_table.append({
                "stat": st, "n_train": 0, "n_test": 0,
                "brier_raw": None, "brier_global_iso": None,
                "brier_per_stat_iso": None,
                "delta_vs_raw": None, "delta_vs_global": None,
            })
            continue
        train, test = sp["train"], sp["test"]
        ps_iso = _fit_iso(train)
        if ps_iso is None:
            continue
        per_stat_isos[st] = ps_iso

        raw_test = [r["model_prob_over"] for r in test]
        hits_test = [r["hit_over"] for r in test]
        cal_global = [float(p) for p in global_iso.predict(raw_test)]
        cal_per_stat = [float(p) for p in ps_iso.predict(raw_test)]

        b_raw = _brier(raw_test, hits_test)
        b_glob = _brier(cal_global, hits_test)
        b_ps = _brier(cal_per_stat, hits_test)

        per_stat_table.append({
            "stat": st,
            "n_train": len(train), "n_test": len(test),
            "brier_raw": round(b_raw, 5),
            "brier_global_iso": round(b_glob, 5),
            "brier_per_stat_iso": round(b_ps, 5),
            "delta_vs_raw_pct": round((b_raw - b_ps) / b_raw * 100, 2)
                if b_raw else None,
            "delta_vs_global_abs": round(b_glob - b_ps, 5),
            "delta_vs_global_pct": round((b_glob - b_ps) / b_glob * 100, 2)
                if b_glob else None,
            "train_date_max": train[-1]["date"],
            "test_date_min": test[0]["date"],
        })

        # Sample curves
        curve = {}
        for p in SAMPLE_RAW_PROBS:
            curve[f"raw_{p:.2f}"] = {
                "global_iso": round(float(global_iso.predict([p])[0]), 4),
                "per_stat_iso": round(float(ps_iso.predict([p])[0]), 4),
            }
        per_stat_curves[st] = curve

        # Save the per-stat iso pkl
        pkl_path = os.path.join(
            args.out_dir, f"model_prob_isotonic_{st}.pkl")
        with open(pkl_path, "wb") as fh:
            pickle.dump(ps_iso, fh)
        print(f"  [{st}] saved -> {pkl_path}")

    # ── Print results table ──
    print("\n  Per-stat calibration comparison")
    print(f"  {'stat':>5s} | {'n_tr':>5s} | {'n_te':>5s} | "
          f"{'b_raw':>7s} | {'b_glob':>7s} | {'b_ps':>7s} | "
          f"{'d_glob_abs':>10s} | {'d_glob_%':>8s}")
    print(f"  {'-'*5} | {'-'*5} | {'-'*5} | {'-'*7} | {'-'*7} | {'-'*7} | "
          f"{'-'*10} | {'-'*8}")
    for row in per_stat_table:
        if row["n_train"] == 0:
            print(f"  {row['stat']:>5s} | {0:>5d} | {0:>5d} |  ---   |  ---   |  ---   |    ---     |   ---")
            continue
        print(f"  {row['stat']:>5s} | {row['n_train']:>5d} | "
              f"{row['n_test']:>5d} | {row['brier_raw']:>7.5f} | "
              f"{row['brier_global_iso']:>7.5f} | {row['brier_per_stat_iso']:>7.5f} | "
              f"{row['delta_vs_global_abs']:>+10.5f} | "
              f"{row['delta_vs_global_pct']:>+7.2f}%")

    # ── Print curve samples ──
    print("\n  Calibration shape -- raw_p -> calibrated_p")
    for st, curve in per_stat_curves.items():
        print(f"\n  [{st}] {'raw':>6s} | {'global':>7s} | {'per_stat':>9s} | "
              f"{'delta':>7s}")
        for p in SAMPLE_RAW_PROBS:
            k = f"raw_{p:.2f}"
            g = curve[k]["global_iso"]
            ps = curve[k]["per_stat_iso"]
            print(f"        {p:>6.2f} | {g:>7.4f} | {ps:>9.4f} | "
                  f"{ps - g:>+7.4f}")

    # ── Recommendation ──
    rec_lines = []
    ship_vote_yes = 0
    ship_vote_no = 0
    for row in per_stat_table:
        if row["n_train"] == 0 or row["delta_vs_global_abs"] is None:
            continue
        # "Meaningful" = per-stat iso beats global by >= 0.001 absolute Brier
        # AND n_test >= 100 (small-sample stats overfit the iso).
        meaningful = (row["delta_vs_global_abs"] >= 0.001
                      and row["n_test"] >= 100)
        if meaningful:
            ship_vote_yes += 1
            rec_lines.append(
                f"  [SHIP {row['stat']}] d_global=+{row['delta_vs_global_abs']:.5f} "
                f"({row['delta_vs_global_pct']:+.2f}%), n_test={row['n_test']}")
        else:
            ship_vote_no += 1
            why = ("small n_test" if row["n_test"] < 100
                   else "d_global below 0.001 threshold")
            rec_lines.append(
                f"  [SKIP {row['stat']}] d_global=+{row['delta_vs_global_abs']:.5f} "
                f"({row['delta_vs_global_pct']:+.2f}%), n_test={row['n_test']} -- {why}")
    print("\n  Recommendation per-stat:")
    for ln in rec_lines:
        print(ln)
    overall_ship = ship_vote_yes >= 3
    print(f"\n  Overall: ship per-stat? {'YES' if overall_ship else 'NO'} "
          f"({ship_vote_yes} ship vs {ship_vote_no} skip)")

    # ── Save summary JSON ──
    summary = {
        "iter": 19,
        "n_records_total": len(records),
        "train_frac": args.train_frac,
        "rows_per_stat": {st: len(by_stat.get(st, [])) for st in STATS_PER_STAT},
        "per_stat_table": per_stat_table,
        "per_stat_curves": per_stat_curves,
        "global_iso_pkl": os.path.join(args.out_dir, "model_prob_isotonic.pkl"),
        "ship_recommendation": {
            "overall_ship_per_stat": overall_ship,
            "ship_vote_yes": ship_vote_yes,
            "ship_vote_no": ship_vote_no,
            "per_stat_reasons": rec_lines,
            "threshold_abs_brier": 0.001,
            "threshold_min_n_test": 100,
        },
    }
    with open(args.summary_out, "w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=2, default=str)
    print(f"\n  Summary JSON -> {args.summary_out}")
    print(f"  Total wall time: {time.time()-t0:.1f}s")


if __name__ == "__main__":
    main()
