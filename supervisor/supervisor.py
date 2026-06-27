"""supervisor.supervisor -- the always-on orchestrator for the M9 stack.

Brings the whole stack up with ONE readiness-gated call, with auto-restart +
capped exponential backoff and graceful shutdown -- so it "just always runs".

  * boot(profile): start ProcSpecs in DEPENDENCY order; a dependent waits until
    every dep is READY (per its readiness probe).
  * supervise(): one tick -- reap dead, restart per RestartPolicy with backoff,
    reap hung (stale-heartbeat) procs, write the status JSON. A FAILED proc does
    NOT sink the rest (failure isolation).
  * drain()/shutdown(): graceful stop in REVERSE dependency order.

Restart/backoff, survivor-reconcile, crash-rate-breaker, self-heartbeat, and
stale-heartbeat reaping bodies live in ``supervisor._restart`` (for the <=300 LOC
rail); methods here delegate. Everything external is injectable (proc / clock /
sleeper / fetcher) so a test drives boot/restart/backoff/drain with FAKES.
States: PENDING -> STARTING -> READY ; on death -> RESTARTING -> (READY|FAILED).
Stdlib-only, ASCII-only. Never writes data/registry/; never flips a flag on.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from scripts.platformkit.autonomy.heartbeat_reaper import HeartbeatReaper
from supervisor import _restart
from supervisor import proc as _proc_mod
from supervisor.proc import to_spawn_spec as _to_spawn_spec
from supervisor.config import load_profile
from supervisor.health import _probe_heartbeat  # re-exported for _restart + tests
from supervisor.health import probe as _probe
from supervisor.manifest import ProcSpec
from supervisor.status import render_rows, supervisor_status, write_status

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

# C1 self-liveness: supervisor stamps its OWN heartbeat each run_forever tick so
# the watchdog distinguishes a WEDGED run_forever (alive, no ticks) from healthy.
SELF_HEARTBEAT_COMPONENT = "m9_supervisor"

# C7 crash-rate breaker: > _CRASH_MAX relaunches within _CRASH_WINDOW_SEC for ONE
# spec trips a DEGRADED breaker (ERROR-logged once) vs silent flap at the 60s cap.
_CRASH_MAX = 5
_CRASH_WINDOW_SEC = 300.0


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
        # stale (hung) is restarted, not read READY forever.
        self._reaper = HeartbeatReaper(
            fail_threshold=2, cooldown_sec=60.0, clock=self._clock)
        # C7 crash-rate breaker: recent relaunch epochs per spec; a config-broken
        # daemon flapping at the 60s cap surfaces as DEGRADED instead of looping
        # silently (distinct from the per-spec backoff that paces ONE relaunch).
        self._restart_epochs: Dict[str, List[float]] = {}
        self._breaker_tripped: Dict[str, bool] = {}

    def _deps_ready(self, spec: ProcSpec) -> bool:
        return all(self._states[d].ready for d in spec.depends_on if d in self._states)

    def _is_alive(self, handle: Optional[Dict[str, Any]]) -> bool:
        """Liveness with the PID-REUSE guard (cmdline token verified if supported).

        A recycled OS pid would otherwise read alive forever; verify_cmdline=True
        rejects it. Backends without the kwarg fall back to the plain pid check.
        """
        if not handle:
            return False
        try:
            return bool(self._proc.is_alive(handle, verify_cmdline=True))
        except TypeError:  # backend without the kwarg (or a test fake)
            return bool(self._proc.is_alive(handle))

    def _refresh_ready(self, st: _ProcState) -> bool:
        """Probe one proc; READY requires alive AND a passing readiness probe."""
        if not st.handle or not self._is_alive(st.handle):
            st.ready = False
            return False
        result = _probe(st.spec, fetcher=self._fetcher, clock=self._clock)
        st.ready = bool(result.get("ready"))
        st.detail = result.get("detail", {})
        return st.ready

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
            if not self._is_alive(st.handle):
                return False
            if self._refresh_ready(st):
                st.state = READY
                return True
            self._sleep(1.0)
        return False

    # -- survivor reconcile / restart / breaker (bodies in _restart) -------- #
    def _match_pattern(self, spec: ProcSpec) -> str:
        return _restart.match_pattern(spec)

    def _reconcile_survivors(self) -> None:
        _restart.reconcile_survivors(self)

    def boot(self, *, max_polls: int = 15) -> Dict[str, Any]:
        """Start every proc in dependency order, gating on dep readiness.

        Reconciles survivors first (idempotent boot, no duplicate daemons / port
        collisions). A proc launches only once its depends_on are READY; an unready
        dep leaves dependents PENDING. Returns the status doc.

        C2 BOOT-STALL FIX: ``max_polls`` defaults to 15 (was 600 -> ~10min stall
        on one cold producer heartbeat). Readiness gating is PRESERVED; a laggard
        hands off to supervise() promptly (which brings up + restarts laggards).
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
                if self._is_alive(st.handle):
                    logger.warning("supervisor: %s started but not READY",
                                   spec.name)
                else:
                    self._arm_backoff(st)
        return self.refresh_status()

    def _arm_backoff(self, st: _ProcState) -> None:
        _restart.arm_backoff(self, st)

    def _reap_and_restart(self, st: _ProcState) -> None:
        _restart.reap_and_restart(self, st)

    def _heartbeat_age(self, st: _ProcState) -> Optional[float]:
        return _restart.heartbeat_age(self, st)

    def _reap_stale_heartbeat(self, st: _ProcState) -> None:
        _restart.reap_stale_heartbeat(self, st)

    def _beat_self(self) -> None:
        """Stamp the supervisor's OWN liveness (a WEDGED run_forever is alive +
        stale-heartbeat to the watchdog). Never raises."""
        _restart.beat_self(self)

    def _note_relaunch(self, st: _ProcState) -> None:
        _restart.note_relaunch(self, st)

    def _breaker_state(self, st: _ProcState) -> bool:
        """True if *st* is in the tripped crash-rate breaker (flap) state."""
        return bool(self._breaker_tripped.get(st.spec.name))

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
        """Boot then supervise on a cadence (max_cycles=None loops forever)."""
        self.boot()
        self._beat_self()  # stamp liveness as soon as the supervise loop starts
        cycles = 0
        while max_cycles is None or cycles < max_cycles:
            self.supervise()
            self._beat_self()  # C1: prove run_forever is still TICKING, not wedged
            cycles += 1
            if max_cycles is None or cycles < max_cycles:
                self._sleep(tick_sec)
        return self.refresh_status()

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

    def _rows(self) -> List[Dict[str, Any]]:
        return render_rows(self._specs, self._states, self._breaker_tripped)

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

    Returns the live Supervisor (caller drives supervise()/drain()); with
    ``max_cycles`` set, runs that many supervise ticks first.
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
