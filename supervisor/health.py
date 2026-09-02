"""supervisor.health -- resolve a ProcSpec's readiness probe.

``probe(spec, *, fetcher=None, clock=None)`` returns ``{"ready": bool, "detail": ...}``
for the four readiness kinds. Everything external is injectable so tests never
touch a real socket, port, or wall clock:

  * fetcher -- a callable used for TCP and HTTP probes. It receives a small dict
    request and returns a small dict response. This lets a test pass a fake that
    asserts what was requested and returns a canned result, while production
    passes a real socket/urllib-backed fetcher.

      TCP request:  {"kind": "tcp", "host": "127.0.0.1", "port": 8099, "timeout": 2.0}
      TCP response: {"open": True}                 (or {"open": False, "error": "..."})

      HTTP request: {"kind": "http", "url": "http://127.0.0.1:8099/health", "timeout": 2.0}
      HTTP response:{"status": 200}                (or {"status": 0, "error": "..."})

  * clock -- a zero-arg callable returning epoch seconds (default time.time);
    used only for the heartbeat-freshness probe.

A probe NEVER raises -- any failure resolves to ``{"ready": False, ...}`` so the
boot driver / watchdog can decide policy. Stdlib-only, ASCII-only, <=300 LOC.
"""
from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from supervisor.manifest import HEARTBEAT, HTTP, NONE, TCP, ProcSpec, ReadinessSpec

logger = logging.getLogger(__name__)

Fetcher = Callable[[Dict[str, Any]], Dict[str, Any]]
Clock = Callable[[], float]

# Repo root: supervisor/ -> repo. Heartbeat paths in the manifest are relative.
_REPO_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_HOST = "127.0.0.1"
_DEFAULT_TIMEOUT = 2.0


def _ok(detail: Any) -> Dict[str, Any]:
    return {"ready": True, "detail": detail}


def _not_ready(detail: Any) -> Dict[str, Any]:
    return {"ready": False, "detail": detail}


# --------------------------------------------------------------------------- #
# Heartbeat freshness
# --------------------------------------------------------------------------- #
def _heartbeat_age(path: Path, now: float) -> Optional[float]:
    """Age (seconds) of the heartbeat: prefer its ``updated_at`` epoch, else mtime.

    Returns None if the file is missing/unreadable. The real writers
    (predict_service.scheduler / ingame.live_loop) stamp ``updated_at`` as an
    epoch float; we fall back to file mtime so a writer without the field still
    works.
    """
    if not path.exists():
        return None
    stamp: Optional[float] = None
    try:
        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw) if raw.strip() else {}
        if isinstance(data, dict):
            val = data.get("updated_at")
            if isinstance(val, (int, float)):
                stamp = float(val)
    except Exception:  # noqa: BLE001 -- unreadable/corrupt -> fall back to mtime
        stamp = None
    if stamp is None:
        try:
            stamp = float(os.path.getmtime(str(path)))
        except OSError:
            return None
    return now - stamp


def _probe_heartbeat(rd: ReadinessSpec, now: float) -> Dict[str, Any]:
    rel = rd.heartbeat_path or ""
    if not rel:
        return _not_ready({"kind": HEARTBEAT, "reason": "no heartbeat_path"})
    path = Path(rel)
    if not path.is_absolute():
        path = _REPO_ROOT / rel
    age = _heartbeat_age(path, now)
    if age is None:
        return _not_ready({"kind": HEARTBEAT, "path": str(path), "reason": "absent"})
    fresh = age <= rd.fresh_sec
    detail = {
        "kind": HEARTBEAT, "path": str(path),
        "age_sec": round(age, 1), "fresh_sec": rd.fresh_sec,
    }
    return _ok(detail) if fresh else _not_ready({**detail, "reason": "stale"})


