"""supervisor.test_beat_thread -- per-file tests for the 2026-07-04 supervisor
self-wedge robustness fix (LANE 1): background BeatThread decoupled from the
main supervise() loop, and boot_initiator stamping in the status doc.

Acceptance criteria:

  BT1. BeatThread calls beat_fn on its own cadence even while a "main loop" is
       simulated as BLOCKED (sleeping) for far longer than one interval --
       i.e. the beat does NOT depend on the caller's own tick duration. This
       is the direct regression test for the wedge-storm root cause (a slow
       serial supervise() tick starving the single end-of-tick beat).

  BT2. BeatThread.stop() halts further beats (idempotent, bounded join; a
       second stop() is a safe no-op) and start() is idempotent (calling it
       twice does not spawn a second thread).

  BT3. A beat_fn that raises does not kill the thread -- it keeps beating on
       schedule (never-raises discipline, mirrors _restart.beat_self).

  BT4. Supervisor wires a BeatThread in __init__; run_forever() starts it and
       drain() stops it (construction-level integration, no real processes).

  BT5. boot_initiator: supervisor_status() carries an optional boot_initiator
       field (None by default; passes through when supplied) -- additive,
       does not disturb the existing shape for callers that omit it.

Run (per-file only -- never the full suite)::
    cd /c/Users/neelj/nba-ai-system && python -m pytest supervisor/test_beat_thread.py -q
"""
from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import List

import pytest

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from supervisor._beat_thread import BeatThread  # noqa: E402
from supervisor.status import supervisor_status  # noqa: E402


# ---------------------------------------------------------------------------
# BT1 -- beat continues while the "main loop" is blocked
# ---------------------------------------------------------------------------

def test_bt1_beats_continue_while_main_loop_blocked():
    """A short-interval BeatThread keeps beating during a long simulated block.

    Simulates the exact wedge-storm scenario: the main thread "blocks" (sleeps)
    for far longer than one beat interval -- as a slow serial supervise() tick
    would under heavy fleet load -- while the BeatThread keeps stamping on its
    own schedule the whole time.
    """
    beats: List[float] = []
    bt = BeatThread(lambda: beats.append(time.time()), interval_sec=0.05)
    bt.start()
    try:
        # Simulate the main loop being blocked for 0.3s (6x the beat interval).
        time.sleep(0.3)
    finally:
        bt.stop()
    assert len(beats) >= 4, (
        "BT1: BeatThread must keep beating independent of the blocked main "
        "loop; expected >=4 beats in 0.3s at 0.05s interval, got %d" % len(beats)
    )


# ---------------------------------------------------------------------------
# BT2 -- start/stop idempotency
# ---------------------------------------------------------------------------

def test_bt2_stop_halts_further_beats_and_is_idempotent():
    """stop() halts beating; calling start()/stop() twice is safe."""
    beats: List[float] = []
    bt = BeatThread(lambda: beats.append(time.time()), interval_sec=0.05)
    bt.start()
    bt.start()  # idempotent: must not spawn a second thread
    time.sleep(0.15)
    bt.stop()
    count_after_stop = len(beats)
    assert count_after_stop > 0, "BT2: at least one beat must have fired"
    time.sleep(0.2)  # give a rogue second thread time to fire if one existed
    assert len(beats) == count_after_stop, (
        "BT2: no further beats after stop(); got %d new beats"
        % (len(beats) - count_after_stop)
    )
    bt.stop()  # second stop() must not raise
    assert not bt.is_running, "BT2: is_running must be False after stop()"


# ---------------------------------------------------------------------------
# BT3 -- a raising beat_fn does not kill the thread
# ---------------------------------------------------------------------------

def test_bt3_raising_beat_fn_does_not_kill_thread():
    """One bad beat_fn call must not stop subsequent beats."""
    calls: List[int] = []

    def _flaky() -> None:
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("simulated beat failure")

    bt = BeatThread(_flaky, interval_sec=0.05)
    bt.start()
    try:
        time.sleep(0.25)
    finally:
        bt.stop()
    assert len(calls) >= 3, (
        "BT3: the thread must keep calling beat_fn after one raises; got %d calls"
        % len(calls)
    )


# ---------------------------------------------------------------------------
# BT4 -- Supervisor wires the BeatThread (construction-level, no real procs)
# ---------------------------------------------------------------------------

def test_bt4_supervisor_run_forever_starts_and_drain_stops_beat_thread(tmp_path, monkeypatch):
    """Supervisor.run_forever() starts the BeatThread; drain() stops it."""
    from supervisor.supervisor import Supervisor

    class _NoOpProc:
        def spawn(self, spec, *, log_dir):
            return {"pid": 1, "name": spec.get("name", "x")}

        def is_alive(self, handle, verify_cmdline=False):
            return True

        def kill(self, handle):
            pass

        def find_by_match(self, pattern):
            return []

    class _EmptyProfile:
        profile = "test"
        log_dir = str(tmp_path)
        global_env: dict = {}

        def specs(self):
            return []

    monkeypatch.setattr(
        "supervisor.supervisor.load_profile", lambda profile: _EmptyProfile())

    sv = Supervisor("test", proc=_NoOpProc(), sleeper=lambda s: None,
                    status_writer=lambda doc: None)
    assert not sv._beat_thread.is_running, "BT4: beat thread must not run before boot"
    sv.run_forever(max_cycles=1)
    assert sv._beat_thread.is_running, (
        "BT4: run_forever() must start the background beat thread")
    sv.drain()
    assert not sv._beat_thread.is_running, (
        "BT4: drain() must stop the background beat thread")


# ---------------------------------------------------------------------------
# BT5 -- boot_initiator passthrough in the status doc
# ---------------------------------------------------------------------------

def test_bt5_boot_initiator_defaults_none_and_passes_through():
    """supervisor_status() carries boot_initiator: None by default, passed
    through when supplied -- additive, does not break existing callers."""
    doc_default = supervisor_status([], profile="default", started_at=1.0,
                                     updated_at=2.0)
    assert doc_default["boot_initiator"] is None, (
        "BT5: boot_initiator must default to None when not supplied")

    doc_stamped = supervisor_status([], profile="default", started_at=1.0,
                                     updated_at=2.0,
                                     boot_initiator="watchdog_autostart")
    assert doc_stamped["boot_initiator"] == "watchdog_autostart", (
        "BT5: boot_initiator must pass through when supplied")


# ---------------------------------------------------------------------------
# Self-runner
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
