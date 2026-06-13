"""test_tennis_adapter_helpers.py — Unit tests for domains/tennis/adapter_helpers.py.

Focuses on _add_rest_days with synthetic match sequences.
No network, no disk, no adapter instantiation needed.
Python 3.9 compatible.  ≤300 LOC.
"""
from __future__ import annotations

import datetime as dt
import math
from typing import List

import pandas as pd
import pytest

from domains.tennis.adapter_helpers import _add_rest_days

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_df(
    rows: List[dict],
) -> pd.DataFrame:
    """Build a minimal match DataFrame expected by _add_rest_days.

    Required columns: date, p1_id, p2_id.
    Rows are already in chronological order (as walk_forward_elo guarantees).
    """
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# 1. Second match → correct integer rest-days = days since prior match
# ---------------------------------------------------------------------------

def test_second_match_correct_rest_days() -> None:
    """A player's second match gets rest_days = days since their first match."""
    rows = [
        {"date": "2024-01-01", "p1_id": 1, "p2_id": 2},
        {"date": "2024-01-08", "p1_id": 1, "p2_id": 3},  # 7 days later
    ]
    df = _make_df(rows)
    out = _add_rest_days(df)

    # p1 (player 1) in the second row: 8 days apart (Jan 1 → Jan 8 = 7 days)
    rest_a_row1 = out["rest_days_a"].iloc[1]
    assert rest_a_row1 == 7.0, (
        f"Expected 7 days rest for p1's second match, got {rest_a_row1}"
    )

    # p2 (player 2) in first row had no prior match → default 15.0
    rest_b_row0 = out["rest_days_b"].iloc[0]
    assert rest_b_row0 == 15.0, (
        f"Expected default 15.0 for p2's first ever match, got {rest_b_row0}"
    )


def test_rest_days_correct_for_multiple_gaps() -> None:
    """Multiple gap sizes all produce correct rest_days values."""
    rows = [
        {"date": "2024-03-01", "p1_id": 10, "p2_id": 20},  # row 0
        {"date": "2024-03-06", "p1_id": 20, "p2_id": 30},  # row 1 — p20 5 days later
        {"date": "2024-03-16", "p1_id": 10, "p2_id": 30},  # row 2 — p10 15d, p30 10d
    ]
    df = _make_df(rows)
    out = _add_rest_days(df)

    # row 1: p20 played on Mar 1 (as p2), now plays on Mar 6 → 5 days
    assert out["rest_days_a"].iloc[1] == 5.0

    # row 2: p10 played on Mar 1, now Mar 16 → 15 days
    assert out["rest_days_a"].iloc[2] == 15.0

    # row 2: p30 played on Mar 6 (as p2 in row 1), now Mar 16 → 10 days
    assert out["rest_days_b"].iloc[2] == 10.0


# ---------------------------------------------------------------------------
# 2. Back-to-back (0-day rest)
# ---------------------------------------------------------------------------

def test_back_to_back_zero_rest() -> None:
    """Player plays on the same calendar date twice → rest_days = 0."""
    rows = [
        {"date": "2024-06-01", "p1_id": 1, "p2_id": 2},
        {"date": "2024-06-01", "p1_id": 1, "p2_id": 3},  # same day, different opponent
    ]
    df = _make_df(rows)
    out = _add_rest_days(df)

    # First appearance: default 15.0
    assert out["rest_days_a"].iloc[0] == 15.0

    # Second match on same day: (Jun 1 - Jun 1).days = 0
    rest = out["rest_days_a"].iloc[1]
    assert rest == 0.0, f"Expected 0.0 rest for back-to-back, got {rest}"


# ---------------------------------------------------------------------------
# 3. First match → documented default (15.0, not NaN)
# ---------------------------------------------------------------------------

def test_first_match_default_is_15() -> None:
    """A player's very first match should get rest_days = 15.0 (documented default)."""
    rows = [
        {"date": "2024-01-01", "p1_id": 99, "p2_id": 100},
    ]
    df = _make_df(rows)
    out = _add_rest_days(df)

    ra = out["rest_days_a"].iloc[0]
    rb = out["rest_days_b"].iloc[0]

    assert ra == 15.0, f"Expected default 15.0 for p1 first match, got {ra}"
    assert rb == 15.0, f"Expected default 15.0 for p2 first match, got {rb}"

    # Confirm it is NOT NaN — the default is a concrete float, not missing
    assert not math.isnan(ra), "First-match rest_days must be 15.0, not NaN"
    assert not math.isnan(rb), "First-match rest_days must be 15.0, not NaN"


