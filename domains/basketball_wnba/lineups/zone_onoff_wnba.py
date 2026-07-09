"""WNBA defensive zone on/off splits -- thin adapter over
domains.basketball_nba.lineups.zone_onoff: load_shot_events (DEFENSE-keyed,
generic actionType/x/y/period/clock/teamId/personId schema, verified
identical on WNBA cdn_backfill PBP in source_shots.py) and compute_zone_onoff
are reused UNMODIFIED. Same three seams on_off_wnba.py already adapts for
this corpus: WNBA subdir/playbyplay.json PBP layout, the 600s/300s quarter/OT
monkeypatch of pbp_lineups._period_length_s, and the WNBA-box player-name
join -- reuses on_off_wnba.py's OWN _attach_player_names (which casts the
box's player_id to int64 before the join), NOT NBA on_off.py's bare version:
the box's player_id is object/str dtype (.astype('int64') for WNBA ids is a
standing landmine in this codebase) while zone_onoff's own player_id is
already int64, so the uncast NBA join silently maps every name to None.

OUTPUT: data/cache/team_system/lineups/zone_onoff_wnba_2026.parquet (same
columns as NBA's zone_onoff_<season>.parquet).

NETWORK: zero. CLI: python -m domains.basketball_wnba.lineups.zone_onoff_wnba
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

import domains.basketball_nba.lineups.pbp_lineups as nba_pbp
from domains.basketball_nba.lineups.on_off import attach_lineup_to_shots
from domains.basketball_nba.lineups.zone_onoff import compute_zone_onoff, load_shot_events
from domains.basketball_wnba.lineups.on_off_wnba import _attach_player_names
from domains.basketball_wnba.lineups.pbp_lineups_wnba import _BOX_SRC, _OUT_PATH as _STINTS_DEFAULT, _PBP_DIR, _wnba_period_length_s

REPO_ROOT = Path(__file__).resolve().parents[3]
_OUT_PATH = REPO_ROOT / "data" / "cache" / "team_system" / "lineups" / "zone_onoff_wnba_2026.parquet"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build WNBA defensive zone on/off splits")
    parser.add_argument("--stints", type=str, default=str(_STINTS_DEFAULT))
    parser.add_argument("--out", type=str, default=str(_OUT_PATH))
    parser.add_argument("--pbp-dir", type=str, default=None)
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
            fp = pbp_dir / str(gid) / "playbyplay.json"
            if fp.exists():
                shot_frames.append(load_shot_events(json.loads(fp.read_text(encoding="utf-8"))))
        shots_df = pd.concat(shot_frames, ignore_index=True) if shot_frames else pd.DataFrame(
            columns=["game_id", "team_id", "period", "elapsed_s", "person_id", "zone", "fgm", "fga"]
        )
        shots_df = attach_lineup_to_shots(stints_df, shots_df)
        result = compute_zone_onoff(stints_df, shots_df)
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
