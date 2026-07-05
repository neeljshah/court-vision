"""supervisor.test_robustness_hardening -- per-file tests for the unattended-
robustness hardening (C1 self-heartbeat, C7 crash-rate breaker, H1 node pattern,
PID+cmdline liveness, C4 m5 tick guard).

Acceptance criteria:

  RH1. C1 supervisor self-heartbeat: run_forever stamps a FRESH m9_supervisor
       heartbeat each tick; a watchdog can read its freshness.

  RH2. C7 crash-rate breaker ESCALATES: > _CRASH_MAX relaunches inside the
       window trip a DEGRADED breaker (status row carries crash_breaker), and
       it clears once the relaunch rate falls back under the cap.

  RH3. H1 node match_pattern targets the bare substring "next" (not
       "npm run dev"); py specs still match their module.

  RH4. PID + cmdline liveness: a reused pid (alive pid, WRONG cmdline) reads
       DEAD under verify_cmdline=True; the matching cmdline reads alive; a
       backend without the kwarg still works via the supervisor fallback.

  RH5. C4 m5 tick guard: a tick() that RAISES does not kill run() -- a DEGRADED
       envelope is published and the heartbeat is beat.

Run (per-file only -- never the full suite)::
    cd /c/Users/neelj/nba-ai-system && python -m pytest supervisor/test_robustness_hardening.py -q
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from supervisor import _restart  # noqa: E402
from supervisor import proc_win  # noqa: E402
from supervisor.manifest import ProcSpec, ReadinessSpec  # noqa: E402
from supervisor.status import render_rows  # noqa: E402


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------

class _FakeClock:
    """Monotonic injectable clock; advance() steps it forward."""

    def __init__(self, t: float = 1000.0) -> None:
        self.t = float(t)

    def __call__(self) -> float:
        return self.t

    def advance(self, dt: float) -> None:
        self.t += float(dt)


class _Spec:
    """Minimal spec stand-in for crash-breaker tests (just needs .name)."""

    def __init__(self, name: str) -> None:
        self.name = name


class _State:
    def __init__(self, spec: _Spec) -> None:
        self.spec = spec
        self.state = "RESTARTING"
        self.attempts = 0
        self.ready = False
        self.detail: Dict[str, Any] = {}
        self.handle: Optional[Dict[str, Any]] = {"pid": 1}

    @property
    def pid(self) -> Optional[int]:
        return self.handle.get("pid") if self.handle else None


class _FakeSupervisor:
    """The slice of Supervisor that _restart.note_relaunch / beat_self touch."""

    def __init__(self, clock: _FakeClock) -> None:
        self._clock = clock
        self._restart_epochs: Dict[str, List[float]] = {}
        self._breaker_tripped: Dict[str, bool] = {}

    def _breaker_state(self, st: _State) -> bool:
        return bool(self._breaker_tripped.get(st.spec.name))


# ---------------------------------------------------------------------------
# RH1 -- C1 supervisor self-heartbeat freshness
# ---------------------------------------------------------------------------

def test_rh1_self_heartbeat_is_stamped_fresh(tmp_path, monkeypatch):
    """beat_self stamps a heartbeat the watchdog can read as FRESH."""
    import ops.liveness as liveness
    hb = tmp_path / "m9_supervisor.txt"
    # Route the component's default path into tmp by monkeypatching the resolver.
    monkeypatch.setattr(liveness, "_default_hb_path", lambda comp: hb)
    clock = _FakeClock(2000.0)
    sv = _FakeSupervisor(clock)
    _restart.beat_self(sv)
    assert hb.exists(), "RH1: self-heartbeat file must be written"
    # Fresh now; stale far in the future.
    assert liveness.is_live("m9_supervisor", max_age_sec=90.0,
                            now=clock.t, path=hb), "RH1: heartbeat must read FRESH"
    assert not liveness.is_live("m9_supervisor", max_age_sec=90.0,
                                now=clock.t + 1000.0, path=hb), \
        "RH1: a stale (wedged) heartbeat must read NOT-fresh"


# ---------------------------------------------------------------------------
# RH2 -- C7 crash-rate breaker escalates + recovers
# ---------------------------------------------------------------------------

def test_rh2_crash_rate_breaker_escalates_and_status_degraded():
    """> _CRASH_MAX relaunches in the window trip the breaker (status DEGRADED)."""
    from supervisor.supervisor import _CRASH_MAX
    clock = _FakeClock(1000.0)
    sv = _FakeSupervisor(clock)
    spec = _Spec("m1_paper")
    st = _State(spec)
    # _CRASH_MAX relaunches: still under the cap -> NOT tripped.
    for _ in range(_CRASH_MAX):
        _restart.note_relaunch(sv, st)
        clock.advance(1.0)
    assert not sv._breaker_state(st), "RH2: at the cap the breaker must NOT be tripped"
    # One more inside the window -> trips.
    _restart.note_relaunch(sv, st)
    assert sv._breaker_state(st), "RH2: exceeding the cap must TRIP the breaker"
    rows = render_rows([spec], {spec.name: st}, sv._breaker_tripped)
    assert rows[0]["detail"].get("crash_breaker") == "DEGRADED", \
        "RH2: a tripped spec must surface crash_breaker=DEGRADED in its status row"


def test_rh2b_crash_rate_breaker_clears_after_window():
    """Once old relaunches age out of the window, the breaker CLEARS."""
    from supervisor.supervisor import _CRASH_MAX, _CRASH_WINDOW_SEC
    clock = _FakeClock(1000.0)
    sv = _FakeSupervisor(clock)
    st = _State(_Spec("m1_line_daemon"))
    for _ in range(_CRASH_MAX + 1):
        _restart.note_relaunch(sv, st)
    assert sv._breaker_state(st), "RH2b: breaker should be tripped after the storm"
    # Jump past the window so the old epochs age out, then relaunch once.
    clock.advance(_CRASH_WINDOW_SEC + 1.0)
    _restart.note_relaunch(sv, st)
    assert not sv._breaker_state(st), "RH2b: breaker must CLEAR when rate falls under cap"


# ---------------------------------------------------------------------------
# RH3 -- H1 node match_pattern targets the bare substring "next"
# ---------------------------------------------------------------------------

def test_rh3_node_match_pattern_targets_next_server():
    """A node spec matches bare "next", not its launch cmd ('npm run dev').

    The real Windows CommandLine of a Next.js listener (verified against a
    live orphaned process) never contains the literal "next-server" -- that
    is an internal Next.js module name, not something Windows reports in the
    process's CommandLine. "next" IS present (e.g. "...\\next\\dist\\bin\\next
    start -p 3000"), so match_pattern targets that bare substring instead.
    """
    node = ProcSpec(name="m1_ui", kind="node", cmd="npm run dev",
                    readiness=ReadinessSpec(kind="tcp-port-open"))
    assert _restart.match_pattern(node) == "next", \
        "RH3: node match must be 'next' (matches the real listener's live " \
        "CommandLine on Windows; 'next-server' never appears there)"
    py = ProcSpec(name="m1_api_paper", kind="py", module="predict_service.app")
    assert _restart.match_pattern(py) == "predict_service.app", \
        "RH3: py specs still match their module"


# ---------------------------------------------------------------------------
# RH4 -- PID + cmdline liveness (defeat pid reuse)
# ---------------------------------------------------------------------------

def test_rh4_cmd_token_extraction():
    """_cmd_token pulls the -m module / next-server token from a handle."""
    h_py = {"cmd": ["python", "-u", "-m", "predict_service.app"]}
    assert proc_win._cmd_token(h_py) == "predict_service.app"
    h_node = {"cmd": ["C:/next-server (v14)"]}
    assert proc_win._cmd_token(h_node) == "next-server"
    assert proc_win._cmd_token({"cmd": []}) is None


def test_rh4_win_pid_reuse_guard(monkeypatch):
    """proc_win.is_alive(verify_cmdline=True): an ALIVE pid whose cmdline lost our
    token reads DEAD; a matching cmdline reads alive. Uses the CURRENT process pid
    (genuinely alive) so the OS pid-liveness primitive is real; only the live
    cmdline is varied to simulate a recycled pid."""
    import os
    pid = os.getpid()
    handle = {"pid": pid, "cmd": ["python", "-u", "-m", "predict_service.app"]}
    # Recycled pid: cmdline lost our token -> DEAD (the new process is not ours).
    monkeypatch.setattr(proc_win, "cmdline_for_pid",
                        lambda p: "python -u -m some.OTHER.module")
    assert proc_win.is_alive(handle, verify_cmdline=True) is False, \
        "RH4: a reused pid (token absent from cmdline) must read DEAD"
    # Matching cmdline -> token present -> alive.
    monkeypatch.setattr(proc_win, "cmdline_for_pid",
                        lambda p: "python -u -m predict_service.app --x")
    assert proc_win.is_alive(handle, verify_cmdline=True) is True, \
        "RH4: the genuine process (token present) must read alive"
    # cmdline table unreadable (None) -> do NOT falsely declare dead.
    monkeypatch.setattr(proc_win, "cmdline_for_pid", lambda p: None)
    assert proc_win.is_alive(handle, verify_cmdline=True) is True, \
        "RH4: an unreadable cmdline must not falsely kill a live pid"
    # And without the guard, the live pid is simply alive.
    assert proc_win.is_alive(handle) is True, \
        "RH4: default (no guard) path reports the live pid alive"


def test_rh4_supervisor_fallback_when_backend_lacks_kwarg():
    """Supervisor._is_alive falls back when the backend has no verify_cmdline."""
    from supervisor.supervisor import Supervisor

    class _OldProc:
        def is_alive(self, handle):  # no verify_cmdline kwarg
            return handle.get("pid") == 7
    sv = Supervisor.__new__(Supervisor)  # skip heavy __init__
    sv._proc = _OldProc()
    assert sv._is_alive({"pid": 7}) is True, "RH4: fallback path must accept alive pid"
    assert sv._is_alive({"pid": 9}) is False
    assert sv._is_alive(None) is False


# ---------------------------------------------------------------------------
# RH5 -- C4 m5 tick guard: a raising tick does not kill the loop
# ---------------------------------------------------------------------------

def test_rh5_m5_tick_guard_publishes_degraded_and_beats(tmp_path, monkeypatch):
    """run(): a tick() that RAISES -> degraded envelope written + heartbeat beat."""
    from scripts.platformkit.autonomy import autonomy_monitor_runner as amr

    status_path = tmp_path / "autonomy_status.json"
    beats: List[float] = []

    monkeypatch.setattr(amr, "_beat", lambda now=None: beats.append(now))

    def _boom(**kwargs):
        raise RuntimeError("simulated composer import failure")
    monkeypatch.setattr(amr, "tick", _boom)

    clock = _FakeClock(3000.0)
    # One tick, then stop -- the loop must NOT raise even though tick() raises.
    ticks = amr.run(status_path=status_path, clock=clock,
                    sleep=lambda s: None, max_ticks=1)
    assert ticks == 1, "RH5: the loop must complete its tick despite the failure"
    assert status_path.exists(), "RH5: a DEGRADED envelope must be published"
    import json
    doc = json.loads(status_path.read_text(encoding="ascii"))
    assert doc.get("overall") == "degraded", \
        "RH5: the published envelope must be DEGRADED (never green) on tick failure"
    assert beats, "RH5: the heartbeat must still be beat after a failed tick"


# ---------------------------------------------------------------------------
# Self-runner
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
