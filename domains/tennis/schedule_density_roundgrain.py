"""domains.tennis.schedule_density_roundgrain -- the ROUND-GRAIN rebuild of the tennis
schedule-density and travel tables (S136).

S122 measured the defect these tables carry BY CONSTRUCTION. Sackmann publishes the TOURNEY
START date, not the match date: 1451/1451 ATP and 974/974 WTA tourneys carry exactly ONE
distinct `date`. The frozen builders therefore

  1. count a trailing time window that spans the player's WHOLE run at the event, including
     rounds played AFTER this match (46.2 pct of rows read `rest_days == 0`), and
  2. assign the grouped rolling result back onto a DUPLICATED date index, so the values are
     permuted across a player's rows within the tie -- the 2025 Wimbledon champion's seven
     matches serve `0,3,4,5,1,6,2`.

The served p1-minus-p2 `matches_last_7d` correlates +0.2616 with the OUTCOME. That is a leak,
not a signal, and it is why `tennis_schedule_density` / `tennis_travel_scouting` are refused in
`foundry/asof_supply.py`.

WHAT THIS MODULE CHANGES: the ORDER, and only the order. Every player's appearances are sorted
by `(tourney start date, ROUND)` using the Sackmann round codes, and a match at `(D, r)` counts
ONLY rows with `date < D`, or `date == D and round < r`. Strictly before at (date, round)
grain -- a row can never see itself, a sibling of equal round, or a later round of its own
event. The travel table's "previous resolved host city" is read under that same order.

DROPPED AS CLOSED AT LIMIT: `rest_days`. Real rest DAYS inside a tournament are not recoverable
from a tourney-grain date -- every round shares one date, so the honest answer is 0 for every
round after the first and the column would be a round-depth proxy wearing a rest name. It is
not in the round-grain table. `matches_last_7d` / `matches_last_14d` SURVIVE because they are
counts, and a same-tourney prior round is inside any trailing window by construction.

RESIDUAL TIE, recorded honestly: round-robin matches all carry the code `RR`, so a player's
group matches cannot be ordered among themselves (5.41 pct of ATP and 5.65 pct of WTA
appearance rows sit in a `(tourney, player, round)` tie, almost all of them `RR`). Under the
strictly-before rule tied rows do NOT see each other -- an UNDER-count, never a leak.

NEW TABLES BESIDE THE OLD ONES -- the S111 rule. The frozen parquets are the pinned `sources`
of families the FWER spec hashes; these are `*_rg` siblings and nothing existing moves.

NETWORK: zero. ASCII only. CALIBRATION ONLY -- no market edge claimed.

Test: python -m pytest domains/tennis/test_schedule_density_roundgrain.py -q
CLI:  python -m domains.tennis.schedule_density_roundgrain
"""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from domains.tennis.wta_schedule_travel import _via_scratch
from scripts.platformkit.geo import travel_scouting_tennis as travel
from scripts.platformkit.ops.safe_parquet_write import write_parquet_atomic

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DATA = _REPO_ROOT / "data" / "domains" / "tennis"
ATP_MATCHES = _DATA / "matches.parquet"
WTA_MATCHES = _DATA / "wta_matches.parquet"

# Sackmann round codes in the order they are PLAYED. `RR` (round robin) never co-occurs with a
# draw code in this corpus -- measured: the only round sets containing RR are {RR}, {RR,SF,F}
# and {RR,QF,SF,F} -- so its rank only has to sit above the draw rounds and below QF.
ROUND_ORDER = {"ER": 0, "R128": 1, "R64": 2, "R32": 3, "R16": 4, "RR": 5,
               "QF": 6, "SF": 7, "BR": 8, "F": 9}

_KEEP_COLS = ["event_id", "player_id", "player_name", "date", "round", "round_ord",
              "year", "surface", "matches_last_7d", "matches_last_14d"]


def round_ord(rounds: pd.Series) -> pd.Series:
    """Round codes -> played order. An unknown code is a hard failure, never a silent NaN that
    would sort to one end and quietly re-order a player's history."""
    out = rounds.astype(str).map(ROUND_ORDER)
    unknown = sorted(set(rounds.astype(str)[out.isna()]))
    if unknown:
        raise ValueError("unknown Sackmann round code(s): %s" % ", ".join(unknown))
    return out.astype(int)


