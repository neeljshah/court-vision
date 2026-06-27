"""Tests for supervisor._singleton -- the one-supervisor-at-a-time lock.

Validates: a second acquire on the SAME lock path (simulating a racing boot in a
separate process) is refused while the first holds it; the lock releases when the
holder's fd closes (process death); and the guard fails OPEN when the lock path
cannot be created. Per-file: python -m pytest tests/supervisor/test_singleton.py -q
"""
from __future__ import annotations

import multiprocessing
import os

from supervisor import _singleton


def test_first_acquire_owns_lock(tmp_path):
    lock = str(tmp_path / "sv.lock")
    h = _singleton.acquire(lock)
    assert h is not None
    assert h.held is True
    assert os.path.exists(lock)


def _hold_then_signal(lock_path, ready, release):
    """Child proc: acquire the lock, announce, hold until told to release."""
    h = _singleton.acquire(lock_path)
    ready.put(h is not None and h.held)
    release.wait(10)  # hold the lock (fd open) until the parent finishes probing


def test_second_acquire_refused_while_held(tmp_path):
    # A real second PROCESS is required: an OS lock is per-process, so a same-proc
    # re-lock of an already-held region does not model a racing boot. Spawn a
    # child that holds the lock, then prove the parent is refused.
    lock = str(tmp_path / "sv.lock")
    ctx = multiprocessing.get_context("spawn")
    ready = ctx.Queue()
    release = ctx.Event()
    child = ctx.Process(target=_hold_then_signal, args=(lock, ready, release))
    child.start()
    try:
        assert ready.get(timeout=10) is True  # child acquired
        # Parent (a distinct process) must be refused -> None.
        assert _singleton.acquire(lock) is None
    finally:
        release.set()
        child.join(10)

    # Once the holder exits, the OS releases the lock -> parent can acquire.
    h = _singleton.acquire(lock)
    assert h is not None and h.held is True


def test_acquire_after_release_succeeds(tmp_path):
    lock = str(tmp_path / "sv.lock")
    ctx = multiprocessing.get_context("spawn")
    ready = ctx.Queue()
    release = ctx.Event()
    child = ctx.Process(target=_hold_then_signal, args=(lock, ready, release))
    child.start()
    assert ready.get(timeout=10) is True
    release.set()
    child.join(10)
    h = _singleton.acquire(lock)
    assert h is not None and h.held is True


def test_fail_open_when_lock_path_unusable(tmp_path):
    # Point the lock at a path whose parent is an existing FILE, so makedirs/open
    # fails -> guard must fail OPEN (a non-owning handle, boot proceeds), never None.
    afile = tmp_path / "not_a_dir"
    afile.write_text("x", encoding="ascii")
    bad_lock = str(afile / "child" / "sv.lock")
    h = _singleton.acquire(bad_lock)
    assert h is not None  # fail-open: never block boot
    assert h.held is False
