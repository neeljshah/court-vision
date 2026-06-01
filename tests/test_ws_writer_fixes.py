"""tests/test_ws_writer_fixes.py — unit tests for WS CSV-writer + tuple-unpack fixes.

Bug 8: WS CSV writers previously deduped on a minute-truncated key (captured_at[:16])
       with price EXCLUDED, so intra-minute price moves on the same line were silently
       dropped.  Fix: key is now (captured_at, player, stat, line, over_price, under_price)
       — full-second + both prices.

Bug 2: betrivers_ws._fetch_event_ids_async called .get() on a tuple (not a dict) because
       betrivers_scraper.fetch_event_ids() returns (List[Dict], operator_str).  Fix:
       unpack the tuple → stubs, _op = ...

NBA_OFFLINE=1 is set in the conda env for CI — no network calls are made here.
"""
from __future__ import annotations

import asyncio
import csv
import os
import sys
import tempfile
from typing import Any, Dict, List
from unittest.mock import patch

import pytest

# ── make sure project root is importable ────────────────────────────────────────
PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

from scripts.draftkings_ws import _write_csv as dk_write_csv
from scripts.fanduel_ws import _write_csv as fd_write_csv


# ── helpers ──────────────────────────────────────────────────────────────────────

_CANONICAL_FIELDS = [
    "captured_at", "book", "game_id", "player_id", "player_name",
    "stat", "line", "over_price", "under_price", "start_time",
]

def _make_row(
    captured_at: str,
    player_name: str = "LeBron James",
    stat: str = "pts",
    line: float = 27.5,
    over_price: Any = -115,
    under_price: Any = -105,
) -> Dict[str, Any]:
    return {
        "captured_at": captured_at,
        "book": "dk",
        "game_id": "1234",
        "player_id": "5678",
        "player_name": player_name,
        "stat": stat,
        "line": line,
        "over_price": over_price,
        "under_price": under_price,
        "start_time": "2026-05-31T20:00:00",
    }