# ---------------------------------------------------------------------------
# 4. CRITICAL leak check: same-day match must not feed its own date as prior
# ---------------------------------------------------------------------------
#
# Implementation note: _add_rest_days uses a last_seen dict that is updated
# AFTER computing rest_days for the current row (row-by-row iteration).
# This means:
#   • A player's first match (not in last_seen yet) → default 15.0  ✓
#   • The current row's own date is NEVER in last_seen when we compute its rest  ✓
#   • There is NO pandas-style "<= date" filter — it's an imperative dict updated
#     strictly post-computation, so the "< current date" invariant is structural.
#
# The test below verifies this by checking that rest_days_a for a player's FIRST
# ever match is 15.0 (not 0.0, which would happen if the row fed its own date).
# A second check ensures the next row correctly reads the PRIOR match's date,
# not the current row's date.

def test_no_same_row_self_feed_leak() -> None:
    """Current row must NOT contribute its own date to the rest-days computation.

    If the implementation accidentally stored last_seen[p] = d BEFORE computing
    rest (a <= leak), the first match of player 1 would see its own date and
    return 0.0 instead of 15.0.  This test catches that regression.
    """
    rows = [
        {"date": "2025-01-10", "p1_id": 7, "p2_id": 8},
        {"date": "2025-01-15", "p1_id": 7, "p2_id": 9},
    ]
    df = _make_df(rows)
    out = _add_rest_days(df)

    # Row 0: player 7's first match — must be 15.0, NOT 0.0
    first_rest = out["rest_days_a"].iloc[0]
    assert first_rest == 15.0, (
        f"LEAK DETECTED: player 7's first match returned rest_days={first_rest}. "
        "Expected 15.0 (default). A value of 0.0 would indicate the row fed its "
        "own date into last_seen before computing rest (strict-prior invariant violated)."
    )

    # Row 1: player 7 was last seen on Jan 10; now Jan 15 → 5 days
    second_rest = out["rest_days_a"].iloc[1]
    assert second_rest == 5.0, (
        f"Row 1 rest for player 7 should be 5 days (Jan 10→Jan 15), got {second_rest}"
    )


def test_last_seen_updates_after_each_row_not_before() -> None:
    """Confirm update order: last_seen updated AFTER rest computed, not before.

    Three-match sequence for the same player verifies each row uses the
    PREVIOUS match's date (strictly less than current date), never the current.
    """
    rows = [
        {"date": "2025-02-01", "p1_id": 5, "p2_id": 6},   # first: 15.0
        {"date": "2025-02-04", "p1_id": 5, "p2_id": 7},   # 3 days later
        {"date": "2025-02-11", "p1_id": 5, "p2_id": 8},   # 7 days after row 1
    ]
    df = _make_df(rows)
    out = _add_rest_days(df)

    expected = [15.0, 3.0, 7.0]
    for i, exp in enumerate(expected):
        got = out["rest_days_a"].iloc[i]
        assert got == exp, (
            f"Row {i}: expected rest_days_a={exp}, got {got}. "
            "This may indicate incorrect update order (pre- vs post-compute)."
        )


# ---------------------------------------------------------------------------
# 5. Cap at 30 days
# ---------------------------------------------------------------------------

def test_rest_days_capped_at_30() -> None:
    """rest_days is capped at 30 even when the real gap is longer."""
    rows = [
        {"date": "2024-01-01", "p1_id": 1, "p2_id": 2},
        {"date": "2024-04-01", "p1_id": 1, "p2_id": 3},  # 91 days later
    ]
    df = _make_df(rows)
    out = _add_rest_days(df)

    capped = out["rest_days_a"].iloc[1]
    assert capped == 30.0, f"Expected cap at 30.0, got {capped}"


# ---------------------------------------------------------------------------
# 6. Output frame preserves row count and drops _date temp column
# ---------------------------------------------------------------------------

def test_output_shape_and_no_temp_column() -> None:
    """Output has same row count as input and does not expose the _date column."""
    rows = [
        {"date": "2024-05-10", "p1_id": 1, "p2_id": 2},
        {"date": "2024-05-15", "p1_id": 3, "p2_id": 4},
        {"date": "2024-05-20", "p1_id": 1, "p2_id": 3},
    ]
    df = _make_df(rows)
    out = _add_rest_days(df)

    assert len(out) == 3
    assert "_date" not in out.columns, "_date temp column must be dropped from output"
    assert "rest_days_a" in out.columns
    assert "rest_days_b" in out.columns


# ---------------------------------------------------------------------------
# 7. Input frame is not mutated (copy semantics)
# ---------------------------------------------------------------------------

def test_input_not_mutated() -> None:
    """_add_rest_days must not modify the caller's DataFrame in place."""
    rows = [
        {"date": "2024-01-01", "p1_id": 1, "p2_id": 2},
    ]
    df = _make_df(rows)
    original_cols = list(df.columns)
    _add_rest_days(df)
    assert list(df.columns) == original_cols, (
        "_add_rest_days must operate on a copy and not mutate the input frame"
    )
    assert "_date" not in df.columns
    assert "rest_days_a" not in df.columns
