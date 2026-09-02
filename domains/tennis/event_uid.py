"""domains.tennis.event_uid -- S48: an additive 1:1 event key for the tennis parquets.

MEASURED 2026-09-03 (Q8 premise check, and it FALSIFIES the register premise):
``event_id`` is NOT "players + season". Both spine builders construct it as
``<YYYYMMDD tourney start>-<tour>-<tourney_id>-<p1_id>-<p2_id>-<match_num>``
(ingest_sackmann._transform_matches, wta_corpus._transform_wta) and both already
run a dedup pass, so tournament AND date are already in the id and BOTH spines
are unique: matches.parquet 30,616/30,616 and wta_matches.parquet 11,270/11,270
distinct ids -- zero collisions.

The duplication lives ONLY in odds.parquet: 33,952 rows over 33,859 distinct ids,
93 ids appearing exactly twice (186 rows). Its cause is the JOIN, not the id:
``ingest_tennisdata_join.join_odds`` walks tennis-data rows and picks a Sackmann
match inside a 20-day window (``_DATE_WINDOW_DAYS = 20``), with nothing stopping
two tennis-data rows from two DIFFERENT tournaments claiming the same Sackmann
match. All 93 pairs differ in both ``tournament_td`` and ``date_td``.

``event_uid`` is ADDITIVE and never replaces ``event_id``:
  spine -- ``event_uid == event_id`` (uniqueness asserted, not assumed).
  odds  -- inside a colliding group the row whose ``date_td`` sits closest to the
           tourney start date encoded in the id keeps ``event_uid == event_id``;
           every further claimant becomes ``<event_id>@<YYYYMMDD>-<tournament
           slug>`` so it can never masquerade as the spine row. Measured on the
           93 real groups: winner median date gap 2 days vs loser 15 days, and
           the winner's tournament name agrees with the spine's 35/93 by naive
           substring against the loser's 1/93.

Calibration infrastructure only -- no dollar, ROI, profit or edge claim here.
"""
from __future__ import annotations

import argparse
import pathlib
import re

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

EVENT_UID = "event_uid"

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_TENNIS_DIR = _REPO_ROOT / "data" / "domains" / "tennis"
ODDS_PARQUET = _TENNIS_DIR / "odds.parquet"
SPINE_PARQUETS = (_TENNIS_DIR / "matches.parquet", _TENNIS_DIR / "wta_matches.parquet")


def _slug(value: object) -> str:
    """Lowercase alphanumeric tournament slug; stable and ASCII-only."""
    return re.sub(r"[^a-z0-9]+", "", str(value).lower())[:24] or "na"


def add_spine_event_uid(frame: pd.DataFrame) -> pd.DataFrame:
    """Append ``event_uid`` to a spine frame. Raises if ``event_id`` collides."""
    duplicated = int(frame["event_id"].duplicated().sum())
    if duplicated:
        raise ValueError(f"spine event_id is not unique: {duplicated} duplicate rows")
    out = frame.copy()
    out[EVENT_UID] = out["event_id"].astype(str)
    return out


def add_odds_event_uid(frame: pd.DataFrame) -> pd.DataFrame:
    """Append a collision-free ``event_uid`` to a joined odds frame.

    Existing columns and row order are untouched; ``event_uid`` is appended last.
    """
    out = frame.copy()
    if out.empty:
        out[EVENT_UID] = pd.Series(dtype=object)
        return out
    out = out.reset_index(drop=True)
    event_id = out["event_id"].astype(str)
    start = pd.to_datetime(event_id.str.slice(0, 8), format="%Y%m%d", errors="coerce")
    played = pd.to_datetime(out["date_td"], errors="coerce")
    gap = (played - start).dt.days.abs().fillna(10**6)
    played_key = played.dt.strftime("%Y%m%d").fillna("00000000")
    slug = out["tournament_td"].map(_slug)
    order = pd.DataFrame(
        {"eid": event_id, "gap": gap, "played": played_key, "slug": slug}
    )
    rank = (
        order.sort_values(["eid", "gap", "played", "slug"], kind="mergesort")
        .groupby("eid", sort=False)
        .cumcount()
        .reindex(out.index)
    )
    displaced = event_id + "@" + played_key + "-" + slug
    out[EVENT_UID] = event_id.where(rank.eq(0), displaced)
    collisions = int(out[EVENT_UID].duplicated().sum())
    if collisions:
        raise ValueError(f"event_uid still collides on {collisions} rows")
    return out


def _apply(path: pathlib.Path, builder) -> dict[str, int]:
    """Derive ``event_uid`` onto an existing parquet in place.

    Every pre-existing column must survive ``DataFrame.equals`` or nothing is
    written -- the migration is additive or it does not happen.
    """
    before = pd.read_parquet(path)
    if EVENT_UID in before.columns:
        return {"rows": len(before), "distinct_event_uid": int(before[EVENT_UID].nunique()),
                "written": 0}
    after = builder(before)
    if list(after.columns) != [*before.columns, EVENT_UID]:
        raise ValueError(f"non-additive column set for {path.name}")
    for column in before.columns:
        if not after[column].reset_index(drop=True).equals(before[column].reset_index(drop=True)):
            raise ValueError(f"{path.name}: existing column changed: {column}")
    pq.write_table(pa.Table.from_pandas(after, preserve_index=False), path, compression="snappy")
    return {"rows": len(after), "distinct_event_uid": int(after[EVENT_UID].nunique()), "written": 1}


def report() -> dict[str, dict[str, int]]:
    """Duplicate-id census over the three tennis parquets."""
    out: dict[str, dict[str, int]] = {}
    for path in (ODDS_PARQUET, *SPINE_PARQUETS):
        frame = pd.read_parquet(path)
        counts = frame["event_id"].value_counts()
        out[path.name] = {
            "rows": len(frame),
            "distinct_event_id": int(frame["event_id"].nunique()),
            "colliding_ids": int((counts > 1).sum()),
            "colliding_rows": int(counts[counts > 1].sum()),
            "has_event_uid": int(EVENT_UID in frame.columns),
        }
    return out


def _cli() -> None:
    parser = argparse.ArgumentParser(description="S48 tennis event_uid census / migration")
    parser.add_argument("--apply-odds", action="store_true",
                        help="derive event_uid onto data/domains/tennis/odds.parquet")
    parser.add_argument("--apply-spines", action="store_true",
                        help="derive event_uid onto the two spine parquets")
    args = parser.parse_args()
    if args.apply_odds:
        print("odds.parquet", _apply(ODDS_PARQUET, add_odds_event_uid))
    if args.apply_spines:
        for path in SPINE_PARQUETS:
            print(path.name, _apply(path, add_spine_event_uid))
    for name, stats in report().items():
        print(name, stats)


if __name__ == "__main__":
    _cli()
