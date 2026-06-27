"""tests.platformkit.ledger_audit.test_dup_runner -- unit tests for dup_runner.run().

Acceptance criteria (from BACKLOG IOX-5):
  1. run() with 8 dup keys -> report written with n_dups:8, status:DUPS_FOUND
  2. run() with clean ledger -> report status:CLEAN, n_dups:0
  3. run() with missing ledger -> report status:UNAVAILABLE, no exception
  4. run() writes clv_dup_report.json atomically (file exists after run)
  5. runner heartbeat component is m18_dupaudit
  6. run() never raises under any input condition
  7. ledger bytes unchanged after run() (read-only)
  8. report JSON contains no forbidden money keys

Per-file tests only; no real ledger touched. ASCII only.
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, List

import pytest

from scripts.platformkit.ledger_audit.dup_runner import run, HEARTBEAT_COMPONENT


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_jsonl(rows: List[Dict[str, Any]], path: Path) -> None:
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row) + "\n")


def _assert_no_dollar_keys(obj, _path="root"):
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


# ---------------------------------------------------------------------------
# Heartbeat component name
# ---------------------------------------------------------------------------

class TestHeartbeatComponent:
    def test_heartbeat_component_name(self):
        assert HEARTBEAT_COMPONENT == "m18_dupaudit"


# ---------------------------------------------------------------------------
# run() with 8 dup keys
# ---------------------------------------------------------------------------

class TestRunEightDups:
    def _make_dup_ledger(self, tmp_path: Path) -> Path:
        ledger = tmp_path / "dup_ledger.jsonl"
        rows: List[Dict[str, Any]] = []
        for i in range(8):
            rows.append({"bet_id": "dup-%d" % i, "status": "open"})
        for i in range(8):
            rows.append({"bet_id": "dup-%d" % i, "status": "settled"})
        _write_jsonl(rows, ledger)
        return ledger

    def test_run_dups_found_status(self, tmp_path):
        ledger = self._make_dup_ledger(tmp_path)
        report_path = tmp_path / "report.json"
        result = run(ledger_path=ledger, report_path=report_path)
        assert result["status"] == "DUPS_FOUND"

    def test_run_n_dups_8(self, tmp_path):
        ledger = self._make_dup_ledger(tmp_path)
        report_path = tmp_path / "report.json"
        result = run(ledger_path=ledger, report_path=report_path)
        assert result["n_dups"] == 8

    def test_run_dup_keys_list_length_8(self, tmp_path):
        ledger = self._make_dup_ledger(tmp_path)
        report_path = tmp_path / "report.json"
        result = run(ledger_path=ledger, report_path=report_path)
        assert len(result["dup_keys"]) == 8

    def test_run_report_written(self, tmp_path):
        ledger = self._make_dup_ledger(tmp_path)
        report_path = tmp_path / "report.json"
        run(ledger_path=ledger, report_path=report_path)
        assert report_path.exists()

    def test_run_report_json_parseable(self, tmp_path):
        ledger = self._make_dup_ledger(tmp_path)
        report_path = tmp_path / "report.json"
        run(ledger_path=ledger, report_path=report_path)
        parsed = json.loads(report_path.read_text(encoding="utf-8"))
        assert parsed["n_dups"] == 8

    def test_run_first_seen_kept_present(self, tmp_path):
        ledger = self._make_dup_ledger(tmp_path)
        report_path = tmp_path / "report.json"
        result = run(ledger_path=ledger, report_path=report_path)
        fsk = result["first_seen_kept"]
        for i in range(8):
            assert "dup-%d" % i in fsk


# ---------------------------------------------------------------------------
# run() with clean ledger
# ---------------------------------------------------------------------------

class TestRunClean:
    def test_run_clean_status(self, tmp_path):
        ledger = tmp_path / "clean.jsonl"
        _write_jsonl([{"bet_id": "u-%d" % i} for i in range(5)], ledger)
        result = run(ledger_path=ledger, report_path=tmp_path / "r.json")
        assert result["status"] == "CLEAN"

    def test_run_clean_n_dups_zero(self, tmp_path):
        ledger = tmp_path / "clean.jsonl"
        _write_jsonl([{"bet_id": "u-%d" % i} for i in range(5)], ledger)
        result = run(ledger_path=ledger, report_path=tmp_path / "r.json")
        assert result["n_dups"] == 0

    def test_run_clean_dup_keys_empty(self, tmp_path):
        ledger = tmp_path / "clean.jsonl"
        _write_jsonl([{"bet_id": "u-%d" % i} for i in range(3)], ledger)
        result = run(ledger_path=ledger, report_path=tmp_path / "r.json")
        assert result["dup_keys"] == []


# ---------------------------------------------------------------------------
# run() with missing ledger -> UNAVAILABLE, never raises
# ---------------------------------------------------------------------------

class TestRunMissingLedger:
    def test_run_missing_returns_unavailable(self, tmp_path):
        missing = tmp_path / "ghost.jsonl"
        result = run(ledger_path=missing, report_path=tmp_path / "r.json")
        assert result["status"] == "UNAVAILABLE"

    def test_run_missing_does_not_raise(self, tmp_path):
        missing = tmp_path / "ghost.jsonl"
        # Must not raise
        result = run(ledger_path=missing, report_path=tmp_path / "r.json")
        assert isinstance(result, dict)

    def test_run_missing_still_writes_report(self, tmp_path):
        missing = tmp_path / "ghost.jsonl"
        report_path = tmp_path / "r.json"
        run(ledger_path=missing, report_path=report_path)
        assert report_path.exists()

    def test_run_missing_report_status_unavailable(self, tmp_path):
        missing = tmp_path / "ghost.jsonl"
        report_path = tmp_path / "r.json"
        run(ledger_path=missing, report_path=report_path)
        parsed = json.loads(report_path.read_text(encoding="utf-8"))
        assert parsed["status"] == "UNAVAILABLE"


# ---------------------------------------------------------------------------
# Atomic write -- report is valid JSON after run
# ---------------------------------------------------------------------------

class TestAtomicWrite:
    def test_report_is_valid_json(self, tmp_path):
        ledger = tmp_path / "led.jsonl"
        _write_jsonl([{"bet_id": "x"}], ledger)
        report_path = tmp_path / "report.json"
        run(ledger_path=ledger, report_path=report_path)
        content = report_path.read_text(encoding="utf-8")
        parsed = json.loads(content)
        assert "status" in parsed

    def test_report_includes_component(self, tmp_path):
        ledger = tmp_path / "led.jsonl"
        _write_jsonl([{"bet_id": "x"}], ledger)
        report_path = tmp_path / "report.json"
        result = run(ledger_path=ledger, report_path=report_path)
        assert result.get("component") == HEARTBEAT_COMPONENT

    def test_report_includes_generated_at(self, tmp_path):
        ledger = tmp_path / "led.jsonl"
        _write_jsonl([{"bet_id": "x"}], ledger)
        report_path = tmp_path / "report.json"
        result = run(ledger_path=ledger, report_path=report_path)
        assert "generated_at" in result
        assert result["generated_at"] is not None

    def test_tmp_file_cleaned_up(self, tmp_path):
        ledger = tmp_path / "led.jsonl"
        _write_jsonl([{"bet_id": "x"}], ledger)
        report_path = tmp_path / "report.json"
        run(ledger_path=ledger, report_path=report_path)
        tmp_file = report_path.with_suffix(".tmp")
        # tmp file should not linger after atomic replace
        assert not tmp_file.exists()


# ---------------------------------------------------------------------------
# Read-only invariant
# ---------------------------------------------------------------------------

class TestReadOnly:
    def test_ledger_bytes_unchanged_after_run(self, tmp_path):
        ledger = tmp_path / "led.jsonl"
        rows = [
            {"bet_id": "a", "sport": "nba"},
            {"bet_id": "a", "sport": "nba"},  # dup
            {"bet_id": "b", "sport": "mlb"},
        ]
        _write_jsonl(rows, ledger)
        original_bytes = ledger.read_bytes()

        run(ledger_path=ledger, report_path=tmp_path / "r.json")

        after_bytes = ledger.read_bytes()
        assert original_bytes == after_bytes, (
            "run() mutated the ledger -- read-only invariant violated"
        )


# ---------------------------------------------------------------------------
# Never raises invariant
# ---------------------------------------------------------------------------

class TestNeverRaises:
    def test_run_with_none_inputs_does_not_raise(self, tmp_path):
        """run() with default None paths should not raise (handles missing canonical ledger)."""
        # Use a temp report path to avoid polluting real ops dir
        report_path = tmp_path / "r.json"
        try:
            result = run(report_path=report_path)
        except Exception as exc:
            pytest.fail("run() raised unexpectedly: %s" % exc)
        assert isinstance(result, dict)
        assert result.get("status") in ("CLEAN", "DUPS_FOUND", "UNAVAILABLE")

    def test_run_never_raises_on_corrupt_ledger(self, tmp_path):
        ledger = tmp_path / "corrupt.jsonl"
        ledger.write_bytes(b"\xff\xfe BROKEN JSON \x00\x01")
        report_path = tmp_path / "r.json"
        try:
            result = run(ledger_path=ledger, report_path=report_path)
        except Exception as exc:
            pytest.fail("run() raised on corrupt ledger: %s" % exc)
        assert isinstance(result, dict)


# ---------------------------------------------------------------------------
# No forbidden money keys in output
# ---------------------------------------------------------------------------

class TestNoForbiddenKeys:
    def test_no_dollar_keys_dups(self, tmp_path):
        ledger = tmp_path / "dup.jsonl"
        rows = [{"bet_id": "d", "sport": "nba"}, {"bet_id": "d", "sport": "nba"}]
        _write_jsonl(rows, ledger)
        result = run(ledger_path=ledger, report_path=tmp_path / "r.json")
        _assert_no_dollar_keys(result)

    def test_no_dollar_keys_clean(self, tmp_path):
        ledger = tmp_path / "clean.jsonl"
        _write_jsonl([{"bet_id": "u1"}, {"bet_id": "u2"}], ledger)
        result = run(ledger_path=ledger, report_path=tmp_path / "r.json")
        _assert_no_dollar_keys(result)

    def test_no_dollar_keys_missing(self, tmp_path):
        result = run(
            ledger_path=tmp_path / "ghost.jsonl",
            report_path=tmp_path / "r.json",
        )
        _assert_no_dollar_keys(result)
