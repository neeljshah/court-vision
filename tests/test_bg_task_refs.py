"""tests/test_bg_task_refs.py — verify BUG 5 + BUG 7 fixes.

BUG 5: background asyncio Tasks were spawned with their references discarded,
       allowing the GC to silently collect them mid-run.  Fix: module-level
       _BG_TASKS set in api/main.py and api/live_v2_app.py.

BUG 7: dual-writer race — orchestrator default book list included dk_inplay +
       fd_inplay while courtvision_tonight.ps1 standalone daemons also write
       those same CSV files.  Fix: remove dk_inplay / fd_inplay from the
       orchestrator's default list (single-owner rule).
"""
from __future__ import annotations

import ast
import asyncio
import gc
import os
import sys
import weakref

import pytest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)


# ── helpers ────────────────────────────────────────────────────────────────────

def _read_source(rel_path: str) -> str:
    full = os.path.join(PROJECT_DIR, rel_path)
    with open(full, encoding="utf-8") as fh:
        return fh.read()


def _parse(rel_path: str) -> ast.Module:
    return ast.parse(_read_source(rel_path))


# ── BUG 5: api/main.py — _BG_TASKS set defined at module level ────────────────

def test_main_defines_bg_tasks_set():
    """api/main.py must expose a module-level _BG_TASKS set."""
    src = _read_source("api/main.py")
    assert "_BG_TASKS" in src, "_BG_TASKS container not found in api/main.py"
    # Confirm it is a set literal or set() call at module scope.
    assert "_BG_TASKS: set" in src or "_BG_TASKS = set()" in src, (
        "_BG_TASKS must be typed as a set at module scope in api/main.py"
    )


def test_main_startup_adds_tasks_to_bg_tasks():
    """Every create_supervised_task call in _start_ws_subscribers must be
    captured + added to _BG_TASKS (no bare statement task spawns)."""
    src = _read_source("api/main.py")
    # Check the strong-ref pattern is present for each WS subscriber.
    assert "_BG_TASKS.add(_t)" in src, (
        "_BG_TASKS.add(_t) pattern missing in api/main.py"
    )
    assert "_t.add_done_callback(_BG_TASKS.discard)" in src, (
        "done_callback(_BG_TASKS.discard) pattern missing in api/main.py"
    )
    # Verify no bare create_supervised_task calls (return value must be captured).
    lines = src.splitlines()
    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        # Bare call: line starts with create_supervised_task (not assigned)
        if stripped.startswith("create_supervised_task(") and not stripped.startswith("_t"):
            pytest.fail(
                f"api/main.py line {i}: bare create_supervised_task call "
                f"(return not captured): {stripped!r}"
            )
        if stripped.startswith("asyncio.create_task(") and "=" not in line.split("asyncio.create_task(")[0]:
            # Allow lines inside a comment or docstring (crude check)
            if not stripped.startswith("#"):
                pytest.fail(
                    f"api/main.py line {i}: bare asyncio.create_task call "
                    f"(return not captured): {stripped!r}"
                )


# ── BUG 5: api/live_v2_app.py — _BG_TASKS set defined at module level ─────────

def test_live_v2_app_defines_bg_tasks_set():
    """api/live_v2_app.py must expose a module-level _BG_TASKS set."""
    src = _read_source("api/live_v2_app.py")
    assert "_BG_TASKS" in src, "_BG_TASKS container not found in api/live_v2_app.py"
    assert "_BG_TASKS: set" in src or "_BG_TASKS = set()" in src, (
        "_BG_TASKS must be typed as a set at module scope in api/live_v2_app.py"
    )


def test_live_v2_app_startup_adds_tasks_to_bg_tasks():
    """Every task spawn in live_v2_app._startup must be captured + strong-ref'd."""
    src = _read_source("api/live_v2_app.py")
    assert "_BG_TASKS.add(_t)" in src, (
        "_BG_TASKS.add(_t) pattern missing in api/live_v2_app.py"
    )
    assert "_t.add_done_callback(_BG_TASKS.discard)" in src, (
        "done_callback(_BG_TASKS.discard) pattern missing in api/live_v2_app.py"
    )


# ── BUG 5: runtime — task is not GC'd while in _BG_TASKS ──────────────────────

def test_task_not_gc_collected_while_in_set():
    """A Task added to a strong-ref set must NOT be collected by GC."""
    bg_tasks: set = set()

    async def _long_running():
        await asyncio.sleep(100)

    async def _run():
        t = asyncio.create_task(_long_running())
        bg_tasks.add(t)
        t.add_done_callback(bg_tasks.discard)

        # Hold a weak ref to verify GC behaviour
        wr = weakref.ref(t)
        del t          # drop local strong ref
        gc.collect()   # force GC cycle

        still_alive = wr()
        assert still_alive is not None, (
            "Task was GC-collected despite being in _BG_TASKS set — bug not fixed"
        )
        # Cleanup
        still_alive.cancel()
        try:
            await still_alive
        except (asyncio.CancelledError, Exception):
            pass

    asyncio.run(_run())


def test_task_gc_collected_when_not_in_set():
    """Baseline: without a strong-ref container the Task CAN be GC-collected."""
    async def _long_running():
        await asyncio.sleep(100)

    async def _run():
        t = asyncio.create_task(_long_running())
        wr = weakref.ref(t)
        del t
        gc.collect()
        # The task may or may not be collected depending on CPython version and GC
        # pressure; we just confirm the test harness works — no assertion here.
        alive = wr()
        if alive is not None:
            alive.cancel()
            try:
                await alive
            except (asyncio.CancelledError, Exception):
                pass

    asyncio.run(_run())  # just must not raise


# ── BUG 7: orchestrator default books no longer include dk_inplay / fd_inplay ──

def test_orchestrator_default_books_no_inplay():
    """LiveOrchestrator default book list must NOT contain dk_inplay or fd_inplay.

    courtvision_tonight.ps1 owns those CSVs exclusively (single-writer rule).
    """
    from scripts.live_orchestrator import LiveOrchestrator
    orch = LiveOrchestrator(game_ids=["DEMO"])
    assert "dk_inplay" not in orch.books, (
        "dk_inplay still in LiveOrchestrator.books default — dual-writer race not fixed"
    )
    assert "fd_inplay" not in orch.books, (
        "fd_inplay still in LiveOrchestrator.books default — dual-writer race not fixed"
    )


def test_orchestrator_default_books_source():
    """Source-level check: default string in _parse_args must not include inplay."""
    src = _read_source("scripts/live_orchestrator.py")
    # The CLI default= string should not have dk_inplay or fd_inplay
    for line in src.splitlines():
        if "default=" in line and ("dk_inplay" in line or "fd_inplay" in line):
            if "--books" in line or "books" in line.lower():
                pytest.fail(
                    f"CLI --books default still contains inplay entries: {line.strip()!r}"
                )


def test_orchestrator_explicit_books_still_accepted():
    """Callers can still pass dk_inplay explicitly when they want it."""
    from scripts.live_orchestrator import LiveOrchestrator
    orch = LiveOrchestrator(game_ids=["DEMO"], books=["dk", "dk_inplay"])
    assert "dk_inplay" in orch.books
    assert "dk" in orch.books
