"""domains.basketball_nba.asof_quarter_shape_full -- the 2024-25 half of asof_quarter_shape.

S111 (b). ``asof_quarter_shape.parquet`` was built from ``linescores.parquet`` alone (1,313
rows, season 2025-26), so on the gate corpus's frozen last-800 screen window it covered 282
of 800 rows (35.2 pct) and the family never reached the frozen 0.8 coverage floor (S85
section 2.3). The missing half is already on disk: ``linescores_2024_25.parquet`` (1,321
rows, 2024-10-22 .. 2025-06-22), keyed by the ESPN ``event_id`` -- and
``espn_nba_game_bridge.parquet`` is the EXACT ESPN-to-NBA map (1,299 rows, every one
``match_confidence == "exact"``), which is the join the S85 memo names.

TWO THINGS THIS FIXES, AND NOTHING ELSE:

1. HISTORY. The as-of walk runs over the UNION of both shards in one chronological pass, so
   a 2025-26 game's trailing quarter-shape now sees the team's 2024-25 games as prior rows.
   That is the same strictly-before rule (``asof_common.walk_forward_asof`` snapshot BEFORE
   update, debut -> NaN); nothing about the rule changes, only how far back history reaches.
2. THE KEY. ``_attach_game_id`` joins (date, canonical abbr) -> ``games.parquet`` and misses
   157 of 1,313 rows. The bridge is an exact per-event id map, so it is applied FIRST and the
   date+abbr join fills only what the bridge does not carry. A row with neither stays NaN --
   unmatched rows drop out of the gate alignment, they are never guessed.

The 2025-26 rows' as-of VALUES move (they now have real prior history where they previously
had none). That is correct and it costs no landed number: ``nba_quarter_shape`` has never
produced a screen -- it was UNCOVERED at T0 in S85 and all-NaN before that.

Writes through ``ops.safe_parquet_write.write_parquet_atomic`` -- refuse-to-shrink + atomic
replace (S95). NETWORK: zero. ASCII only.
ACCURACY / CALIBRATION ONLY -- NO MARKET EDGE CLAIMED.

Test: python -m pytest \
      domains/basketball_nba/test_asof_quarter_shape_full.py -q
"""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Optional

import pandas as pd

from domains.basketball_nba.asof_quarter_shape import build_asof_quarter_shape
from scripts.platformkit.ops.safe_parquet_write import write_parquet_atomic

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DATA = _REPO_ROOT / "data" / "domains" / "basketball_nba"
SHARDS = ("linescores_2024_25.parquet", "linescores.parquet")
BRIDGE = _DATA / "espn_nba_game_bridge.parquet"
OUT = _DATA / "asof_quarter_shape.parquet"


def union_linescores(shards: Optional[list] = None) -> pd.DataFrame:
    """Both linescores shards as one date-ordered frame, deduplicated on the ESPN event_id."""
    paths = [_DATA / name for name in SHARDS] if shards is None else [Path(p) for p in shards]
    frame = pd.concat([pd.read_parquet(p) for p in paths if p.exists()], ignore_index=True)
    frame["event_id"] = frame["event_id"].astype(str)
    frame = frame.drop_duplicates("event_id", keep="first")
    return frame.sort_values("date", kind="mergesort").reset_index(drop=True)


def bridge_game_ids(bridge: Optional[pd.DataFrame] = None) -> pd.Series:
    """ESPN event_id -> NBA game_id, from the exact-match bridge only."""
    frame = pd.read_parquet(BRIDGE) if bridge is None else bridge
    frame = frame[frame["match_confidence"].astype(str) == "exact"]
    frame = frame.dropna(subset=["game_id"]).drop_duplicates("event_id", keep="first")
    return frame.set_index(frame["event_id"].astype(str))["game_id"].astype(str)


def attach_bridge_key(result: pd.DataFrame, bridge: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    """Bridge id first, existing (date, abbr) join second; neither -> NaN, never a guess."""
    mapped = result["event_id"].astype(str).map(bridge_game_ids(bridge))
    result = result.copy()
    result["game_id"] = mapped.where(mapped.notna(), result["game_id"])
    return result


def build_full(out_path: Optional[Path] = None, *, linescores: Optional[pd.DataFrame] = None,
               games: Optional[pd.DataFrame] = None,
               bridge: Optional[pd.DataFrame] = None) -> Path:
    """Rebuild asof_quarter_shape over BOTH shards with the bridge key; atomic, no shrink."""
    dest = Path(out_path) if out_path is not None else OUT
    frame = union_linescores() if linescores is None else linescores
    # ponytail: the frozen builder writes its own parquet, so it writes a scratch file next to
    # the target and we re-write that atomically. Forking its walk to return a frame instead
    # would leave two maintained copies of the leak-free pass.
    scratch = dest.with_name("%s.build.parquet" % dest.stem)
    try:
        build_asof_quarter_shape(linescores=frame, games=games, out_path=str(scratch))
        result = pd.read_parquet(scratch)
    finally:
        scratch.unlink(missing_ok=True)
    return write_parquet_atomic(attach_bridge_key(result, bridge), dest)


def _cli() -> None:
    parser = argparse.ArgumentParser(description="Fold both linescores shards into asof_quarter_shape")
    parser.add_argument("--out-path", default=None)
    args = parser.parse_args()
    path = build_full(None if args.out_path is None else Path(args.out_path))
    frame = pd.read_parquet(path)
    print("asof_quarter_shape: %d rows, %d with an NBA game_id -> %s"
          % (len(frame), int(frame["game_id"].notna().sum()), path))


if __name__ == "__main__":
    _cli()


__all__ = ["build_full", "union_linescores", "bridge_game_ids", "attach_bridge_key", "SHARDS", "OUT"]
