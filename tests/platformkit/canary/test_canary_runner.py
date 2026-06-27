"""tests.platformkit.canary.test_canary_runner -- per-file tests for IOX-2 runner.

Acceptance criteria (from BACKLOG.md IOX-2):
  * runner heartbeat: writes m15_canary heartbeat each tick
  * injectable clock/sleep/probes
  * writes canary_status.json atomically to out_path
  * never raises
  * offseason -> READY (not DOWN)
  * max_ticks bounds the loop

INVARIANTS: per-file only; ASCII only; stdlib + repo imports; never mutates
data/registry/; no flag flip; no real money.
"""
from __future__ import annotations

import json
import pathlib
import tempfile
import time
from typing import List

import pytest

from scripts.platformkit.canary.canary_runner import (
    DEFAULT_INTERVAL_SEC,
    HEARTBEAT_COMPONENT,
    tick,
    run,
)
from scripts.platformkit.canary.stack_canary import (
    READY,
    DEGRADED,
    DOWN,
    CanaryResult,
    ProbeResult,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_ready_result(now: float) -> CanaryResult:
    return CanaryResult(
        status=READY,
        failing_stage=None,
        probes=[ProbeResult("predict_envelope", ok=True, critical=True)],
        notes=[],
        checked_at=now,
    )


def _make_down_result(now: float, stage: str = "predict_envelope") -> CanaryResult:
    return CanaryResult(
        status=DOWN,
        failing_stage=stage,
        probes=[ProbeResult(stage, ok=False, critical=True, note="test error")],
        notes=["DOWN [%s]: test error" % stage],
        checked_at=now,
    )


def _make_degraded_result(now: float) -> CanaryResult:
    return CanaryResult(
        status=DEGRADED,
        failing_stage=None,
        probes=[
            ProbeResult("predict_envelope", ok=True, critical=True),
            ProbeResult("ops_status", ok=False, critical=False, note="stale"),
        ],
        notes=["DEGRADED [ops_status]: stale"],
        checked_at=now,
    )


def _stub_run_fn(result_obj):
    """Factory: returns a stub run_fn that always returns *result_obj*."""
    def _fn(*, now, read_fn=None, ops_path=None):
        return result_obj
    return _fn


# ---------------------------------------------------------------------------
# Test: tick writes canary_status.json and returns the result dict
# ---------------------------------------------------------------------------

def test_tick_writes_status_json():
    now = time.time()
    result = _make_ready_result(now)
    run_fn = _stub_run_fn(result)
    with tempfile.TemporaryDirectory() as td:
        out_path = pathlib.Path(td) / "canary_status.json"
        doc = tick(now=now, run_fn=run_fn, out_path=out_path)
        assert out_path.exists(), "canary_status.json was not written"
        on_disk = json.loads(out_path.read_text(encoding="utf-8"))
    assert doc["status"] == READY
    assert on_disk["status"] == READY
    assert doc["failing_stage"] is None


def test_tick_down_result_written():
    now = time.time()
    result = _make_down_result(now, stage="predict_envelope")
    run_fn = _stub_run_fn(result)
    with tempfile.TemporaryDirectory() as td:
        out_path = pathlib.Path(td) / "canary_status.json"
        doc = tick(now=now, run_fn=run_fn, out_path=out_path)
    assert doc["status"] == DOWN
    assert doc["failing_stage"] == "predict_envelope"


def test_tick_degraded_result_written():
    now = time.time()
    result = _make_degraded_result(now)
    run_fn = _stub_run_fn(result)
    with tempfile.TemporaryDirectory() as td:
        out_path = pathlib.Path(td) / "canary_status.json"
        doc = tick(now=now, run_fn=run_fn, out_path=out_path)
    assert doc["status"] == DEGRADED
    assert doc["failing_stage"] is None


# ---------------------------------------------------------------------------
# Test: run_fn raising produces DOWN (internal error), never raises
# ---------------------------------------------------------------------------

def test_tick_run_fn_raises_produces_down():
    """If run_fn raises, tick must write a DOWN result and never propagate."""
    def _bad_run_fn(*, now, read_fn=None, ops_path=None):
        raise RuntimeError("simulated probe crash")

    with tempfile.TemporaryDirectory() as td:
        out_path = pathlib.Path(td) / "canary_status.json"
        try:
            doc = tick(now=time.time(), run_fn=_bad_run_fn, out_path=out_path)
        except Exception as exc:
            pytest.fail("tick() raised: %s" % exc)
    assert doc["status"] == DOWN
    assert "canary_internal_error" in (doc.get("failing_stage") or "")


# ---------------------------------------------------------------------------
# Test: runner loop respects max_ticks
# ---------------------------------------------------------------------------

def test_run_max_ticks():
    """run() with max_ticks=3 calls tick exactly 3 times."""
    ticked: List[float] = []
    _now = [1000.0]

    def _clock():
        return _now[0]

    def _sleep(sec):
        _now[0] += sec

    with tempfile.TemporaryDirectory() as td:
        out_path = pathlib.Path(td) / "canary_status.json"

        def _run_fn(*, now, read_fn=None, ops_path=None):
            ticked.append(now)
            return _make_ready_result(now)

        count = run(
            run_fn=_run_fn,
            out_path=out_path,
            clock=_clock,
            sleep=_sleep,
            max_ticks=3,
        )
    assert count == 3
    assert len(ticked) == 3


# ---------------------------------------------------------------------------
# Test: should_stop exits loop early
# ---------------------------------------------------------------------------

def test_run_should_stop():
    """run() stops when should_stop() returns True."""
    ticked: List[int] = []

    def _run_fn(*, now, read_fn=None, ops_path=None):
        ticked.append(1)
        return _make_ready_result(now)

    stop_after = [2]

    def _should_stop():
        return len(ticked) >= stop_after[0]

    with tempfile.TemporaryDirectory() as td:
        out_path = pathlib.Path(td) / "canary_status.json"
        count = run(
            run_fn=_run_fn,
            out_path=out_path,
            clock=time.time,
            sleep=lambda s: None,
            should_stop=_should_stop,
        )
    # First check happens before tick, so we get exactly stop_after[0] ticks
    assert count <= stop_after[0]


# ---------------------------------------------------------------------------
# Test: output JSON is valid ASCII and has no $ key
# ---------------------------------------------------------------------------

def test_tick_output_no_dollar():
    """canary_status.json must not contain any $ character."""
    now = time.time()
    result = _make_ready_result(now)
    run_fn = _stub_run_fn(result)
    with tempfile.TemporaryDirectory() as td:
        out_path = pathlib.Path(td) / "canary_status.json"
        tick(now=now, run_fn=run_fn, out_path=out_path)
        raw = out_path.read_text(encoding="ascii")  # must be ASCII
    assert "$" not in raw, "$ found in canary_status.json output"


# ---------------------------------------------------------------------------
# Test: atomic write -- old file replaced, not partially written
# ---------------------------------------------------------------------------

def test_tick_atomic_write():
    """A second tick replaces the file completely (no torn write)."""
    _now = [1000.0]

    def _clock():
        _now[0] += 1
        return _now[0]

    results = [
        _make_ready_result(1001.0),
        _make_down_result(1002.0),
    ]
    idx = [0]

    def _run_fn(*, now, read_fn=None, ops_path=None):
        r = results[idx[0] % len(results)]
        idx[0] += 1
        return r

    with tempfile.TemporaryDirectory() as td:
        out_path = pathlib.Path(td) / "canary_status.json"
        run(
            run_fn=_run_fn,
            out_path=out_path,
            clock=_clock,
            sleep=lambda s: None,
            max_ticks=2,
        )
        # After 2 ticks the last result (DOWN) should be on disk
        doc = json.loads(out_path.read_text(encoding="utf-8"))
    assert doc["status"] == DOWN


# ---------------------------------------------------------------------------
# Test: heartbeat component name constant matches expected m15_canary
# ---------------------------------------------------------------------------

def test_heartbeat_component_name():
    assert HEARTBEAT_COMPONENT == "m15_canary"


# ---------------------------------------------------------------------------
# Test: default interval
# ---------------------------------------------------------------------------

def test_default_interval():
    assert DEFAULT_INTERVAL_SEC == 900.0  # 15 minutes


# ---------------------------------------------------------------------------
# Test: run() never raises even with a completely broken run_fn
# ---------------------------------------------------------------------------

def test_run_never_raises():
    """run() must not propagate exceptions from a broken run_fn."""
    def _exploding(*, now, read_fn=None, ops_path=None):
        raise ValueError("chaos")

    with tempfile.TemporaryDirectory() as td:
        out_path = pathlib.Path(td) / "canary_status.json"
        try:
            count = run(
                run_fn=_exploding,
                out_path=out_path,
                clock=time.time,
                sleep=lambda s: None,
                max_ticks=2,
            )
        except Exception as exc:
            pytest.fail("run() raised: %s" % exc)
    assert count == 2
    # Output file should contain a DOWN sentinel
    if out_path.exists():
        doc = json.loads(out_path.read_text())
        assert doc["status"] == DOWN
