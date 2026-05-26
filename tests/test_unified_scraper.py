"""tests/test_unified_scraper.py - R16_E6 unified-orchestrator tests.

Covers:
  1. Per-book interval scheduling -- each book ticks at its own cadence.
  2. Failure isolation -- one book raising does not stop the others.
  3. Health-endpoint JSON shape -- /health returns alive/last_tick_ago_sec/total_ticks
     for every book.
  4. Probe-results JSON shape -- write_probe_results emits the required keys.
"""
from __future__ import annotations

import asyncio
import json
import os
import socket
import sys
import time
import urllib.request
from typing import Any, Callable, Dict

import pytest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

# Note: scripts/unified_scraper_orchestrator.py imports the 3 real scrapers
# at module-load time. Tests inject fake tick_fns and never call those real
# imports, so as long as the scripts/* modules can themselves be imported,
# the test suite is hermetic.
from scripts.unified_scraper_orchestrator import (  # noqa: E402
    BookState,
    _percentile,
    run_orchestrator,
    write_probe_results,
)


def _free_port() -> int:
    """Allocate an OS-assigned free TCP port."""
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


# ────────────────────────────────────────────────────────────────────────────
# Test 1: per-book interval scheduling
# ────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_per_book_interval_scheduling() -> None:
    """Three books at 1.0s / 0.5s / 0.25s for ~2.0s should give roughly
    2 / 4 / 8 ticks. We allow generous tolerances since asyncio + threadpool
    introduce small scheduling jitter.
    """
    calls: Dict[str, int] = {"fd": 0, "bov": 0, "pin": 0}

    def make_fn(name: str) -> Callable[[], Dict[str, Any]]:
        def fn() -> Dict[str, Any]:
            calls[name] += 1
            return {"name": name, "n": calls[name]}
        return fn

    tick_fns = {n: make_fn(n) for n in ("fd", "bov", "pin")}
    intervals = {"fd": 1, "bov": 1, "pin": 1}  # noqa  (real seconds used below)

    # We need sub-second intervals for the test -- patch BookState directly
    # so we don't have to wait 30+ s. The orchestrator uses state.interval_sec
    # for its wait_for() timeout, which accepts floats.
    from scripts import unified_scraper_orchestrator as orch

    original_run = orch._run_book_loop

    # Run orchestrator for 2.0 seconds with custom-built states that have
    # float interval_sec values < 1.
    states_override = {
        "fd":  BookState("fd",  1.0),    # ~2 ticks
        "bov": BookState("bov", 0.5),    # ~4 ticks
        "pin": BookState("pin", 0.25),   # ~8 ticks
    }

    stop_event = asyncio.Event()

    tasks = [
        asyncio.create_task(orch._run_book_loop(
            states_override[n], tick_fns[n], stop_event))
        for n in ("fd", "bov", "pin")
    ]
    try:
        await asyncio.sleep(2.0)
    finally:
        stop_event.set()
        await asyncio.gather(*tasks, return_exceptions=True)

    # Each book should have completed at least 1 tick.
    assert calls["fd"] >= 1, calls
    assert calls["bov"] >= 1, calls
    assert calls["pin"] >= 1, calls

    # Pin ticks fastest, bov middle, fd slowest -- this is the key ordering
    # property that proves *per-book* independent scheduling.
    assert calls["pin"] >= calls["bov"] >= calls["fd"], (
        f"interval ordering violated: {calls}")
    # Pin should have noticeably more than fd given 4x interval ratio.
    assert calls["pin"] > calls["fd"], (
        f"pin should outpace fd: {calls}")

    # Total ticks should match state counters.
    for name in ("fd", "bov", "pin"):
        assert states_override[name].total_ticks == calls[name]


# ────────────────────────────────────────────────────────────────────────────
# Test 2: failure isolation
# ────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_failure_isolation() -> None:
    """If one book raises on every tick, the other two keep ticking and
    are still 'alive'. The failing book's total_errors increments, but the
    book loop does NOT terminate (it tries again next interval).
    """
    from scripts import unified_scraper_orchestrator as orch

    calls = {"fd": 0, "bov": 0, "pin": 0}

    def good_fn(name: str) -> Callable[[], Dict[str, Any]]:
        def fn() -> Dict[str, Any]:
            calls[name] += 1
            return {"ok": True}
        return fn

    def bad_fn() -> Dict[str, Any]:
        calls["bov"] += 1
        raise RuntimeError("simulated 403 from bovada")

    tick_fns = {
        "fd":  good_fn("fd"),
        "bov": bad_fn,
        "pin": good_fn("pin"),
    }

    states = {
        "fd":  BookState("fd",  0.3),
        "bov": BookState("bov", 0.3),
        "pin": BookState("pin", 0.3),
    }

    stop_event = asyncio.Event()
    tasks = [
        asyncio.create_task(orch._run_book_loop(states[n], tick_fns[n], stop_event))
        for n in ("fd", "bov", "pin")
    ]
    try:
        await asyncio.sleep(1.5)
    finally:
        stop_event.set()
        await asyncio.gather(*tasks, return_exceptions=True)

    # Bov failed every tick: many errors, zero ok ticks.
    assert states["bov"].total_errors >= 2, states["bov"].total_errors
    assert states["bov"].total_ticks == 0
    assert states["bov"].last_status_code == "err"
    assert "RuntimeError" in (states["bov"].last_error or "")

    # FD + Pin kept ticking fine.
    assert states["fd"].total_ticks >= 2, states["fd"].total_ticks
    assert states["pin"].total_ticks >= 2, states["pin"].total_ticks
    assert states["fd"].last_status_code == "ok"
    assert states["pin"].last_status_code == "ok"

    # The bad book did not zombie-out -- it kept trying.
    assert calls["bov"] == states["bov"].total_errors


