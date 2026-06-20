"""supervisor.supervisor -- the always-on orchestrator for the M9 stack.

Brings the whole stack up with ONE readiness-gated call, with auto-restart +
capped exponential backoff and graceful shutdown -- so it "just always runs".

  * boot(profile): start ProcSpecs in DEPENDENCY order; do not start a dependent
    until every dep it depends_on is READY (per its readiness probe).
  * supervise(): one tick -- reap dead procs, restart per RestartPolicy with
    backoff, reap hung (stale-heartbeat) procs, and write the status JSON. A
    FAILED non-critical proc must NOT sink the rest (failure isolation).
  * drain()/shutdown(): graceful stop in REVERSE dependency order.

The restart/backoff, survivor-reconcile, and stale-heartbeat reaping bodies live
in ``supervisor._restart`` (behavior-preserving extraction for the <=300 LOC
rail); the methods here delegate to them. Everything external is injectable
(proc / clock / sleeper / fetcher) so a test drives boot / restart / backoff /
drain with FAKE processes + a FAKE clock and NO real spawning, binding, or
sleeping. States: PENDING -> STARTING -> READY ; on death -> RESTARTING ->
(READY | FAILED). A FAILED proc stays FAILED and is logged; the rest keeps
running (failure isolation).

Run live (always-on):  python -u -m supervisor.supervisor [--profile NAME]

Stdlib-only, ASCII-only, <=300 LOC. Never writes data/registry/; never flips a
flag on; never spawns in module-level code.
"""
from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from scripts.platformkit.autonomy.heartbeat_reaper import HeartbeatReaper
from supervisor import _restart
from supervisor import proc as _proc_mod
from supervisor.config import load_profile
from supervisor.health import _probe_heartbeat  # re-exported for _restart + tests
from supervisor.health import probe as _probe
from supervisor.manifest import ProcSpec
from supervisor.status import supervisor_status, write_status

logger = logging.getLogger("supervisor.supervisor")

# Per-proc lifecycle states.
PENDING = "PENDING"
STARTING = "STARTING"
READY = "READY"
RESTARTING = "RESTARTING"
FAILED = "FAILED"
STOPPED = "STOPPED"

Clock = Callable[[], float]
Sleeper = Callable[[float], None]
Fetcher = Callable[[Dict[str, Any]], Dict[str, Any]]


@dataclass
class _ProcState:
    """Mutable supervisor-side bookkeeping for one ProcSpec."""

    spec: ProcSpec
    state: str = PENDING
    handle: Optional[Dict[str, Any]] = None
    attempts: int = 0          # relaunch attempts so far (restart count)
    next_start_at: float = 0.0  # earliest epoch the next (re)launch may happen
    ready: bool = False
    detail: Dict[str, Any] = field(default_factory=dict)

    @property
    def pid(self) -> Optional[int]:
        return self.handle.get("pid") if self.handle else None