# --------------------------------------------------------------------------- #
# TCP / HTTP (delegated to the injected fetcher)
# --------------------------------------------------------------------------- #
def _probe_tcp(spec: ProcSpec, fetcher: Optional[Fetcher]) -> Dict[str, Any]:
    if spec.port is None:
        return _not_ready({"kind": TCP, "reason": "spec has no port"})
    if fetcher is None:
        return _not_ready({"kind": TCP, "reason": "no fetcher injected"})
    req = {"kind": "tcp", "host": _DEFAULT_HOST, "port": int(spec.port),
           "timeout": _DEFAULT_TIMEOUT}
    try:
        resp = fetcher(req) or {}
    except Exception as exc:  # noqa: BLE001
        return _not_ready({"kind": TCP, "port": spec.port,
                           "reason": "fetcher_raised", "error": type(exc).__name__})
    is_open = bool(resp.get("open"))
    detail = {"kind": TCP, "port": spec.port, "open": is_open}
    if "error" in resp:
        detail["error"] = resp["error"]
    return _ok(detail) if is_open else _not_ready(detail)


def _probe_http(spec: ProcSpec, rd: ReadinessSpec,
                fetcher: Optional[Fetcher]) -> Dict[str, Any]:
    if spec.port is None:
        return _not_ready({"kind": HTTP, "reason": "spec has no port"})
    if fetcher is None:
        return _not_ready({"kind": HTTP, "reason": "no fetcher injected"})
    path = rd.http_path or "/health"
    if not path.startswith("/"):
        path = "/" + path
    url = "http://%s:%d%s" % (_DEFAULT_HOST, int(spec.port), path)
    req = {"kind": "http", "url": url, "timeout": _DEFAULT_TIMEOUT}
    try:
        resp = fetcher(req) or {}
    except Exception as exc:  # noqa: BLE001
        return _not_ready({"kind": HTTP, "url": url,
                           "reason": "fetcher_raised", "error": type(exc).__name__})
    status = resp.get("status")
    is_200 = status == 200
    detail = {"kind": HTTP, "url": url, "status": status}
    if "error" in resp:
        detail["error"] = resp["error"]
    return _ok(detail) if is_200 else _not_ready(detail)


# --------------------------------------------------------------------------- #
# Public entrypoint
# --------------------------------------------------------------------------- #
def probe(spec: ProcSpec, *, fetcher: Optional[Fetcher] = None,
          clock: Optional[Clock] = None) -> Dict[str, Any]:
    """Resolve *spec*'s readiness probe. Never raises.

    Returns ``{"ready": bool, "detail": {...}}``. ``detail`` always carries the
    probe ``kind`` plus kind-specific fields (port/url/status, path/age, etc.)
    so an operator can see WHY a process is or isn't ready.

    ``fetcher`` is required for TCP/HTTP kinds (inject a fake in tests, a real
    socket/urllib fetcher in production). ``clock`` (default time.time) is used
    only by the heartbeat-freshness probe.
    """
    now = float(clock() if clock is not None else time.time())
    rd = spec.readiness
    kind = rd.kind
    if kind == NONE:
        return _ok({"kind": NONE, "reason": "no probe; ready if alive"})
    if kind == HEARTBEAT:
        return _probe_heartbeat(rd, now)
    if kind == TCP:
        return _probe_tcp(spec, fetcher)
    if kind == HTTP:
        return _probe_http(spec, rd, fetcher)
    return _not_ready({"kind": kind, "reason": "unknown probe kind"})


# --------------------------------------------------------------------------- #
# A real (production) fetcher -- NOT used by tests.
# --------------------------------------------------------------------------- #
def real_fetcher(req: Dict[str, Any]) -> Dict[str, Any]:  # pragma: no cover
    """Socket/urllib-backed fetcher for live boot drivers. Never raises."""
    kind = req.get("kind")
    timeout = float(req.get("timeout", _DEFAULT_TIMEOUT))
    if kind == "tcp":
        import socket
        try:
            with socket.create_connection(
                (req["host"], int(req["port"])), timeout=timeout):
                return {"open": True}
        except Exception as exc:  # noqa: BLE001
            return {"open": False, "error": type(exc).__name__}
    if kind == "http":
        import urllib.request
        try:
            with urllib.request.urlopen(req["url"], timeout=timeout) as resp:
                return {"status": int(resp.status)}
        except Exception as exc:  # noqa: BLE001
            code = getattr(exc, "code", 0)
            return {"status": int(code) if code else 0, "error": type(exc).__name__}
    return {"error": "unknown_fetcher_kind"}


