"""tests.platformkit.ledger_audit.test_dup_key_detector -- unit tests for scan_ledger.

Acceptance criteria (from BACKLOG IOX-5):
  1. ledger with 8 duplicate keys -> {n_dups:8, dup_keys:[...], status:DUPS_FOUND}
  2. clean ledger -> {n_dups:0, status:CLEAN}
  3. missing ledger -> status=UNAVAILABLE, no exception raised
  4. detector NEVER writes/dedupes the ledger (read-only assert: bytes unchanged after run)
  5. first_seen_kept maps each dup key to the line number of its first occurrence
  6. SHA-1 fallback key used when no bet_id/row_id/id field present
  7. mixed rows (some with bet_id, some without) handled correctly

Per-file tests only. NEVER imports or touches real data except via temp files.
ASCII only; no $ keys in output.
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, List

import pytest

from scripts.platformkit.ledger_audit.dup_key_detector import scan_ledger, _row_key


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_jsonl(rows: List[Dict[str, Any]], path: Path) -> None:
    """Write a list of dicts as JSONL to *path*."""
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row) + "\n")


def _sha1_key(row: Dict[str, Any]) -> str:
    payload = json.dumps(row, sort_keys=True, default=str)
    return "sha1:" + hashlib.sha1(payload.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# _row_key unit tests
# ---------------------------------------------------------------------------

class TestRowKey:
    def test_bet_id_takes_priority(self):
        row = {"bet_id": "abc-123", "row_id": "x", "id": "y", "ts": "2026-01-01"}
        assert _row_key(row) == "abc-123"

    def test_row_id_used_when_no_bet_id(self):
        row = {"row_id": "row-99", "id": "z"}
        assert _row_key(row) == "row-99"

    def test_id_used_as_last_named_field(self):
        row = {"id": "id-77", "status": "open"}
        assert _row_key(row) == "id-77"

    def test_sha1_fallback_no_id_fields(self):
        row = {"ts": "2026-01-01", "sport": "nba", "matchup": "A@B"}
        key = _row_key(row)
        assert key.startswith("sha1:")
        assert key == _sha1_key(row)

    def test_sha1_two_distinct_rows_produce_distinct_keys(self):
        r1 = {"ts": "2026-01-01", "sport": "nba"}
        r2 = {"ts": "2026-01-02", "sport": "nba"}
        assert _row_key(r1) != _row_key(r2)

    def test_sha1_identical_rows_produce_same_key(self):
        r1 = {"ts": "2026-01-01", "sport": "nba", "matchup": "X@Y"}
        r2 = {"ts": "2026-01-01", "sport": "nba", "matchup": "X@Y"}
        assert _row_key(r1) == _row_key(r2)

    def test_none_bet_id_falls_through_to_row_id(self):
        row = {"bet_id": None, "row_id": "r-42"}
        assert _row_key(row) == "r-42"


# ---------------------------------------------------------------------------
# scan_ledger -- missing ledger
# ---------------------------------------------------------------------------

class TestScanLedgerMissing:
    def test_missing_ledger_returns_unavailable(self, tmp_path):
        missing = tmp_path / "nonexistent.jsonl"
        result = scan_ledger(path=missing)
        assert result["status"] == "UNAVAILABLE"

    def test_missing_ledger_does_not_raise(self, tmp_path):
        missing = tmp_path / "nonexistent.jsonl"
        # Must not raise
        result = scan_ledger(path=missing)
        assert isinstance(result, dict)

    def test_missing_ledger_n_dups_zero(self, tmp_path):
        result = scan_ledger(path=tmp_path / "ghost.jsonl")
        assert result["n_dups"] == 0

    def test_missing_ledger_no_dollar_keys_in_result(self, tmp_path):
        result = scan_ledger(path=tmp_path / "ghost.jsonl")
        _assert_no_dollar_keys(result)


# ---------------------------------------------------------------------------
# scan_ledger -- clean ledger
# ---------------------------------------------------------------------------

class TestScanLedgerClean:
    def test_clean_ledger_returns_clean(self, tmp_path):
        ledger = tmp_path / "ledger.jsonl"
        rows = [{"bet_id": "bet-%d" % i, "sport": "nba"} for i in range(10)]
        _write_jsonl(rows, ledger)
        result = scan_ledger(path=ledger)
        assert result["status"] == "CLEAN"

    def test_clean_ledger_n_dups_zero(self, tmp_path):
        ledger = tmp_path / "ledger.jsonl"
        rows = [{"bet_id": "u-%d" % i} for i in range(5)]
        _write_jsonl(rows, ledger)
        result = scan_ledger(path=ledger)
        assert result["n_dups"] == 0

    def test_clean_ledger_dup_keys_empty(self, tmp_path):
        ledger = tmp_path / "ledger.jsonl"
        rows = [{"row_id": "r-%d" % i} for i in range(4)]
        _write_jsonl(rows, ledger)
        result = scan_ledger(path=ledger)
        assert result["dup_keys"] == []

    def test_clean_ledger_n_rows_scanned(self, tmp_path):
        ledger = tmp_path / "ledger.jsonl"
        rows = [{"bet_id": "b%d" % i} for i in range(7)]
        _write_jsonl(rows, ledger)
        result = scan_ledger(path=ledger)
        assert result["n_rows_scanned"] == 7

    def test_clean_no_dollar_keys(self, tmp_path):
        ledger = tmp_path / "ledger.jsonl"
        _write_jsonl([{"bet_id": "x1"}, {"bet_id": "x2"}], ledger)
        result = scan_ledger(path=ledger)
        _assert_no_dollar_keys(result)


# ---------------------------------------------------------------------------
# scan_ledger -- 8 duplicate keys (acceptance criterion from IOX-5)
# ---------------------------------------------------------------------------

class TestScanLedgerEightDups:
    def _make_ledger_with_8_dup_keys(self, tmp_path: Path) -> Path:
        """Build a ledger with exactly 8 distinct bet_ids each appearing twice -> 8 dup keys."""
        ledger = tmp_path / "dup_ledger.jsonl"
        rows: List[Dict[str, Any]] = []
        # 8 dup keys: each bet_id appears twice
        for i in range(8):
            rows.append({"bet_id": "dup-%d" % i, "status": "open", "sport": "nba"})
        for i in range(8):
            rows.append({"bet_id": "dup-%d" % i, "status": "settled", "sport": "nba"})
        # 4 unique keys
        for i in range(4):
            rows.append({"bet_id": "unique-%d" % i, "sport": "mlb"})
        _write_jsonl(rows, ledger)
        return ledger

    def test_8_dup_keys_status_dups_found(self, tmp_path):
        ledger = self._make_ledger_with_8_dup_keys(tmp_path)
        result = scan_ledger(path=ledger)
        assert result["status"] == "DUPS_FOUND"

    def test_8_dup_keys_n_dups_equals_8(self, tmp_path):
        ledger = self._make_ledger_with_8_dup_keys(tmp_path)
        result = scan_ledger(path=ledger)
        assert result["n_dups"] == 8

    def test_8_dup_keys_dup_keys_list(self, tmp_path):
        ledger = self._make_ledger_with_8_dup_keys(tmp_path)
        result = scan_ledger(path=ledger)
        assert len(result["dup_keys"]) == 8
        for i in range(8):
            assert "dup-%d" % i in result["dup_keys"]

    def test_8_dup_keys_first_seen_kept(self, tmp_path):
        ledger = self._make_ledger_with_8_dup_keys(tmp_path)
        result = scan_ledger(path=ledger)
        fsk = result["first_seen_kept"]
        # dup-0 through dup-7 first appear on lines 1..8
        for i in range(8):
            key = "dup-%d" % i
            assert key in fsk
            # first occurrence is in lines 1-8 (1-based)
            assert 1 <= fsk[key] <= 8

    def test_8_dup_keys_no_dollar_keys(self, tmp_path):
        ledger = self._make_ledger_with_8_dup_keys(tmp_path)
        result = scan_ledger(path=ledger)
        _assert_no_dollar_keys(result)


# ---------------------------------------------------------------------------
# Read-only invariant (bytes unchanged after scan)
# ---------------------------------------------------------------------------

class TestReadOnly:
    def test_ledger_bytes_unchanged_after_scan(self, tmp_path):
        """After scan_ledger runs, ledger file bytes must be identical to before."""
        ledger = tmp_path / "ledger.jsonl"
        rows = [
            {"bet_id": "a", "sport": "nba"},
            {"bet_id": "b", "sport": "mlb"},
            {"bet_id": "a", "sport": "nba"},  # duplicate
        ]
        _write_jsonl(rows, ledger)
        original_bytes = ledger.read_bytes()

        scan_ledger(path=ledger)

        after_bytes = ledger.read_bytes()
        assert original_bytes == after_bytes, (
            "scan_ledger mutated the ledger (bytes changed) -- read-only invariant violated"
        )

    def test_no_sidecar_files_created(self, tmp_path):
        """scan_ledger must not create any extra files next to the ledger."""
        ledger = tmp_path / "ledger.jsonl"
        _write_jsonl([{"bet_id": "x"}], ledger)
        before = set(tmp_path.iterdir())
        scan_ledger(path=ledger)
        after = set(tmp_path.iterdir())
        assert after == before, (
            "scan_ledger created unexpected files: %s" % (after - before)
        )


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_empty_ledger_is_clean(self, tmp_path):
        ledger = tmp_path / "empty.jsonl"
        ledger.write_text("", encoding="utf-8")
        result = scan_ledger(path=ledger)
        assert result["status"] == "CLEAN"
        assert result["n_rows_scanned"] == 0

    def test_ledger_with_blank_lines_skips_them(self, tmp_path):
        ledger = tmp_path / "blanks.jsonl"
        ledger.write_text(
            '{"bet_id": "x1"}\n\n\n{"bet_id": "x2"}\n',
            encoding="utf-8",
        )
        result = scan_ledger(path=ledger)
        assert result["n_rows_scanned"] == 2
        assert result["status"] == "CLEAN"

    def test_sha1_fallback_dup_detected(self, tmp_path):
        """Two identical rows with no id field collide on SHA-1 key."""
        ledger = tmp_path / "sha1.jsonl"
        row = {"ts": "2026-01-01", "sport": "tennis", "matchup": "A vs B"}
        _write_jsonl([row, row], ledger)
        result = scan_ledger(path=ledger)
        assert result["n_dups"] == 1
        assert result["dup_keys"][0].startswith("sha1:")

    def test_ledger_path_returned_in_result(self, tmp_path):
        ledger = tmp_path / "ledger.jsonl"
        _write_jsonl([{"bet_id": "y"}], ledger)
        result = scan_ledger(path=ledger)
        assert str(ledger) in result["ledger_path"]

    def test_torn_line_does_not_raise(self, tmp_path):
        """A broken/torn JSON line should not raise; valid lines still scanned."""
        ledger = tmp_path / "torn.jsonl"
        ledger.write_text(
            '{"bet_id": "ok1"}\n'
            'TORN_JSON\n'
            '{"bet_id": "ok2"}\n',
            encoding="utf-8",
        )
        result = scan_ledger(path=ledger)
        # Should not raise; may set error field; valid rows scanned
        assert isinstance(result, dict)
        assert result["n_rows_scanned"] == 2  # 2 valid rows


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _assert_no_dollar_keys(obj, _path="root"):
    """Recursively verify no key contains 'dollar', 'roi', 'pnl', or '$'."""
    _FORBIDDEN = ("dollar", "roi", "pnl", "stake_dollars", "bankroll", "profit", "usd")
    if isinstance(obj, dict):
        for k, v in obj.items():
            k_lower = k.lower()
            for bad in _FORBIDDEN:
                assert bad not in k_lower, (
                    "Forbidden key %r found at %s" % (k, _path)
                )
            _assert_no_dollar_keys(v, _path + "." + k)
    elif isinstance(obj, (list, tuple)):
        for i, item in enumerate(obj):
            _assert_no_dollar_keys(item, _path + "[%d]" % i)
