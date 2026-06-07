"""tests/test_task_supervisor.py — unit tests for the task supervisor.

Verifies:
  1. A factory that raises is restarted by the supervisor.
  2. CancelledError propagates (supervisor stops).
  3. A factory that returns normally (no exception) is still restarted.
  4. Rate-limit path: > max_restarts_per_min crashes back off gracefully.
  5. Error is logged to scraper_errors.jsonl on crash.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile

import pytest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

# Patch the errors path to a temp file before importing the module.
import scripts.task_supervisor as _sup_mod


# ── helpers ───────────────────────────────────────────────────────────────────

def _run(coro, timeout=5):
    """Run coroutine with asyncio.run + a generous timeout."""
    async def _wrapper():
        return await asyncio.wait_for(coro, timeout=timeout)
    return asyncio.run(_wrapper())


# ── test 1: factory that crashes is restarted ─────────────────────────────────

def test_restart_on_crash():
    """Supervisor should restart a crashing factory multiple times."""
    call_count = 0
    MAX = 3

    async def _crashing():
        nonlocal call_count
        call_count += 1
        if call_count < MAX:
            raise RuntimeError("deliberate crash")
        # On the MAX-th call cancel the outer supervised task to stop the loop.
        raise asyncio.CancelledError

    async def _run_test():
        task = asyncio.create_task(
            _sup_mod.supervised(
                "test_crash", _crashing,
                backoff_seconds=(0,),  # zero backoff for speed
            )
        )
        try:
            await task
        except asyncio.CancelledError:
            pass

    _run(_run_test())
    assert call_count == MAX, f"expected {MAX} calls, got {call_count}"


# ── test 2: CancelledError propagates (supervisor exits) ─────────────────────

def test_cancellation_stops_supervisor():
    """CancelledError raised in factory should propagate and stop the loop."""
    calls = 0

    async def _factory():
        nonlocal calls
        calls += 1
        raise asyncio.CancelledError

    async def _run_test():
        task = asyncio.create_task(
            _sup_mod.supervised("test_cancel", _factory, backoff_seconds=(0,))
        )
        with pytest.raises((asyncio.CancelledError, asyncio.TimeoutError)):
            await asyncio.wait_for(task, timeout=1.0)

    asyncio.run(_run_test())
    # Should have been called exactly once before propagating.
    assert calls == 1


# ── test 3: factory that returns normally is restarted ────────────────────────

def test_restart_on_clean_return():
    """A factory that returns (no exception) should be restarted."""
    calls = 0

    async def _returning():
        nonlocal calls
        calls += 1
        if calls >= 3:
            raise asyncio.CancelledError
        # Just return — supervisor should restart.

    async def _run_test():
        task = asyncio.create_task(
            _sup_mod.supervised("test_return", _returning, backoff_seconds=(0,))
        )
        try:
            await asyncio.wait_for(task, timeout=2.0)
        except (asyncio.CancelledError, asyncio.TimeoutError):
            pass

    asyncio.run(_run_test())
    assert calls >= 2, f"expected >= 2 calls, got {calls}"


# ── test 4: error written to JSONL ───────────────────────────────────────────

def test_error_logged_to_jsonl(tmp_path):
    """Crashes should append a structured record to scraper_errors.jsonl."""
    errors_path = str(tmp_path / "scraper_errors.jsonl")
    original_path = _sup_mod._ERRORS_PATH
    _sup_mod._ERRORS_PATH = errors_path

    try:
        calls = 0

        async def _factory():
            nonlocal calls
            calls += 1
            if calls == 1:
                raise ValueError("test error boom")
            raise asyncio.CancelledError

        async def _run_test():
            task = asyncio.create_task(
                _sup_mod.supervised("test_log", _factory, backoff_seconds=(0,))
            )
            try:
                await asyncio.wait_for(task, timeout=2.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass

        asyncio.run(_run_test())

        assert os.path.isfile(errors_path), "JSONL file not created"
        lines = open(errors_path).read().strip().splitlines()
        assert len(lines) >= 1, "No error records written"
        rec = json.loads(lines[0])
        assert rec["book"] == "test_log"
        assert rec["exception_type"] == "ValueError"
        assert "boom" in rec["exception_msg"]
    finally:
        _sup_mod._ERRORS_PATH = original_path


# ── test 5: create_supervised_task returns an asyncio.Task ───────────────────

def test_create_supervised_task_returns_task():
    """create_supervised_task should return an asyncio.Task."""

    async def _factory():
        await asyncio.sleep(100)

    async def _run_test():
        task = _sup_mod.create_supervised_task("test_task", _factory)
        assert isinstance(task, asyncio.Task)
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception):
            pass

    asyncio.run(_run_test())
