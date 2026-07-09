"""Per-file tests for pa_outcome_v2_replicate_2024. Run with:
  cd /c/Users/neelj/nba-ai-system && python -m pytest \
    domains/mlb/matchup/test_pa_outcome_v2_replicate_2024.py -q

Fast (no real corpus IO) -- the real end-to-end run is `python -m
domains.mlb.matchup.pa_outcome_v2_replicate_2024` (several minutes over
711k rows), exercised separately.

Acceptance criteria:
  (a) NO FUTURE LEAKAGE: for every fold build_folds keeps, every train date
      is strictly before every test date (the mission's explicit leak-guard
      requirement for the fold scheme).
  (b) MIN_TRAIN_N floor: a month whose train pool is below the floor is
      skipped, not silently run on too little data.
  (c) a month with zero test-side dates (e.g. after the corpus ends) is
      skipped, not returned as a degenerate empty-test fold.
"""
from __future__ import annotations

import pandas as pd

from domains.mlb.matchup import pa_outcome_v2_replicate_2024 as m


def _synthetic_dates() -> pd.Series:
    # ~40 pitches/day so April (28-30 = 3 days) clears a low floor but not a high one.
    days = pd.date_range("2024-03-28", "2024-06-15", freq="D")
    return pd.Series(days.repeat(40))


def test_no_future_leakage_across_kept_folds():
    dates = _synthetic_dates()
    folds = m.build_folds(dates, min_train_n=50)
    assert folds, "expected at least one fold on this synthetic range"
    for month, cutoff, train_mask, test_mask in folds:
        train_max = dates[train_mask].max()
        test_min = dates[test_mask].min()
        assert train_max < test_min, (
            f"fold {month}: train_max={train_max} must be strictly before test_min={test_min}"
        )
        assert train_max < cutoff <= test_min


def test_min_train_n_floor_skips_thin_early_fold():
    dates = _synthetic_dates()
    # April train pool = only the 3 March days (~120 rows) -- a high floor must skip it.
    folds_low = m.build_folds(dates, min_train_n=50)
    folds_high = m.build_folds(dates, min_train_n=1000)
    months_low = [f[0] for f in folds_low]
    months_high = [f[0] for f in folds_high]
    assert "2024-04" in months_low
    assert "2024-04" not in months_high


def test_month_beyond_corpus_end_is_skipped():
    dates = _synthetic_dates()  # ends 2024-06-15, well before September
    folds = m.build_folds(dates, min_train_n=50)
    months = [f[0] for f in folds]
    assert "2024-09" not in months
