"""domains.tennis.wta_schedule_travel -- the WTA half of schedule_density / travel_scouting.

S122. `tennis_schedule_density` (469/800) and `tennis_travel_scouting` (454/800) sat under the
frozen 0.8 coverage floor for the same reason S111's three families did: their sources are
built from the ATP spine `matches.parquet` (30,616 rows, tour=="atp") while the tennis gate
corpus is 41,886 rows = 30,616 ATP + 11,270 WTA. `wta_matches.parquet` carries EVERY column
both builders read (`event_id, date, surface, tourney_name, p1_id, p2_id, p1_name, p2_name`,
zero nulls in all eight), so neither family is at limit on a missing column.

NO NEW MATH. Both builders are ALREADY parametrised by their spine:
`ingest_schedule_density.build(src, out)` and `travel_scouting_tennis.build_corpus(matches_path)`
+ `add_descriptors` + `write(df, out)`. The WTA table is those exact functions called with the
WTA spine, so the strictly-before rule is byte-for-byte the shared one:

  * schedule density: `groupby(player_id)["date"].diff()` (a player's FIRST appearance -> NaN)
    and a trailing-window rolling count minus the current row, over that player's own sorted
    history -- a match on date D sees only that player's matches strictly before D.
  * travel: `prior_city_travel` reads the player's PREVIOUS resolved host city; the first
    appearance in the corpus -> NaN.

WHY A SEPARATE TABLE AND NOT A WIDER SPINE (the S111 rule): the ATP parquets are the frozen
`sources` of families the FWER spec pins by hash. Appending WTA rows to them would move a
family's source; a sibling table cannot. The bridge that unions the pair is declared in
`foundry/asof_supply.py`, which is consulted only for the pairs it lists.

Writes through `ops.safe_parquet_write.write_parquet_atomic` -- atomic replace and
refuse-to-shrink (S95).

NETWORK: zero. Every input is on disk. ASCII only.
ACCURACY / CALIBRATION ONLY -- NO MARKET EDGE CLAIMED.

Test: python -m pytest domains/tennis/test_wta_schedule_travel.py -q
CLI:  python -m domains.tennis.wta_schedule_travel
"""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Optional

import pandas as pd

from domains.tennis.ingest_schedule_density import build as build_schedule_density
from scripts.platformkit.geo import travel_scouting_tennis as travel
from scripts.platformkit.ops.safe_parquet_write import write_parquet_atomic

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DATA = _REPO_ROOT / "data" / "domains" / "tennis"
WTA_MATCHES = _DATA / "wta_matches.parquet"


def _via_scratch(stem: str, dest: Path, writer) -> Path:
    """Let a frozen builder write its own parquet next to the target, then re-write it
    atomically. ponytail: copying the builders' bodies to return a frame instead would fork
    the strictly-before walk into two versions to keep in step -- the S111 shape."""
    scratch = dest.with_name("%s.build.parquet" % stem)
    try:
        writer(scratch)
        frame = pd.read_parquet(scratch)
    finally:
        scratch.unlink(missing_ok=True)
    dest.parent.mkdir(parents=True, exist_ok=True)
    return write_parquet_atomic(frame, dest)


def build_schedule_density_wta(spine: Optional[Path] = None,
                               out_dir: Optional[Path] = None) -> Path:
    """`ingest_schedule_density.build` run against the WTA spine."""
    dest = (Path(out_dir) if out_dir is not None else _DATA) / "schedule_density_wta.parquet"
    src = Path(spine) if spine is not None else WTA_MATCHES
    return _via_scratch("schedule_density_wta", dest,
                        lambda scratch: build_schedule_density(src=src, out=scratch))


def build_travel_scouting_wta(spine: Optional[Path] = None,
                              out_dir: Optional[Path] = None) -> Path:
    """`travel_scouting_tennis`'s own corpus + descriptor + stamp path, on the WTA spine."""
    dest = (Path(out_dir) if out_dir is not None else _DATA) / "travel_scouting_wta.parquet"
    src = Path(spine) if spine is not None else WTA_MATCHES
    frame = travel.add_descriptors(travel.build_corpus(src))
    return _via_scratch("travel_scouting_wta", dest,
                        lambda scratch: travel.write(frame, out=scratch))


def build_all(out_dir: Optional[Path] = None) -> list:
    """Build both WTA siblings; returns the written paths."""
    return [build_schedule_density_wta(out_dir=out_dir),
            build_travel_scouting_wta(out_dir=out_dir)]


def _cli() -> None:
    parser = argparse.ArgumentParser(description="Build the WTA siblings of the tennis "
                                                 "schedule-density and travel tables")
    parser.add_argument("--out-dir", default=None)
    args = parser.parse_args()
    for path in build_all(None if args.out_dir is None else Path(args.out_dir)):
        frame = pd.read_parquet(path)
        print("%s: %d rows, %d players -> %s" % (
            path.stem, len(frame),
            frame["player_id" if "player_id" in frame.columns else "player"].nunique(), path))


if __name__ == "__main__":
    _cli()


__all__ = ["build_all", "build_schedule_density_wta", "build_travel_scouting_wta", "WTA_MATCHES"]
