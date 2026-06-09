#!/usr/bin/env python3
"""
backfill_status.py — R20 progress monitor for run_backfill.py.

Reads data/backfill_log.csv and shows a one-shot summary, or tails it live.

Usage:
  python3 scripts/backfill_status.py                    # one-shot
  python3 scripts/backfill_status.py --watch            # refresh every 30s
  python3 scripts/backfill_status.py --watch --interval 60
  python3 scripts/backfill_status.py --csv data/custom_log.csv
"""
from __future__ import annotations

import argparse
import csv
import sys
import time
from pathlib import Path
from collections import Counter

PROJECT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_LOG = PROJECT_DIR / "data" / "backfill_log.csv"


def read_log(path: Path) -> list:
    if not path.exists():
        return []
    try:
        with open(path, encoding="utf-8") as f:
            return list(csv.DictReader(f))
    except Exception as exc:
        print(f"ERROR reading {path}: {exc}", file=sys.stderr)
        return []


def fmt_summary(rows: list) -> str:
    if not rows:
        return "no rows in log yet"
    n = len(rows)
    status_counts = Counter(r.get("status", "") for r in rows)
    ok    = status_counts.get("ok", 0)
    fail  = status_counts.get("fail", 0)
    crash = status_counts.get("crash", 0)
    timeout  = status_counts.get("timeout", 0)
    no_vid   = status_counts.get("no_video", 0)
    total_sec = sum(float(r.get("wall_clock_sec") or 0) for r in rows if r.get("status") != "no_video")
    total_min = total_sec / 60
    successful_durations = [float(r["wall_clock_sec"]) for r in rows
                            if r.get("status") == "ok" and r.get("wall_clock_sec")]
    if successful_durations:
        avg_min = sum(successful_durations) / len(successful_durations) / 60
        min_min = min(successful_durations) / 60
        max_min = max(successful_durations) / 60
    else:
        avg_min = min_min = max_min = 0
    total_tracking = sum(int(r.get("tracking_rows") or 0) for r in rows)
    total_shots    = sum(int(r.get("shot_count")     or 0) for r in rows)
    total_poss     = sum(int(r.get("possession_count") or 0) for r in rows)
    by_gpu = Counter(r.get("gpu_id", "?") for r in rows if r.get("status") != "no_video")

    lines = [
        f"== Backfill status — {n} game-records ==",
        f"  OK:        {ok:5d}",
        f"  Fail:      {fail:5d}",
        f"  Crash:     {crash:5d}",
        f"  Timeout:   {timeout:5d}",
        f"  No-video:  {no_vid:5d}",
        f"",
        f"  Compute used:    {total_min:.1f} min  ({total_min/60:.1f} hr)",
        f"  Avg / OK game:   {avg_min:.1f} min  (range {min_min:.1f}–{max_min:.1f})",
        f"  Total tracking:  {total_tracking:,} rows",
        f"  Total shots:     {total_shots:,}",
        f"  Total possess:   {total_poss:,}",
        f"",
        f"  Per-GPU game count:  " + ", ".join(f"GPU{g}={c}" for g, c in sorted(by_gpu.items())),
    ]
    # Last 5 games
    last5 = rows[-5:]
    lines.append("")
    lines.append("  Last 5 games:")
    for r in last5:
        lines.append(
            f"    {r.get('timestamp','')}  {r.get('game_id',''):12s}  "
            f"GPU{r.get('gpu_id','?')}  {r.get('status','?'):8s}  "
            f"{float(r.get('wall_clock_sec') or 0)/60:5.1f}m  "
            f"rows={int(r.get('tracking_rows') or 0):6d}  "
            f"shots={int(r.get('shot_count') or 0):3d}"
        )
    # Failures (last 5)
    failures = [r for r in rows if r.get("status") not in ("ok", "no_video")][-5:]
    if failures:
        lines.append("")
        lines.append("  Recent failures:")
        for r in failures:
            err = (r.get("error") or "")[:60]
            lines.append(f"    {r.get('game_id',''):12s}  {r.get('status','?'):8s}  {err}")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--csv", type=Path, default=DEFAULT_LOG, help="Backfill log CSV path.")
    ap.add_argument("--watch", action="store_true", help="Refresh continuously.")
    ap.add_argument("--interval", type=int, default=30, help="Refresh interval in seconds.")
    args = ap.parse_args()

    if not args.watch:
        print(fmt_summary(read_log(args.csv)))
        return 0
    try:
        while True:
            print("\033[2J\033[H", end="")   # clear screen
            print(fmt_summary(read_log(args.csv)))
            print(f"\n(refreshing every {args.interval}s — Ctrl-C to quit)")
            time.sleep(args.interval)
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    sys.exit(main())
