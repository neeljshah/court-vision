"""supervisor._restart -- restart/backoff + survivor-reconcile + stale-heartbeat
reaping helpers extracted from supervisor.supervisor (behavior-preserving move).

These were Supervisor methods; they are pulled out VERBATIM (logic-identical) as
module-level functions that take the live Supervisor ``sv`` as their first arg so
``supervisor.py`` stays under the <=300 LOC rail. Supervisor keeps thin wrapper
methods that delegate here, so the public/internal method API the tests drive
(``_arm_backoff`` / ``_reap_and_restart`` / ``_heartbeat_age`` /
``_reap_stale_heartbeat`` / ``_match_pattern`` / ``_reconcile_survivors``) is
unchanged. Stdlib-only, ASCII-only, no spawn at import, no flag flip.
"""
from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from supervisor.manifest import HEARTBEAT, ProcSpec

if TYPE_CHECKING:  # avoid an import cycle at runtime
    from supervisor.supervisor import Supervisor, _ProcState

logger = logging.getLogger("supervisor.supervisor")

# Lifecycle state strings (mirrors supervisor.supervisor; kept local to avoid a
# circular import). These are the SAME literal values.
STARTING = "STARTING"
READY = "READY"
RESTARTING = "RESTARTING"
FAILED = "FAILED"
STOPPED = "STOPPED"


# -- survivor reconciliation (idempotent boot) ----------------------------- #
def match_pattern(spec: ProcSpec) -> str:
    """The cmdline substring identifying a running instance of *spec*.

    For a py spec the module name is unique enough (e.g. predict_service.app);
    for a node spec the cmd (e.g. "npm run dev") is matched. Empty => skip.
    """
    return (spec.module or spec.cmd or "").strip()


def reconcile_survivors(sv: "Supervisor") -> None:
    """Kill any ALREADY-RUNNING child of each spec BEFORE the launch loop.

    On a crash/kill of a PREVIOUS supervisor its children keep running
    (port :8099/:8098/:3000 + the headless loops). A fresh Supervisor that
    re-launched every spec unconditionally would duplicate those daemons and
    collide on the listen ports (EADDRINUSE restart-loop) + double-write the
    CLV ledger / line snapshots / inplay history.

    So before launching anything we adopt-by-removal: find every survivor by
    cmdline match (proc.find_by_match) and kill it, so the subsequent
    _launch() is the SOLE instance. This makes boot idempotent -- running
    boot twice never leaves two copies of a daemon. Best-effort + never
    raises: a backend without find_by_match (or a match failure) just falls
    through to a normal launch.
    """
    finder = getattr(sv._proc, "find_by_match", None)
    if not callable(finder):
        return
    for spec in sv._specs:
        pattern = match_pattern(spec)
        if not pattern:
            continue
        try:
            survivors = finder(pattern) or []
        except Exception as exc:  # noqa: BLE001 -- reconciliation must not block boot
            logger.warning("supervisor: find_by_match(%s) raised %s",
                           pattern, type(exc).__name__)
            continue
        for handle in survivors:
            try:
                sv._proc.kill(handle)
                logger.info("supervisor: reaped survivor %s pid=%s before boot",
                            spec.name, handle.get("pid") if isinstance(handle, dict) else "?")
            except Exception as exc:  # noqa: BLE001
                logger.warning("supervisor: kill survivor %s raised %s",
                               spec.name, type(exc).__name__)


# -- restart / backoff ----------------------------------------------------- #
def arm_backoff(sv: "Supervisor", st: "_ProcState") -> None:
    """Arm the next relaunch window using the spec's backoff envelope.

    ``attempts`` counts relaunches that have been *scheduled*; the delay is
    keyed off the (about-to-be) attempt number so the first restart waits
    backoff_for(1), the second backoff_for(2), etc.
    """
    delay = st.spec.restart_policy.backoff_for(st.attempts + 1)
    st.next_start_at = sv._clock() + delay
    st.state = RESTARTING
    logger.info("supervisor: %s restart #%d armed in %.1fs",
                st.spec.name, st.attempts + 1, delay)


def reap_and_restart(sv: "Supervisor", st: "_ProcState") -> None:
    """If a proc died, restart per policy (backoff) or mark it FAILED."""
    alive = bool(st.handle and sv._proc.is_alive(st.handle))
    if alive:
        sv._refresh_ready(st)
        if st.ready and st.state in (STARTING, RESTARTING):
            st.state = READY
        return

    # dead
    st.ready = False
    if st.state in (FAILED, STOPPED):
        return
    # Out of retries -> FAILED, isolated; the rest of the stack continues.
    if st.spec.restart_policy.exhausted(st.attempts):
        if st.state != FAILED:
            st.state = FAILED
            logger.error("supervisor: %s FAILED after %d attempts "
                         "(isolated; rest of stack continues)",
                         st.spec.name, st.attempts)
        return
    # Not yet in a backoff window -> arm one (rate cap: no immediate relaunch).
    if st.state != RESTARTING:
        arm_backoff(sv, st)
        return
    # In a backoff window: relaunch only once it has elapsed.
    if sv._clock() >= st.next_start_at:
        st.attempts += 1
        sv._launch(st)
        # Re-probe immediately so a process that comes back healthy on the
        # same tick is reported READY (not stuck RESTARTING).
        if sv._refresh_ready(st):
            st.state = READY


