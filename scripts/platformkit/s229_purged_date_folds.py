"""S229 date-fold OOS helper with a symmetric one-day embargo.

Preregistration: docs/evidence/harness/S229_ATTEMPT2_PREREG_2026-09-04.md
Pre-seal SHA-256: 6ca56099a0bac5067f68740ae7d9ac2bdbf1d2c6fa71e75728ace6e1210ef1e7
"""
from __future__ import annotations

from typing import Iterator

import numpy as np
import pandas as pd

EMBARGO_DAYS = 1


def purged_date_folds(frame: pd.DataFrame, folds: int = 4, *,
                      date_col: str = "game_date", game_col: str = "game_id",
                      embargo_days: int = EMBARGO_DAYS) -> Iterator[tuple[int, pd.DataFrame, pd.DataFrame]]:
    """Yield expanding OOS date folds with cluster purge and symmetric embargo."""
    if embargo_days <= 0:
        raise ValueError("S229 requires a nonzero symmetric embargo")
    dates = np.array(sorted(frame[date_col].unique()))
    blocks = np.array_split(dates, folds + 1)
    for fold, test_dates in enumerate(blocks[1:], start=1):
        first = pd.Timestamp(str(test_dates[0])).normalize()
        test = frame[frame[date_col].isin(test_dates)].copy()
        train = frame[pd.to_datetime(frame[date_col]).dt.normalize() < first].copy()
        train = train[pd.to_datetime(train[date_col]).dt.normalize() < first - pd.Timedelta(days=embargo_days)]
        test_games = set(test[game_col])
        train = train[~train[game_col].isin(test_games)].copy()
        train_days = set(pd.to_datetime(train[date_col]).dt.normalize())
        test_days = set(pd.to_datetime(test[date_col]).dt.normalize())
        assert train_days.isdisjoint(test_days)
        assert not set(train[game_col]).intersection(test_games), "game-cluster purge violation"
        assert all(abs((train_day - test_day).days) > embargo_days
                   for train_day in train_days for test_day in test_days), "symmetric embargo violation"
        if train.empty:
            raise RuntimeError("CLOSED AT LIMIT: embargo left no training rows")
        yield fold, train, test
