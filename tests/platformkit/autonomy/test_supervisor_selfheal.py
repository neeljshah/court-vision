"""tests for supervisor self-healing wiring (RB-P0-02 + RB-P0-03).

  * a STALE heartbeat on an ALIVE service triggers a restart (hung != green);
  * spec.env / global_env reach the child EXPLICITLY (governance fail-CLOSED).

Drives a FAKE proc + FAKE clock; no real spawn / port / sleep. Run ONLY this file:
    python -m pytest tests/platformkit/autonomy/test_supervisor_selfheal.py -q
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest

_REPO = Path(__file__).resolve().parents[3]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

import supervisor.supervisor as _sup  # noqa: E402
from supervisor.manifest import (  # noqa: E402
    HEARTBEAT,
    NONE,
    ProcSpec,
    ReadinessSpec,
    RestartPolicy,
    topo_order,
)
from supervisor.supervisor import (  # noqa: E402
    READY,
    RESTARTING,
    Supervisor,
    _to_spawn_spec,
)


# --------------------------------------------------------------------------- #
# Fakes
# --------------------------------------------------------------------------- #
class FakeClock:
    def __init__(self, start=1000.0):
        self.t = start

    def __call__(self):
        return self.t

    def advance(self, dt):
        self.t += dt


class FakeProc:
    def __init__(self):
        self._next_pid = 2000
        self.alive: Dict[int, bool] = {}
        self.name_of: Dict[int, str] = {}
        self.spawn_order: List[str] = []
        self.kill_order: List[str] = []
        self.captured_env: List[Dict[str, Any]] = []

    def spawn(self, spec, *, log_dir, subprocess_factory=None):
        self._next_pid += 1
        pid = self._next_pid
        self.alive[pid] = True
        self.name_of[pid] = spec["name"]
        self.spawn_order.append(spec["name"])
        self.captured_env.append(spec.get("env") or {})
        return {"name": spec["name"], "pid": pid, "pid_file": None,
                "cmd": ["py", "-m", spec["module"]]}

    def is_alive(self, handle):
        pid = handle.get("pid")
        return bool(pid and self.alive.get(pid, False))

    def kill(self, handle):
        pid = handle.get("pid")
        if pid in self.alive:
            self.alive[pid] = False
            self.kill_order.append(self.name_of.get(pid, "?"))


class _FakeProfile:
    def __init__(self, specs, global_env=None):
        self._specs = specs
        self.profile = "default"
        self.log_dir = "logs"
        self.global_env = global_env or {}

    def specs(self):
        return list(self._specs)


# --------------------------------------------------------------------------- #
# RB-P0-03: stale heartbeat on an alive service -> restart
# --------------------------------------------------------------------------- #
class TestStaleHeartbeatRestart:
    def _setup(self, monkeypatch, hb_age_holder):
        """One HEARTBEAT-readiness service 'h'. Its heartbeat age is read from
        hb_age_holder['age'] via a monkeypatched _probe_heartbeat."""
        spec = ProcSpec(
            name="h", kind="py", module="m.h",
            readiness=ReadinessSpec(kind=HEARTBEAT, heartbeat_path="x/hb.json",
                                    fresh_sec=300.0),
            restart_policy=RestartPolicy(max_retries=None))
        ordered = topo_order([spec])
        monkeypatch.setattr(_sup, "load_profile",
                            lambda *a, **k: _FakeProfile(ordered))

        def _result(rd):
            age = hb_age_holder["age"]
            if age is None:
                return {"ready": False,
                        "detail": {"kind": HEARTBEAT, "reason": "absent"}}
            return {"ready": age <= rd.fresh_sec,
                    "detail": {"kind": HEARTBEAT, "age_sec": age,
                               "fresh_sec": rd.fresh_sec}}

        # _probe(spec, *, fetcher, clock); _probe_heartbeat(rd, now).
        monkeypatch.setattr(
            _sup, "_probe",
            lambda spec, *, fetcher=None, clock=None: _result(spec.readiness))
        monkeypatch.setattr(_sup, "_probe_heartbeat",
                            lambda rd, now: _result(rd))
        fp = FakeProc()
        clk = FakeClock()
        sv = Supervisor("default", proc=fp, clock=clk,
                        sleeper=lambda s: None, fetcher=lambda r: {},
                        status_writer=lambda doc, **k: None)
        return sv, fp, clk

    def test_hung_loop_with_stale_heartbeat_is_restarted(self, monkeypatch):
        holder = {"age": 10.0}  # fresh at boot
        sv, fp, clk = self._setup(monkeypatch, holder)
        doc = sv.boot()
        assert {p["name"]: p["state"] for p in doc["procs"]}["h"] == READY
        spawns_before = fp.spawn_order.count("h")

        # The loop HANGS: still alive, but its heartbeat goes stale.
        holder["age"] = 9000.0
        # fail_threshold=2 -> need two stale ticks to trip the breaker.
        sv.supervise()
        # not yet restarted (absorbing one), still alive.
        assert "h" not in fp.kill_order
        doc = sv.supervise()
        # Now the hung loop is reaped + armed for restart -- NOT left green.
        assert "h" in fp.kill_order
        st = {p["name"]: p for p in doc["procs"]}["h"]
        assert st["state"] == RESTARTING
        assert st["ready"] is False

        # After backoff elapses + heartbeat fresh again, it recovers to READY.
        holder["age"] = 5.0
        clk.advance(120.0)
        doc = sv.supervise()
        st = {p["name"]: p for p in doc["procs"]}["h"]
        assert st["state"] == READY
        assert fp.spawn_order.count("h") == spawns_before + 1

    def test_fresh_heartbeat_is_never_reaped(self, monkeypatch):
        holder = {"age": 10.0}
        sv, fp, clk = self._setup(monkeypatch, holder)
        sv.boot()
        for _ in range(10):
            sv.supervise()
        # A healthy beating loop is never killed by the reaper.
        assert "h" not in fp.kill_order


# --------------------------------------------------------------------------- #
# RB-P0-02: env reaches the child explicitly (governance fail-CLOSED)
# --------------------------------------------------------------------------- #
class TestEnvPropagation:
    def test_spec_env_and_global_env_reach_spawn_dict(self):
        spec = ProcSpec(name="x", kind="py", module="m.x",
                        env={"GOVERNANCE_ELIGIBLE": "1"})
        d = _to_spawn_spec(spec, {"NBA_AI_SUPERVISED": "1"})
        assert d["env"]["GOVERNANCE_ELIGIBLE"] == "1"
        assert d["env"]["NBA_AI_SUPERVISED"] == "1"

    def test_spec_env_wins_over_global_env(self):
        spec = ProcSpec(name="x", kind="py", module="m.x",
                        env={"GOVERNANCE_ELIGIBLE": "0"})
        d = _to_spawn_spec(spec, {"GOVERNANCE_ELIGIBLE": "1"})
        # per-proc env has highest precedence.
        assert d["env"]["GOVERNANCE_ELIGIBLE"] == "0"

    def test_missing_env_fails_closed_no_governance_flag(self):
        """A spec with NO env + NO global_env must NOT carry GOVERNANCE_ELIGIBLE
        -- governance is fail-CLOSED (absent flag => not eligible), never green
        by accidental shell inheritance assumption."""
        spec = ProcSpec(name="x", kind="py", module="m.x")
        d = _to_spawn_spec(spec, {})
        assert "GOVERNANCE_ELIGIBLE" not in d["env"]

    def test_env_reaches_child_through_boot(self, monkeypatch):
        spec = ProcSpec(name="g", kind="py", module="m.g",
                        readiness=ReadinessSpec(kind=NONE),
                        env={"GOVERNANCE_ELIGIBLE": "1"},
                        restart_policy=RestartPolicy(max_retries=None))
        ordered = topo_order([spec])
        monkeypatch.setattr(
            _sup, "load_profile",
            lambda *a, **k: _FakeProfile(ordered, {"NBA_AI_SUPERVISED": "1"}))
        fp = FakeProc()
        sv = Supervisor("default", proc=fp, clock=FakeClock(),
                        sleeper=lambda s: None, fetcher=lambda r: {},
                        status_writer=lambda doc, **k: None)
        sv.boot()
        # The child's spawn captured BOTH the governance flag and the global env.
        env = fp.captured_env[0]
        assert env.get("GOVERNANCE_ELIGIBLE") == "1"
        assert env.get("NBA_AI_SUPERVISED") == "1"
