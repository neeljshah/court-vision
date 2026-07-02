"""Per-file tests for feed_health_runner (no network, no real sleep/heartbeat)."""
from __future__ import annotations

from scripts.platformkit.odds_provider.feed_health_runner import (
    HEARTBEAT_COMPONENT, run, tick)


def _fake_scan_green():
    return {"rows": [{"provider": "p", "sport": "mlb", "status": "GREEN"}],
            "n_probed": 1, "n_red": 0, "overall": "GREEN"}


def _fake_scan_red():
    return {"rows": [{"provider": "p", "sport": "mlb", "status": "RED",
                      "reason": "boom"}],
            "n_probed": 1, "n_red": 1, "overall": "RED"}


def test_tick_calls_scan_and_write():
    written = []

    def write_fn(doc, now=None):
        written.append((doc, now))
        return True

    doc = tick(now=100.0, scan_fn=_fake_scan_green, write_fn=write_fn)
    assert doc["overall"] == "GREEN"
    assert len(written) == 1
    assert written[0][1] == 100.0


def test_tick_never_raises_when_scan_raises():
    def boom_scan():
        raise RuntimeError("network down")

    doc = tick(now=1.0, scan_fn=boom_scan, write_fn=lambda doc, now=None: True)
    assert doc["overall"] == "GREEN"  # degrades to the safe empty default, never crashes


def test_tick_never_raises_when_write_raises():
    def boom_write(doc, now=None):
        raise RuntimeError("disk full")

    doc = tick(now=1.0, scan_fn=_fake_scan_red, write_fn=boom_write)
    assert doc["overall"] == "RED"  # scan result still returned even if write failed


def test_run_executes_max_ticks_and_heartbeats():
    clock_calls = {"n": 0}

    def clock():
        clock_calls["n"] += 1
        return float(clock_calls["n"])

    sleeps = []
    ticks = run(scan_fn=_fake_scan_green, write_fn=lambda doc, now=None: True,
               clock=clock, sleep=sleeps.append, max_ticks=3)
    assert ticks == 3
    assert len(sleeps) == 2  # sleeps BETWEEN ticks only; breaks before the final sleep


def test_run_respects_should_stop_immediately():
    ticks = run(scan_fn=_fake_scan_green, write_fn=lambda doc, now=None: True,
               clock=lambda: 1.0, sleep=lambda s: None, should_stop=lambda: True)
    assert ticks == 0


def test_heartbeat_component_name_stable():
    assert HEARTBEAT_COMPONENT == "m30_feed_health"
