"""Cycle 91d sanity tests: rest_travel.parquet must cover 2025-26.

Backfill ensures is_b2b is non-zero in the live holdout window so the T1-C
b2b veteran probe (and every downstream caller of rest features) actually
fires instead of silently defaulting to 0.
"""
from __future__ import annotations

import os

import pandas as pd
import pytest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_PARQUET = os.path.join(PROJECT_DIR, "data", "rest_travel.parquet")

_EXPECTED_COLS = {
    "game_id",
    "team_abbreviation",
    "game_date",
    "is_b2b",
    "is_b3b",
    "miles_traveled",
    "altitude_ft",
}


@pytest.fixture(scope="module")
def df() -> pd.DataFrame:
    assert os.path.exists(_PARQUET), f"missing {_PARQUET} — run scripts/build_rest_travel_parquet.py"
    return pd.read_parquet(_PARQUET)


def test_parquet_has_nov_2025_rows(df: pd.DataFrame) -> None:
    """At least one team has a game logged in 2025-11."""
    nov = df[df["game_date"].astype(str).str.startswith("2025-11")]
    assert len(nov) > 0, "no November 2025 rows — backfill missed 2025-26"


def test_is_b2b_distribution_2025_26(df: pd.DataFrame) -> None:
    """B2B share in 2025-26 must match historical (~10-18%) so the holdout
    doesn't silently default every player-game to is_b2b=0.
    """
    gd = pd.to_datetime(df["game_date"])
    sub = df[gd >= pd.Timestamp("2025-10-01")]
    assert len(sub) > 0, "no 2025-26 rows in parquet"
    mean_b2b = float(sub["is_b2b"].mean())
    assert mean_b2b > 0.05, (
        f"is_b2b mean in 2025-26 is {mean_b2b:.4f} — expected >0.05 "
        f"(historical ~0.10-0.18). Backfill likely failed."
    )


def test_column_schema_unchanged(df: pd.DataFrame) -> None:
    """Callers (build_pergame_dataset, predict_slate.py, _RestTravel) key on
    exact column names — don't drift the schema.
    """
    assert set(df.columns) == _EXPECTED_COLS, (
        f"columns drift: have {sorted(df.columns)}, "
        f"expected {sorted(_EXPECTED_COLS)}"
    )
