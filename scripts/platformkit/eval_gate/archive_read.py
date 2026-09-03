"""S143 -- read an archived eval-gate series CSV without truncating '#' cluster ids.

The in-game cluster convention is `mlb:<TICKER>#<real_game_seq>`, so a
`pd.read_csv(..., comment="#")` read truncates every row and returns an all-NaN
loss column SILENTLY (measured: 9,669 of 9,669 MLB rows on
`s116_pooled_ingame_2026-09-03.csv`).  Two archives do carry a leading
`# prereg_sha256=... k_launch=...` seal line, so the comment convention is real --
it is just a HEADER convention, and only leading '#' lines are skipped here.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd


def read_series(path: Path) -> pd.DataFrame:
    """Read `path`, skipping only the leading `#` seal lines; '#' inside a cell survives."""
    skip = 0
    with open(path, "r", encoding="utf-8") as handle:
        for line in handle:
            if not line.startswith("#"):
                break
            skip += 1
    return pd.read_csv(path, skiprows=skip)
