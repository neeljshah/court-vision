"""G370 replacement fresh set: G366's sealed eligibility ladder on this pod's ledger.

The prereg's G366 fresh set (59 sections) was lost with the previous pod on
2026-09-10. This driver re-applies the SAME sealed ladder from `g366_fresh`
(census then every-k-th sample) to this pod's ledger, changing only the freshness
epoch (this pod's daemon start) and the sample target. No threshold moves; nothing
under `data/` is written.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from scripts.platformkit.tracking import g366_fresh


def build(ledger: Path, sections_dir: Path, sealed: Path, out: Path, epoch: int,
          target: int, pool: str) -> None:
    """Archive the census that decides eligibility, then seal the sample."""
    g366_fresh.FRESH_EPOCH = epoch
    g366_fresh.SAMPLE_TARGET = target
    g366_fresh.POOL = pool
    g366_fresh.census(ledger, sections_dir, sealed, out)
    g366_fresh.sample(out)


def main() -> None:
    parser = argparse.ArgumentParser(description="G370 replacement fresh set")
    parser.add_argument("--ledger", required=True, type=Path)
    parser.add_argument("--sections-dir", required=True, type=Path)
    parser.add_argument("--sealed", required=True, type=Path)
    parser.add_argument("--fresh-epoch", required=True, type=int)
    parser.add_argument("--target", required=True, type=int)
    parser.add_argument("--pool", default="G370_FRESH_POD_2026-09-10")
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    build(args.ledger, args.sections_dir, args.sealed, args.out, args.fresh_epoch,
          args.target, args.pool)


if __name__ == "__main__":
    main()
