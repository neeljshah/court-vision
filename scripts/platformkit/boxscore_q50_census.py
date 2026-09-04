"""Filename-only candidate selection for the S262 store census."""

from __future__ import annotations

from pathlib import Path


_STAT_MARKERS = ("pts", "points", "reb", "rebounds", "ast", "assists")
_SHAPE_MARKERS = ("q10", "q50", "q90", "quantile", "sample", "distribution")


def is_distribution_candidate(path: str | Path) -> bool:
    """Return whether a filename warrants a later column-level inspection.

    This function deliberately reads only the basename.  It does not imply
    that a matching file is an NBA store or that it contains usable fields.
    """
    name = Path(path).name.lower()
    return any(marker in name for marker in _STAT_MARKERS) and any(
        marker in name for marker in _SHAPE_MARKERS
    )
