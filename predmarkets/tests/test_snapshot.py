"""Network smoke tests for the daily snapshotter."""

from __future__ import annotations

import os
import tempfile
from datetime import date

import pandas as pd
import pytest

from predmarkets.snapshot import (
    _derive_pm_category,
    snapshot_kalshi,
    snapshot_polymarket,
)

pytestmark = [
    pytest.mark.network,
    pytest.mark.skipif(
        bool(os.environ.get("SKIP_NETWORK_TESTS")),
        reason="SKIP_NETWORK_TESTS set",
    ),
]


_REQUIRED_COLS = (
    "venue", "market_id", "slug_or_ticker", "question_or_title", "category",
    "end_date", "status", "yes_bid", "yes_ask", "volume", "is_multivariate",
    "snapshot_ts",
)


def test_snapshot_polymarket_writes_parquet(tmp_path) -> None:
    path = snapshot_polymarket(date.today(), out_dir=str(tmp_path))
    assert os.path.exists(path)
    df = pd.read_parquet(path)
    assert len(df) >= 100, f"expected >= 100 PM rows, got {len(df)}"
    for col in _REQUIRED_COLS:
        assert col in df.columns, f"missing column {col}"
    assert set(df.status.unique()).issubset({"open", "resolved"})
    assert (df.yes_bid.notna().sum()) >= 50, "fewer than 50 rows have yes_bid populated"


def test_snapshot_kalshi_writes_parquet(tmp_path) -> None:
    path = snapshot_kalshi(date.today(), out_dir=str(tmp_path))
    assert os.path.exists(path)
    df = pd.read_parquet(path)
    assert len(df) >= 100, f"expected >= 100 Kalshi rows, got {len(df)}"
    for col in _REQUIRED_COLS:
        assert col in df.columns
    assert set(df.status.unique()).issubset({"open", "settled"})
    # Exclude_multivariate should zero out parlay markets in the snapshot.
    assert df.is_multivariate.sum() == 0, "snapshot leaked multivariate markets"
    # Categories should be present on at least the open rows (event-level join).
    open_rows = df[df.status == "open"]
    assert (open_rows.category != "").sum() >= len(open_rows) * 0.8, \
        "fewer than 80% of open Kalshi rows have a category"


@pytest.mark.parametrize("slug,question,expected", [
    ("when-will-bitcoin-hit-150k", "Will Bitcoin hit $150k", "Crypto"),
    ("nba-finals-2026", "Will the Lakers win the NBA finals", "Sports"),
    ("trump-2028-election", "Will Trump run in 2028", "Politics"),
    ("iran-ceasefire-may", "Iran ceasefire", "Geopolitics"),
    ("random-nonsense-market", "Some nonsense question", ""),
])
def test_derive_pm_category(slug: str, question: str, expected: str) -> None:
    assert _derive_pm_category(slug, question) == expected
