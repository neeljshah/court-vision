"""supervisor.webapp_build_drift -- stale-build drift detector for the Next.js webapp.

``next start`` serves the build on disk AT STARTUP.  A fresh ``next build`` does not
restart the server, so new routes (/live, /paper-trading) return 404 from the stale
server.  This module detects that drift so the orchestrator can restart the webapp.

Detection: read on-disk ``webapp/.next/BUILD_ID``; probe the running server for
``/_next/static/<build_id>/_buildManifest.js``.  HTTP 200 -> OK (IDs match).
HTTP 404 -> DRIFT (server is stale).  HTTP 0 or no BUILD_ID -> UNAVAILABLE.

Pure observation: no restart, no data/registry write, no flag flip, no $ claim.
All I/O injectable (build_id_reader / fetcher / clock) -- tests never touch sockets.
Stdlib-only, ASCII-only, <=300 LOC.
"""
from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger("supervisor.webapp_build_drift")

# ---------------------------------------------------------------------------
# Paths + constants
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parents[1]
_NEXT_BUILD_ID_PATH = _REPO_ROOT / "webapp" / ".next" / "BUILD_ID"
_DEFAULT_STATUS_PATH = (
    _REPO_ROOT / "data" / "frontend" / "ops" / "webapp_build_drift.json"
)
_DEFAULT_WEBAPP_PORT = 3000
_DEFAULT_HOST = "127.0.0.1"
_DEFAULT_TIMEOUT = 3.0
_SCHEMA_VERSION = "1.0.0"

# Verdict constants (exported for tests and the ops surface).
STATUS_OK = "OK"
STATUS_DRIFT = "DRIFT"
STATUS_UNAVAILABLE = "UNAVAILABLE"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _read_disk_build_id(path: Path) -> Optional[str]:
    """Return the build ID from ``webapp/.next/BUILD_ID``, or None if absent/unreadable."""
    try:
        raw = path.read_text(encoding="utf-8").strip()
        return raw if raw else None
    except Exception:  # noqa: BLE001
        return None


def _manifest_url(host: str, port: int, build_id: str) -> str:
    """URL for the Next.js build manifest corresponding to *build_id*."""
    return "http://%s:%d/_next/static/%s/_buildManifest.js" % (host, port, build_id)


def _real_fetcher(url: str, timeout: float) -> int:
    """Production HTTP fetcher.  Returns the HTTP status code, or 0 on error."""
    import urllib.request
    import urllib.error
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return int(resp.status)
    except urllib.error.HTTPError as exc:
        return int(exc.code)
    except Exception:  # noqa: BLE001 -- connection refused / timeout / etc.
        return 0


def _build_status_doc(
    status: str,
    disk_build_id: Optional[str],
    now: float,
    detail: str = "",
) -> Dict[str, Any]:
    """Construct the heartbeat-stamped status document."""
    return {
        "schema_version": _SCHEMA_VERSION,
        "status": status,
        "ok": status == STATUS_OK,
        "disk_build_id": disk_build_id or "",
        "detail": detail,
        "updated_at": now,
    }


