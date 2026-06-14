"""domains.tennis.match_postmortem_eval — CLI reporting for the post-mortem layer.

Loads data/domains/tennis/postmortem.parquet (or builds it on-the-fly) and
prints the decided_by distribution on the full ATP corpus plus retirement rate.

KNOWLEDGE layer only.  Output is purely descriptive; no edge claim is made.

Usage
-----
  python -m domains.tennis.match_postmortem_eval [--no-write]

  --no-write   Build the postmortem DataFrame but skip writing parquet (dry run).
"""
from __future__ import annotations

import argparse
from pathlib import Path

from domains.tennis.match_postmortem import build_postmortem, write_postmortem


def main(no_write: bool = False) -> None:
    print("Loading data and building post-mortem …")
    df = build_postmortem()
    print(f"Built {len(df):,} postmortem records\n")

    dist = df["decided_by"].value_counts()
    total = len(df)
    print("decided_by distribution (DESCRIPTIVE — realized match stats, no edge claim):")
    for label, cnt in dist.items():
        print(f"  {label:<30s}  {cnt:>6,}  ({cnt / total:.1%})")

    ret_rate = df["retirement"].mean()
    print(f"\nRetirement rate (NOISE/CENSORING flag): {ret_rate:.3%}")
    print("  -> RETIREMENT_CENSORED rows must NOT be used as predictive labels.")

    if not no_write:
        path = write_postmortem(df)
        print(f"\nWrote: {path}")
    else:
        print("\n[dry run] skipped write")


def _cli() -> None:
    parser = argparse.ArgumentParser(
        description="Report decided_by distribution on the tennis post-mortem corpus."
    )
    parser.add_argument(
        "--no-write", action="store_true",
        help="Skip writing parquet output (dry run).",
    )
    args = parser.parse_args()
    main(no_write=args.no_write)


if __name__ == "__main__":
    _cli()
