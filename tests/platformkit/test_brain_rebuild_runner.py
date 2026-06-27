"""Per-file test for brain_rebuild_runner -- supervised M14 loop-wrapper. NO full pytest.

  cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/test_brain_rebuild_runner.py -q
"""
from __future__ import annotations

from scripts.platformkit import brain_rebuild_runner as r


def _no_lock(monkeypatch):
    """Make lock acquire/release hermetic (no real filesystem side effects)."""
    monkeypatch.setattr(r, "_acquire", lambda now: True)
    monkeypatch.setattr(r, "_release", lambda: None)


def test_bounded_run_rebuilds_and_stops(monkeypatch):
    """A bounded run executes exactly max_ticks rebuilds and ALWAYS stops."""
    _no_lock(monkeypatch)
    ticks = {"n": 0}

    def _run_fn():
        ticks["n"] += 1
        return {"summary": {"fully_reachable": True}}

    slept = []
    n = r.run(interval_sec=10.0, run_fn=_run_fn,
              clock=lambda: 100.0, sleep=lambda s: slept.append(s), max_ticks=3)
    assert n == 3
    assert ticks["n"] == 3
    # slept between ticks but NOT after the final one (loop breaks at max_ticks).
    assert slept == [10.0, 10.0]


def test_heartbeat_beat_at_boot_and_each_tick(monkeypatch):
    """Beats the m14 liveness heartbeat at boot + every boundary (stale-never-green)."""
    _no_lock(monkeypatch)
    beats = []
    monkeypatch.setattr(r, "_beat", lambda now=None: beats.append(now))
    r.run(interval_sec=1.0, run_fn=lambda: None,
          clock=lambda: 7.0, sleep=lambda s: None, max_ticks=2)
    # 1 boot beat + 1 per tick = 3 total; the per-tick beats carry the tick's now.
    assert len(beats) == 3
    assert beats.count(7.0) >= 2


def test_fresh_lock_skips_rebuild_but_still_beats(monkeypatch):
    """If a manual rebuild holds a FRESH lock, the rebuild is skipped but liveness advances."""
    monkeypatch.setattr(r, "_acquire", lambda now: False)  # someone else holds it
    monkeypatch.setattr(r, "_release", lambda: None)
    beats = []
    monkeypatch.setattr(r, "_beat", lambda now=None: beats.append(now))
    ran = {"n": 0}
    n = r.run(interval_sec=1.0, run_fn=lambda: ran.__setitem__("n", ran["n"] + 1),
              clock=lambda: 5.0, sleep=lambda s: None, max_ticks=2)
    assert n == 2          # loop kept ticking
    assert ran["n"] == 0   # but rebuild never ran while the lock was held
    assert len(beats) == 3  # boot + 2 boundary beats -> never a stale-green


def test_run_fn_raise_does_not_crash(monkeypatch):
    """A raising rebuild is isolated; the loop continues and the lock is released."""
    _no_lock(monkeypatch)

    def _boom():
        raise RuntimeError("rebuild dead")

    n = r.run(interval_sec=1.0, run_fn=_boom,
              clock=lambda: 0.0, sleep=lambda s: None, max_ticks=2)
    assert n == 2  # loop did NOT crash; it kept ticking


def test_should_stop_halts_loop(monkeypatch):
    _no_lock(monkeypatch)
    calls = {"n": 0}

    def _stop():
        calls["n"] += 1
        return calls["n"] >= 2

    n = r.run(interval_sec=1.0, run_fn=lambda: None,
              clock=lambda: 0.0, sleep=lambda s: None, should_stop=_stop, max_ticks=99)
    assert n == 1  # stopped before max_ticks


def test_lock_blocks_only_for_live_holder(tmp_path, monkeypatch):
    """A lock blocks ONLY while its writer PID is alive; a dead/old/absent lock is
    reclaimable -- so a hard-killed mid-rebuild never strands the brain."""
    import os
    lp = tmp_path / "m14.lock"
    monkeypatch.setattr(r, "_lock_path", lambda: lp)

    # absent lock -> never blocks.
    assert r._lock_blocks(1000.0) is False

    # live holder (this very process) at a recent epoch -> blocks (skip).
    lp.write_text(f"m14_brain_rebuild pid={os.getpid()} epoch=1000", encoding="ascii")
    assert r._lock_blocks(1001.0) is True

    # dead holder (a PID that does not exist) -> reclaimable, even if young.
    lp.write_text("m14_brain_rebuild pid=999999 epoch=1000", encoding="ascii")
    assert r._lock_blocks(1001.0) is False

    # live holder but past the hard age cap -> reclaimable (belt-and-suspenders).
    lp.write_text(f"m14_brain_rebuild pid={os.getpid()} epoch=1000", encoding="ascii")
    assert r._lock_blocks(1000.0 + r._LOCK_HARD_CAP_SEC + 1.0) is False


def test_pid_alive_self_and_dead():
    """_pid_alive: True for our own PID, False for an impossible one."""
    import os
    assert r._pid_alive(os.getpid()) is True
    assert r._pid_alive(999999) is False


if __name__ == "__main__":
    import sys
    import types

    class _MP:
        """Minimal monkeypatch shim so this file runs standalone (no pytest)."""
        def __init__(self):
            self._undo = []

        def setattr(self, obj, name, val):
            old = getattr(obj, name)
            self._undo.append((obj, name, old))
            setattr(obj, name, val)

        def undo(self):
            for obj, name, old in reversed(self._undo):
                setattr(obj, name, old)
            self._undo = []

    mp = _MP()
    test_bounded_run_rebuilds_and_stops(mp); mp.undo()
    print("ok: bounded_run")
    test_heartbeat_beat_at_boot_and_each_tick(mp); mp.undo()
    print("ok: heartbeat")
    test_fresh_lock_skips_rebuild_but_still_beats(mp); mp.undo()
    print("ok: fresh_lock_skip")
    test_run_fn_raise_does_not_crash(mp); mp.undo()
    print("ok: raise_no_crash")
    test_should_stop_halts_loop(mp); mp.undo()
    print("ok: should_stop")
    # tmp_path-dependent test skipped in standalone mode (needs pytest fixtures).
    print("ok: standalone subset passed")
    sys.exit(0)
