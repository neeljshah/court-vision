"""domains.tennis.asof_wta_siblings -- the WTA half of asof_features / asof_return / asof_meta.

S111 (a). Three frozen tennis as-of tables are ATP-only because their default spine is
``matches.parquet`` (30,616 rows, 100 pct tour=="atp"). The gate corpus is 41,886 rows =
30,616 ATP + 11,270 WTA, so five tennis families sat at 58 pct coverage on the served
window and never reached the frozen 0.8 floor (S85 section 2.3). The WTA spine has been
on disk since ``wta_corpus.py``: ``wta_matches.parquet`` (11,270 rows), and the
``match_stats.parquet`` sidecar is already MIXED (28,696 WTA-tagged rows, 11,270/11,270
event_id overlap with the spine). The same pattern ``asof_hold_wta.parquet`` /
``asof_setdetail_wta.parquet`` already follow.

NO NEW WALK-FORWARD MATH. ``build_asof_features`` and ``build_asof_return`` are ALREADY
parametrised by ``(match_stats, matches, out_path)``, so the WTA table is the SAME builder
called with the WTA spine -- byte-for-byte the same strictly-before rule (snapshot BEFORE
the match's own rates enter the player's history; debut -> NaN). ``build_asof_meta`` reads
raw year CSVs by glob, so it takes one additive ``pattern`` argument and nothing else.

WHY A SEPARATE TABLE AND NOT A WIDER SPINE: the ATP parquets are frozen inputs of already
-screened families. Appending WTA rows to them would move a screened family's source; a
sibling table cannot. The bridge that unions the pair is declared in
``foundry/asof_supply.py``, which is consulted only for the pairs it lists.

Writes through ``ops.safe_parquet_write.write_parquet_atomic`` -- refuse-to-shrink + atomic
replace (S95).

NETWORK: zero. Every input is on disk. ASCII only.
ACCURACY / CALIBRATION ONLY -- NO MARKET EDGE CLAIMED.

Test: python -m pytest \
      domains/tennis/test_asof_wta_siblings.py -q
"""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Callable, Optional

import pandas as pd

from domains.tennis.asof_features import build_asof_features
from domains.tennis.asof_meta import build_asof_meta
from domains.tennis.asof_return import build_asof_return
from scripts.platformkit.ops.safe_parquet_write import write_parquet_atomic

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DATA = _REPO_ROOT / "data" / "domains" / "tennis"
WTA_MATCHES = _DATA / "wta_matches.parquet"
MATCH_STATS = _DATA / "match_stats.parquet"
WTA_RAW_PATTERN = "wta_matches_*.csv"

# (output stem, the builder, whether it consumes the match_stats sidecar)
BUILDERS: tuple[tuple[str, Callable, bool], ...] = (
    ("asof_features_wta", build_asof_features, True),
    ("asof_return_wta", build_asof_return, True),
    ("asof_meta_wta", build_asof_meta, False),
)


def wta_match_stats(match_stats: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    """The WTA-tagged rows of the MIXED sidecar -- the same '-wta-' event_id tag asof_hold_wta uses."""
    frame = pd.read_parquet(MATCH_STATS) if match_stats is None else match_stats
    return frame[frame["event_id"].astype(str).str.contains("-wta-", regex=False)].copy()


def _atomic(frame: pd.DataFrame, dest: Path) -> Path:
    return write_parquet_atomic(frame, dest)


def build_one(stem: str, builder: Callable, needs_stats: bool, *,
              spine: Optional[pd.DataFrame] = None,
              match_stats: Optional[pd.DataFrame] = None,
              out_dir: Optional[Path] = None) -> Path:
    """Run one frozen ATP builder against the WTA spine; atomic, refuse-to-shrink write."""
    spine = pd.read_parquet(WTA_MATCHES) if spine is None else spine
    dest = (Path(out_dir) if out_dir is not None else _DATA) / ("%s.parquet" % stem)
    dest.parent.mkdir(parents=True, exist_ok=True)
    # ponytail: the frozen builders write their own parquet, so we let them write a scratch
    # file next to the target and re-write it atomically. Copying their bodies to return a
    # frame instead would fork the leak-free walk into two maintained versions.
    scratch = dest.with_name("%s.build.parquet" % stem)
    try:
        if needs_stats:
            builder(match_stats=wta_match_stats(match_stats), matches=spine, out_path=str(scratch))
        else:
            builder(pattern=WTA_RAW_PATTERN, matches=spine, out_path=str(scratch))
        frame = pd.read_parquet(scratch)
    finally:
        scratch.unlink(missing_ok=True)
    return _atomic(frame, dest)


def build_all(out_dir: Optional[Path] = None) -> list:
    """Build all three WTA siblings; returns the written paths in BUILDERS order."""
    spine = pd.read_parquet(WTA_MATCHES)
    stats = pd.read_parquet(MATCH_STATS)
    return [build_one(stem, builder, needs, spine=spine, match_stats=stats, out_dir=out_dir)
            for stem, builder, needs in BUILDERS]


def _cli() -> None:
    parser = argparse.ArgumentParser(description="Build the WTA siblings of the ATP as-of tables")
    parser.add_argument("--out-dir", default=None)
    args = parser.parse_args()
    for path in build_all(None if args.out_dir is None else Path(args.out_dir)):
        frame = pd.read_parquet(path)
        print("%s: %d rows -> %s" % (path.stem, len(frame), path))


if __name__ == "__main__":
    _cli()


__all__ = ["build_all", "build_one", "wta_match_stats", "BUILDERS", "WTA_MATCHES", "MATCH_STATS"]
