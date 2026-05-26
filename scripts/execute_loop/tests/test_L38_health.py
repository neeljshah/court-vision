"""Tests for scripts/execute_loop/L38_health_dashboard.py.

Run:
    conda run -n basketball_ai --no-capture-output \
        python -m pytest scripts/execute_loop/tests/test_L38_health.py -v
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Project root + stub heavy side-effect imports
# ---------------------------------------------------------------------------
PROJECT_DIR = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(PROJECT_DIR))

# Stub nba_api_headers_patch so it doesn't need the real package
_api_stub = types.ModuleType("src.data.nba_api_headers_patch")
sys.modules.setdefault("src.data.nba_api_headers_patch", _api_stub)

# Stub src.prediction.live_engine (so live_engine check can be tested in isolation)
_le_stub = types.ModuleType("src.prediction.live_engine")
sys.modules.setdefault("src.prediction.live_engine", _le_stub)

import scripts.execute_loop.L38_health_dashboard as L38  # noqa: E402


# ---------------------------------------------------------------------------
# Helper: build a minimal stub check function
# ---------------------------------------------------------------------------

def _make_stub(name: str, status: str = "PASS", severity: str = "critical",
               raise_exc: bool = False) -> "callable":
    """Return a zero-arg callable that produces a HealthCheck (or raises)."""
    def _fn():
        if raise_exc:
            raise RuntimeError("simulated failure")
        return L38.HealthCheck(
            name=name,
            status=status,
            latency_ms=1.0,
            last_data_ts=None,
            days_stale=0.0,
            details="stub",
            severity=severity,
        )
    return _fn


# ---------------------------------------------------------------------------
# Test 1 — run_check with stub returning PASS
# ---------------------------------------------------------------------------

def test_run_check_pass(tmp_path):
    """Registering a stub that returns PASS → run_check returns status PASS."""
    # Temporarily inject a stub into the registry
    original = L38._REGISTRY.copy()
    L38._REGISTRY["__test_pass__"] = _make_stub("__test_pass__", "PASS", "critical")
    try:
        result = L38.run_check("__test_pass__")
        assert result.status == "PASS"
        assert result.name == "__test_pass__"
    finally:
        L38._REGISTRY.clear()
        L38._REGISTRY.update(original)


# ---------------------------------------------------------------------------
# Test 2 — run_check with stub raising Exception → FAIL + traceback in details
# ---------------------------------------------------------------------------

def test_run_check_exception_becomes_fail():
    """A stub that raises should produce status FAIL with 'Traceback' in details."""
    original = L38._REGISTRY.copy()
    # Wrap with the register decorator's exception handling by using the raw wrapper
    # pattern from the module: we store the _wrapper directly.
    def _raising():
        raise ValueError("boom")

    # Manually apply the wrapper logic (mirrors what @register does)
    def _wrapped() -> L38.HealthCheck:
        t0 = time.perf_counter()
        try:
            return _raising()
        except Exception:
            import traceback as _tb
            latency_ms = (time.perf_counter() - t0) * 1000
            tb = _tb.format_exc()[-800:]
            return L38.HealthCheck(
                name="__test_exc__",
                status="FAIL",
                latency_ms=round(latency_ms, 1),
                last_data_ts=None,
                days_stale=0.0,
                details=f"Traceback:\n{tb}",
                severity="critical",
            )

    L38._REGISTRY["__test_exc__"] = _wrapped
    try:
        result = L38.run_check("__test_exc__")
        assert result.status == "FAIL"
        assert "Traceback" in result.details
    finally:
        L38._REGISTRY.clear()
        L38._REGISTRY.update(original)


# ---------------------------------------------------------------------------
# Test 3 — run_all_checks with one critical FAIL → overall FAILED
# ---------------------------------------------------------------------------

def test_run_all_checks_critical_fail_gives_failed(tmp_path):
    """One critical FAIL among checks should produce overall_status == FAILED."""
    with patch.dict(L38._REGISTRY, {
        "a": _make_stub("a", "PASS", "critical"),
        "b": _make_stub("b", "FAIL", "critical"),   # ← critical fail
        "c": _make_stub("c", "WARN", "warning"),
    }, clear=True), \
    patch.object(L38, "_persist"):   # don't write to disk
        report = L38.run_all_checks()

    assert report.overall_status == "FAILED"


# ---------------------------------------------------------------------------
# Test 4 — run_all_checks with only WARNs (no FAIL) → DEGRADED
# ---------------------------------------------------------------------------

def test_run_all_checks_warn_only_gives_degraded(tmp_path):
    """All checks WARN (warning severity) and no FAILs → DEGRADED."""
    with patch.dict(L38._REGISTRY, {
        "a": _make_stub("a", "WARN", "warning"),
        "b": _make_stub("b", "WARN", "critical"),
    }, clear=True), \
    patch.object(L38, "_persist"):
        report = L38.run_all_checks()

    assert report.overall_status == "DEGRADED"


# ---------------------------------------------------------------------------
# Test 5 — run_all_checks all PASS → HEALTHY
# ---------------------------------------------------------------------------

def test_run_all_checks_all_pass_gives_healthy():
    """All checks PASS → overall_status == HEALTHY."""
    with patch.dict(L38._REGISTRY, {
        "a": _make_stub("a", "PASS", "critical"),
        "b": _make_stub("b", "PASS", "warning"),
        "c": _make_stub("c", "PASS", "info"),
    }, clear=True), \
    patch.object(L38, "_persist"):
        report = L38.run_all_checks()

    assert report.overall_status == "HEALTHY"


# ---------------------------------------------------------------------------
# Test 6 — get_latest_health called twice within 60s hits cache
# ---------------------------------------------------------------------------

def test_get_latest_health_cache(tmp_path, monkeypatch):
    """Second call to get_latest_health within TTL must not re-read from disk."""
    # Reset cache state
    monkeypatch.setattr(L38, "_CACHE", None)
    monkeypatch.setattr(L38, "_CACHE_TS", 0.0)

    fake_report = L38.HealthReport(
        timestamp="2025-01-01T00:00:00+00:00",
        overall_status="HEALTHY",
        checks=[],
    )

    call_count = {"n": 0}

    def _fake_run_all():
        call_count["n"] += 1
        return fake_report

    monkeypatch.setattr(L38, "run_all_checks", _fake_run_all)

    # Simulate no cached file on disk so first call hits run_all_checks
    monkeypatch.setattr(L38._HEALTH_FILE.__class__, "exists",
                        lambda self: False, raising=False)

    # First call — should invoke run_all_checks
    r1 = L38.get_latest_health()
    # Manually seed the in-process cache as run_all_checks would do
    monkeypatch.setattr(L38, "_CACHE", fake_report)
    monkeypatch.setattr(L38, "_CACHE_TS", time.monotonic())

    # Second call — should hit in-process cache, NOT run_all_checks again
    r2 = L38.get_latest_health()

    assert r1.overall_status == r2.overall_status == "HEALTHY"
    assert call_count["n"] == 1, "run_all_checks should only be called once"


# ---------------------------------------------------------------------------
# Test 7 — run_all_checks writes valid JSON that round-trips
# ---------------------------------------------------------------------------

def test_run_all_checks_writes_valid_json(tmp_path, monkeypatch):
    """JSON written by run_all_checks must be parseable and round-trip."""
    health_path = tmp_path / "system_health.json"
    monkeypatch.setattr(L38, "_HEALTH_FILE", health_path)

    with patch.dict(L38._REGISTRY, {
        "a": _make_stub("a", "PASS", "critical"),
    }, clear=True):
        report = L38.run_all_checks()

    assert health_path.exists(), "health JSON file not written"
    raw = health_path.read_text(encoding="utf-8")
    parsed = json.loads(raw)
    assert parsed["overall_status"] == report.overall_status
    assert isinstance(parsed["checks"], list)
    assert parsed["checks"][0]["name"] == "a"


# ---------------------------------------------------------------------------
# Test 8 — CLI `once` exits with codes 0/1/2
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("overall,expected_code", [
    ("HEALTHY", 0),
    ("DEGRADED", 1),
    ("FAILED", 2),
])
def test_cli_once_exit_codes(overall, expected_code, tmp_path, monkeypatch):
    """CLI `once` must exit 0/1/2 for HEALTHY/DEGRADED/FAILED."""
    script = PROJECT_DIR / "scripts" / "execute_loop" / "L38_health_dashboard.py"

    # Build a tiny inline script that monkey-patches run_all_checks, then
    # calls main(["once"]).  We pass it via -c to python.
    inline = f"""
