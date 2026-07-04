"""Offline tests for ops.liveness and ops.structured_log.

Injects fake clocks, fake heartbeat files, and fake log paths.
Never spawns real processes, binds real ports, or writes to production paths.

Per-file run only:
    python -m pytest tests/ops/test_liveness.py -q
"""
from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path

import pytest

from ops import liveness as _lv
from ops import structured_log as _sl


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_text_hb(path: Path, ts: float) -> None:
    """Write a plain-text ISO heartbeat file (daemon_heartbeats style)."""
    from datetime import datetime, timezone
    path.parent.mkdir(parents=True, exist_ok=True)
    content = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    path.write_text(content, encoding="ascii")


def _write_json_hb(path: Path, ts: float, extra: dict | None = None) -> None:
    """Write a JSON heartbeat file (predict_service / ingame style)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"ts": ts, "status": "ok"}
    if extra:
        payload.update(extra)
    path.write_text(json.dumps(payload), encoding="utf-8")


# ---------------------------------------------------------------------------
# liveness.heartbeat
# ---------------------------------------------------------------------------

class TestHeartbeat:
    def test_writes_iso_timestamp(self, tmp_path: Path) -> None:
        hb = tmp_path / "comp.txt"
        fake_ts = 1_000_000.0
        _lv.heartbeat("comp", path=hb, _now=fake_ts)
        assert hb.exists()
        content = hb.read_text(encoding="ascii").strip()
        assert "T" in content and "Z" in content  # ISO-8601 UTC

    def test_atomic_no_tmp_left(self, tmp_path: Path) -> None:
        hb = tmp_path / "comp.txt"
        _lv.heartbeat("comp", path=hb, _now=9999.0)
        tmp_files = list(tmp_path.glob("*.tmp"))
        assert tmp_files == [], "tmp file should be removed after atomic replace"

    def test_never_raises_on_bad_dir(self) -> None:
        # Path that cannot be created (drive root of a non-existent drive).
        bad = Path("/nonexistent_xyz_drive/deep/comp.txt")
        _lv.heartbeat("comp", path=bad)  # must not raise


# ---------------------------------------------------------------------------
# liveness.heartbeat -- test-isolation hazard (wave-22 LANE B)
#
# A bare heartbeat("some_component", _now=...) call with NO explicit path
# (exactly what every real daemon runner's _beat() helper does, and what a
# test that forgets to inject a path/mock also does) must NEVER touch the
# real production data/cache/daemon_heartbeats/ directory while running
# under pytest. Verified two ways: (1) the resolved path is redirected away
# from the production dir, (2) the real production file for a throwaway
# component name is untouched after the bare call.
# ---------------------------------------------------------------------------

class TestHeartbeatTestIsolation:
    def test_bare_call_under_pytest_does_not_resolve_to_production_dir(self) -> None:
        # This test itself runs under pytest, so PYTEST_CURRENT_TEST is set
        # by the test runner already -- no monkeypatch needed to prove the
        # in-test behavior.
        resolved = _lv._resolve_write_path("wave22_isolation_probe", None)
        assert str(_lv._DAEMON_HB_DIR) not in str(resolved)

    def test_bare_call_under_pytest_leaves_production_file_untouched(self) -> None:
        component = "wave22_isolation_probe_writeonce"
        prod_path = _lv._DAEMON_HB_DIR / f"{component}.txt"
        existed_before = prod_path.exists()
        before_content = prod_path.read_text(encoding="ascii") if existed_before else None
        try:
            _lv.heartbeat(component, _now=1.0)  # bare call, no path= -- like a daemon's _beat()
            if existed_before:
                assert prod_path.read_text(encoding="ascii") == before_content
            else:
                assert not prod_path.exists()
        finally:
            # Clean up only if we created it (we shouldn't have).
            if not existed_before and prod_path.exists():
                prod_path.unlink()

    def test_explicit_path_still_wins_under_pytest(self, tmp_path: Path) -> None:
        # Explicit path must always be honored -- this is what real daemons
        # would use if they opted in, and what well-isolated tests already do.
        hb = tmp_path / "explicit.txt"
        resolved = _lv._resolve_write_path("comp", hb)
        assert resolved == hb
        _lv.heartbeat("comp", path=hb, _now=42.0)
        assert hb.exists()

    def test_bare_call_outside_pytest_resolves_to_default_path(self, monkeypatch) -> None:
        # Simulate a real daemon process (PYTEST_CURRENT_TEST unset) to prove
        # daemon call sites are byte-identical to pre-fix behavior.
        monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
        resolved = _lv._resolve_write_path("some_daemon", None)
        assert resolved == _lv._default_hb_path("some_daemon")


# ---------------------------------------------------------------------------
# liveness.is_live
# ---------------------------------------------------------------------------

class TestIsLive:
    def test_fresh_heartbeat_is_live(self, tmp_path: Path) -> None:
        hb = tmp_path / "svc.txt"
        fake_now = 2_000_000.0
        _write_text_hb(hb, fake_now - 5.0)  # 5 s old
        assert _lv.is_live("svc", max_age_sec=60, now=fake_now, path=hb) is True

    def test_stale_heartbeat_is_not_live(self, tmp_path: Path) -> None:
        hb = tmp_path / "svc.txt"
        fake_now = 2_000_000.0
        _write_text_hb(hb, fake_now - 200.0)  # 200 s old
        assert _lv.is_live("svc", max_age_sec=60, now=fake_now, path=hb) is False

    def test_missing_file_is_not_live(self, tmp_path: Path) -> None:
        hb = tmp_path / "nonexistent.txt"
        assert _lv.is_live("svc", max_age_sec=60, path=hb) is False

    def test_fresh_json_heartbeat_is_live(self, tmp_path: Path) -> None:
        hb = tmp_path / "_heartbeat.json"
        fake_now = 3_000_000.0
        _write_json_hb(hb, fake_now - 10.0)
        # Pass path directly so component->JSON path lookup is bypassed
        assert _lv.is_live("predict_service_scheduler", max_age_sec=120, now=fake_now, path=hb) is True

    def test_stale_json_heartbeat_is_not_live(self, tmp_path: Path) -> None:
        hb = tmp_path / "_heartbeat.json"
        fake_now = 3_000_000.0
        _write_json_hb(hb, fake_now - 300.0)
        assert _lv.is_live("predict_service_scheduler", max_age_sec=120, now=fake_now, path=hb) is False

    def test_never_raises_on_corrupt_file(self, tmp_path: Path) -> None:
        hb = tmp_path / "bad.txt"
        hb.write_text("NOT_A_VALID_TIMESTAMP_OR_JSON", encoding="ascii")
        # Should fall back to mtime; mtime is just-now so expect live is True
        result = _lv.is_live("bad", max_age_sec=60, path=hb)
        # We only require it does not raise; value is implementation-defined
        assert isinstance(result, bool)

    def test_exact_boundary_fresh(self, tmp_path: Path) -> None:
        hb = tmp_path / "edge.txt"
        fake_now = 5_000_000.0
        _write_text_hb(hb, fake_now - 60.0)  # exactly at max_age_sec
        assert _lv.is_live("edge", max_age_sec=60, now=fake_now, path=hb) is True

    def test_one_second_over_boundary_stale(self, tmp_path: Path) -> None:
        hb = tmp_path / "edge2.txt"
        fake_now = 5_000_000.0
        _write_text_hb(hb, fake_now - 61.0)
        assert _lv.is_live("edge2", max_age_sec=60, now=fake_now, path=hb) is False


# ---------------------------------------------------------------------------
# liveness.liveness_snapshot
# ---------------------------------------------------------------------------

class TestLivenessSnapshot:
    def _make_registry(self, tmp_path: Path, entries: list) -> Path:
        reg = {"daemons": entries}
        p = tmp_path / "daemon_registry.json"
        p.write_text(json.dumps(reg), encoding="utf-8")
        return p

    def test_snapshot_has_known_keys(self, tmp_path: Path) -> None:
        fake_now = 7_000_000.0

        # Build two fake heartbeat files
        hb1 = tmp_path / "comp_a.txt"
        hb2 = tmp_path / "comp_b.txt"
        _write_text_hb(hb1, fake_now - 10.0)  # fresh
        _write_text_hb(hb2, fake_now - 9999.0)  # stale

        reg_path = self._make_registry(tmp_path, [
            {
                "name": "comp_a",
                "heartbeat_file": str(hb1),
                "expected_interval_sec": 60,
            },
            {
                "name": "comp_b",
                "heartbeat_file": str(hb2),
                "expected_interval_sec": 60,
            },
        ])

        snap = _lv.liveness_snapshot(
            now=fake_now,
            _registry_path=reg_path,
            _hb_dir=tmp_path,
        )
        assert "comp_a" in snap
        assert "comp_b" in snap

    def test_snapshot_live_vs_stale(self, tmp_path: Path) -> None:
        fake_now = 7_000_000.0

        hb_live = tmp_path / "live_d.txt"
        hb_dead = tmp_path / "dead_d.txt"
        _write_text_hb(hb_live, fake_now - 30.0)
        _write_text_hb(hb_dead, fake_now - 100_000.0)

        reg_path = self._make_registry(tmp_path, [
            {"name": "live_d", "heartbeat_file": str(hb_live), "expected_interval_sec": 60},
            {"name": "dead_d", "heartbeat_file": str(hb_dead), "expected_interval_sec": 60},
        ])

        snap = _lv.liveness_snapshot(now=fake_now, _registry_path=reg_path, _hb_dir=tmp_path)
        assert snap["live_d"]["live"] is True
        assert snap["dead_d"]["live"] is False

    def test_snapshot_missing_file(self, tmp_path: Path) -> None:
        fake_now = 7_000_001.0
        reg_path = self._make_registry(tmp_path, [
            {
                "name": "ghost",
                "heartbeat_file": str(tmp_path / "ghost.txt"),
                "expected_interval_sec": 30,
            }
        ])
        snap = _lv.liveness_snapshot(now=fake_now, _registry_path=reg_path, _hb_dir=tmp_path)
        assert snap["ghost"]["live"] is False
        assert snap["ghost"]["age_sec"] is None

    def test_snapshot_never_raises_on_bad_registry(self, tmp_path: Path) -> None:
        bad_reg = tmp_path / "bad_reg.json"
        bad_reg.write_text("NOT JSON {{{", encoding="utf-8")
        snap = _lv.liveness_snapshot(_registry_path=bad_reg)
        assert isinstance(snap, dict)  # may be empty but must not raise

    def test_snapshot_each_entry_has_required_keys(self, tmp_path: Path) -> None:
        fake_now = 7_000_002.0
        hb = tmp_path / "chk.txt"
        _write_text_hb(hb, fake_now - 5.0)
        reg_path = self._make_registry(tmp_path, [
            {"name": "chk", "heartbeat_file": str(hb), "expected_interval_sec": 60},
        ])
        snap = _lv.liveness_snapshot(now=fake_now, _registry_path=reg_path, _hb_dir=tmp_path)
        entry = snap["chk"]
        assert "live" in entry
        assert "age_sec" in entry
        assert "path" in entry


# ---------------------------------------------------------------------------
# structured_log round-trip
# ---------------------------------------------------------------------------

class TestStructuredLog:
    def test_log_event_writes_json_line(self, tmp_path: Path) -> None:
        log_path = tmp_path / "events.jsonl"
        _sl.log_event("test_comp", "INFO", "hello world", path=log_path, _now=1234.0)
        lines = log_path.read_text(encoding="ascii").splitlines()
        assert len(lines) == 1
        rec = json.loads(lines[0])
        assert rec["component"] == "test_comp"
        assert rec["level"] == "INFO"
        assert rec["msg"] == "hello world"
        assert rec["ts"] == 1234.0

    def test_log_event_extra_fields(self, tmp_path: Path) -> None:
        log_path = tmp_path / "events.jsonl"
        _sl.log_event("c", "DEBUG", "m", path=log_path, _now=1.0, sport="nba", count=7)
        rec = json.loads(log_path.read_text(encoding="ascii").strip())
        assert rec["sport"] == "nba"
        assert rec["count"] == 7

    def test_log_event_never_raises_on_bad_path(self) -> None:
        _sl.log_event("c", "ERROR", "bad", path="/nonexistent_xyz/deep/events.jsonl")

    def test_read_events_empty_when_missing(self, tmp_path: Path) -> None:
        events = _sl.read_events(path=tmp_path / "nope.jsonl")
        assert events == []

    def test_read_events_since_filter(self, tmp_path: Path) -> None:
        log_path = tmp_path / "events.jsonl"
        _sl.log_event("c", "INFO", "old", path=log_path, _now=100.0)
        _sl.log_event("c", "INFO", "new", path=log_path, _now=200.0)
        events = _sl.read_events(since=150.0, path=log_path)
        assert len(events) == 1
        assert events[0]["msg"] == "new"

    def test_read_events_since_none_returns_all(self, tmp_path: Path) -> None:
        log_path = tmp_path / "events.jsonl"
        for i in range(3):
            _sl.log_event("c", "INFO", f"msg{i}", path=log_path, _now=float(i))
        events = _sl.read_events(path=log_path)
        assert len(events) == 3

    def test_read_events_skips_corrupt_lines(self, tmp_path: Path) -> None:
        log_path = tmp_path / "events.jsonl"
        log_path.write_text('{"ts":1.0,"component":"c","level":"INFO","msg":"ok"}\nNOT JSON\n', encoding="ascii")
        events = _sl.read_events(path=log_path)
        assert len(events) == 1
        assert events[0]["msg"] == "ok"

    def test_multiple_appends_stay_separate_lines(self, tmp_path: Path) -> None:
        log_path = tmp_path / "events.jsonl"
        for i in range(5):
            _sl.log_event("c", "INFO", f"msg{i}", path=log_path, _now=float(i * 10))
        lines = [l for l in log_path.read_text(encoding="ascii").splitlines() if l.strip()]
        assert len(lines) == 5

    def test_log_event_level_is_uppercased(self, tmp_path: Path) -> None:
        log_path = tmp_path / "events.jsonl"
        _sl.log_event("c", "warning", "m", path=log_path)
        rec = json.loads(log_path.read_text(encoding="ascii").strip())
        assert rec["level"] == "WARNING"

    def test_read_events_since_inclusive_boundary(self, tmp_path: Path) -> None:
        log_path = tmp_path / "events.jsonl"
        _sl.log_event("c", "INFO", "boundary", path=log_path, _now=500.0)
        events = _sl.read_events(since=500.0, path=log_path)
        assert len(events) == 1
