"""WNBA gravity-proxy + lineup-spacing -- thin adapter over
domains.basketball_nba.lineups.gravity_spacing: build_gravity/build_spacing/
load_shot_events_xy plus on_off.attach_lineup_to_shots are all pure functions
over dataframes and are reused UNMODIFIED.

One seam differs: NBA's gravity_spacing.main() assumes a flat
<pbp_dir>/<gameId>.json filename with no CLI override -- WNBA's cdn_backfill
layout is <pbp_dir>/<gameId>/playbyplay.json (a subdir, not a flat file), so
this file reimplements just that file-loading loop + CLI glue (near-identical
shape to NBA's own main()) and calls the real machinery unmodified.

Also patches pbp_lineups._period_length_s to WNBA's 600s/300s quarter/OT
length while loading shots (load_shot_events_xy computes elapsed_s via the
same shared, imported _elapsed_s the stint builder patches).

OUTPUT: data/cache/team_system/lineups/gravity_proxy_wnba_2026.parquet,
        data/cache/team_system/lineups/lineup_spacing_wnba_2026.parquet

NETWORK: zero. CLI: python -m domains.basketball_wnba.lineups.gravity_spacing_wnba
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

import domains.basketball_nba.lineups.pbp_lineups as nba_pbp
from domains.basketball_nba.lineups.gravity_spacing import build_gravity, build_spacing, load_shot_events_xy
from domains.basketball_nba.lineups.on_off import attach_lineup_to_shots
from domains.basketball_wnba.lineups.pbp_lineups_wnba import _OUT_PATH as _STINTS_DEFAULT, _PBP_DIR, _wnba_period_length_s

REPO_ROOT = Path(__file__).resolve().parents[3]
_ON_OFF_DEFAULT = REPO_ROOT / "data" / "cache" / "team_system" / "lineups" / "on_off_wnba_2026.parquet"
_GRAVITY_OUT = REPO_ROOT / "data" / "cache" / "team_system" / "lineups" / "gravity_proxy_wnba_2026.parquet"
_SPACING_OUT = REPO_ROOT / "data" / "cache" / "team_system" / "lineups" / "lineup_spacing_wnba_2026.parquet"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build WNBA gravity-proxy + lineup-spacing claims inputs")
    parser.add_argument("--stints", type=str, default=str(_STINTS_DEFAULT))
    parser.add_argument("--on-off", type=str, default=str(_ON_OFF_DEFAULT))
    parser.add_argument("--pbp-dir", type=str, default=None, help="override input dir (default: wnba/cdn_backfill)")
    parser.add_argument("--gravity-out", type=str, default=str(_GRAVITY_OUT))
    parser.add_argument("--spacing-out", type=str, default=str(_SPACING_OUT))
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args(argv)

    pbp_dir = Path(args.pbp_dir) if args.pbp_dir else _PBP_DIR
    gravity_out, spacing_out = Path(args.gravity_out), Path(args.spacing_out)

    on_off_df = pd.read_parquet(args.on_off)
    gravity_df = build_gravity(on_off_df)
    gravity_out.parent.mkdir(parents=True, exist_ok=True)
    gravity_df.to_parquet(gravity_out, index=False)
    print(f"gravity_proxy rows={len(gravity_df)} -> {gravity_out}")

    stints_df = pd.read_parquet(args.stints)
    game_ids = stints_df["game_id"].unique()
    if args.limit:
        game_ids = game_ids[: args.limit]
        stints_df = stints_df[stints_df["game_id"].isin(game_ids)]

    orig_period_len = nba_pbp._period_length_s
    nba_pbp._period_length_s = _wnba_period_length_s
    try:
        shot_frames = []
        for gid in game_ids:
            fp = pbp_dir / str(gid) / "playbyplay.json"  # WNBA layout: subdir, not flat <gid>.json
            if fp.exists():
                shot_frames.append(load_shot_events_xy(json.loads(fp.read_text(encoding="utf-8"))))
        shots_xy_df = pd.concat(shot_frames, ignore_index=True) if shot_frames else pd.DataFrame(
            columns=["game_id", "team_id", "period", "elapsed_s", "person_id", "x", "y"]
        )
        shots_xy_df = attach_lineup_to_shots(stints_df, shots_xy_df)
        spacing_df = build_spacing(stints_df, shots_xy_df)
    finally:
        nba_pbp._period_length_s = orig_period_len

    spacing_out.parent.mkdir(parents=True, exist_ok=True)
    spacing_df.to_parquet(spacing_out, index=False)
    print(f"lineup_spacing rows={len(spacing_df)} -> {spacing_out}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