def _to_spawn_spec(spec: ProcSpec,
                   global_env: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """Translate a ProcSpec into the dict shape supervisor.proc.spawn expects.

    RB-P0-02: thread the env EXPLICITLY into the spawn dict so a governance flag
    (GOVERNANCE_ELIGIBLE) + other per-child env reach the child by VALUE, not via
    fragile shell inheritance. Precedence (low -> high): ``os.environ`` <
    ``global_env`` (profile-wide) < ``spec.env`` (per-proc). Fails CLOSED: the
    child sees the explicit env on every spawn path (posix watchdog / test /
    remote) even when it does not inherit the booting shell.
    """
    merged: Dict[str, str] = {}
    for k, v in os.environ.items():
        merged[str(k)] = str(v)
    for src in (global_env or {}, spec.env or {}):
        for k, v in src.items():
            merged[str(k)] = str(v)
    return {"name": spec.name, "kind": spec.kind, "module": spec.module or "",
            "args": list(spec.argv or []), "cmd": spec.cmd or "",
            "cwd": spec.cwd or "", "env": merged}


class Supervisor:
    """Dependency-ordered, readiness-gated, auto-restarting process supervisor."""

    def __init__(
        self,
        profile: str = "default",
        *,
        proc: Any = _proc_mod,
        clock: Optional[Clock] = None,
        sleeper: Optional[Sleeper] = None,
        fetcher: Optional[Fetcher] = None,
        log_dir: str = "logs",
        status_writer: Callable[..., Any] = write_status,
    ) -> None:
        self._bp = load_profile(profile)
        self.profile = self._bp.profile
        self._specs: List[ProcSpec] = self._bp.specs()  # topo-ordered (deps first)
        self._proc = proc
        self._clock: Clock = clock or time.time
        self._sleep: Sleeper = sleeper or time.sleep
        self._fetcher = fetcher
        self._log_dir = self._bp.log_dir or log_dir
        self._write_status = status_writer
        self.started_at: float = self._clock()
        self._states: Dict[str, _ProcState] = {
            s.name: _ProcState(spec=s) for s in self._specs
        }
        # RB-P0-02: profile-wide env threaded EXPLICITLY into every spawn.
        self._global_env: Dict[str, str] = dict(
            getattr(self._bp, "global_env", {}) or {})
        # RB-P0-03: stale-heartbeat reaper -- an ALIVE daemon whose heartbeat went
        # stale (hung, not crashed) is restarted, not read READY forever.
        self._reaper = HeartbeatReaper(
            fail_threshold=2, cooldown_sec=60.0, clock=self._clock)

    # -- readiness ---------------------------------------------------------- #
    def _deps_ready(self, spec: ProcSpec) -> bool:
        return all(self._states[d].ready for d in spec.depends_on if d in self._states)

    def _refresh_ready(self, st: _ProcState) -> bool:
        """Probe one proc; READY requires alive AND a passing readiness probe."""
        if not st.handle or not self._proc.is_alive(st.handle):
            st.ready = False
            return False
        result = _probe(st.spec, fetcher=self._fetcher, clock=self._clock)
        st.ready = bool(result.get("ready"))
        st.detail = result.get("detail", {})
        return st.ready

    # -- launch ------------------------------------------------------------- #
    def _launch(self, st: _ProcState) -> None:
        """Spawn one proc (no readiness wait here) and mark it STARTING."""
        st.handle = self._proc.spawn(
            _to_spawn_spec(st.spec, self._global_env), log_dir=self._log_dir)
        st.state = STARTING
        st.ready = False
        logger.info("supervisor: launched %s pid=%s", st.spec.name, st.pid)

    def _await_ready(self, st: _ProcState, *, max_polls: int = 600) -> bool:
        """Poll readiness until READY, the proc dies, or max_polls elapse.

        Sleeps via the injected sleeper between polls (the test records, never
        sleeps). Returns True once READY."""
        for _ in range(max_polls):
            if not self._proc.is_alive(st.handle or {}):
                return False
            if self._refresh_ready(st):
                st.state = READY
                return True
            self._sleep(1.0)
        return False

    # -- survivor reconciliation (idempotent boot; body in _restart) -------- #
    def _match_pattern(self, spec: ProcSpec) -> str:
        return _restart.match_pattern(spec)

    def _reconcile_survivors(self) -> None:
        _restart.reconcile_survivors(self)

    # -- boot --------------------------------------------------------------- #
    def boot(self, *, max_polls: int = 600) -> Dict[str, Any]:
        """Start every proc in dependency order, gating on dep readiness.

        Before launching ANYTHING, reconcile survivors from a previous supervisor
        (idempotent boot) so a relaunch never duplicates a daemon or collides on a
        port. A proc launches only once all its depends_on are READY; if a dep
        never becomes ready its dependents stay PENDING. Returns the status doc.
        """
        self._reconcile_survivors()
        for spec in self._specs:  # topo order: deps precede dependents
            st = self._states[spec.name]
            if not self._deps_ready(spec):
                logger.warning(
                    "supervisor: %s deps not ready (%s); leaving PENDING",
                    spec.name, ",".join(spec.depends_on))
                st.state = PENDING
                continue
            self._launch(st)
            if not self._await_ready(st, max_polls=max_polls):
                # alive-but-not-ready or died during boot: hand to supervise().
                if self._proc.is_alive(st.handle or {}):
                    logger.warning("supervisor: %s started but not READY",
                                   spec.name)
                else:
                    self._arm_backoff(st)
        return self.refresh_status()

    # -- restart/backoff + stale-heartbeat reaping (bodies in _restart) ----- #
    def _arm_backoff(self, st: _ProcState) -> None:
        _restart.arm_backoff(self, st)

    def _reap_and_restart(self, st: _ProcState) -> None:
        _restart.reap_and_restart(self, st)

    def _heartbeat_age(self, st: _ProcState) -> Optional[float]:
        return _restart.heartbeat_age(self, st)

    def _reap_stale_heartbeat(self, st: _ProcState) -> None:
        _restart.reap_stale_heartbeat(self, st)

    # -- supervise tick ----------------------------------------------------- #
    def supervise(self) -> Dict[str, Any]:
        """One supervise tick: reap dead, reap hung (stale heartbeat), restart."""
        for spec in self._specs:
            st = self._states[spec.name]
            if st.state == PENDING and self._deps_ready(spec):
                self._launch(st)
                continue
            self._reap_and_restart(st)
            self._reap_stale_heartbeat(st)
        return self.refresh_status()

    def run_forever(self, *, max_cycles: Optional[int] = None,
                    tick_sec: float = 2.0) -> Dict[str, Any]:
        """Boot then supervise on a cadence. ``max_cycles=None`` loops forever
        (production always-on); a small int bounds the loop for tests."""
        self.boot()
        cycles = 0
        while max_cycles is None or cycles < max_cycles:
            self.supervise()
            cycles += 1
            if max_cycles is None or cycles < max_cycles:
                self._sleep(tick_sec)
        return self.refresh_status()

    # -- shutdown ----------------------------------------------------------- #
    def drain(self) -> Dict[str, Any]:
        """Graceful stop in REVERSE dependency order (dependents before deps)."""
        for spec in reversed(self._specs):
            st = self._states[spec.name]
            if st.handle:
                try:
                    self._proc.kill(st.handle)
                except Exception as exc:  # noqa: BLE001 -- kill must not raise out
                    logger.warning("supervisor: kill %s raised %s",
                                   spec.name, type(exc).__name__)
            st.state = STOPPED
            st.ready = False
            st.handle = None
        return self.refresh_status()

    shutdown = drain

    # -- status ------------------------------------------------------------- #
    def _rows(self) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        for spec in self._specs:
            st = self._states[spec.name]
            rows.append({
                "name": spec.name, "state": st.state, "pid": st.pid,
                "restarts": st.attempts, "ready": st.ready, "detail": st.detail,
            })
        return rows

    def refresh_status(self) -> Dict[str, Any]:
        """Build the status doc, persist it atomically, and return it."""
        doc = supervisor_status(
            self._rows(), profile=self.profile,
            started_at=self.started_at, updated_at=self._clock())
        self._write_status(doc)
        return doc


def boot(profile: str = "default", *, proc: Any = _proc_mod,
         clock: Optional[Clock] = None, sleeper: Optional[Sleeper] = None,
         fetcher: Optional[Fetcher] = None,
         max_cycles: Optional[int] = None) -> Supervisor:
    """Construct a Supervisor, boot the stack, and (optionally) supervise.

    Returns the live Supervisor so a caller can drive ``supervise()`` / ``drain()``;
    with ``max_cycles`` set, runs that many supervise ticks first.
    """
    sv = Supervisor(profile, proc=proc, clock=clock, sleeper=sleeper,
                    fetcher=fetcher)
    if max_cycles is None:
        sv.boot()
    else:
        sv.run_forever(max_cycles=max_cycles)
    return sv


__all__ = ["Supervisor", "boot", "PENDING", "STARTING", "READY",
           "RESTARTING", "FAILED", "STOPPED"]
