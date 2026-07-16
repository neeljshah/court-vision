"""scripts.platformkit.autonomy.http_wedge_probe -- REAL (non-test) probes for
http_wedge_reaper: port-listening check, HTTP-timeout probe, per-PID CPU%.

Split out from the pure decision core (http_wedge_reaper.py) so tests exercise
``HttpWedgeReaper.observe`` with fakes/mocks and NEVER touch a real socket, PID,
or wall clock (per the charter's binding test invariant). Everything here is
best-effort + fails toward "no signal" (never fabricates a wedge condition):
psutil is OPTIONAL (mirrors resource_governor.probe_reading); a probe failure
resolves to a value that does NOT count toward a kill (fail-safe direction).

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/autonomy/test_http_wedge_reaper.py -q
"""
from __future__ import annotations

import socket
import time
import urllib.request
from typing import Any, Dict, Optional

_DEFAULT_HOST = "127.0.0.1"
# The charter's timeout floor is >10s; probe slightly above it so a probe that
# times out AT the floor still counts (10.5s > 10.0s strictly).
_HTTP_PROBE_TIMEOUT_SEC = 10.5


def port_is_listening(port: int, *, host: str = _DEFAULT_HOST,
                       timeout: float = 2.0) -> bool:
    """True iff a TCP connection to (host, port) succeeds. Never raises."""
    try:
        with socket.create_connection((host, int(port)), timeout=timeout):
            return True
    except Exception:  # noqa: BLE001 -- closed/refused/unreachable -> not listening
        return False


def http_probe(url: str, *, timeout: float = _HTTP_PROBE_TIMEOUT_SEC) -> Dict[str, Any]:
    """One HTTP GET against *url*; returns {"timed_out", "elapsed_sec", "status"}.

    ``timed_out`` is True only on an actual timeout (socket.timeout / URLError
    wrapping a timeout) -- a fast non-200 response is NOT a timeout (that is a
    normal-but-unhealthy readiness failure, not a wedge signal). Never raises.
    """
    start = time.monotonic()
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            elapsed = time.monotonic() - start
            return {"timed_out": False, "elapsed_sec": elapsed,
                    "status": int(resp.status)}
    except socket.timeout:
        return {"timed_out": True, "elapsed_sec": time.monotonic() - start,
                "status": 0}
    except Exception as exc:  # noqa: BLE001
        elapsed = time.monotonic() - start
        # urllib wraps a socket timeout in URLError(reason=socket.timeout(...)).
        reason = getattr(exc, "reason", None)
        timed_out = isinstance(reason, socket.timeout) or elapsed >= timeout
        return {"timed_out": bool(timed_out), "elapsed_sec": elapsed,
                "status": 0, "error": type(exc).__name__}


# 2026-07-15 fix: psutil.Process.cpu_percent(interval=0/None) measures usage
# SINCE THE LAST CALL on that same Process object. The runner used to build a
# fresh Process() every tick, so every call was "first call" forever -> always
# the meaningless baseline (the audit's cpu_pct=null finding). Caching the
# handle across ticks (module-level, per-pid) means tick N+1 reads a real delta
# since tick N.
_PROC_CACHE: Dict[int, Any] = {}


def pid_cpu_percent(pid: int, *, psutil_mod: Optional[Any] = None,
                     interval: float = 0.0,
                     _cache: Optional[Dict[int, Any]] = None) -> Optional[float]:
    """Recent CPU utilization (percent, can exceed 100 on multi-core) for *pid*.

    psutil is OPTIONAL: returns None (UNKNOWN, never counts toward a kill) if
    unavailable, the pid does not exist, or any probe step fails. Never raises.
    The underlying Process handle is cached per-pid (see module note above) so
    only the very first-ever observation of a pid is the meaningless baseline.
    """
    mod = psutil_mod
    if mod is None:
        try:
            import psutil as mod  # type: ignore[no-redef]
        except Exception:  # noqa: BLE001
            return None
    cache = _PROC_CACHE if _cache is None else _cache
    key = int(pid)
    try:
        proc = cache.get(key)
        if proc is None:
            proc = mod.Process(key)
            cache[key] = proc
        pct = proc.cpu_percent(interval=interval)
        return float(pct) if isinstance(pct, (int, float)) else None
    except Exception:  # noqa: BLE001 -- pid gone / access denied / bad psutil state
        cache.pop(key, None)
        return None


__all__ = [
    "port_is_listening",
    "http_probe",
    "pid_cpu_percent",
]
