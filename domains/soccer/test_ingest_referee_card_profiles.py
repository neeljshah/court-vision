"""Per-file test for domains/soccer/ingest_referee_card_profiles.py.

Runs build() against the REAL on-disk match_stats.parquet (no mocking, per
codebase convention for these ingest tests) and checks the honesty-critical
invariants: no blank-referee rows leak through, per-match totals are
non-negative and internally consistent, and every declared output column
exists.

Run: python -m pytest domains/soccer/test_ingest_referee_card_profiles.py -q
"""
from __future__ import annotations

import pandas as pd
import pytest

from domains.soccer.ingest_referee_card_profiles import _KEEP_COLS, _SRC, build


@pytest.fixture(scope="module")
def out_df() -> pd.DataFrame:
    if not _SRC.exists():
        pytest.skip(f"source parquet not present in this checkout: {_SRC}")
    return build()


def test_columns_present(out_df: pd.DataFrame) -> None:
    assert list(out_df.columns) == _KEEP_COLS


def test_no_blank_referee_rows(out_df: pd.DataFrame) -> None:
    assert (out_df["referee"].astype(str).str.strip() == "").sum() == 0


def test_totals_are_sums_of_home_and_away(out_df: pd.DataFrame) -> None:
    raw = pd.read_parquet(_SRC)
    raw = raw[raw["referee"].astype(str).str.strip() != ""].reset_index(drop=True)
    assert (out_df["total_fouls"] == (raw["home_fouls"] + raw["away_fouls"])).all()
    assert (out_df["total_cards"] == (out_df["total_yellow"] + out_df["total_red"])).all()
    assert (out_df["total_fouls"] >= 0).all()


def test_year_range_sane(out_df: pd.DataFrame) -> None:
    assert out_df["year"].min() >= 2000
    assert out_df["year"].max() <= 2030


def test_fewer_rows_than_raw_source_due_to_blank_referee_drop(out_df: pd.DataFrame) -> None:
    raw = pd.read_parquet(_SRC)
    assert len(out_df) < len(raw)
    assert len(out_df) > 0


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
