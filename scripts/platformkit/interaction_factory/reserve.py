"""scripts.platformkit.interaction_factory.reserve -- RESERVED_CORPUS_SPEC.md
R1/R5: split a builder's frame into a DISCOVERY slice (what the factory fits)
and a RESERVE slice (held out for M21 independent-corpus replication), named
so the replication join is mechanical (R3).

R1: a literal "season" column -> reserve = the most recent COMPLETE season
    (a season is complete iff a LATER season has rows -- i.e. every distinct
    season value except the max is complete; "most recent complete" = the
    2nd-highest distinct value). <2 distinct seasons -> no split (R5).
    A "game_date"/"date" column (no "season") -> reserve = trailing 25% of
    rows ordered by that column (stable sort).
R5: no candidate column present at all -> (frame, None), unchanged.

The MIN_N*2-too-small-to-split gate (R5's other trigger) is the CALLER's
job (runner.py already knows MIN_N) -- this module only knows how to split
once asked; it never second-guesses whether a split is worth doing.
"""
from __future__ import annotations

from typing import Optional, Tuple

import pandas as pd

DATE_COL_CANDIDATES = ("game_date", "date", "season")


def reserve_mask(frame: pd.DataFrame,
                  date_col_candidates: Tuple[str, ...] = DATE_COL_CANDIDATES,
                  ) -> Tuple[pd.DataFrame, Optional[str]]:
    """Returns (discovery_frame, reserve_name). reserve_name is None when no
    time axis is present, or a season axis exists but has <2 distinct values
    (degenerate -- no "complete" season to reserve, same R5 honesty as no
    axis at all)."""
    axis_col = next((c for c in date_col_candidates if c in frame.columns), None)
    if axis_col is None:
        return frame, None

    if axis_col == "season":
        seasons = sorted(frame[axis_col].dropna().unique())
        if len(seasons) < 2:
            return frame, None
        reserve_val = seasons[-2]  # most recent COMPLETE season
        discovery = frame[frame[axis_col] != reserve_val].reset_index(drop=True)
        return discovery, str(reserve_val)

    # date-like axis (game_date/date) -> trailing 25% of rows, stable sort.
    ordered = frame.sort_values(axis_col, kind="mergesort")
    cut = int(len(ordered) * 0.75)
    discovery = ordered.iloc[:cut].reset_index(drop=True)
    return discovery, "trailing_25pct_by_%s" % axis_col


__all__ = ["reserve_mask", "DATE_COL_CANDIDATES"]
