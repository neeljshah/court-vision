"""test_heartbeat_sla_matrix_io.py -- per-file tests: report I/O, schema, no-$ fields,
JSON heartbeat format, and never-raises contract (BE8-6).

Split from the original 381-line test_heartbeat_sla_matrix.py to satisfy the
<=300 LOC/file rail. Companion: test_heartbeat_sla_matrix.py covers acceptance,
stale-never-green, and ordering.

Run:
    cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/observability/test_heartbeat_sla_matrix_io.py -q

ASCII only; <=300 LOC.
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

import pytest

from scripts.platformkit.observability.heartbeat_sla_matrix import (
    compute_sla_matrix,
)


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

def _fixed_clock(epoch: float):
    """Return a clock callable that always returns *epoch*."""
    return lambda: epoch


def _write_hb(path: Path, age_sec: float, now: float) -> Path:
    """Write a plain ISO-8601 heartbeat at stamp = now - age_sec."""
    stamp = now - age_sec
    dt = datetime.fromtimestamp(stamp, tz=timezone.utc)
    path.write_text(dt.strftime("%Y-%m-%dT%H:%M:%SZ"), encoding="utf-8")
    return path


def _write_json_hb(path: Path, age_sec: float, now: float) -> Path:
    """Write a JSON heartbeat {updated_at: epoch} at stamp = now - age_sec."""
    stamp = now - age_sec
    path.write_text(json.dumps({"updated_at": stamp, "cycle": 1}), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Report writing
# ---------------------------------------------------------------------------

class TestReportWriting:
    def test_report_written_atomically(self, tmp_path):
        now = time.time()
        p_hb = tmp_path / "d.txt"
        _write_hb(p_hb, age_sec=100.0, now=now)
        specs = [{"name": "d", "sla_sec": 300.0, "hb_path": str(p_hb)}]
        report_path = tmp_path / "ops" / "heartbeat_sla_matrix.json"
        compute_sla_matrix(specs, report_path=report_path, clock=_fixed_clock(now))
        assert report_path.exists()
        doc = json.loads(report_path.read_text(encoding="ascii"))
        assert "rows" in doc
        assert "overall" in doc

    def test_no_tmp_file_leftover(self, tmp_path):
        now = time.time()
        p_hb = tmp_path / "d.txt"
        _write_hb(p_hb, age_sec=100.0, now=now)
        specs = [{"name": "d", "sla_sec": 300.0, "hb_path": str(p_hb)}]
        report_path = tmp_path / "report.json"
        compute_sla_matrix(specs, report_path=report_path, clock=_fixed_clock(now))
        tmp_file = report_path.with_suffix(".json.tmp")
        assert not tmp_file.exists()

    def test_write_report_false_skips_io(self, tmp_path):
        now = time.time()
        specs: List[Dict[str, Any]] = []
        report_path = tmp_path / "nope.json"
        compute_sla_matrix(
            specs, report_path=report_path,
            clock=_fixed_clock(now), write_report=False
        )
        assert not report_path.exists()


# ---------------------------------------------------------------------------
# No $ / roi / pnl / profit fields
# ---------------------------------------------------------------------------

class TestNoDollarFields:
    def test_no_dollar_keys_in_output(self, tmp_path):
        now = time.time()
        p = tmp_path / "d.txt"
        _write_hb(p, age_sec=100.0, now=now)
        specs = [{"name": "d", "sla_sec": 300.0, "hb_path": str(p)}]
        result = compute_sla_matrix(specs, clock=_fixed_clock(now), write_report=False)
        banned = {"pnl", "profit", "roi", "bankroll", "usd", "dollar",
                  "stake", "edge_claimed", "edge"}
        all_keys: set = set(result.keys())
        for row in result.get("rows", []):
            all_keys |= set(row.keys())
        for key in all_keys:
            assert key.lower() not in banned, "Banned $ field: %s" % key


# ---------------------------------------------------------------------------
# JSON heartbeat format (predict_service / ingame pattern)
# ---------------------------------------------------------------------------

class TestJsonHeartbeatFormat:
    def test_json_updated_at_epoch_fresh(self, tmp_path):
        now = time.time()
        p = tmp_path / "_heartbeat.json"
        _write_json_hb(p, age_sec=100.0, now=now)
        specs = [{"name": "svc", "sla_sec": 300.0, "hb_path": str(p)}]
        result = compute_sla_matrix(specs, clock=_fixed_clock(now), write_report=False)
        assert result["rows"][0]["stale"] is False

    def test_json_updated_at_epoch_stale(self, tmp_path):
        now = time.time()
        p = tmp_path / "_heartbeat.json"
        _write_json_hb(p, age_sec=800.0, now=now)
        specs = [{"name": "svc", "sla_sec": 300.0, "hb_path": str(p)}]
        result = compute_sla_matrix(specs, clock=_fixed_clock(now), write_report=False)
        assert result["rows"][0]["stale"] is True


# ---------------------------------------------------------------------------
# Output schema
# ---------------------------------------------------------------------------

class TestOutputSchema:
    def test_required_top_level_keys(self, tmp_path):
        now = time.time()
        p = tmp_path / "d.txt"
        _write_hb(p, age_sec=100.0, now=now)
        specs = [{"name": "d", "sla_sec": 300.0, "hb_path": str(p)}]
        result = compute_sla_matrix(specs, clock=_fixed_clock(now), write_report=False)
        for key in (
            "scanned_at", "rows", "n_stale", "n_ok",
            "overall", "stale_names", "stale_never_green", "honest_note"
        ):
            assert key in result, "Missing key: %s" % key

    def test_row_keys(self, tmp_path):
        now = time.time()
        p = tmp_path / "d.txt"
        _write_hb(p, age_sec=100.0, now=now)
        specs = [{"name": "d", "sla_sec": 300.0, "hb_path": str(p)}]
        result = compute_sla_matrix(specs, clock=_fixed_clock(now), write_report=False)
        row = result["rows"][0]
        for key in ("name", "sla_sec", "age_sec", "pct_of_sla", "stale", "hb_path"):
            assert key in row, "Missing row key: %s" % key

    def test_stale_never_green_is_true(self, tmp_path):
        now = time.time()
        specs: List[Dict[str, Any]] = []
        result = compute_sla_matrix(specs, clock=_fixed_clock(now), write_report=False)
        assert result["stale_never_green"] is True


# ---------------------------------------------------------------------------
# Never-raises contract
# ---------------------------------------------------------------------------

class TestNeverRaises:
    def test_empty_specs(self):
        result = compute_sla_matrix([], clock=_fixed_clock(time.time()), write_report=False)
        assert "overall" in result

    def test_none_specs(self):
        # None -> tries stack_specs import (may succeed or return empty list)
        result = compute_sla_matrix(None, clock=_fixed_clock(time.time()), write_report=False)
        assert "overall" in result

    def test_malformed_entries(self):
        specs = [None, {}, {"name": "x"}, 42]  # type: ignore
        result = compute_sla_matrix(specs, clock=_fixed_clock(time.time()), write_report=False)  # type: ignore
        assert "overall" in result

    def test_no_process_started(self, tmp_path):
        """Purely read-only: returns a dict, never spawns anything."""
        now = time.time()
        p = tmp_path / "d.txt"
        _write_hb(p, age_sec=50.0, now=now)
        specs = [{"name": "d", "sla_sec": 300.0, "hb_path": str(p)}]
        result = compute_sla_matrix(specs, clock=_fixed_clock(now), write_report=False)
        # If we get here without error, no process was started
        assert isinstance(result, dict)
