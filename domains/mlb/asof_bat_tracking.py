"""domains.mlb.asof_bat_tracking -- leak-free trailing join of Statcast
bat-tracking leaderboard snapshots onto PA rows.

Baseball Savant's bat-tracking leaderboard is a SEASON-CUMULATIVE stat
computed at query time (one row per player, no per-PA date). Its `year`
query param is silently ignored by Savant's endpoint -- confirmed by direct
byte-for-byte diff: the 2024/2025/2026-labeled leaderboard CSVs on disk are
identical (see docs/research/bat_tracking_asof_2026-07-11.md and
docs/research/bat_tracking_gate_rerun_2026-07-11.md, an earlier lane's
premise check + puller fix). The current consolidated file therefore stores
one row per (player id, as_of DATE the puller actually ran), never a fake
season label.

The only leak-free way to condition a PA outcome on this stat is a
snapshot-before-game join: use the most recent snapshot captured STRICTLY
BEFORE the PA's game_date. A same-day or later snapshot already contains
that PA's own contribution to the season aggregate -- raw same-day values
LEAK, per the standing landmine this module exists to avoid.

data/cache/statcast/leaderboards/bat_tracking_consolidated.parquet carries
exactly ONE as_of date today (2026-07-09, 592 rows -- confirmed by direct
read this session). More dates accrue as the daily puller runs; this
builder is generic so it starts returning real trailing joins the moment a
PA's game_date falls after a second captured as_of date.

NETWORK: zero. Pure pandas (merge_asof does the strictly-prior lookup
natively -- no custom nearest-prior loop).
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

_REPO_ROOT = Path(__file__).resolve().parents[2]
SNAPSHOT_PATH = _REPO_ROOT / "data" / "cache" / "statcast" / "leaderboards" / "bat_tracking_consolidated.parquet"

TRAILING_COLS = ("avg_bat_speed", "swing_length")


def load_snapshots(path: Path = SNAPSHOT_PATH) -> pd.DataFrame:
    """id / as_of (parsed to Timestamp) / TRAILING_COLS, sorted by id, as_of."""
    df = pd.read_parquet(path, columns=["id", "as_of", *TRAILING_COLS])
    df["as_of"] = pd.to_datetime(df["as_of"])
    return df.sort_values(["id", "as_of"]).reset_index(drop=True)


def join_asof_trailing(pa: pd.DataFrame, snapshots: pd.DataFrame,
                        pa_id_col: str = "batter", pa_date_col: str = "game_date") -> pd.DataFrame:
    """Strictly-prior as-of join: for each row of `pa`, attach the most
    recent snapshot with as_of < that row's date for the same player id.
    Rows with no qualifying prior snapshot get NaN trailing columns (never
    silently 0-filled) -- the leak guard this module exists for. Returns a
    frame aligned 1:1 with `pa`'s original row order/index (safe to
    pd.concat back onto it column-wise).
    """
    left = pa[[pa_id_col, pa_date_col]].copy()
    left[pa_date_col] = pd.to_datetime(left[pa_date_col])
    left["_row"] = range(len(left))
    left = left.sort_values(pa_date_col, kind="mergesort")

    right = (snapshots.rename(columns={"id": pa_id_col, "as_of": pa_date_col})
              .sort_values(pa_date_col, kind="mergesort"))

    joined = pd.merge_asof(
        left, right, on=pa_date_col, by=pa_id_col,
        direction="backward", allow_exact_matches=False,  # strictly prior -- same-day leak guard
    ).sort_values("_row", kind="mergesort").drop(columns="_row").reset_index(drop=True)
    return joined[list(TRAILING_COLS)]