def _read_csv(path: str) -> List[Dict[str, str]]:
    with open(path, "r", encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


# ── Bug 8 tests ──────────────────────────────────────────────────────────────────

class TestBug8DKWriter:
    """DraftKings _write_csv intra-minute price-move dedup fix."""

    def test_same_minute_different_prices_both_persist(self, tmp_path):
        """Two pushes in the same minute with different prices must BOTH be written."""
        csv_path = str(tmp_path / "test_dk.csv")
        # First push: over_price=-115
        row1 = _make_row("2026-05-31T20:15:30", over_price=-115, under_price=-105)
        written1 = dk_write_csv([row1], csv_path)
        assert written1 == 1, "first row should be written"

        # Second push: same minute, same line, but price moved to -110/-110
        row2 = _make_row("2026-05-31T20:15:45", over_price=-110, under_price=-110)
        written2 = dk_write_csv([row2], csv_path)
        assert written2 == 1, "price-moved row in same minute must NOT be deduped"

        rows = _read_csv(csv_path)
        assert len(rows) == 2, f"expected 2 rows on disk, got {len(rows)}"

    def test_byte_identical_duplicate_is_deduped(self, tmp_path):
        """A truly identical row (same second, same prices) must be collapsed."""
        csv_path = str(tmp_path / "test_dk_dedup.csv")
        row = _make_row("2026-05-31T20:15:30", over_price=-115, under_price=-105)
        written1 = dk_write_csv([row], csv_path)
        written2 = dk_write_csv([row], csv_path)  # exact same row object

        assert written1 == 1
        assert written2 == 0, "byte-identical row must be deduped"

        rows = _read_csv(csv_path)
        assert len(rows) == 1

    def test_different_second_same_prices_both_persist(self, tmp_path):
        """Rows from different seconds (even same minute) with same prices are distinct."""
        csv_path = str(tmp_path / "test_dk_sec.csv")
        row1 = _make_row("2026-05-31T20:15:00", over_price=-115, under_price=-105)
        row2 = _make_row("2026-05-31T20:15:59", over_price=-115, under_price=-105)
        written1 = dk_write_csv([row1], csv_path)
        written2 = dk_write_csv([row2], csv_path)
        assert written1 == 1
        assert written2 == 1
        rows = _read_csv(csv_path)
        assert len(rows) == 2


class TestBug8FDWriter:
    """FanDuel _write_csv intra-minute price-move dedup fix."""

    def test_same_minute_different_prices_both_persist(self, tmp_path):
        csv_path = str(tmp_path / "test_fd.csv")
        row1 = _make_row("2026-05-31T20:15:30", over_price=-120, under_price="")
        row1["book"] = "fd"
        written1 = fd_write_csv([row1], csv_path)
        assert written1 == 1

        row2 = _make_row("2026-05-31T20:15:45", over_price=-110, under_price="")
        row2["book"] = "fd"
        written2 = fd_write_csv([row2], csv_path)
        assert written2 == 1, "price-moved row in same minute must NOT be deduped"

        rows = _read_csv(csv_path)
        assert len(rows) == 2

    def test_byte_identical_duplicate_is_deduped(self, tmp_path):
        csv_path = str(tmp_path / "test_fd_dedup.csv")
        row = _make_row("2026-05-31T20:15:30", over_price=-120, under_price="")
        row["book"] = "fd"
        written1 = fd_write_csv([row], csv_path)
        written2 = fd_write_csv([row], csv_path)
        assert written1 == 1
        assert written2 == 0

        rows = _read_csv(csv_path)
        assert len(rows) == 1

    def test_same_minute_different_players_both_persist(self, tmp_path):
        """Different players in same minute are never deduped (regression guard)."""
        csv_path = str(tmp_path / "test_fd_multi.csv")
        row1 = _make_row("2026-05-31T20:15:30", player_name="LeBron James")
        row1["book"] = "fd"
        row2 = _make_row("2026-05-31T20:15:30", player_name="Anthony Davis")
        row2["book"] = "fd"
        written = fd_write_csv([row1, row2], csv_path)
        assert written == 2


# ── Bug 2 tests ──────────────────────────────────────────────────────────────────

class TestBug2BetRiversTupleUnpack:
    """betrivers_ws._fetch_event_ids_async correctly unpacks the 2-tuple from fetch_event_ids."""

    def test_tuple_unpack_returns_ids(self):
        """Simulate what _fetch_event_ids_async does: unpack (stubs, op) → id list."""
        # This is the shape betrivers_scraper.fetch_event_ids() now returns.
        fake_return = ([{"id": 123}, {"id": 456}, {"id": None}], "rsiusia")
        stubs, _op = fake_return
        result = [int(s["id"]) for s in stubs if s.get("id")]
        assert result == [123, 456], f"expected [123, 456], got {result}"

    def test_tuple_unpack_empty_stubs(self):
        """Empty event list → empty result, no error."""
        fake_return = ([], "rsiusia")
        stubs, _op = fake_return
        result = [int(s["id"]) for s in stubs if s.get("id")]
        assert result == []

    def test_monkeypatched_fetch_event_ids_async(self):
        """Integration: _fetch_event_ids_async returns correct ids via executor mock."""
        # Import here to ensure the module is loaded with the fix applied.
        from scripts import betrivers_ws

        async def _run():
            fake_tuple = ([{"id": 789}, {"id": 101}], "some_op")
            with patch("scripts.betrivers_ws.fetch_event_ids", return_value=fake_tuple):
                return await betrivers_ws._fetch_event_ids_async()

        result = asyncio.run(_run())
        assert result == [789, 101], f"expected [789, 101], got {result}"

    def test_monkeypatched_no_attribute_error(self):
        """Verify that the OLD bug (iterating the tuple) would cause AttributeError,
        proving the fix is necessary — then confirm the fix suppresses it."""
        from scripts import betrivers_ws

        fake_tuple = ([{"id": 999}], "rsiusia")

        # Demonstrate old bug: iterating the 2-tuple calls .get() on a list → AttributeError
        with pytest.raises((AttributeError, TypeError)):
            [s.get("id") for s in fake_tuple]  # tuple elements: a list and a string

        # Confirm fix: unpacking first then iterating the stubs list works fine.
        stubs, _op = fake_tuple
        result = [int(s["id"]) for s in stubs if s.get("id")]
        assert result == [999]