# --------------------------------------------------------------------------- #
# Mount self-check + smoke probe (idempotent startup guards)
# --------------------------------------------------------------------------- #

# Routes required for the API to be considered fully operational.
_REQUIRED_ROUTES: tuple = ("/api/paper/predictions", "/health", "/api/sports")
_SELFCHECK_ATTR = "_supervisor_health_selfcheck_done"


def mount_selfcheck(app: Any) -> Dict[str, Any]:
    """Mount-verification self-check, evaluated at CALL time.

    Inspects the FastAPI *app*'s routes and verifies every path in
    _REQUIRED_ROUTES is present. Missing routes log WARN (never green-on-
    missing). Safe to call repeatedly: the route table is re-read on EVERY call
    -- a snapshot cached at import time (before the paper routers mounted) made
    /ready a false negative for the life of the process, so the last result is
    kept only to log the WARN once per change. Returns {checked, present,
    missing, ok} -- ok=True iff missing==[]. Never raises; non-conforming *app*
    objects yield ok=False.
    """
    prev = getattr(app, _SELFCHECK_ATTR, None)
    checked = list(_REQUIRED_ROUTES)
    present: list = []
    missing: list = []
    try:
        mounted = {str(getattr(r, "path", "")) for r in (getattr(app, "routes", None) or [])}
        for rp in checked:
            (present if rp in mounted else missing).append(rp)
    except Exception as exc:  # noqa: BLE001
        logger.warning("supervisor.health: mount_selfcheck inspect failed (%s); "
                       "treating all required routes as missing.", exc)
        missing = list(checked)
        present = []
    ok = not missing
    if not isinstance(prev, dict) or prev.get("missing") != missing:
        for rp in missing:
            logger.warning(
                "supervisor.health: mount_selfcheck WARN -- required route %r "
                "NOT mounted (stale process or failed import). "
                "FE will 404. Restart predict_service to fix.", rp)
        if ok:
            logger.info("supervisor.health: mount_selfcheck OK -- %d required "
                        "routes present", len(checked))
    result: Dict[str, Any] = {"checked": checked, "present": present,
                               "missing": missing, "ok": ok}
    try:
        setattr(app, _SELFCHECK_ATTR, result)
    except Exception:  # noqa: BLE001
        pass
    return result


def smoke_probe(url: str, route_name: str = "", *,
                fetcher: Optional[Fetcher] = None) -> Dict[str, Any]:
    """Probe one HTTP URL; log WARN and return ok=False on any non-200 response.

    Never returns ok=True on a non-200 -- caller can assert result["ok"] is
    True and it will only pass when the route genuinely responds. Uses
    real_fetcher when no fetcher is injected. Never raises.
    """
    label = route_name or url
    _f = fetcher if fetcher is not None else real_fetcher
    try:
        resp = _f({"kind": "http", "url": url, "timeout": _DEFAULT_TIMEOUT})
    except Exception as exc:  # noqa: BLE001
        logger.warning("supervisor.health: smoke_probe WARN -- %s raised %s",
                       label, type(exc).__name__)
        return {"ok": False, "url": url, "status": 0, "error": type(exc).__name__}
    status = int(resp.get("status") or 0)
    ok = (status == 200)
    if ok:
        logger.info("supervisor.health: smoke_probe OK -- %s HTTP 200", label)
    else:
        logger.warning("supervisor.health: smoke_probe WARN -- %s HTTP %d "
                       "(not 200); route NOT green-on-missing.", label, status)
    detail: Dict[str, Any] = {"ok": ok, "url": url, "status": status}
    if "error" in resp:
        detail["error"] = resp["error"]
    return detail
