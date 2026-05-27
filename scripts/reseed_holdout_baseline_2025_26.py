"""reseed_holdout_baseline_2025_26.py — Iter-23 clean baseline reseeder.

Re-seeds data/cache/holdout_baseline.json using ONLY 2025-26 data:
  - data/external/historical_lines/regular_season_2025_26_oddsapi.csv (all rows)
  - data/external/historical_lines/playoffs_2025_26_oddsapi.csv (all rows)

The Iter-22 shifted-cutoff retrain (commit 5fb964f1) trained on all data
through 2025-04-21, so the 2024 playoffs + 2024-25 RS slices are no longer
valid OOS eval. The 2025-26-only slice is the honest clean baseline going
forward.

Usage:
    python scripts/reseed_holdout_baseline_2025_26.py
"""
from __future__ import annotations

import csv
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
BASELINE_PATH = PROJECT_DIR / "data" / "cache" / "holdout_baseline.json"
RS_CSV = PROJECT_DIR / "data" / "external" / "historical_lines" / "regular_season_2025_26_oddsapi.csv"
PO_CSV = PROJECT_DIR / "data" / "external" / "historical_lines" / "playoffs_2025_26_oddsapi.csv"

STATS = ["pts", "ast", "reb", "fg3m", "stl", "blk"]  # tov absent from 2025-26 CSVs

