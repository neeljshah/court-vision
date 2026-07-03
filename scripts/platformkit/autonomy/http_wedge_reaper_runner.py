"""scripts.platformkit.autonomy.http_wedge_reaper_runner -- supervised entry
point wiring http_wedge_reaper's decision core to the REAL probes + kill action.

Every tick: for each declared HTTP-readiness target (name, port, cmdline match
pattern) -- probe port-listening + HTTP-timeout + per-PID CPU%, feed to
HttpWedgeReaper.observe, persist state across ticks, and on a KILL verdict find
the PID by cmdline match and kill ONLY that PID (the supervisor's own restart/
backoff path relaunches it -- this runner never spawns). Read-only otherwise;
writes decisions to data/frontend/ops/http_wedge_reaper.json for visibility.

TARGETS: today only m1_api_paper (:8099, predict_service.app) declares HTTP
readiness in supervisor.stack_specs -- see TARGETS below. A future HTTP-
readiness ProcSpec is covered by adding one row here (TABLE-DRIFT is caught by
the per-file test asserting TARGETS' names are a subset of every HTTP-kind spec
in supervisor.manifest()).

Heartbeat: m33_http_wedge_reaper -> data/cache/daemon_heartbeats/m33_http_wedge_reaper.txt
Cadence: DEFAULT_INTERVAL_SEC = 30s (tight -- a wedge is a live-incident detector,
not a slow batch sentinel). stdlib + repo-internal; ASCII only; <=300 LOC.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/autonomy/test_http_wedge_reaper.py -q
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, NamedTuple, Optional

from scripts.platformkit.autonomy.http_wedge_reaper import HttpWedgeReaper, KILL
from scripts.platformkit.autonomy.http_wedge_reaper_io import (
    load_state_file,
    save_state_file,
    write_decisions,
)

logger = logging.getLogger("http_wedge_reaper_runner")

HEARTBEAT_COMPONENT = "m33_http_wedge_reaper"
DEFAULT_INTERVAL_SEC = 30.0


class _Target(NamedTuple):
    name: str
    port: int
    http_path: str
    match_pattern: str  # cmdline substring used to find + kill the PID


# The declared HTTP-readiness fleet (mirrors supervisor.stack_specs' HTTP-kind
# ProcSpecs). m1_api_paper (:8099, predict_service.app) is the ONLY HTTP-kind
# spec today (m1_api_boards/:8098 and m1_ui/:3000 are TCP-readiness, out of
# scope for this rule per the charter -- a TCP-open port cannot itself hang the
# way an async event loop with a wedged HTTP handler can).
TARGETS: List[_Target] = [
    _Target(name="m1_api_paper", port=8099, http_path="/health",
            match_pattern="predict_service.app"),
]


def _beat(now_epoch: Optional[float] = None) -> None:
    try:
        from ops.liveness import heartbeat
        heartbeat(HEARTBEAT_COMPONENT, _now=now_epoch)
    except Exception as exc:  # noqa: BLE001
        logger.debug("http_wedge_reaper heartbeat skipped: %s", exc)


def _kill_pid_by_pattern(pattern: str) -> Optional[int]:
    """Find the running PID matching *pattern* and kill it. Returns the killed
    pid, or None if no match / kill failed. Never raises."""
    try:
        from supervisor import proc as _p
        survivors = _p.find_by_match(pattern) or []
        if not survivors:
            return None
        handle = survivors[0]
        pid = handle.get("pid")
        _p.kill(handle)
        logger.warning("http_wedge_reaper: killed WEDGED pid=%s (match=%s)",
                       pid, pattern)
        return pid
    except Exception as exc:  # noqa: BLE001 -- kill must never crash the tick
        logger.warning("http_wedge_reaper: kill(%s) raised %s", pattern,
                       type(exc).__name__)
        return None


def tick(
    *,
    now: float,
    targets: Optional[List[_Target]] = None,
    reaper: Optional[HttpWedgeReaper] = None,
    port_check: Optional[Callable[[int], bool]] = None,
    http_probe_fn: Optional[Callable[[str], Dict[str, Any]]] = None,
    cpu_probe_fn: Optional[Callable[[int], Optional[float]]] = None,
    pid_lookup_fn: Optional[Callable[[str], Optional[int]]] = None,
    killer: Optional[Callable[[str], Optional[int]]] = None,
    load_fn: Optional[Callable[..., Dict[str, Any]]] = None,
    save_fn: Optional[Callable[..., bool]] = None,
    write_fn: Optional[Callable[..., bool]] = None,
) -> List[Dict[str, Any]]:
    """One reaper tick over every target. Everything injectable; never raises.

    Returns the list of verdict dicts (one per target). A KILL verdict invokes
    *killer* (default: find-by-pattern + supervisor.proc.kill) for THAT target
    only -- never any other PID.
    """
    from scripts.platformkit.autonomy.http_wedge_probe import (
        http_probe as _real_http_probe,
        pid_cpu_percent as _real_cpu_probe,
        port_is_listening as _real_port_check,
    )

    _targets = targets if targets is not None else TARGETS
    _port_check = port_check if port_check is not None else _real_port_check
    _http = http_probe_fn if http_probe_fn is not None else (
        lambda url: _real_http_probe(url))
    _cpu = cpu_probe_fn if cpu_probe_fn is not None else _real_cpu_probe
    _load = load_fn if load_fn is not None else load_state_file
    _save = save_fn if save_fn is not None else save_state_file
    _write = write_fn if write_fn is not None else write_decisions
    _kill = killer if killer is not None else _kill_pid_by_pattern

    r = reaper if reaper is not None else HttpWedgeReaper(clock=lambda: now)
    try:
        r.load_state(_load())
    except Exception as exc:  # noqa: BLE001
        logger.debug("http_wedge_reaper: load_state skipped: %s", exc)

    rows: List[Dict[str, Any]] = []
    for t in _targets:
        try:
            listening = bool(_port_check(t.port))
            http_res: Dict[str, Any] = {"timed_out": False, "elapsed_sec": 0.0}
            pid: Optional[int] = None
            cpu_pct: Optional[float] = None
            if listening:
                url = "http://127.0.0.1:%d%s" % (t.port, t.http_path)
                http_res = _http(url) or {}
                if pid_lookup_fn is not None:
                    pid = pid_lookup_fn(t.match_pattern)
                if pid is not None:
                    cpu_pct = _cpu(pid)
            verdict = r.observe(
                t.name,
                port_listening=listening,
                probe_timed_out=bool(http_res.get("timed_out")),
                probe_elapsed_sec=http_res.get("elapsed_sec"),
                cpu_pct=cpu_pct,
            )
            if verdict.get("verdict") == KILL:
                killed_pid = _kill(t.match_pattern)
                verdict["detail"]["killed_pid"] = killed_pid
            rows.append(verdict)
        except Exception as exc:  # noqa: BLE001 -- one bad target must not sink the tick
            logger.debug("http_wedge_reaper: target %s raised %s", t.name,
                         type(exc).__name__)
            rows.append({"name": t.name, "verdict": "keep",
                         "detail": {"reason": "tick_raised"}})

    try:
        _save(r.dump_state())
    except Exception as exc:  # noqa: BLE001
        logger.debug("http_wedge_reaper: save_state skipped: %s", exc)
    try:
        _write({row["name"]: row for row in rows}, now=now)
    except Exception as exc:  # noqa: BLE001
        logger.debug("http_wedge_reaper: write_decisions skipped: %s", exc)
    _beat(now)
    return rows


def run(*, interval_sec: float = DEFAULT_INTERVAL_SEC,
        clock: Optional[Callable[[], float]] = None,
        sleep: Optional[Callable[[float], None]] = None,
        max_ticks: Optional[int] = None,
        should_stop: Optional[Callable[[], bool]] = None) -> int:
    """Run the reaper loop forever (or max_ticks). Never raises out."""
    import time as _time
    _clock = clock if clock is not None else _time.time
    _sleep = sleep if sleep is not None else _time.sleep
    ticks = 0
    try:
        _beat(float(_clock()))
    except Exception:  # noqa: BLE001
        _beat()
    while True:
        if should_stop is not None:
            try:
                if should_stop():
                    break
            except Exception:  # noqa: BLE001
                break
        try:
            now = float(_clock())
        except Exception:  # noqa: BLE001
            now = _time.time()
        rows = tick(now=now)
        n_kill = sum(1 for r in rows if r.get("verdict") == KILL)
        print("%s | tick=%d targets=%d killed=%d" % (
            HEARTBEAT_COMPONENT, ticks, len(rows), n_kill), flush=True)
        ticks += 1
        if max_ticks is not None and ticks >= max_ticks:
            break
        try:
            _sleep(float(interval_sec))
        except Exception:  # noqa: BLE001
            break
    return ticks


def _main() -> int:  # pragma: no cover
    import argparse
    p = argparse.ArgumentParser(
        description="Supervised HTTP-readiness wedge reaper (M33): kills a "
                    "wedged HTTP-readiness proc on >=3 consecutive >10s "
                    "timeouts while its port stays listening AND CPU>50% "
                    "sustained >120s. No $ field.")
    p.add_argument("--interval", type=float, default=DEFAULT_INTERVAL_SEC)
    a = p.parse_args()
    print("http_wedge_reaper_runner | started interval=%ss component=%s"
          % (a.interval, HEARTBEAT_COMPONENT), flush=True)
    try:
        run(interval_sec=a.interval)
    except KeyboardInterrupt:
        print("http_wedge_reaper_runner | stopped by KeyboardInterrupt", flush=True)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_main())