def _atomic_write(doc: Dict[str, Any], path: Path) -> bool:
    """Write *doc* as JSON to *path* atomically via tmp + os.replace.  Never raises."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(
            json.dumps(doc, indent=2, sort_keys=False, default=str),
            encoding="utf-8",
        )
        os.replace(str(tmp), str(path))
        return True
    except Exception:  # noqa: BLE001
        return False


# ---------------------------------------------------------------------------
# Core check
# ---------------------------------------------------------------------------

def check(
    *,
    build_id_reader: Optional[Callable[[], Optional[str]]] = None,
    fetcher: Optional[Callable[[str, float], int]] = None,
    clock: Optional[Callable[[], float]] = None,
    host: str = _DEFAULT_HOST,
    port: int = _DEFAULT_WEBAPP_PORT,
    timeout: float = _DEFAULT_TIMEOUT,
    next_build_id_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Perform one drift check and return a status dict.  Never raises.

    Parameters
    ----------
    build_id_reader:
        Zero-arg callable returning the on-disk build ID string (or None when
        the file is missing/unreadable).  Defaults to reading the real
        ``webapp/.next/BUILD_ID`` file.
    fetcher:
        callable(url: str, timeout: float) -> int.  Returns the HTTP status
        code (200 = served, 404 = not found, 0 = connection error/timeout).
        Defaults to a real urllib-backed fetcher.
    clock:
        Zero-arg callable returning epoch seconds.  Defaults to time.time.
    host:
        Hostname for the running webapp (default 127.0.0.1).
    port:
        Port for the running webapp (default 3000).
    timeout:
        HTTP request timeout in seconds (default 3.0).
    next_build_id_path:
        Override path to ``BUILD_ID`` file (default: repo/webapp/.next/BUILD_ID).

    Returns
    -------
    dict with keys: schema_version, status, ok, disk_build_id, detail, updated_at.
    ``ok`` is True ONLY when status == STATUS_OK.
    """
    now = float(clock() if clock is not None else time.time())
    _fetcher = fetcher if fetcher is not None else _real_fetcher
    _bid_path = (
        Path(next_build_id_path) if next_build_id_path is not None
        else _NEXT_BUILD_ID_PATH
    )

    if build_id_reader is not None:
        disk_id = build_id_reader()
    else:
        disk_id = _read_disk_build_id(_bid_path)

    if not disk_id:
        # No on-disk build artefact -- we cannot compare; report honest unavailable.
        doc = _build_status_doc(
            STATUS_UNAVAILABLE, None, now,
            detail="webapp/.next/BUILD_ID absent or empty; run next build first",
        )
        logger.info("webapp_build_drift: UNAVAILABLE (no on-disk build ID)")
        return doc

    # Probe the server: ask it to serve the manifest for the current build ID.
    url = _manifest_url(host, port, disk_id)
    try:
        http_status = int(_fetcher(url, timeout))
    except Exception:  # noqa: BLE001
        http_status = 0

    if http_status == 200:
        # Server knows this build ID -- no drift.
        doc = _build_status_doc(
            STATUS_OK, disk_id, now,
            detail="server serves build %s (no drift)" % disk_id,
        )
        logger.debug("webapp_build_drift: OK build=%s", disk_id)
        return doc

    if http_status == 0:
        # Server is not reachable (connection refused / timeout).
        doc = _build_status_doc(
            STATUS_UNAVAILABLE, disk_id, now,
            detail="server not reachable at %s:%d (http_status=0)" % (host, port),
        )
        logger.info("webapp_build_drift: UNAVAILABLE (server not reachable, port=%d)", port)
        return doc

    # Any non-200 response (typically 404) means the server doesn't know this
    # build ID -- it's serving a different (stale) build.
    doc = _build_status_doc(
        STATUS_DRIFT, disk_id, now,
        detail=(
            "server returned HTTP %d for build manifest of %s; "
            "running server predates this build -- restart webapp"
            % (http_status, disk_id)
        ),
    )
    logger.warning(
        "webapp_build_drift: DRIFT disk_build=%s server_http=%d (restart needed)",
        disk_id, http_status,
    )
    return doc


# ---------------------------------------------------------------------------
# Tick + run loop (same pattern as clv_dup_watch)
# ---------------------------------------------------------------------------

def tick(
    *,
    build_id_reader: Optional[Callable[[], Optional[str]]] = None,
    fetcher: Optional[Callable[[str, float], int]] = None,
    clock: Optional[Callable[[], float]] = None,
    status_path: Optional[Path] = None,
    host: str = _DEFAULT_HOST,
    port: int = _DEFAULT_WEBAPP_PORT,
    timeout: float = _DEFAULT_TIMEOUT,
    next_build_id_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Run one drift-check tick, write the status JSON, and return the doc.  Never raises."""
    doc = check(
        build_id_reader=build_id_reader,
        fetcher=fetcher,
        clock=clock,
        host=host,
        port=port,
        timeout=timeout,
        next_build_id_path=next_build_id_path,
    )
    out = Path(status_path) if status_path is not None else _DEFAULT_STATUS_PATH
    _atomic_write(doc, out)
    return doc


def run(
    *,
    interval_sec: float = 60.0,
    build_id_reader: Optional[Callable[[], Optional[str]]] = None,
    fetcher: Optional[Callable[[str, float], int]] = None,
    clock: Optional[Callable[[], float]] = None,
    sleep_fn: Optional[Callable[[float], None]] = None,
    status_path: Optional[Path] = None,
    host: str = _DEFAULT_HOST,
    port: int = _DEFAULT_WEBAPP_PORT,
    timeout: float = _DEFAULT_TIMEOUT,
    next_build_id_path: Optional[Path] = None,
    max_ticks: Optional[int] = None,
) -> int:
    """Run the drift-check daemon loop.

    Calls tick() then sleeps interval_sec, repeating until max_ticks is hit
    (or forever when max_ticks is None).  Returns the number of ticks completed.
    All I/O is injectable so tests never block on real timers or sockets.
    """
    _sleep = sleep_fn if sleep_fn is not None else time.sleep
    completed = 0
    while max_ticks is None or completed < max_ticks:
        tick(
            build_id_reader=build_id_reader,
            fetcher=fetcher,
            clock=clock,
            status_path=status_path,
            host=host,
            port=port,
            timeout=timeout,
            next_build_id_path=next_build_id_path,
        )
        completed += 1
        if max_ticks is not None and completed >= max_ticks:
            break
        _sleep(interval_sec)
    return completed


__all__ = [
    "check",
    "tick",
    "run",
    "STATUS_OK",
    "STATUS_DRIFT",
    "STATUS_UNAVAILABLE",
]
