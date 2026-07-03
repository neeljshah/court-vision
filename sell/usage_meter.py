"""sell.usage_meter -- atomic per-tenant call counters and quota helpers.

Per-tenant call counts are persisted as newline-delimited JSON records appended
to each tenant's usage.jsonl file (under their isolated namespace in
data/frontend/sell/tenants/<tenant>/usage.jsonl). The append is best-effort
atomic on POSIX (O_APPEND is atomic for small writes) and similarly safe on
Windows. record() NEVER raises -- a broken meter must not crash the API.

Usage model:
    * record(tenant, endpoint)  -- append one call record (fire-and-forget)
    * usage(tenant)             -- count of all calls, keyed by endpoint
    * total_calls(tenant)       -- total call count across all endpoints
    * within_quota(tenant, limit) -- True iff total_calls < limit

INVARIANTS: <=300 LOC; ASCII only; no secrets; no $-edge field; never raises
from record(); thread-safe via O_APPEND; no data/registry/ writes.
"""
from __future__ import annotations

import json
import os
import pathlib
import time
from typing import Dict, Optional

from sell.tenancy import Namespace, namespace_for

#: File name inside each tenant's namespace that holds usage records.
_USAGE_FILE = "usage.jsonl"

#: Maximum line length we allow when reading back records (defensive).
_MAX_LINE = 512


# --------------------------------------------------------------------------- #
# Internal helpers                                                              #
# --------------------------------------------------------------------------- #

def _usage_path(tenant: str, ns: Optional[Namespace] = None) -> Optional[pathlib.Path]:
    """Return the usage.jsonl path for *tenant*, or None on any error."""
    try:
        n = ns or namespace_for(tenant)
        n.ensure_dir()            # create tenant dir if needed
        return n.path(_USAGE_FILE)
    except Exception:
        return None


def _append_line(path: pathlib.Path, line: str) -> None:
    """Atomically append *line*+newline to *path* via O_APPEND.

    On POSIX, O_APPEND writes < PIPE_BUF (4096 bytes) are atomic. On Windows,
    the same append mode is used (best-effort). Never raises -- failures are
    silently swallowed so a broken meter cannot crash the API.
    """
    try:
        encoded = (line + "\n").encode("ascii")
        fd = os.open(
            str(path),
            os.O_WRONLY | os.O_CREAT | os.O_APPEND,
            0o644,
        )
        try:
            os.write(fd, encoded)
        finally:
            os.close(fd)
    except Exception:
        pass  # meter must never raise


# --------------------------------------------------------------------------- #
# Public API                                                                   #
# --------------------------------------------------------------------------- #

def record(
    tenant: str,
    endpoint: str,
    *,
    _ns: Optional[Namespace] = None,
) -> None:
    """Record one API call for *tenant* at *endpoint*.

    Appends a JSON record to the tenant's usage.jsonl. Fire-and-forget:
    this function NEVER raises -- a logging failure must not crash the API.

    Args:
        tenant:   The tenant identifier.
        endpoint: The endpoint or action name (e.g. "/predict/slate").
        _ns:      Override Namespace (for tests -- avoids real disk I/O).
    """
    try:
        path = _usage_path(tenant, _ns)
        if path is None:
            return
        rec = json.dumps({
            "tenant": str(tenant),
            "endpoint": str(endpoint),
            "ts": int(time.time()),
        }, ensure_ascii=True)
        _append_line(path, rec)
    except Exception:
        pass  # never raises


def usage(
    tenant: str,
    *,
    _ns: Optional[Namespace] = None,
) -> Dict[str, int]:
    """Return per-endpoint call counts for *tenant*.

    Reads the usage.jsonl file and counts calls per endpoint. Returns an empty
    dict if the file does not exist or cannot be read.

    Args:
        tenant: The tenant identifier.
        _ns:    Override Namespace (for tests).

    Returns:
        Dict mapping endpoint -> call count. Empty on any error.
    """
    counts: Dict[str, int] = {}
    try:
        path = _usage_path(tenant, _ns)
        if path is None or not path.exists():
            return counts
        with open(str(path), "r", encoding="ascii", errors="replace") as fh:
            for raw in fh:
                line = raw.strip()
                if not line or len(line) > _MAX_LINE:
                    continue
                try:
                    obj = json.loads(line)
                    ep = str(obj.get("endpoint", ""))
                    if ep:
                        counts[ep] = counts.get(ep, 0) + 1
                except (json.JSONDecodeError, Exception):
                    continue
    except Exception:
        pass
    return counts


def total_calls(
    tenant: str,
    *,
    _ns: Optional[Namespace] = None,
) -> int:
    """Return the total number of recorded calls for *tenant* across all endpoints.

    Args:
        tenant: The tenant identifier.
        _ns:    Override Namespace (for tests).

    Returns:
        Integer call count. Returns 0 on any error.
    """
    return sum(usage(tenant, _ns=_ns).values())


def within_quota(
    tenant: str,
    limit: int,
    *,
    _ns: Optional[Namespace] = None,
) -> bool:
    """Return True iff the tenant's total calls are strictly less than *limit*.

    A quota of 0 or negative always returns False (no quota means denied).

    Args:
        tenant: The tenant identifier.
        limit:  Maximum number of calls allowed (exclusive upper bound).
        _ns:    Override Namespace (for tests).

    Returns:
        True iff total_calls(tenant) < limit.
    """
    if limit <= 0:
        return False
    return total_calls(tenant, _ns=_ns) < limit


__all__ = [
    "record",
    "usage",
    "total_calls",
    "within_quota",
]
