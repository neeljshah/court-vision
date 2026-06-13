"""test_capture_sgp_builder.py — Unit tests for _build_sgp_rows in capture_sgp_builder.py.

Tests the row-generation generator directly with synthetic payloads.
No network, no disk, no ledger writes.  Python 3.9 compatible.  ≤300 LOC.

Dedup note: _build_sgp_rows does NOT mutate the `seen` set — dedup is the
CALLER's responsibility.  The idempotency test simulates the caller pattern:
collect keys from run-1, pre-seed seen, then assert run-2 yields no genuinely
new keys (caller would write 0 rows).
"""
from __future__ import annotations

import datetime
import sys
from pathlib import Path
from typing import Any, Dict, Iterator, List, Set, Tuple

ROOT = Path(__file__).resolve().parents[2]
CAPTURE_DIR = ROOT / "scripts" / "platformkit" / "capture"
sys.path.insert(0, str(CAPTURE_DIR))

from capture_sgp_builder import _build_sgp_rows, make_sgp_market_tag  # noqa: E402
from ledger_schema import record_key, validate, REQUIRED_FIELDS  # noqa: E402

_EVENT_ID = "sgp_builder_test_event_001"
_COMMENCE = "2030-06-15T02:00:00Z"
_NOW_UTC = datetime.datetime(2030, 6, 14, 21, 0, 0, tzinfo=datetime.timezone.utc)
_TS = "2030-06-14T21:00:00Z"
_LEGS = ("player_points", "player_rebounds")


def _empty_seen() -> Set[Tuple]:
    return set()


def _make_bookmakers(
    book: str = "fanduel",
    player: str = "Jalen Brunson",
    point: float = 27.5,
    over_price: int = -120,
    under_price: int = 100,
) -> List[Dict[str, Any]]:
    return [
        {
            "key": book,
            "markets": [
                {
                    "key": "player_points",
                    "outcomes": [
                        {"name": "Over", "description": player,
                         "price": over_price, "point": point},
                        {"name": "Under", "description": player,
                         "price": under_price, "point": point},
                    ],
                }
            ],
        }
    ]


def _collect(gen: Iterator[dict]) -> List[dict]:
    return list(gen)


# ---------------------------------------------------------------------------
# 1. Valid payload yields rows with expected side format
# ---------------------------------------------------------------------------

def test_valid_payload_yields_rows_with_correct_side_format() -> None:
    """Well-formed bookmaker payload → rows with side 'over:Player:27.5'."""
    bms = _make_bookmakers(player="Jalen Brunson", point=27.5)
    rows = _collect(
        _build_sgp_rows(_EVENT_ID, _COMMENCE, _LEGS, bms, _TS, _empty_seen(), _NOW_UTC)
    )
    assert len(rows) > 0, "Expected at least one row from valid payload"
    sides = {r["side"] for r in rows}
    # name is lowercased; format is "{name}:{description}:{point}"
    assert "over:Jalen Brunson:27.5" in sides, f"Got sides: {sides}"
    assert "under:Jalen Brunson:27.5" in sides, f"Got sides: {sides}"


def test_market_tag_encoded_in_yielded_rows() -> None:
    """Each yielded row's market field must match the canonical SGP market tag."""
    bms = _make_bookmakers()
    rows = _collect(
        _build_sgp_rows(_EVENT_ID, _COMMENCE, _LEGS, bms, _TS, _empty_seen(), _NOW_UTC)
    )
    expected_tag = make_sgp_market_tag(_LEGS)
    for row in rows:
        assert row["market"] == expected_tag


# ---------------------------------------------------------------------------
# 2. Outcome with price=None is skipped
# ---------------------------------------------------------------------------

def test_outcome_with_price_none_is_skipped() -> None:
    """price=None outcome must produce zero rows."""
    bms: List[Dict[str, Any]] = [{"key": "fanduel", "markets": [{"key": "player_points",
        "outcomes": [{"name": "Over", "description": "JB", "price": None, "point": 27.5}]}]}]
    rows = _collect(
        _build_sgp_rows(_EVENT_ID, _COMMENCE, _LEGS, bms, _TS, _empty_seen(), _NOW_UTC)
    )
    assert rows == [], f"Expected 0 rows when price=None, got {len(rows)}"


# ---------------------------------------------------------------------------
# 3. Outcome with no name (empty / None / whitespace) is skipped
# ---------------------------------------------------------------------------

