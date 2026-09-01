"""Observed-player coverage-ceiling measurements for soccer broadcast video.

This is deliberately a diagnostic, not a tracker and not a harness input.
It counts only rows declared ``observation=observed``.  A caller supplies the
sampled frame range so frames with no detector rows remain zero-player frames.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from pathlib import Path

import pandas as pd


@dataclass(frozen=True)
class CoverageCeiling:
    """Distribution of distinct observed player identities per sampled frame."""

    first_frame: int
    last_frame: int
    sampled_frames: int
    observed_rows: int
    median_players: float
    p90_players: float
    max_players: int
    frames_at_least_14: int
    pct_at_least_14: float
    histogram: dict[int, int]


def measure(rows: pd.DataFrame, first_frame: int, last_frame: int) -> CoverageCeiling:
    """Measure observed identities, retaining zero-row frames in the denominator."""
    if last_frame < first_frame:
        raise ValueError("last_frame must be at least first_frame")
    required = {"frame", "track_id", "cls", "observation"}
    missing = required.difference(rows.columns)
    if missing:
        raise ValueError("rows missing columns: %s" % ", ".join(sorted(missing)))
    observed = rows[(rows["cls"] == "player") & (rows["observation"] == "observed")]
    observed = observed[observed["frame"].between(first_frame, last_frame)]
    counts = observed.groupby("frame")["track_id"].nunique()
    per_frame = [int(counts.get(frame, 0)) for frame in range(first_frame, last_frame + 1)]
    histogram = {count: per_frame.count(count) for count in sorted(set(per_frame))}
    threshold = sum(count >= 14 for count in per_frame)
    series = pd.Series(per_frame, dtype="int64")
    return CoverageCeiling(
        first_frame=first_frame,
        last_frame=last_frame,
        sampled_frames=len(per_frame),
        observed_rows=len(observed),
        median_players=float(series.median()),
        p90_players=float(series.quantile(0.90)),
        max_players=max(per_frame),
        frames_at_least_14=threshold,
        pct_at_least_14=100.0 * threshold / len(per_frame),
        histogram=histogram,
    )


def _main() -> int:
    parser = argparse.ArgumentParser(description="Measure observed soccer-player coverage ceiling")
    parser.add_argument("csv", type=Path)
    parser.add_argument("first_frame", type=int)
    parser.add_argument("last_frame", type=int)
    args = parser.parse_args()
    report = measure(pd.read_csv(args.csv), args.first_frame, args.last_frame)
    print(asdict(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