def _prior_counts(dates: np.ndarray, ords: np.ndarray, days: int) -> np.ndarray:
    """For each row of one player's (date, round)-sorted history, the number of that player's
    rows STRICTLY BEFORE it at (date, round) grain whose date lies in `(D - days, D]` -- the
    pandas `rolling("<n>D")` window, closed on the right, minus every row at (D, r) itself.

    Two bounds, both read off the sorted arrays. `lo` is the first row inside the window.
    `first` is the first row carrying THIS row's own (date, round) key -- so the count stops
    before the whole tie, not merely before this row. A round-robin sibling therefore counts
    zero of its group, an UNDER-count; counting positions instead would let tied RR rows see
    each other, which is the leak class this module exists to remove.
    """
    lo = np.searchsorted(dates, dates - np.timedelta64(days, "D"), side="right")
    change = np.ones(len(dates), bool)
    change[1:] = (dates[1:] != dates[:-1]) | (ords[1:] != ords[:-1])
    first = np.maximum.accumulate(np.where(change, np.arange(len(dates)), 0))
    return (first - lo).astype(float)


def _long(spine: pd.DataFrame) -> pd.DataFrame:
    """One row per player-appearance (p1 and p2 of every match), carrying the round."""
    base = ["event_id", "date", "surface", "round"]
    sides = [spine[base + ["%s_id" % s, "%s_name" % s]].rename(
        columns={"%s_id" % s: "player_id", "%s_name" % s: "player_name"}) for s in ("p1", "p2")]
    long_df = pd.concat(sides, ignore_index=True).dropna(subset=["player_id"]).copy()
    long_df["date"] = pd.to_datetime(long_df["date"])
    long_df["round_ord"] = round_ord(long_df["round"])
    return long_df.sort_values(["player_id", "date", "round_ord"],
                              kind="mergesort").reset_index(drop=True)


def build_density(src: Path, out: Path) -> Path:
    """The round-grain schedule-density table for one spine."""
    long_df = _long(pd.read_parquet(src))
    long_df["year"] = long_df["date"].dt.year.astype(int)
    dates = long_df["date"].to_numpy("datetime64[ns]")
    ords = long_df["round_ord"].to_numpy()
    groups = long_df.groupby("player_id", sort=False).indices  # contiguous: already sorted
    for days in (7, 14):
        column = np.empty(len(long_df), float)
        for rows in groups.values():
            column[rows] = _prior_counts(dates[rows], ords[rows], days)
        long_df["matches_last_%dd" % days] = column
    out.parent.mkdir(parents=True, exist_ok=True)
    return write_parquet_atomic(long_df[_KEEP_COLS].reset_index(drop=True), out)


def build_travel(src: Path, out: Path) -> Path:
    """The round-grain travel table: the frozen city-resolution and descriptor walk, handed a
    frame already ordered by (player, date, round) so `prior_city_travel`'s original-row-order
    tiebreak IS the round order."""
    spine = pd.read_parquet(src)
    frame = travel.build_corpus(src)
    rounds = spine.drop_duplicates("event_id").set_index("event_id")["round"]
    frame["round"] = frame["event_id"].map(rounds)
    frame["round_ord"] = round_ord(frame["round"])
    frame["date"] = pd.to_datetime(frame["date"])
    frame = frame.sort_values(["player", "date", "round_ord"],
                              kind="mergesort").reset_index(drop=True)
    frame = travel.add_descriptors(frame)
    return _via_scratch(out.stem, out, lambda scratch: travel.write(frame, out=scratch))


def build_all(out_dir: Optional[Path] = None) -> list:
    """Both tables for both spines: `*_rg` (ATP) and `*_rg_wta`."""
    dest = Path(out_dir) if out_dir is not None else _DATA
    return [build_density(ATP_MATCHES, dest / "schedule_density_rg.parquet"),
            build_density(WTA_MATCHES, dest / "schedule_density_rg_wta.parquet"),
            build_travel(ATP_MATCHES, dest / "travel_scouting_rg.parquet"),
            build_travel(WTA_MATCHES, dest / "travel_scouting_rg_wta.parquet")]


def _cli() -> None:
    parser = argparse.ArgumentParser(description="Build the round-grain tennis schedule-density "
                                                 "and travel tables (S136)")
    parser.add_argument("--out-dir", default=None)
    args = parser.parse_args()
    for path in build_all(None if args.out_dir is None else Path(args.out_dir)):
        frame = pd.read_parquet(path)
        key = "player_id" if "player_id" in frame.columns else "player"
        print("%s: %d rows, %d players -> %s"
              % (Path(path).stem, len(frame), frame[key].nunique(), path))


if __name__ == "__main__":
    _cli()


__all__ = ["ROUND_ORDER", "round_ord", "build_density", "build_travel", "build_all",
           "ATP_MATCHES", "WTA_MATCHES"]