import sys, types

# Stub heavy side-effects
sys.modules.setdefault("src.data.nba_api_headers_patch", types.ModuleType("x"))
sys.modules.setdefault("src.prediction.live_engine", types.ModuleType("y"))

sys.path.insert(0, r"{PROJECT_DIR}")
import scripts.execute_loop.L38_health_dashboard as L38
from unittest.mock import patch
from dataclasses import dataclass

fake = L38.HealthReport(
    timestamp="2025-01-01T00:00:00+00:00",
    overall_status="{overall}",
    checks=[],
)
with patch.object(L38, "run_all_checks", return_value=fake), \\
     patch.object(L38, "_print_report"):
    L38.main(["once"])
"""
    proc = subprocess.run(
        [sys.executable, "-c", inline],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert proc.returncode == expected_code, (
        f"Expected exit {expected_code} for {overall}, got {proc.returncode}\n"
        f"stdout: {proc.stdout}\nstderr: {proc.stderr}"
    )


# ---------------------------------------------------------------------------
# Test 9 — _atomic_write_text replaces an existing file atomically
# ---------------------------------------------------------------------------

def test_atomic_write_replaces_existing_file(tmp_path):
    """_atomic_write_text must overwrite an existing file with new content."""
    target = tmp_path / "out.json"
    target.write_text("old content", encoding="utf-8")

    L38._atomic_write_text(target, "new content")

    assert target.exists()
    assert target.read_text(encoding="utf-8") == "new content"
    # No leftover .tmp files
    tmps = list(tmp_path.glob("*.tmp"))
    assert tmps == [], f"Leftover tmp files: {tmps}"


# ---------------------------------------------------------------------------
# Test 10 — _atomic_write_text cleans up .tmp and leaves original on failure
# ---------------------------------------------------------------------------

def test_atomic_write_no_partial_on_failure(tmp_path, monkeypatch):
    """When os.replace raises, the original file must be unchanged and .tmp cleaned up."""
    target = tmp_path / "out.json"
    target.write_text("original", encoding="utf-8")

    def _failing_replace(src, dst):
        raise OSError("simulated replace failure")

    monkeypatch.setattr(os, "replace", _failing_replace)

    with pytest.raises(OSError, match="simulated replace failure"):
        L38._atomic_write_text(target, "should not appear")

    # Original must be untouched
    assert target.read_text(encoding="utf-8") == "original"
    # Temp file must have been cleaned up
    tmps = list(tmp_path.glob("out.json.*.tmp"))
    assert tmps == [], f"Leftover tmp files after failure: {tmps}"
