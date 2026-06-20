"""supervisor.test_restart -- per-file tests for restart_predict_service().

Acceptance criteria (WS1 restart-api):

  RS1. When existing predict_service.app processes are found by find_by_match,
       they are killed and their pids appear in killed_pids.

  RS2. A fresh spawn succeeds -> new_pid is set and ok=True.

  RS3. When spawn raises, ok=False, new_pid is None, and the function does
       NOT raise (never-raises guarantee).

  RS4. When find_by_match raises, killed_pids is empty, the function does
       NOT raise, and spawn is still attempted.

  RS5. Multiple survivors are all killed (killed_pids has all their pids).

Run (per-file only -- never the full suite)::
    cd /c/Users/neelj/nba-ai-system && python -m pytest supervisor/test_restart.py -q
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List, Optional
import pytest

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from supervisor._restart import restart_predict_service  # noqa: E402


# ---------------------------------------------------------------------------
# Fake proc helpers -- no real processes, no real kill, no real spawn
# ---------------------------------------------------------------------------

class _FakeProc:
    """Minimal stand-in for supervisor.proc used by restart_predict_service.

    find_by_match(pattern) returns the registered fake handles.
    kill(handle) marks the pid dead and records the call.
    spawn(spec, log_dir) returns a handle with a fresh pid (or raises).
    """

    def __init__(
        self,
        survivors: Optional[List[Dict[str, Any]]] = None,
        spawn_pid: Optional[int] = 9999,
        spawn_raises: bool = False,
        find_raises: bool = False,
    ) -> None:
        self._survivors: List[Dict[str, Any]] = survivors or []
        self._spawn_pid = spawn_pid
        self._spawn_raises = spawn_raises
        self._find_raises = find_raises
        self.killed_pids: List[int] = []
        self.spawned: List[Dict[str, Any]] = []

    def find_by_match(self, pattern: str) -> List[Dict[str, Any]]:
        if self._find_raises:
            raise RuntimeError("find_by_match simulated failure")
        return list(self._survivors)

    def kill(self, handle: Dict[str, Any]) -> None:
        pid = handle.get("pid")
        self.killed_pids.append(pid)

    def spawn(self, spec: Dict[str, Any], *, log_dir: str,
              subprocess_factory: Any = None) -> Dict[str, Any]:
        if self._spawn_raises:
            raise RuntimeError("spawn simulated failure")
        handle = {"name": spec["name"], "pid": self._spawn_pid,
                  "pid_file": None, "cmd": []}
        self.spawned.append(handle)
        return handle


def _make_handle(pid: int) -> Dict[str, Any]:
    return {"name": "predict_service.app", "pid": pid, "pid_file": None, "cmd": []}


def _run(fake: _FakeProc) -> Dict[str, Any]:
    """Patch supervisor.proc module-level functions with fake, then call restart.

    restart_predict_service does ``from supervisor import proc as _p`` at call
    time, then calls _p.find_by_match / _p.kill / _p.spawn. Since _p IS the
    supervisor.proc module object we monkey-patch its attributes directly;
    they are restored in the finally block.
    """
    import supervisor.proc as _proc_mod  # ensure already imported before patching
    orig_fbm = _proc_mod.find_by_match
    orig_kill = _proc_mod.kill
    orig_spawn = _proc_mod.spawn
    _proc_mod.find_by_match = fake.find_by_match
    _proc_mod.kill = fake.kill
    _proc_mod.spawn = fake.spawn
    try:
        return restart_predict_service(log_dir="logs")
    finally:
        _proc_mod.find_by_match = orig_fbm
        _proc_mod.kill = orig_kill
        _proc_mod.spawn = orig_spawn


# ---------------------------------------------------------------------------
# RS1 -- survivors are killed, killed_pids populated
# ---------------------------------------------------------------------------

def test_rs1_survivors_killed_pids_populated():
    """RS1: existing process is killed -> killed_pids contains its pid."""
    fake = _FakeProc(survivors=[_make_handle(1234)])
    result = _run(fake)
    assert 1234 in result["killed_pids"], (
        "RS1: pid 1234 must be in killed_pids; got %r" % result["killed_pids"]
    )
    assert fake.killed_pids == [1234], (
        "RS1: kill() must have been called once with pid 1234; got %r" % fake.killed_pids
    )


# ---------------------------------------------------------------------------
# RS2 -- spawn succeeds -> new_pid set, ok=True
# ---------------------------------------------------------------------------

def test_rs2_spawn_success_new_pid_ok_true():
    """RS2: no survivors, spawn returns pid 9999 -> new_pid=9999, ok=True."""
    fake = _FakeProc(survivors=[], spawn_pid=9999)
    result = _run(fake)
    assert result["new_pid"] == 9999, (
        "RS2: new_pid must be 9999; got %r" % result["new_pid"]
    )
    assert result["ok"] is True, (
        "RS2: ok must be True when spawn succeeds; got ok=%r" % result["ok"]
    )


# ---------------------------------------------------------------------------
# RS3 -- spawn raises -> ok=False, new_pid=None, no raise
# ---------------------------------------------------------------------------

def test_rs3_spawn_failure_ok_false_no_raise():
    """RS3: spawn() raises -> ok=False, new_pid is None, function does not raise."""
    fake = _FakeProc(survivors=[], spawn_raises=True)
    result = _run(fake)  # must not raise
    assert result["ok"] is False, (
        "RS3: ok must be False when spawn raises; got ok=%r" % result["ok"]
    )
    assert result["new_pid"] is None, (
        "RS3: new_pid must be None when spawn raises; got %r" % result["new_pid"]
    )


# ---------------------------------------------------------------------------
# RS4 -- find_by_match raises -> killed_pids empty, spawn still attempted
# ---------------------------------------------------------------------------

def test_rs4_find_raises_killed_empty_spawn_still_attempted():
    """RS4: find_by_match raises -> killed_pids=[], spawn is still attempted."""
    fake = _FakeProc(find_raises=True, spawn_pid=8888)
    result = _run(fake)  # must not raise
    assert result["killed_pids"] == [], (
        "RS4: killed_pids must be empty when find_by_match raises; got %r"
        % result["killed_pids"]
    )
    # Spawn is still attempted after the find failure.
    assert result["new_pid"] == 8888, (
        "RS4: spawn must still run; expected new_pid=8888, got %r" % result["new_pid"]
    )
    assert result["ok"] is True, "RS4: ok must be True since spawn succeeded"


# ---------------------------------------------------------------------------
# RS5 -- multiple survivors all killed
# ---------------------------------------------------------------------------

def test_rs5_multiple_survivors_all_killed():
    """RS5: two survivors -> both pids in killed_pids."""
    survivors = [_make_handle(101), _make_handle(202)]
    fake = _FakeProc(survivors=survivors, spawn_pid=5555)
    result = _run(fake)
    assert 101 in result["killed_pids"], (
        "RS5: pid 101 must be in killed_pids; got %r" % result["killed_pids"]
    )
    assert 202 in result["killed_pids"], (
        "RS5: pid 202 must be in killed_pids; got %r" % result["killed_pids"]
    )
    assert len(result["killed_pids"]) == 2, (
        "RS5: exactly 2 pids must be killed; got %r" % result["killed_pids"]
    )
    assert result["ok"] is True


# ---------------------------------------------------------------------------
# Self-runner
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed = 0
    for fn in fns:
        try:
            fn()
            print("PASS", fn.__name__)
            passed += 1
        except Exception as exc:
            print("FAIL", fn.__name__, "->", exc)
    print("%d/%d green" % (passed, len(fns)))
