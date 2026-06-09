"""build_team_reports.py — write one assembled dossier JSON per team.

Reads the 16 shipped atlas_team_*.parquet sections and writes
``data/cache/profiles/teams/<TRI>_dossier.json`` for every team. Pure
assembly over existing data — deterministic, $0/team, no external feeds.

Usage:
  python scripts/intel/build_team_reports.py                 # all 30 teams
  python scripts/intel/build_team_reports.py --team OKC       # one team -> stdout
  python scripts/intel/build_team_reports.py --no-write       # build, summarize only
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src.intel.team_report import (  # noqa: E402
    TEAMS_PROF_DIR, build_all_team_reports, build_team_report,
)


def _write(tri: str, dossier: dict) -> Path:
    TEAMS_PROF_DIR.mkdir(parents=True, exist_ok=True)
    path = TEAMS_PROF_DIR / f"{tri}_dossier.json"
    path.write_text(json.dumps(dossier, indent=2, default=str), encoding="utf-8")
    return path


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--team", default=None, help="single team tricode (else all)")
    ap.add_argument("--build-date", default=date.today().isoformat())
    ap.add_argument("--no-write", action="store_true")
    args = ap.parse_args()

    if args.team:
        d = build_team_report(args.team.upper(), build_date=args.build_date)
        if not args.no_write:
            p = _write(args.team.upper(), d)
            print(f"wrote {p}")
        print(json.dumps(d, indent=2, default=str))
        return

    reports = build_all_team_reports(build_date=args.build_date)
    written = 0
    print(f"{'TEAM':4s} {'COV%':>5s}  HOW THEY PLAY (truncated)")
    for tri, d in reports.items():
        if not args.no_write:
            _write(tri, d)
            written += 1
        cov = d["completeness"]["coverage_pct"]
        print(f"{tri:4s} {cov:5.1f}  {d['how_they_play'][:90]}")
    print(f"\n{'WROTE' if not args.no_write else 'BUILT'} {len(reports)} team dossiers"
          f"{'' if args.no_write else f' -> {TEAMS_PROF_DIR}'}")


if __name__ == "__main__":
    main()
