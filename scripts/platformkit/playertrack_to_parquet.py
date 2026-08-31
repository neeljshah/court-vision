"""Aggregate data/nba/playertrackv3_*.json into one player-GAME-grain parquet.

Closes the gap named in .planning/NOW.md 2026-08-16b: 972 harvested games /
25,699 player-game tracking rows existed only as raw JSON; persisted parquets
were player-season grain with no game_id. Output keeps every field + gameId.

Run: python scripts/platformkit/playertrack_to_parquet.py
"""
from __future__ import annotations

import glob
import json
import os
import sys

import pandas as pd

SRC_GLOB = os.path.join("data", "nba", "playertrackv3_*.json")
OUT_PATH = os.path.join("data", "nba", "player_tracking_games.parquet")


def build(src_glob: str = SRC_GLOB, out_path: str = OUT_PATH) -> pd.DataFrame:
    files = sorted(glob.glob(src_glob))
    if not files:
        raise FileNotFoundError(f"no files match {src_glob}")
    frames = []
    for f in files:
        with open(f, encoding="utf-8") as fh:
            rows = json.load(fh)
        if rows:  # ponytail: skip empty games silently; count reported below
            frames.append(pd.DataFrame(rows))
    df = pd.concat(frames, ignore_index=True)
    df.to_parquet(out_path, index=False)
    print(f"files={len(files)} nonempty={len(frames)} rows={len(df)} "
          f"cols={len(df.columns)} games={df['gameId'].nunique()} "
          f"players={df['personId'].nunique()} -> {out_path}")
    return df


if __name__ == "__main__":
    d = build()
    # self-check: player-game grain, identity intact
    assert d["gameId"].nunique() > 900, "expected ~972 games"
    assert not d.duplicated(["gameId", "personId"]).any(), "dup player-game rows"
    assert d["personId"].notna().all()
    sys.stdout.write("SELF-CHECK OK\n")
