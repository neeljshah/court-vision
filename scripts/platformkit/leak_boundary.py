"""Shared feature and chronology guards for offline evidence harnesses."""
from __future__ import annotations

from typing import Iterable

import numpy as np
import pandas as pd


def assert_no_same_game_columns(columns: Iterable[str]) -> None:
    """Reject raw same-game and team-identity columns at a feature boundary."""
    forbidden = []
    for name in columns:
        normalized = "".join(character for character in str(name).lower() if character.isalnum())
        if "samegame" in normalized or "teamid" in normalized:
            forbidden.append(str(name))
    if forbidden:
        raise ValueError("Same-game columns are forbidden: {0}".format(", ".join(forbidden)))


def embargo_indices(dates: Iterable[object], test_dates: Iterable[object], blocks: int) -> np.ndarray:
    """Return safe pre-test row positions after a date-block embargo.

    A one-block embargo removes the last training date before the test window,
    not the first (most distant) training date.  The latter off-by-one inversion
    keeps adjacent history and discards the history that should remain usable.
    """
    if blocks < 0:
        raise ValueError("blocks must be non-negative")
    all_dates = pd.Series(pd.to_datetime(list(dates), errors="raise")).reset_index(drop=True)
    held_out = pd.Series(pd.to_datetime(list(test_dates), errors="raise"))
    if held_out.empty:
        raise ValueError("test_dates must not be empty")
    cutoff = held_out.min()
    train_blocks = np.sort(all_dates[all_dates < cutoff].drop_duplicates().to_numpy())
    blocked = set(train_blocks[-blocks:]) if blocks else set()
    keep = (all_dates < cutoff) & ~all_dates.isin(blocked)
    return np.flatnonzero(keep.to_numpy())
