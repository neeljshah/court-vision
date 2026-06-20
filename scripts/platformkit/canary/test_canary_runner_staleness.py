"""Per-file tests for canary_runner staleness logic.

Acceptance:
  python -m pytest scripts/platformkit/canary/test_canary_runner_staleness.py -q

Tests cover:
  * tick() stamps generated_at + canary_interval_sec into the written JSON.
  * read_canary_status() returns STALE when generated_at is older than the interval.
  * read_canary_status() preserves the original status when the file is fresh.
  * read_canary_status() returns STALE for absent / unreadable / legacy files.
  * run() propagates interval_sec into each tick so the file is always stamped.
  * No $ field anywhere; stale-never-green rail honored throughout.

No real sleep, no real network, no real store -- all injectable.
"""
from __future__ import annotations

import json
import pathlib
import tempfile
import time

import pytest

# ---------------------------------------------------------------------------
# Module under test
# ---------------------------------------------------------------------------
from scripts.platformkit.canary.canary_runner import (
    DEFAULT_INTERVAL_SEC,
    tick,
    read_canary_status,
    run,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_BASE_EPOCH = 1_700_000_000.0  # arbitrary fixed epoch for clock injection


def _stub_run_fn(status: str = "READY"):
    """Return a run_fn stub that produces a fixed CanaryResult-like dict."""
    def _fn(now=None, read_fn=None, ops_path=None):
        class _R:
            def to_dict(self):
                return {
                    "status": status,
                    "failing_stage": None,
                    "probes": [],
                    "notes": [],
                    "checked_at": now or _BASE_EPOCH,
                }
        return _R()
    return _fn


def _write_json(path: pathlib.Path, doc: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, ensure_ascii=True), encoding="ascii")


# ---------------------------------------------------------------------------
# tick() -- generated_at + canary_interval_sec stamped
# ---------------------------------------------------------------------------

class TestTickStampsProvenance:
    def test_generated_at_present(self, tmp_path):
        out = tmp_path / "canary_status.json"
        doc = tick(
            now=_BASE_EPOCH,
            run_fn=_stub_run_fn("READY"),
            out_path=out,
            interval_sec=60.0,
        )
        assert "generated_at" in doc, "tick() must stamp generated_at"
        assert doc["generated_at"] == _BASE_EPOCH

    def test_canary_interval_sec_present(self, tmp_path):
        out = tmp_path / "canary_status.json"
        doc = tick(
            now=_BASE_EPOCH,
            run_fn=_stub_run_fn("READY"),
            out_path=out,
            interval_sec=120.0,
        )
        assert doc["canary_interval_sec"] == 120.0

    def test_file_written_with_provenance(self, tmp_path):
        out = tmp_path / "canary_status.json"
        tick(now=_BASE_EPOCH, run_fn=_stub_run_fn("READY"), out_path=out)
        written = json.loads(out.read_text(encoding="ascii"))
        assert "generated_at" in written
        assert "canary_interval_sec" in written

    def test_no_dollar_field(self, tmp_path):
        """Stale-never-green + no $ field: doc must not contain any $ ROI."""
        out = tmp_path / "canary_status.json"
        doc = tick(now=_BASE_EPOCH, run_fn=_stub_run_fn("READY"), out_path=out)
        dollar_keys = [k for k in doc if "$" in k or "roi" in k.lower() or "profit" in k.lower()]
        assert dollar_keys == [], "No $ / ROI fields allowed: %s" % dollar_keys


# ---------------------------------------------------------------------------
# read_canary_status() -- stale detection
# ---------------------------------------------------------------------------

