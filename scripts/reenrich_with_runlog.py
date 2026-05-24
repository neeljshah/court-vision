#!/usr/bin/env python3
"""Re-run Stage 2 enrichment on all games, appending enrich output to each
game's run.log so audit_completed.py picks up new PBP recall numbers.

No tracking re-run — uses existing data/tracking/<gid>/{shot_log.csv,
ball_tracking.csv, scoreboard_log.csv, possessions.csv}. Only re-runs the
PBP matcher with current _SHOT_MATCH_WINDOW_SEC from nba_enricher.py.

Usage:
    python3 scripts/reenrich_with_runlog.py                  # all games
    python3 scripts/reenrich_with_runlog.py --game-ids ...   # subset
    python3 scripts/reenrich_with_runlog.py --dry-run        # print plan, no writes
"""
from __future__ import annotations

import argparse
import contextlib
import io
import os
import re
import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

TRACKING_ROOT = PROJECT_DIR / "data" / "tracking"

_PBP_RECALL_RE = re.compile(r"PBP recall.*?(\d+)/(\d+) = ([\d.]+)%")


def reenrich_one(gid: str, dry: bool = False) -> dict:
    d = TRACKING_ROOT / gid
    if not d.is_dir():
        return {"gid": gid, "skip": "no_dir"}
    sl = d / "shot_log.csv"
    if not sl.exists():
        return {"gid": gid, "skip": "no_shot_log"}

    from src.data.nba_enricher import enrich, _infer_period_count, _infer_fps

    periods, max_ts = _infer_period_count(str(d))
    fps = _infer_fps(str(d), default=30.0)

    if dry:
        return {"gid": gid, "periods": periods, "fps": fps, "max_ts": max_ts}

    # Capture stdout from enrich() — it prints "PBP recall (relevant): X/Y = Z%" etc.
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        print(f"\n============================================================")
        print(f" Stage 2 / 3 — NBA API Enrichment (re-enrich {gid})")
        print(f"============================================================")
        try:
            if len(periods) == 1:
                enrich(game_id=gid, period=1, clip_start_sec=0.0,
                       fps=fps, data_dir=str(d))
            else:
                enrich(game_id=gid, periods=periods, clip_start_sec=0.0,
                       fps=fps, data_dir=str(d))
        except Exception as e:
            print(f"  [error] enrich failed: {e}")
    out = buf.getvalue()

    # Append captured output to run.log so audit picks it up
    runlog = d / "run.log"
    with open(runlog, "a", encoding="utf-8") as f:
        f.write(out)

    # Extract new recall number for return value
    m_all = list(_PBP_RECALL_RE.finditer(out))
    new_recall = float(m_all[-1].group(3)) if m_all else None
    return {"gid": gid, "new_recall": new_recall, "lines_appended": len(out.splitlines())}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--game-ids", nargs="*", help="Specific games; default = all under data/tracking/")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if args.game_ids:
        gids = args.game_ids
    else:
        gids = sorted(
            p.name for p in TRACKING_ROOT.iterdir()
            if p.is_dir() and p.name.startswith("00")
            and (p / "shot_log.csv").exists()
        )

    from src.data.nba_enricher import _SHOT_MATCH_WINDOW_SEC
    print(f"Re-enriching {len(gids)} games (current _SHOT_MATCH_WINDOW_SEC={_SHOT_MATCH_WINDOW_SEC})")
    if args.dry_run:
        print("DRY RUN — no writes")

    n_ok = n_err = 0
    for gid in gids:
        try:
            r = reenrich_one(gid, dry=args.dry_run)
            if "skip" in r:
                print(f"  {gid:12} SKIP {r['skip']}")
                continue
            if args.dry_run:
                print(f"  {gid:12} periods={r['periods']} fps={r['fps']} max_ts={r['max_ts']:.0f}")
            else:
                tag = f"recall={r['new_recall']:.2f}%" if r['new_recall'] is not None else "no recall line"
                print(f"  {gid:12} {tag}")
            n_ok += 1
        except Exception as e:
            print(f"  {gid:12} ERR {e}")
            n_err += 1

    print(f"\nDone: {n_ok} re-enriched, {n_err} errors")
    return 0


if __name__ == "__main__":
    sys.exit(main())