# Regex parsers matching backtest script stdout patterns
_ROI_RX   = re.compile(r"ROI(?:@-?\d+)?=([+-]?\d+\.\d+)%")
_HIT_RX   = re.compile(r"hit(?:_rate)?=([+-]?\d+\.\d+)%")
_NBETS_RX = re.compile(r"n_bets=(\d+)")
_NPRED_RX = re.compile(r"n_pred=(\d+)")
_MAE_RX   = re.compile(r"MAE_actual=([+-]?\d+\.\d+)")
_UNITS_RX = re.compile(r"units=([+-]?\d+\.\d+)")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _build_merged_csv(tmp_path: str) -> dict:
    """Merge RS + PO 2025-26 CSVs into a single temp file. Returns stat counts."""
    fieldnames = ["date", "player", "opp", "venue", "stat",
                  "closing_line", "over_odds", "under_odds", "actual_value"]
    rows = []
    # Regular season 2025-26 (all rows are 2025-26 season)
    with open(RS_CSV, encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            rows.append({k: r.get(k, "") for k in fieldnames})
    # Playoffs 2025-26 (all rows)
    with open(PO_CSV, encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            rows.append({k: r.get(k, "") for k in fieldnames})

    with open(tmp_path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    from collections import Counter
    return dict(Counter(r["stat"] for r in rows))


def _run_stat(stat: str, csv_path: str) -> dict:
    """Run one per-stat backtest with NBA_BACKTEST_CSV_OVERRIDE set. Returns parsed metrics."""
    env = os.environ.copy()
    env["NBA_INJURY_WIRE_DISABLE"] = "1"
    env["NBA_BACKTEST_CSV_OVERRIDE"] = csv_path
    env["HOLDOUT_STAT"] = stat
    env["HOLDOUT_SEASON"] = "2025-26"

    if stat in ("reb", "fg3m", "stl", "blk", "tov"):
        script = PROJECT_DIR / "scripts" / "backtest_qstat_oos_override.py"
        cmd = [sys.executable, str(script), "--stat", stat]
    elif stat == "ast":
        script = PROJECT_DIR / "scripts" / "backtest_ast_oos.py"
        cmd = [sys.executable, str(script)]
    else:  # pts
        script = PROJECT_DIR / "scripts" / "backtest_pts_oos.py"
        cmd = [sys.executable, str(script)]

    t0 = time.time()
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(PROJECT_DIR),
            env=env,
            capture_output=True,
            text=True,
            timeout=900,
        )
    except subprocess.TimeoutExpired:
        return {"stat": stat, "ok": False, "reason": "timeout"}

    elapsed = time.time() - t0
    out = (proc.stdout or "") + "\n" + (proc.stderr or "")

    roi   = _ROI_RX.search(out)
    hit   = _HIT_RX.search(out)
    nb    = _NBETS_RX.search(out)
    npred = _NPRED_RX.search(out)
    mae   = _MAE_RX.search(out)
    units = _UNITS_RX.search(out)

    if not (roi and hit and nb):
        tail = "\n".join(out.splitlines()[-25:])
        print(f"  [PARSE FAIL for {stat}] exit={proc.returncode}", flush=True)
        print(f"  tail:\n{tail}", flush=True)
        return {"stat": stat, "ok": False, "reason": "parse_failed",
                "exit": proc.returncode, "tail": tail}

    return {
        "stat": stat, "ok": True,
        "roi_pct":   float(roi.group(1)),
        "hit_rate":  float(hit.group(1)),
        "n_bets":    int(nb.group(1)),
        "n_pred":    int(npred.group(1)) if npred else None,
        "mae_actual": float(mae.group(1)) if mae else None,
        "roi_units": float(units.group(1)) if units else None,
        "elapsed_s": round(elapsed, 1),
    }


def main() -> None:
    print("=" * 60, flush=True)
    print("Iter-23: Re-seeding holdout baseline (2025-26 only)", flush=True)
    print("=" * 60, flush=True)

    # Build merged CSV in temp file
    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False,
                                     dir=str(PROJECT_DIR / "data" / "cache"),
                                     prefix="_iter23_2025_26_merged_") as tf:
        tmp_csv = tf.name
    stat_counts = _build_merged_csv(tmp_csv)
    total_rows = sum(stat_counts.values())
    print(f"\nMerged 2025-26 CSV: {total_rows} rows → {tmp_csv}", flush=True)
    print(f"Stat breakdown: {stat_counts}", flush=True)

    results = {}
    try:
        for stat in STATS:
            print(f"\n[{stat.upper()}] running backtest ...", flush=True)
            r = _run_stat(stat, tmp_csv)
            results[stat] = r
            if r.get("ok"):
                print(f"  n_bets={r['n_bets']}  hit={r['hit_rate']:.2f}%  "
                      f"ROI={r['roi_pct']:+.2f}%  MAE={r.get('mae_actual','N/A')}",
                      flush=True)
            else:
                print(f"  FAILED: {r.get('reason')}", flush=True)
    finally:
        try:
            os.unlink(tmp_csv)
        except OSError:
            pass

    # Build per-stat baseline blob
    per_stat: dict = {}
    ok_results = []
    for stat, r in results.items():
        if r.get("ok"):
            per_stat[stat] = {
                "roi_pct":    r["roi_pct"],
                "hit_rate":   r["hit_rate"],
                "mae_actual": r.get("mae_actual"),
                "roi_units":  r.get("roi_units"),
                "n_bets":     r["n_bets"],
            }
            ok_results.append(r)

    # Aggregate
    total_bets = sum(r["n_bets"] for r in ok_results) or 1
    roi_weighted = sum(r["roi_pct"] * r["n_bets"] for r in ok_results) / total_bets
    hit_weighted = sum(r["hit_rate"] * r["n_bets"] for r in ok_results) / total_bets
    mae_vals = [r["mae_actual"] for r in ok_results if r.get("mae_actual") is not None]
    mae_avg = sum(mae_vals) / len(mae_vals) if mae_vals else None

    # Write baseline
    baseline_doc = {
        "__global__": per_stat,
        "__updated_at__": _now_iso(),
        "__source__": {
            "iter": "iter23",
            "slices": ["regular_season_2025_26", "playoffs_2025_26"],
            "files": [
                str(RS_CSV).replace("\\", "/"),
                str(PO_CSV).replace("\\", "/"),
            ],
            "generated_at": _now_iso(),
            "note": (
                "iter23 clean 2025-26-only baseline. "
                "Post Iter-22 shifted-cutoff retrain (commit 5fb964f1) trains on all data "
                "through 2025-04-21 — 2024 playoffs and 2024-25 RS slices are now "
                "TRAINING data and no longer valid OOS eval. "
                "This baseline uses ONLY 2025-26 RS (all rows) + 2025-26 playoffs."
            ),
            "cutoff_shift_commit": "5fb964f1",
            "old_baseline_note": "+13.87% on 6,448 bets across 4 slices — contaminated by training data",
        },
    }
    BASELINE_PATH.write_text(json.dumps(baseline_doc, indent=2), encoding="utf-8")
    print(f"\nBaseline written to {BASELINE_PATH}", flush=True)

    # Print table
    print("\n" + "=" * 70)
    print(f"{'stat':<8} {'n_bets':>7} {'roi_pct':>9} {'hit_rate':>10} {'mae_actual':>12}")
    print("-" * 70)
    for stat in STATS:
        r = results.get(stat, {})
        if r.get("ok"):
            mae_s = f"{r['mae_actual']:.4f}" if r.get("mae_actual") is not None else "N/A"
            print(f"{stat:<8} {r['n_bets']:>7} {r['roi_pct']:>+9.2f}% {r['hit_rate']:>9.2f}% {mae_s:>12}")
        else:
            print(f"{stat:<8} {'N/A':>7} {'N/A':>9}  {'N/A':>9}  {'N/A':>12}  FAILED")
    print("-" * 70)
    print(f"{'TOTAL':<8} {total_bets:>7} {roi_weighted:>+9.2f}% {hit_weighted:>9.2f}%   (weighted)")
    print("=" * 70)

    print(f"\nOLD baseline: +13.87% ROI on 6,448 bets (contaminated: 4 slices incl. training data)")
    print(f"NEW baseline: {roi_weighted:+.2f}% ROI on {total_bets} bets (clean 2025-26-only)")
    print("\nDone.", flush=True)


if __name__ == "__main__":
    main()
