"""WNBA on/off splits -- thin adapter over domains.basketball_nba.lineups.on_off:
load_shot_events/attach_lineup_to_shots/compute_on_off are reused UNMODIFIED
(generic over any stint/shot dataframe with the NBA schema, which the WNBA
stint table -- pbp_lineups_wnba.py -- already matches column-for-column).

One seam differs: NBA's on_off.py hardcodes reading its own NBA _BOX_SRC
inside main() (no CLI override) for the player-name attach -- joining WNBA
player_ids against the NBA box would silently mismatch/NaN every name, so
this file reimplements just that one join against the WNBA box instead of
calling NBA's main() at all.

Also patches pbp_lineups._period_length_s to WNBA's 600s/300s quarter/OT
length for the duration of the shot-loading step: load_shot_events computes
each shot's elapsed_s via the same imported _elapsed_s the stint builder
uses, and that function reads period length from pbp_lineups' own globals
at call time.

OUTPUT: data/cache/team_system/lineups/on_off_wnba_2026.parquet (same columns
as NBA's on_off_2025_26.parquet).

NETWORK: zero. CLI: python -m domains.basketball_wnba.lineups.on_off_wnba
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

import domains.basketball_nba.lineups.pbp_lineups as nba_pbp
from domains.basketball_nba.lineups.on_off import attach_lineup_to_shots, compute_on_off, load_shot_events
from domains.basketball_wnba.lineups.pbp_lineups_wnba import _BOX_SRC, _OUT_PATH as _STINTS_DEFAULT, _PBP_DIR, _wnba_period_length_s

REPO_ROOT = Path(__file__).resolve().parents[3]
_OUT_PATH = REPO_ROOT / "data" / "cache" / "team_system" / "lineups" / "on_off_wnba_2026.parquet"


def _attach_player_names(df: pd.DataFrame, box_df: pd.DataFrame) -> pd.DataFrame:
    box_df = box_df.assign(player_id=box_df["player_id"].astype("int64"))
    names = box_df.drop_duplicates(subset=["player_id"]).set_index("player_id")["player_name"]
    out = df.copy()
    out["player_name"] = out["player_id"].map(names)
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build WNBA on/off splits from stint table")
    parser.add_argument("--stints", type=str, default=str(_STINTS_DEFAULT))
    parser.add_argument("--out", type=str, default=str(_OUT_PATH))
    parser.add_argument("--pbp-dir", type=str, default=None, help="override input dir (default: wnba/cdn_backfill)")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args(argv)

    pbp_dir = Path(args.pbp_dir) if args.pbp_dir else _PBP_DIR
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
                shot_frames.append(load_shot_events(json.loads(fp.read_text(encoding="utf-8"))))
        shots_df = pd.concat(shot_frames, ignore_index=True) if shot_frames else pd.DataFrame(
            columns=["game_id", "team_id", "period", "elapsed_s", "person_id", "fgm", "fg3m", "fga"]
        )
        shots_df = attach_lineup_to_shots(stints_df, shots_df)
        result = compute_on_off(stints_df, shots_df)
    finally:
        nba_pbp._period_length_s = orig_period_len

    result = _attach_player_names(result, pd.read_parquet(_BOX_SRC))

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    result.to_parquet(out_path, index=False)
    print(f"players={len(result)} -> {out_path}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
