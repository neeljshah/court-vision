"""scripts.platformkit.odds_provider.transport -- per-host escalating HTTP transport.

THE GAP: a bot-walled source (401/403/406/429/503, or an HTML challenge page
served where JSON was expected) makes the plain urllib fetch (http_cache.
http_get_json) fail even though the endpoint is genuinely reachable from a real
browser. This module tries the plain (polite, cheap) path first; only on a
BLOCKED-SHAPED failure does it escalate to the stealth tier (stealth_fetch,
browser-TLS impersonation). A host that has recently needed stealth is
remembered (on disk) so we go straight to stealth next time -- and the memory
EXPIRES (default 6h) so we keep re-probing the polite path and drop back to it
the moment a wall lifts.

Honesty: never masks a real outage. Any failure that is NOT blocked-shaped
(timeout, DNS failure, 5xx already retried by http_get_json, a genuine 404)
re-raises immediately -- no stealth escalation, no silent retry. If stealth
ALSO fails, the ORIGINAL plain error is re-raised (never the stealth error) so
a provider's existing except-and-degrade-to-UNAVAILABLE logic is unchanged.

Kill switch: CV_STEALTH_FALLBACK=0 (or "false"/"no") restores exact legacy
behavior (plain fetch only, scrapling never imported).

Everything injectable for offline tests: plain_get, stealth_get, prefs_path,
now. No scrapling import here -- only stealth_fetch imports it, and only when
actually used.
"""
from __future__ import annotations

import json
import logging
import os
import time
import urllib.error
from pathlib import Path
from typing import Any, Callable, Dict, Optional
from urllib.parse import urlparse

from .http_cache import http_get_json
from .stealth_fetch import stealth_get_json

logger = logging.getLogger(__name__)

_REPO = Path(__file__).resolve().parents[3]
_DEFAULT_PREFS_PATH = _REPO / "data" / "cache" / "odds_transport" / "transport_prefs.json"

# Entries older than this are treated as expired -- plain is re-probed first
# again so we return to the polite path once a wall lifts.
DEFAULT_STEALTH_TTL_SEC = 21600.0  # 6h

_BLOCKED_HTTP_CODES = (401, 403, 406, 409, 429, 451, 503)


def _kill_switch_on() -> bool:
    return os.environ.get("CV_STEALTH_FALLBACK", "1").strip().lower() in ("0", "false", "no")


def _stealth_ttl_sec() -> float:
    try:
        return float(os.environ.get("CV_STEALTH_TTL_SEC", DEFAULT_STEALTH_TTL_SEC))
    except (TypeError, ValueError):
        return DEFAULT_STEALTH_TTL_SEC


def _host(url: str) -> str:
    try:
        return urlparse(url).netloc.lower()
    except Exception:  # noqa: BLE001 -- never let host parsing sink a fetch
        return url


def _prefs_file(prefs_path: Optional[Path]) -> Path:
    return Path(prefs_path) if prefs_path is not None else _DEFAULT_PREFS_PATH


def _load_prefs(prefs_path: Optional[Path] = None) -> Dict[str, Any]:
    """Best-effort read of the transport prefs file. Never raises; missing or
    corrupt file -> empty prefs (equivalent to "no host has ever needed stealth")."""
    path = _prefs_file(prefs_path)
    try:
        if not path.is_file():
            return {}
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception as exc:  # noqa: BLE001 -- corrupt prefs must never sink a fetch
        logger.debug("transport prefs read failed for %s: %s", path, exc)
        return {}


def _save_prefs(prefs: Dict[str, Any], prefs_path: Optional[Path] = None) -> None:
    """Best-effort atomic write (tmp + os.replace). Never raises."""
    path = _prefs_file(prefs_path)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(prefs, ensure_ascii=True, indent=2, sort_keys=True),
                       encoding="ascii")
        os.replace(str(tmp), str(path))
    except Exception as exc:  # noqa: BLE001 -- write must never sink a fetch
        logger.debug("transport prefs write failed for %s: %s", path, exc)


def mark_stealth_first(
    host: str,
    *,
    prefs_path: Optional[Path] = None,
    now: Callable[[], float] = time.time,
) -> None:
    """Record that *host* should be tried via stealth FIRST going forward.

    Idempotent; refreshes ``since``/``last_used`` on every call. Never raises.
    """
    prefs = _load_prefs(prefs_path)
    ts = float(now())
    entry = prefs.get(host)
    since = ts if not isinstance(entry, dict) else float(entry.get("since", ts))
    prefs[host] = {"since": since, "last_used": ts}
    _save_prefs(prefs, prefs_path)


def _is_stealth_first(host: str, *, prefs_path: Optional[Path], now: Callable[[], float]) -> bool:
    prefs = _load_prefs(prefs_path)
    entry = prefs.get(host)
    if not isinstance(entry, dict):
        return False
    try:
        since = float(entry.get("since", 0.0))
    except (TypeError, ValueError):
        return False
    return (float(now()) - since) < _stealth_ttl_sec()


def _is_blocked_shaped(exc: BaseException) -> bool:
    """True iff *exc* looks like a bot-wall: a blocked HTTP status, or a JSON
    parse failure (HTML challenge page served where JSON was expected)."""
    if isinstance(exc, urllib.error.HTTPError):
        return exc.code in _BLOCKED_HTTP_CODES
    if isinstance(exc, (ValueError,)):  # covers json.JSONDecodeError
        return True
    return False


def resilient_get_json(
    url: str,
    timeout: float = 20.0,
    *,
    plain_get: Callable[..., Any] = http_get_json,
    stealth_get: Callable[..., Any] = stealth_get_json,
    prefs_path: Optional[Path] = None,
    now: Callable[[], float] = time.time,
) -> Any:
    """Fetch *url* as JSON, escalating from plain to stealth only when blocked.

    Order:
      1. Kill switch (CV_STEALTH_FALLBACK=0) -> plain_get only, exact legacy path.
      2. Host has a fresh stealth-first mark -> try stealth first, fall back to
         plain on ANY stealth failure (never lose a feed to a stealth-only bug).
      3. Otherwise plain first; on a BLOCKED-SHAPED failure, try stealth; on
         stealth success the host is marked stealth-first for next time.
      4. If stealth also fails, the ORIGINAL plain error is re-raised (never the
         stealth error) -- honest degrade, provider goes UNAVAILABLE as today.
      5. A non-blocked-shaped plain failure re-raises immediately -- never masks
         a real outage with a stealth retry.
    """
    if _kill_switch_on():
        return plain_get(url, timeout)

    host = _host(url)

    if _is_stealth_first(host, prefs_path=prefs_path, now=now):
        try:
            result = stealth_get(url, timeout)
            mark_stealth_first(host, prefs_path=prefs_path, now=now)  # refresh last_used
            return result
        except Exception as exc:  # noqa: BLE001 -- stealth-first hosts still fall back
            logger.debug("stealth-first fetch failed for %s, falling back to plain: %s",
                        host, exc)
            return plain_get(url, timeout)

    try:
        return plain_get(url, timeout)
    except Exception as plain_exc:  # noqa: BLE001 -- classify before escalating
        if not _is_blocked_shaped(plain_exc):
            raise
        try:
            result = stealth_get(url, timeout)
        except Exception as stealth_exc:  # noqa: BLE001 -- honest degrade
            logger.debug("stealth fallback also failed for %s: %s", host, stealth_exc)
            raise plain_exc
        mark_stealth_first(host, prefs_path=prefs_path, now=now)
        return result


__all__ = [
    "resilient_get_json",
    "mark_stealth_first",
    "DEFAULT_STEALTH_TTL_SEC",
]
