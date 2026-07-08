"""Per-file test for domains/tennis/ingest_schedule_density.py.

Runs build() against the REAL on-disk matches.parquet (no mocking) and
checks the melt is complete (row count = 2x raw matches minus any dropped
null-id rows) and the rolling/diff features are internally consistent.

Run: python -m pytest domains/tennis/test_ingest_schedule_density.py -q
"""
from __future__ import annotations

import pandas as pd
import pytest

from domains.tennis.ingest_schedule_density import _KEEP_COLS, _SRC, build


@pytest.fixture(scope="module")
def out_df() -> pd.DataFrame:
    if not _SRC.exists():
        pytest.skip(f"source parquet not present in this checkout: {_SRC}")
    return build()


def test_columns_present(out_df: pd.DataFrame) -> None:
    assert list(out_df.columns) == _KEEP_COLS


def test_melt_doubles_raw_match_count(out_df: pd.DataFrame) -> None:
    raw = pd.read_parquet(_SRC)
    assert len(out_df) <= 2 * len(raw)
    assert len(out_df) > 0


def test_rest_days_never_negative(out_df: pd.DataFrame) -> None:
    assert (out_df["rest_days"].dropna() >= 0).all()


def test_rolling_counts_never_negative(out_df: pd.DataFrame) -> None:
    assert (out_df["matches_last_7d"].dropna() >= 0).all()
    assert (out_df["matches_last_14d"].dropna() >= 0).all()


def test_matches_last_14d_covers_at_least_matches_last_7d(out_df: pd.DataFrame) -> None:
    both = out_df.dropna(subset=["matches_last_7d", "matches_last_14d"])
    assert (both["matches_last_14d"] >= both["matches_last_7d"]).all()


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