def test_outcome_with_empty_name_is_skipped() -> None:
    """Outcome where name strips to empty must produce zero rows."""
    for bad_name in ("", None, "   "):
        bms: List[Dict[str, Any]] = [{"key": "fanduel", "markets": [{"key": "player_points",
            "outcomes": [{"name": bad_name, "description": "JB", "price": -120, "point": 27.5}]}]}]
        rows = _collect(
            _build_sgp_rows(_EVENT_ID, _COMMENCE, _LEGS, bms, _TS, _empty_seen(), _NOW_UTC)
        )
        assert rows == [], f"Expected 0 rows for name={bad_name!r}, got {rows}"


# ---------------------------------------------------------------------------
# 4. Idempotency: seen set dedup — second call same payload yields 0 genuinely new rows
#
# _build_sgp_rows does NOT mutate seen; dedup is caller-side.
# Simulate caller: seed seen from run-1 keys, then run-2 has no new keys.
# ---------------------------------------------------------------------------

def test_idempotency_caller_pattern_zero_new_rows() -> None:
    """After pre-seeding seen with run-1 keys, run-2 yields no genuinely new rows."""
    bms = _make_bookmakers()
    seen: Set[Tuple] = set()

    run1 = _collect(
        _build_sgp_rows(_EVENT_ID, _COMMENCE, _LEGS, bms, _TS, seen, _NOW_UTC)
    )
    assert len(run1) > 0, "Run 1 must yield rows"
    for row in run1:
        seen.add(record_key(row))  # caller tracks written keys

    run2 = _collect(
        _build_sgp_rows(_EVENT_ID, _COMMENCE, _LEGS, bms, _TS, seen, _NOW_UTC)
    )
    new_rows = [r for r in run2 if record_key(r) not in seen]
    assert len(new_rows) == 0, (
        f"Expected 0 new rows in run-2 (caller dedup), got {len(new_rows)}: {new_rows}"
    )


# ---------------------------------------------------------------------------
# 5. Every yielded row passes schema validation
# ---------------------------------------------------------------------------

def test_all_yielded_rows_pass_schema_validation() -> None:
    """Every row from _build_sgp_rows must satisfy ledger_schema.validate."""
    bms = _make_bookmakers()
    rows = _collect(
        _build_sgp_rows(_EVENT_ID, _COMMENCE, _LEGS, bms, _TS, _empty_seen(), _NOW_UTC)
    )
    assert len(rows) > 0, "Need rows to validate"
    for row in rows:
        validated = validate(row)
        assert validated is row  # returns same dict unchanged
    for row in rows:
        for field in REQUIRED_FIELDS:
            assert field in row and row[field] is not None, (
                f"Required field {field!r} missing or None in: {row}"
            )


# ---------------------------------------------------------------------------
# 6. sport / source always correct; first-call kind is 'open'
# ---------------------------------------------------------------------------

def test_sport_source_and_open_kind() -> None:
    """Rows carry sport='nba', source='odds_api_sgp', kind='open' on first call."""
    bms = _make_bookmakers()
    rows = _collect(
        _build_sgp_rows(_EVENT_ID, _COMMENCE, _LEGS, bms, _TS, _empty_seen(), _NOW_UTC)
    )
    assert rows
    for row in rows:
        assert row["sport"] == "nba"
        assert row["source"] == "odds_api_sgp"
        assert row["kind"] == "open", f"Expected 'open' on first call, got {row['kind']!r}"


# ---------------------------------------------------------------------------
# 7. Edge cases: empty bookmakers / missing book key → zero rows
# ---------------------------------------------------------------------------

def test_empty_bookmakers_yields_no_rows() -> None:
    """Empty bookmakers list yields nothing and does not raise."""
    rows = _collect(
        _build_sgp_rows(_EVENT_ID, _COMMENCE, _LEGS, [], _TS, _empty_seen(), _NOW_UTC)
    )
    assert rows == []


def test_bookmaker_missing_key_is_skipped() -> None:
    """Bookmaker with empty key string must be skipped entirely."""
    bms: List[Dict[str, Any]] = [{"key": "", "markets": [{"key": "player_points",
        "outcomes": [{"name": "Over", "description": "A", "price": -110, "point": 20.5}]}]}]
    rows = _collect(
        _build_sgp_rows(_EVENT_ID, _COMMENCE, _LEGS, bms, _TS, _empty_seen(), _NOW_UTC)
    )
    assert rows == [], f"Expected 0 rows for empty book key, got {rows}"
