#!/usr/bin/env python3
"""recompute_paint_pressure.py — Re-derive paint_pressure_* rolling features
from the homography-corrected tracking data.

The original `paint_pressure_90` / `paint_pressure_opp_90` columns in
features.csv were computed from `paint_count_own` / `paint_count_opp` (live
pipeline counts of players-in-paint per frame). Those counts were ~0 because
the live court_zone classifier hit "paint" on only 0.01% of player-frames
(see Open Issues #13).

This script recomputes paint pressure using the corrected `in_paint_fixed`
column from `tracking_data_corrected.csv` (produced by
`fix_homography_offset.py`). It also derives `paint_pressure_opp_90` by
joining with team info from tracking_data.csv.

Output: appends `paint_pressure_90_fixed`, `paint_pressure_opp_90_fixed`
columns to `tracking_data_corrected.csv`.

Usage:
    python scripts/recompute_paint_pressure.py 0022500279
    python scripts/recompute_paint_pressure.py --all
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

BACKUP = Path(r"C:\Users\neelj\nba-data-backup\tracking")
WINDOW = 90  # frames (~3 sec at 30 fps)


def recompute_one(game_id: str) -> dict:
    d = BACKUP / game_id
    fix_path  = d / "tracking_data_corrected.csv"
    td_path   = d / "tracking_data.csv"
    if not fix_path.exists():
        return {"game_id": game_id, "ok": False,
                "error": "tracking_data_corrected.csv missing — run fix_homography_offset.py first"}
    if not td_path.exists():
        return {"game_id": game_id, "ok": False,
                "error": "tracking_data.csv missing"}

    fix = pd.read_csv(fix_path, low_memory=False)
    if "in_paint_fixed" not in fix.columns:
        return {"game_id": game_id, "ok": False,
                "error": "in_paint_fixed missing (older fix file)"}

    # Pull team column from tracking_data.csv via (frame, player_id) merge
    td_team = pd.read_csv(td_path, usecols=["frame", "player_id", "team"],
                          low_memory=False)
    merged = fix.merge(td_team, on=["frame", "player_id"], how="left")
    merged["in_paint_fixed"] = pd.to_numeric(
        merged["in_paint_fixed"], errors="coerce"
    ).fillna(0)

    # Per-frame count of players in paint per team
    frame_paint = (
        merged.groupby(["frame", "team"])["in_paint_fixed"]
        .sum()
        .reset_index()
        .pivot(index="frame", columns="team", values="in_paint_fixed")
        .fillna(0)
    )

    # Identify the two TEAM cols (drop "referee" / "" / NaN)
    teams = [c for c in frame_paint.columns
             if c and str(c).lower() not in ("nan", "referee", "")]
    if len(teams) < 2:
        return {"game_id": game_id, "ok": False,
                "error": f"need 2 teams, found {teams}"}

    # Total players in paint per frame (any team)
    frame_paint["paint_any"] = frame_paint[teams].sum(axis=1)
    # Rolling pressure: fraction of last 90 frames where any player is in paint
    frame_paint = frame_paint.sort_index()
    frame_paint["paint_pressure_90_fixed"] = (
        (frame_paint["paint_any"] >= 1)
        .rolling(WINDOW, min_periods=1)
        .mean()
        .round(4)
    )

    # Per-team variants for "opp pressure"
    # For each player, opp_pressure is the OTHER team's paint_pressure
    per_team_pressure = {}
    for t in teams:
        per_team_pressure[t] = (
            (frame_paint[t] >= 1)
            .rolling(WINDOW, min_periods=1)
            .mean()
            .round(4)
        )

    # Re-shape: one row per (frame, team) → pressure of own + opp
    pressure_rows = []
    for t in teams:
        opp_t = [u for u in teams if u != t][0]
        for frame, own_p, opp_p in zip(
            frame_paint.index, per_team_pressure[t], per_team_pressure[opp_t]
        ):
            pressure_rows.append({
                "frame": int(frame),
                "team":  t,
                "paint_pressure_own_90_fixed": float(own_p),
                "paint_pressure_opp_90_fixed": float(opp_p),
            })
    pdf = pd.DataFrame(pressure_rows)

    # Merge back into the corrected file by (frame, team)
    merged_out = merged.merge(pdf, on=["frame", "team"], how="left")
    # Always derive paint_pressure_90_fixed (team-agnostic, the most important
    # signal) from the frame map. If per-team merge failed (e.g. corrupted
    # team column), at minimum we get the agnostic version.
    merged_out["paint_pressure_90_fixed"] = (
        merged_out["frame"].map(frame_paint["paint_pressure_90_fixed"])
    )
    # Defensive defaults for per-team cols when merge yielded no matches
    for col in ("paint_pressure_own_90_fixed",
                "paint_pressure_opp_90_fixed"):
        if col not in merged_out.columns:
            merged_out[col] = np.nan

    keep_cols = list(fix.columns) + [
        "paint_pressure_90_fixed",
        "paint_pressure_own_90_fixed",
        "paint_pressure_opp_90_fixed",
    ]
    # Dedup any keep_cols that already exist in fix.columns
    keep_cols = list(dict.fromkeys(keep_cols))
    out = merged_out[keep_cols].copy()
    out.to_csv(fix_path, index=False)

    # Diagnostic summary
    nz_own = (pd.to_numeric(out["paint_pressure_own_90_fixed"],
                            errors="coerce").fillna(0) > 0).mean()
    nz_opp = (pd.to_numeric(out["paint_pressure_opp_90_fixed"],
                            errors="coerce").fillna(0) > 0).mean()
    nz_any = (pd.to_numeric(out["paint_pressure_90_fixed"],
                            errors="coerce").fillna(0) > 0).mean()
    return {
        "game_id": game_id,
        "ok": True,
        "n_rows": len(out),
        "teams": teams,
        "paint_pressure_90_nz_pct":     round(100 * nz_any, 1),
        "paint_pressure_own_90_nz_pct": round(100 * nz_own, 1),
        "paint_pressure_opp_90_nz_pct": round(100 * nz_opp, 1),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("game_id", nargs="?")
    ap.add_argument("--all", action="store_true")
    args = ap.parse_args()

    if args.all:
        ids = sorted(p.name for p in BACKUP.iterdir() if p.is_dir())
    elif args.game_id:
        ids = [args.game_id]
    else:
        ap.print_help()
        return 1

    n_ok = 0
    for g in ids:
        r = recompute_one(g)
        if r["ok"]:
            n_ok += 1
            print(f"  [{g}] paint_pressure_90 nz={r['paint_pressure_90_nz_pct']}% "
                  f"own={r['paint_pressure_own_90_nz_pct']}% "
                  f"opp={r['paint_pressure_opp_90_nz_pct']}%  n={r['n_rows']}")
        else:
            print(f"  [{g}] FAIL: {r['error']}")
    print(f"\n{n_ok}/{len(ids)} recomputed.")
    return 0 if n_ok == len(ids) else 2


if __name__ == "__main__":
    sys.exit(main())