# -- stale-heartbeat reaping (hung != crashed) ----------------------------- #
def heartbeat_age(sv: "Supervisor", st: "_ProcState") -> Optional[float]:
    """Age (sec) of this spec's heartbeat file, or None if absent/none.

    For a HEARTBEAT-readiness spec the probe already computed it (st.detail).
    For a NONE-readiness spec that DECLARES a heartbeat_path (m1_paper /
    m1_line_daemon, RB-P0-03) we read the file directly so the reaper can
    watch a daemon whose boot is alive-only but which (once it emits) must
    not read green while hung.
    """
    rd = st.spec.readiness
    if rd.kind == HEARTBEAT:
        detail = st.detail if isinstance(st.detail, dict) else {}
        age = detail.get("age_sec")
        return float(age) if isinstance(age, (int, float)) else None
    if rd.heartbeat_path:
        # Resolve via the supervisor module so a test that monkeypatches
        # supervisor.supervisor._probe_heartbeat still takes effect (the prior
        # call site lived there). Imported lazily to dodge the import cycle.
        from supervisor.supervisor import _probe_heartbeat
        res = _probe_heartbeat(rd, sv._clock())
        d = res.get("detail", {}) if isinstance(res, dict) else {}
        age = d.get("age_sec")
        return float(age) if isinstance(age, (int, float)) else None
    return None


def reap_stale_heartbeat(sv: "Supervisor", st: "_ProcState") -> None:
    """Restart an ALIVE service whose heartbeat has gone stale (hung loop).

    ``reap_and_restart`` only acts on a DEAD proc. A hung loop stays alive
    and (without this) would read READY/green forever. We feed the heartbeat
    age/window to the reaper; a sustained-stale heartbeat trips the breaker
    -> RESTART: we kill + relaunch the hung child. Watches both HEARTBEAT
    readiness specs and NONE specs that declare a heartbeat_path.
    """
    rd = st.spec.readiness
    if rd.kind != HEARTBEAT and not rd.heartbeat_path:
        return
    alive = bool(st.handle and sv._proc.is_alive(st.handle))
    if not alive or st.state in (FAILED, STOPPED, RESTARTING):
        return
    age = heartbeat_age(sv, st)
    fresh = float(rd.fresh_sec)
    verdict = sv._reaper.observe(
        st.spec.name,
        age_sec=age if isinstance(age, (int, float)) else None,
        fresh_sec=fresh, alive=True, expects_heartbeat=True)
    if verdict.get("verdict") == "restart":
        logger.warning(
            "supervisor: %s heartbeat STALE/hung (age=%s fresh=%s) -> restart",
            st.spec.name, age, fresh)
        try:
            sv._proc.kill(st.handle)
        except Exception as exc:  # noqa: BLE001 -- kill must not sink the tick
            logger.warning("supervisor: kill hung %s raised %s",
                           st.spec.name, type(exc).__name__)
        st.ready = False
        st.handle = None
        sv._reaper.note_restarted(st.spec.name)
        arm_backoff(sv, st)


# -- targeted predict_service restart (idempotent, standalone) --------------- #

def restart_predict_service(log_dir: str = "logs") -> Dict[str, Any]:
    """Kill and relaunch the predict_service.app process (m1_api_paper).

    Idempotent and standalone -- does NOT require a running Supervisor instance.
    Finds any existing predict_service.app process by cmdline match, kills it,
    then launches a fresh instance so the new route table (including routes
    that were added after the previous start) is picked up from the current
    app.py. Returns a result dict::

        {"killed_pids": [...], "new_pid": <int|None>, "ok": bool}

    ``ok=True`` means a new process was spawned (pid obtained). The supervisor's
    existing restart/backoff loop will then take over health-tracking via its
    normal supervise() tick. Never raises -- all errors are caught and surfaced
    in the returned dict.
    """
    import sys  # noqa: PLC0415 -- local import; stdlib-only; avoids circular at module level
    from supervisor import proc as _p  # noqa: PLC0415

    _MATCH = "predict_service.app"

    killed: list = []
    try:
        survivors = _p.find_by_match(_MATCH) or []
        for h in survivors:
            try:
                _p.kill(h)
                pid = h.get("pid")
                killed.append(pid)
                logger.info("supervisor._restart: killed predict_service.app pid=%s", pid)
            except Exception as exc:  # noqa: BLE001
                logger.warning("supervisor._restart: kill pid=%s raised %s",
                               h.get("pid"), type(exc).__name__)
    except Exception as exc:  # noqa: BLE001
        logger.warning("supervisor._restart: find_by_match raised %s", type(exc).__name__)

    # Launch fresh instance using the same spec the supervisor uses.
    spec = {
        "name": "m1_api_paper",
        "kind": "py",
        "module": "predict_service.app",
        "args": [],
        "cmd": "",
        "cwd": "",
        "env": dict(os.environ),
        "python": sys.executable,
    }
    new_pid = None
    try:
        handle = _p.spawn(spec, log_dir=log_dir)
        new_pid = handle.get("pid")
        logger.info("supervisor._restart: launched predict_service.app new pid=%s", new_pid)
    except Exception as exc:  # noqa: BLE001
        logger.error("supervisor._restart: relaunch predict_service.app failed: %s", exc)

    ok = new_pid is not None
    return {"killed_pids": killed, "new_pid": new_pid, "ok": ok}


__all__ = [
    "match_pattern", "reconcile_survivors", "arm_backoff",
    "reap_and_restart", "heartbeat_age", "reap_stale_heartbeat",
    "restart_predict_service",
]