class TestReadCanaryStatusStaleness:

    def test_stale_when_age_exceeds_interval(self, tmp_path):
        """CORE TEST: 8h-stale READY file must read back as STALE, not READY."""
        out = tmp_path / "canary_status.json"
        interval = 900.0  # 15 min
        # File was written 8 hours ago (28800s >> 900s interval).
        write_epoch = _BASE_EPOCH - 28_800.0
        _write_json(out, {
            "status": "READY",
            "generated_at": write_epoch,
            "canary_interval_sec": interval,
            "probes": [],
            "notes": [],
        })
        result = read_canary_status(path=out, now=_BASE_EPOCH, interval_sec=interval)
        assert result["status"] == "STALE", (
            "8h-stale READY should degrade to STALE, got %s" % result["status"]
        )
        assert "stale_reason" in result
        assert result["age_sec"] == pytest.approx(28_800.0, abs=1.0)

    def test_degraded_file_also_becomes_stale(self, tmp_path):
        """DEGRADED file that is 2h old must also become STALE."""
        out = tmp_path / "canary_status.json"
        interval = 900.0
        write_epoch = _BASE_EPOCH - 7_200.0
        _write_json(out, {
            "status": "DEGRADED",
            "generated_at": write_epoch,
            "canary_interval_sec": interval,
            "probes": [],
            "notes": [],
        })
        result = read_canary_status(path=out, now=_BASE_EPOCH, interval_sec=interval)
        assert result["status"] == "STALE"

    def test_fresh_file_preserves_status(self, tmp_path):
        """File written just now (age << interval) must keep its original status."""
        out = tmp_path / "canary_status.json"
        interval = 900.0
        # Written 10 seconds ago -- well within the 900s interval.
        write_epoch = _BASE_EPOCH - 10.0
        _write_json(out, {
            "status": "READY",
            "generated_at": write_epoch,
            "canary_interval_sec": interval,
            "probes": [],
            "notes": [],
        })
        result = read_canary_status(path=out, now=_BASE_EPOCH, interval_sec=interval)
        assert result["status"] == "READY", (
            "Fresh file (10s old, interval=900s) should stay READY, got %s" % result["status"]
        )
        assert result["age_sec"] == pytest.approx(10.0, abs=1.0)
        assert "stale_reason" not in result or result.get("stale_reason") is None

    def test_fresh_down_preserved(self, tmp_path):
        """A fresh DOWN file must stay DOWN (stale check must not promote it to STALE)."""
        out = tmp_path / "canary_status.json"
        interval = 900.0
        write_epoch = _BASE_EPOCH - 5.0
        _write_json(out, {
            "status": "DOWN",
            "generated_at": write_epoch,
            "canary_interval_sec": interval,
            "probes": [],
            "notes": [],
        })
        result = read_canary_status(path=out, now=_BASE_EPOCH, interval_sec=interval)
        assert result["status"] == "DOWN"

    def test_absent_file_returns_stale(self, tmp_path):
        out = tmp_path / "nonexistent.json"
        result = read_canary_status(path=out, now=_BASE_EPOCH)
        assert result["status"] == "STALE"

    def test_legacy_file_no_generated_at_returns_stale(self, tmp_path):
        """Legacy canary_status.json without generated_at must read as STALE."""
        out = tmp_path / "canary_status.json"
        # Old format: no generated_at key.
        _write_json(out, {"status": "READY", "probes": [], "notes": []})
        result = read_canary_status(path=out, now=_BASE_EPOCH)
        assert result["status"] == "STALE", (
            "Legacy file without generated_at must be STALE, got %s" % result["status"]
        )

    def test_caller_interval_override_beats_file_stamp(self, tmp_path):
        """Caller can override interval; a 60s-old file is fresh at 900s but stale at 30s."""
        out = tmp_path / "canary_status.json"
        write_epoch = _BASE_EPOCH - 60.0
        _write_json(out, {
            "status": "READY",
            "generated_at": write_epoch,
            "canary_interval_sec": 900.0,
        })
        # With a 30s override interval, 60s age -> STALE.
        result_stale = read_canary_status(path=out, now=_BASE_EPOCH, interval_sec=30.0)
        assert result_stale["status"] == "STALE"
        # With a 900s override interval, 60s age -> still READY.
        result_fresh = read_canary_status(path=out, now=_BASE_EPOCH, interval_sec=900.0)
        assert result_fresh["status"] == "READY"


# ---------------------------------------------------------------------------
# Integration: tick() then read_canary_status()
# ---------------------------------------------------------------------------

class TestTickThenRead:

    def test_fresh_tick_reads_healthy(self, tmp_path):
        """A tick() run just now: read_canary_status at the same clock -> not STALE."""
        out = tmp_path / "canary_status.json"
        interval = 900.0
        tick(now=_BASE_EPOCH, run_fn=_stub_run_fn("READY"), out_path=out,
             interval_sec=interval)
        result = read_canary_status(path=out, now=_BASE_EPOCH, interval_sec=interval)
        # age_sec = 0 (<< 900), status must remain READY.
        assert result["status"] == "READY"
        assert result["age_sec"] == pytest.approx(0.0, abs=0.1)

    def test_stale_tick_reads_stale(self, tmp_path):
        """A tick() run 8h ago: read_canary_status now -> STALE."""
        out = tmp_path / "canary_status.json"
        interval = 900.0
        write_time = _BASE_EPOCH - 28_800.0
        tick(now=write_time, run_fn=_stub_run_fn("READY"), out_path=out,
             interval_sec=interval)
        result = read_canary_status(path=out, now=_BASE_EPOCH, interval_sec=interval)
        assert result["status"] == "STALE", (
            "8h-old tick must read as STALE, got %s" % result["status"]
        )

    def test_stale_reason_contains_interval(self, tmp_path):
        """stale_reason must mention the interval so ops knows the threshold."""
        out = tmp_path / "canary_status.json"
        interval = 900.0
        write_time = _BASE_EPOCH - 28_800.0
        tick(now=write_time, run_fn=_stub_run_fn("READY"), out_path=out,
             interval_sec=interval)
        result = read_canary_status(path=out, now=_BASE_EPOCH, interval_sec=interval)
        reason = result.get("stale_reason", "")
        assert "900" in reason, "stale_reason must include interval; got: %s" % reason


# ---------------------------------------------------------------------------
# run() loop -- interval propagated to tick()
# ---------------------------------------------------------------------------

class TestRunLoopInterval:

    def test_run_stamps_interval_in_output(self, tmp_path):
        """run() with custom interval must write that interval into canary_status.json."""
        out = tmp_path / "canary_status.json"
        clk = iter([_BASE_EPOCH, _BASE_EPOCH + 60.0])
        run(
            run_fn=_stub_run_fn("READY"),
            out_path=out,
            interval_sec=300.0,
            clock=lambda: next(clk),
            sleep=lambda s: None,
            max_ticks=1,
        )
        written = json.loads(out.read_text(encoding="ascii"))
        assert written["canary_interval_sec"] == 300.0
        assert "generated_at" in written
