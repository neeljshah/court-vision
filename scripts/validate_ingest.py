#!/usr/bin/env python3
"""validate_ingest.py — Quality check one game's local backup vs the
readiness thresholds.

Reads C:\\Users\\neelj\\nba-data-backup\\tracking\\<game_id>\\ and reports:
  * file presence (8 expected files)
  * row counts (tracking_data, features)
  * real_player_name_pct on tracking_data
  * pbp_matched mean on possessions_enriched (target >= 0.90)
  * made fill rate on shot_log_enriched (target >= 0.70)
  * nonzero rates of defender_dist_mean_90, paint_pressure_90 (target >= 80%)
  * contest_arm_angle nonzero rate (probe for pose issue)

Usage:
    python scripts/validate_ingest.py 0022500280
    python scripts/validate_ingest.py --all       # all dirs under nba-data-backup
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

BACKUP = Path(r"C:\Users\neelj\nba-data-backup\tracking")

EXPECTED = [
    "tracking_data.csv",
    "possessions.csv",
    "shot_log.csv",
    "possessions_enriched.csv",
    "shot_log_enriched.csv",
    "features.csv",
    "jersey_name_map.json",
    "player_clip_stats.csv",
]


def _check(game_id: str) -> dict:
    d = BACKUP / game_id
    out: dict = {"game_id": game_id, "ok": True, "files": {}, "metrics": {}}
    if not d.is_dir():
        out["ok"] = False
        out["error"] = f"missing dir {d}"
        return out

    for f in EXPECTED:
        p = d / f
        out["files"][f] = {
            "exists": p.exists(),
            "bytes": p.stat().st_size if p.exists() else 0,
        }
        if not p.exists():
            out["ok"] = False

    # tracking_data
    td = d / "tracking_data.csv"
    if td.exists() and td.stat().st_size > 0:
        try:
            df = pd.read_csv(td, low_memory=False)
            out["metrics"]["tracking_rows"] = len(df)
            if "player_name" in df.columns:
                real = df["player_name"].notna() & (df["player_name"] != "")
                if real.any():
                    real = real & ~df["player_name"].astype(str).str.match(
                        r"^placeholder", case=False, na=False
                    )
                out["metrics"]["real_player_name_pct"] = round(
                    100.0 * real.mean(), 1
                )
            if "contest_arm_angle" in df.columns:
                ca = pd.to_numeric(df["contest_arm_angle"], errors="coerce")
                nz = (ca.fillna(0) > 0).mean()
                out["metrics"]["contest_arm_angle_nonzero_pct"] = round(
                    100.0 * nz, 1
                )
            if "ankle_x" in df.columns:
                ax = pd.to_numeric(df["ankle_x"], errors="coerce")
                out["metrics"]["ankle_x_notna_pct"] = round(
                    100.0 * ax.notna().mean(), 1
                )
        except Exception as e:
            out["metrics"]["tracking_err"] = str(e)[:120]

    # possessions_enriched
    pe = d / "possessions_enriched.csv"
    if pe.exists() and pe.stat().st_size > 0:
        try:
            df = pd.read_csv(pe, low_memory=False)
            out["metrics"]["possessions_rows"] = len(df)
            if "pbp_matched" in df.columns:
                pm = pd.to_numeric(df["pbp_matched"], errors="coerce").fillna(0)
                out["metrics"]["pbp_matched_pct"] = round(100.0 * pm.mean(), 1)
        except Exception as e:
            out["metrics"]["poss_err"] = str(e)[:120]

    # shot_log_enriched
    se = d / "shot_log_enriched.csv"
    if se.exists() and se.stat().st_size > 0:
        try:
            df = pd.read_csv(se, low_memory=False)
            out["metrics"]["shots_rows"] = len(df)
            if "made" in df.columns:
                m = pd.to_numeric(df["made"], errors="coerce")
                out["metrics"]["shots_made_fill_pct"] = round(
                    100.0 * m.notna().mean(), 1
                )
        except Exception as e:
            out["metrics"]["shots_err"] = str(e)[:120]

    # features.csv
    fc = d / "features.csv"
    if fc.exists() and fc.stat().st_size > 0:
        try:
            df = pd.read_csv(fc, low_memory=False)
            out["metrics"]["features_rows"] = len(df)
            out["metrics"]["features_cols"] = len(df.columns)
            for col in ("defender_dist_mean_90", "paint_pressure_90",
                        "off_ball_dist_mean_90", "team_spacing_imputed"):
                if col in df.columns:
                    v = pd.to_numeric(df[col], errors="coerce").fillna(0)
                    out["metrics"][f"{col}_nonzero_pct"] = round(
                        100.0 * (v != 0).mean(), 1
                    )
        except Exception as e:
            out["metrics"]["features_err"] = str(e)[:120]

    return out


def _pp(r: dict) -> str:
    if "error" in r:
        return f"  [{r['game_id']}] {'OK' if r['ok'] else 'FAIL'}  {r['error']}"
    lines = [f"  [{r['game_id']}] {'OK' if r['ok'] else 'FAIL'}"]
    files = r["files"]
    missing = [f for f, v in files.items() if not v["exists"]]
    if missing:
        lines.append(f"    missing files: {missing}")
    m = r["metrics"]
    if m:
        for k, v in m.items():
            lines.append(f"    {k:35} = {v}")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("game_id", nargs="?")
    ap.add_argument("--all", action="store_true",
                    help="Validate every game dir under nba-data-backup/tracking/")
    ap.add_argument("--from-log", action="store_true",
                    help="Validate every game marked OK in .ingest_log.csv")
    ap.add_argument("--json", action="store_true",
                    help="Print machine-readable JSON to stdout")
    ap.add_argument("--write-snapshot", action="store_true",
                    help="Persist a .quality.json snapshot inside each game dir")
    args = ap.parse_args()

    if args.all:
        ids = sorted(p.name for p in BACKUP.iterdir() if p.is_dir())
    elif args.from_log:
        # Validate every game logged OK in .ingest_log.csv (one level above
        # BACKUP, since BACKUP points at the tracking/ subdir).
        log = BACKUP.parent / ".ingest_log.csv"
        ids = []
        if log.exists():
            import csv as _csv
            with open(log, newline="") as f:
                for row in _csv.DictReader(f):
                    if (row.get("status") == "OK"
                            and row.get("game_id") not in ids):
                        ids.append(row["game_id"])
    elif args.game_id:
        ids = [args.game_id]
    else:
        ap.print_help()
        return 1

    results = [_check(gid) for gid in ids]
    if args.write_snapshot:
        for r in results:
            snap = BACKUP / r["game_id"] / ".quality.json"
            try:
                snap.write_text(json.dumps(r, indent=2))
            except Exception as e:
                print(f"  [snapshot] failed for {r['game_id']}: {e}")
    if args.json:
        print(json.dumps(results, indent=2))
    else:
        for r in results:
            print(_pp(r))
    n_ok = sum(1 for r in results if r["ok"])
    print(f"\nSummary: {n_ok}/{len(results)} games complete")
    return 0 if n_ok == len(results) else 2


if __name__ == "__main__":
    sys.exit(main())
