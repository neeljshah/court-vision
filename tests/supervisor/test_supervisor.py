"""tests/supervisor/test_supervisor.py -- unit tests for the M9 orchestrator.

Drives boot / readiness-gating / restart-backoff / failure-isolation / drain
with FAKE processes + a FAKE clock + a FAKE sleeper. NO real process is spawned,
NO real port is bound, NO real time elapses.

Run ONLY this file:
    python -m pytest tests/supervisor/test_supervisor.py -q
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest

_REPO = Path(__file__).resolve().parent.parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

import supervisor.supervisor as _sup
from supervisor.manifest import (
    HTTP,
    TCP,
    ProcSpec,
    ReadinessSpec,
    RestartPolicy,
    topo_order,
)
from supervisor.supervisor import FAILED, PENDING, READY, RESTARTING, STOPPED, Supervisor


# --------------------------------------------------------------------------- #
# Fakes
# --------------------------------------------------------------------------- #
class FakeClock:
    """Monotone, manually-advanced epoch clock."""

    def __init__(self, start: float = 1000.0) -> None:
        self.t = start

    def __call__(self) -> float:
        return self.t

    def advance(self, dt: float) -> None:
        self.t += dt


class FakeSleeper:
    """Records requested sleeps; never actually sleeps."""

    def __init__(self) -> None:
        self.calls: List[float] = []

    def __call__(self, sec: float) -> None:
        self.calls.append(sec)


class FakeProc:
    """A fake supervisor.proc backend driven entirely by test state.

    spawn() returns a handle with a unique pid + the spawn order. Tests flip a
    pid's liveness via .die(pid) / .revive(pid). Readiness for ready-gated specs
    is controlled by .ready_names; spawn order is recorded for ordering asserts.
    """

    def __init__(self) -> None:
        self._next_pid = 1000
        self.alive: Dict[int, bool] = {}
        self.spawn_order: List[str] = []
        self.kill_order: List[str] = []
        self.name_of: Dict[int, str] = {}
        # Survivors a PREVIOUS supervisor left running, keyed by the cmdline
        # match pattern (the spec module). find_by_match() returns these so a
        # boot can reconcile (kill) them before launching its own copy.
        self.survivors: Dict[str, List[Dict[str, Any]]] = {}

    def spawn(self, spec: Dict[str, Any], *, log_dir: str,
              subprocess_factory: Optional[Any] = None) -> Dict[str, Any]:
        self._next_pid += 1
        pid = self._next_pid
        self.alive[pid] = True
        self.name_of[pid] = spec["name"]
        self.spawn_order.append(spec["name"])
        return {"name": spec["name"], "pid": pid, "pid_file": None,
                "cmd": ["py", "-m", spec["module"]]}

    def is_alive(self, handle: Dict[str, Any]) -> bool:
        pid = handle.get("pid")
        return bool(pid and self.alive.get(pid, False))

    def kill(self, handle: Dict[str, Any]) -> None:
        pid = handle.get("pid")
        if pid in self.alive:
            self.alive[pid] = False
            self.kill_order.append(self.name_of.get(pid, "?"))

    def die(self, name: str) -> None:
        for pid, nm in self.name_of.items():
            if nm == name:
                self.alive[pid] = False

    # -- survivor reconciliation -------------------------------------------- #
    def add_survivor(self, pattern: str, pid: int) -> Dict[str, Any]:
        """Register a survivor from a prior supervisor matchable by *pattern*."""
        h = {"name": pattern, "pid": pid, "pid_file": None, "cmd": [pattern]}
        self.alive[pid] = True
        self.name_of[pid] = pattern
        self.survivors.setdefault(pattern, []).append(h)
        return h

    def find_by_match(self, pattern: str) -> List[Dict[str, Any]]:
        # Return only survivors that are still alive (a killed one is gone).
        return [h for h in self.survivors.get(pattern, [])
                if self.alive.get(h["pid"], False)]


def _ready_fetcher_all_ok(req: Dict[str, Any]) -> Dict[str, Any]:
    """A fetcher that reports every TCP/HTTP probe as ready."""
    if req.get("kind") == "tcp":
        return {"open": True}
    return {"status": 200}


def _tiny_manifest(monkeypatch: pytest.MonkeyPatch) -> List[ProcSpec]:
    """A small NONE-readiness DAG: a -> b -> c, plus an independent d.

    NONE readiness => ready as soon as alive, so we test dep-ordering and
    restart logic without heartbeat/port machinery.
    """
    base = [
        ProcSpec(name="a", kind="py", module="m.a",
                 restart_policy=RestartPolicy(max_retries=None)),
        ProcSpec(name="b", kind="py", module="m.b", depends_on=["a"],
                 restart_policy=RestartPolicy(max_retries=None)),
        ProcSpec(name="c", kind="py", module="m.c", depends_on=["b"],
                 restart_policy=RestartPolicy(max_retries=2,
                                              backoff_base_sec=2.0,
                                              backoff_cap_sec=60.0)),
        ProcSpec(name="d", kind="py", module="m.d",
                 restart_policy=RestartPolicy(max_retries=None)),
    ]
    ordered = topo_order(base)
    monkeypatch.setattr(_sup, "load_profile", lambda *a, **k: _FakeProfile(ordered))
    return ordered


class _FakeProfile:
    def __init__(self, specs: List[ProcSpec]) -> None:
        self._specs = specs
        self.profile = "default"
        self.log_dir = "logs"

    def specs(self) -> List[ProcSpec]:
        return list(self._specs)


def _make(monkeypatch: pytest.MonkeyPatch, **kw):
    _tiny_manifest(monkeypatch)
    fp = FakeProc()
    clk = FakeClock()
    slp = FakeSleeper()
    status_docs: List[Dict[str, Any]] = []
    sv = Supervisor("default", proc=fp, clock=clk, sleeper=slp,
                    fetcher=_ready_fetcher_all_ok,
                    status_writer=lambda doc, **k: status_docs.append(doc),
                    **kw)
    return sv, fp, clk, slp, status_docs


# --------------------------------------------------------------------------- #
# boot: dependency order + readiness gating
# --------------------------------------------------------------------------- #
class TestBoot:
    def test_boot_starts_in_dependency_order(self, monkeypatch):
        sv, fp, _clk, _slp, _docs = _make(monkeypatch)
        sv.boot()
        # a before b before c; d independent (after its deps = none).
        assert fp.spawn_order.index("a") < fp.spawn_order.index("b")
        assert fp.spawn_order.index("b") < fp.spawn_order.index("c")
        assert "d" in fp.spawn_order

    def test_boot_all_ready(self, monkeypatch):
        sv, _fp, _clk, _slp, _docs = _make(monkeypatch)
        doc = sv.boot()
        states = {p["name"]: p["state"] for p in doc["procs"]}
        assert states == {n: READY for n in ("a", "b", "c", "d")}
        assert doc["all_ready"] is True

    def test_dependent_not_started_until_dep_ready(self, monkeypatch):
        # If a never becomes ready (dies on spawn), b/c must NOT start.
        sv, fp, _clk, _slp, _docs = _make(monkeypatch)
        orig_spawn = fp.spawn

        def spawn_a_dies(spec, **k):
            h = orig_spawn(spec, **k)
            if spec["name"] == "a":
                fp.alive[h["pid"]] = False  # a is dead immediately
            return h

        monkeypatch.setattr(fp, "spawn", spawn_a_dies)
        doc = sv.boot(max_polls=3)
        states = {p["name"]: p["state"] for p in doc["procs"]}
        assert states["b"] == PENDING
        assert states["c"] == PENDING
        assert "b" not in fp.spawn_order
        assert "c" not in fp.spawn_order
        # d is independent and must still be up (failure isolation).
        assert states["d"] == READY


# --------------------------------------------------------------------------- #
# BUG 1: idempotent boot -- reconcile survivors so a restart never duplicates
# --------------------------------------------------------------------------- #
class TestIdempotentBoot:
    def test_survivor_is_reaped_before_relaunch(self, monkeypatch):
        """A child left running by a PRIOR supervisor must be killed before the
        new supervisor launches its own copy (no duplicate, no port collision)."""
        sv, fp, _clk, _slp, _docs = _make(monkeypatch)
        # Simulate a survivor of spec 'a' (module 'm.a') from a dead supervisor.
        surv = fp.add_survivor("m.a", pid=777)
        assert fp.is_alive(surv) is True
        sv.boot()
        # The survivor was killed during reconciliation...
        assert fp.is_alive(surv) is False
        assert "m.a" in fp.kill_order
        # ...and exactly ONE fresh 'a' was launched (single instance).
        assert fp.spawn_order.count("a") == 1

    def test_boot_twice_does_not_duplicate(self, monkeypatch):
        """Running boot() a second time (watchdog re-run) must not leave two
        copies of any daemon: the first boot's children are reaped, then one
        fresh copy is launched."""
        sv, fp, _clk, _slp, _docs = _make(monkeypatch)
        sv.boot()
        # Register every just-launched child as a survivor of a second boot,
        # exactly as proc_win.find_by_match would discover them on disk.
        for pid, name in list(fp.name_of.items()):
            module = "m.%s" % name  # tiny manifest maps name->module m.<name>
            fp.survivors.setdefault(module, []).append(
                {"name": module, "pid": pid, "pid_file": None, "cmd": [module]})
        # Second boot (fresh Supervisor over the same fake proc/state).
        sv2 = Supervisor("default", proc=fp, clock=FakeClock(), sleeper=FakeSleeper(),
                         fetcher=_ready_fetcher_all_ok,
                         status_writer=lambda doc, **k: None)
        sv2.boot()
        # Each daemon ends with exactly ONE live instance.
        for name in ("a", "b", "c", "d"):
            live = [pid for pid, nm in fp.name_of.items()
                    if nm == name and fp.alive.get(pid, False)]
            assert len(live) == 1, "duplicate live instance for %s: %s" % (name, live)

    def test_reconcile_no_survivors_is_noop(self, monkeypatch):
        """With no survivors, boot launches normally and kills nothing."""
        sv, fp, _clk, _slp, _docs = _make(monkeypatch)
        sv.boot()
        assert fp.kill_order == []
        assert fp.spawn_order.count("a") == 1


# --------------------------------------------------------------------------- #
# restart + backoff + FAILED
# --------------------------------------------------------------------------- #
class TestRestart:
    def test_crash_is_restarted_with_backoff(self, monkeypatch):
        sv, fp, clk, _slp, _docs = _make(monkeypatch)
        sv.boot()
        # 'd' crashes; first supervise schedules a restart (backoff), not relaunch.
        fp.die("d")
        spawned_before = list(fp.spawn_order)
        doc = sv.supervise()
        st = {p["name"]: p for p in doc["procs"]}["d"]
        assert st["state"] == RESTARTING
        assert fp.spawn_order == spawned_before  # no relaunch yet (in backoff)
        # backoff window not elapsed -> still no relaunch.
        sv.supervise()
        assert fp.spawn_order.count("d") == 1
        # advance past backoff -> relaunch happens, becomes READY again.
        clk.advance(100.0)
        doc = sv.supervise()
        assert fp.spawn_order.count("d") == 2
        st = {p["name"]: p for p in doc["procs"]}["d"]
        assert st["state"] == READY

    def test_backoff_is_exponential_capped(self, monkeypatch):
        sv, _fp, _clk, _slp, _docs = _make(monkeypatch)
        pol = RestartPolicy(backoff_base_sec=2.0, backoff_cap_sec=60.0)
        assert pol.backoff_for(1) == 2.0
        assert pol.backoff_for(2) == 4.0
        assert pol.backoff_for(3) == 8.0
        assert pol.backoff_for(10) == 60.0  # capped

    def test_marked_failed_after_max_retries(self, monkeypatch):
        sv, fp, clk, _slp, _docs = _make(monkeypatch)
        sv.boot()
        # 'c' has max_retries=2. Kill it and keep it dead through restarts.
        for _ in range(6):
            fp.die("c")
            sv.supervise()
            clk.advance(120.0)  # always clear the backoff window
        doc = sv.supervise()
        st = {p["name"]: p for p in doc["procs"]}["c"]
        assert st["state"] == FAILED
        assert st["restarts"] >= 2

    def test_failed_proc_does_not_stop_others(self, monkeypatch):
        sv, fp, clk, _slp, _docs = _make(monkeypatch)
        sv.boot()
        for _ in range(6):
            fp.die("c")
            sv.supervise()
            clk.advance(120.0)
        doc = sv.supervise()
        states = {p["name"]: p["state"] for p in doc["procs"]}
        assert states["c"] == FAILED
        # a, b, d remain READY -- failure of c is isolated.
        assert states["a"] == READY
        assert states["b"] == READY
        assert states["d"] == READY


# --------------------------------------------------------------------------- #
# drain (reverse order) + status
# --------------------------------------------------------------------------- #
class TestDrain:
    def test_drain_stops_in_reverse_dependency_order(self, monkeypatch):
        sv, fp, _clk, _slp, _docs = _make(monkeypatch)
        sv.boot()
        sv.drain()
        # killed dependents before deps: c before b before a.
        assert fp.kill_order.index("c") < fp.kill_order.index("b")
        assert fp.kill_order.index("b") < fp.kill_order.index("a")

    def test_drain_marks_stopped(self, monkeypatch):
        sv, _fp, _clk, _slp, _docs = _make(monkeypatch)
        sv.boot()
        doc = sv.drain()
        assert all(p["state"] == STOPPED for p in doc["procs"])
        assert all(p["ready"] is False for p in doc["procs"])

    def test_drain_swallows_kill_errors(self, monkeypatch):
        sv, fp, _clk, _slp, _docs = _make(monkeypatch)
        sv.boot()

        def boom(handle):
            raise RuntimeError("kill failed")

        monkeypatch.setattr(fp, "kill", boom)
        doc = sv.drain()  # must not raise
        assert all(p["state"] == STOPPED for p in doc["procs"])


# --------------------------------------------------------------------------- #
# status doc + rate cap + run_forever bound
# --------------------------------------------------------------------------- #
class TestStatusAndLoop:
    def test_status_doc_shape(self, monkeypatch):
        sv, _fp, _clk, _slp, docs = _make(monkeypatch)
        doc = sv.boot()
        assert doc["profile"] == "default"
        assert doc["schema_version"] == "1.0.0"
        assert doc["started_at"] == 1000.0
        for row in doc["procs"]:
            assert set(row) >= {"name", "state", "pid", "restarts", "ready", "detail"}
        # status_writer was invoked (status.json would be persisted).
        assert docs and docs[-1]["all_ready"] is True

    def test_run_forever_is_bounded_by_max_cycles(self, monkeypatch):
        sv, _fp, _clk, slp, _docs = _make(monkeypatch)
        sv.run_forever(max_cycles=3, tick_sec=2.0)
        # 3 ticks => 2 inter-tick sleeps of tick_sec (last tick does not sleep).
        tick_sleeps = [s for s in slp.calls if s == 2.0]
        assert len(tick_sleeps) == 2

    def test_rate_cap_one_relaunch_per_backoff_window(self, monkeypatch):
        # A flapping proc must not be relaunched faster than its backoff allows.
        sv, fp, clk, _slp, _docs = _make(monkeypatch)
        sv.boot()
        fp.die("d")
        # many supervise ticks WITHOUT advancing the clock -> at most the
        # initial scheduling, never a relaunch (rate cap honored).
        for _ in range(20):
            sv.supervise()
        assert fp.spawn_order.count("d") == 1


# --------------------------------------------------------------------------- #
# readiness kinds beyond NONE (HTTP/TCP via fetcher) gate correctly
# --------------------------------------------------------------------------- #
class TestReadinessKinds:
    def test_http_gate_blocks_until_200(self, monkeypatch):
        spec = ProcSpec(name="api", kind="py", module="m.api", port=8099,
                        readiness=ReadinessSpec(kind=HTTP, http_path="/health"))
        dep = ProcSpec(name="ui", kind="py", module="m.ui", port=3000,
                       depends_on=["api"], readiness=ReadinessSpec(kind=TCP))
        ordered = topo_order([spec, dep])
        monkeypatch.setattr(_sup, "load_profile",
                            lambda *a, **k: _FakeProfile(ordered))
        fp = FakeProc()
        state = {"http_ok": False}

        def fetcher(req):
            if req.get("kind") == "http":
                return {"status": 200 if state["http_ok"] else 503}
            return {"open": True}

        sv = Supervisor("default", proc=fp, clock=FakeClock(),
                        sleeper=FakeSleeper(), fetcher=fetcher,
                        status_writer=lambda doc, **k: None)
        doc = sv.boot(max_polls=2)
        states = {p["name"]: p["state"] for p in doc["procs"]}
        # api not READY (503) -> ui (depends on api) must stay PENDING.
        assert states["ui"] == PENDING
        assert "ui" not in fp.spawn_order
        # api comes healthy -> next supervise readies it, then ui can start.
        state["http_ok"] = True
        sv.supervise()
        doc = sv.supervise()
        states = {p["name"]: p["state"] for p in doc["procs"]}
        assert states["api"] == READY
        assert "ui" in fp.spawn_order