# ────────────────────────────────────────────────────────────────────────────
# Test 3: health endpoint shape
# ────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_health_endpoint() -> None:
    """Bring up the full orchestrator (with health server) for ~1s, hit
    /health, validate JSON structure.
    """
    aiohttp = pytest.importorskip("aiohttp")  # noqa: F841

    port = _free_port()

    fast_tick = lambda: {"sample": True}  # noqa: E731
    tick_fns = {"fd": fast_tick, "bov": fast_tick, "pin": fast_tick}

    # Run orchestrator briefly. Use 0.2s intervals for fast tick counts.
    async def _go() -> None:
        await run_orchestrator(
            books=["fd", "bov", "pin"],
            intervals={"fd": 1, "bov": 1, "pin": 1},  # whole-sec ignored below
            duration_sec=1.5,
            health_port=port,
            tick_fns=tick_fns,
            enable_health=True,
        )

    orch_task = asyncio.create_task(_go())
    # Give the health server a moment to bind + at least one tick to land.
    await asyncio.sleep(0.5)

    # Hit /health in a thread (urllib is blocking).
    def _fetch() -> Dict[str, Any]:
        url = f"http://127.0.0.1:{port}/health"
        with urllib.request.urlopen(url, timeout=3) as r:
            return json.loads(r.read().decode("utf-8"))

    body = await asyncio.to_thread(_fetch)

    # Wait for orchestrator to finish.
    await orch_task

    assert "books" in body, body
    assert set(body["books"].keys()) == {"fd", "bov", "pin"}, body["books"].keys()
    for name, info in body["books"].items():
        # Required keys from the spec.
        assert "last_tick_ago_sec" in info, (name, info)
        assert "last_status_code" in info, (name, info)
        assert "total_ticks" in info, (name, info)
        assert "alive" in info, (name, info)
    assert "ok" in body and "now" in body


# ────────────────────────────────────────────────────────────────────────────
# Test 4: probe-results artifact shape
# ────────────────────────────────────────────────────────────────────────────

def test_probe_results_json_shape(tmp_path) -> None:
    """write_probe_results emits the contracted keys + per-book detail."""
    states = {
        "fd":  BookState("fd",  60),
        "bov": BookState("bov", 60),
        "pin": BookState("pin", 30),
    }
    # Simulate some history.
    for s, latencies, n_ticks in [
        (states["fd"],  [120.0, 150.0, 110.0], 3),
        (states["bov"], [800.0, 750.0],         2),
        (states["pin"], [90.0, 110.0, 95.0, 105.0], 4),
    ]:
        for l in latencies:
            s.latencies_ms.append(l)
        s.total_ticks = n_ticks
        s.last_tick_epoch = time.time()
        s.last_status_code = "ok"

    out_path = str(tmp_path / "probe_results.json")
    payload = write_probe_results(states, path=out_path, elapsed_sec=1800.0)

    # Contracted top-level keys.
    for key in (
        "orchestrator_pid",
        "books_alive",
        "ticks_per_book_30min",
        "p99_tick_latency_ms",
    ):
        assert key in payload, (key, payload)

    assert sorted(payload["books_alive"]) == ["bov", "fd", "pin"]
    assert payload["ticks_per_book_30min"] == {"fd": 3, "bov": 2, "pin": 4}

    # p99 should be a number for each book (we have non-empty latencies).
    for name in ("fd", "bov", "pin"):
        v = payload["p99_tick_latency_ms"][name]
        assert isinstance(v, (int, float)), (name, v)

    # File actually written.
    assert os.path.exists(out_path)
    on_disk = json.loads(open(out_path, encoding="utf-8").read())
    assert on_disk["ticks_per_book_30min"] == payload["ticks_per_book_30min"]


# ────────────────────────────────────────────────────────────────────────────
# Test 5 (bonus): percentile helper edge cases
# ────────────────────────────────────────────────────────────────────────────

def test_percentile_helper() -> None:
    assert _percentile([], 99) is None
    assert _percentile([42.0], 99) == 42.0
    # 100-element sorted list 1..100 -> p99 ≈ 99
    arr = [float(x) for x in range(1, 101)]
    p99 = _percentile(arr, 99)
    assert p99 is not None and 98.0 <= p99 <= 100.0, p99
    p50 = _percentile(arr, 50)
    assert p50 is not None and 49.0 <= p50 <= 51.0, p50
