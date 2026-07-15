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

TIER 3 (browser render): when plain AND stealth BOTH fail blocked-shaped, and
only if the caller has explicitly opted in with env CV_BROWSER_FALLBACK=1,
one more escalation is tried via browser_fetch (a real headless-browser page
load -- see that module's docstring for why this exists and its one known
limitation). DEFAULT OFF -- this is a transport CONFIG knob, not a model or
feature flag: it exists so a human or a reviewed wake can turn on the
heaviest, slowest tier for a specific probe run without changing any
daemon's behavior by default. A host that succeeds via browser is remembered
with tier tag "browser" in the SAME prefs file/TTL as the stealth tier.

Everything injectable for offline tests: plain_get, stealth_get, browser_get,
prefs_path, now. No scrapling import here -- only stealth_fetch/browser_fetch
import it, and only when actually used.
"""
from __future__ import annotations

import concurrent.futures
import json
import logging
import os
import time
import urllib.error
from pathlib import Path
from typing import Any, Callable, Dict, Optional
from urllib.parse import urlparse

from .browser_fetch import browser_get_json
from .http_cache import http_get_json
from .stealth_fetch import stealth_get_json

logger = logging.getLogger(__name__)

# ponytail: stealth_get/browser_get delegate to 3rd-party libs (scrapling/
# playwright) whose own `timeout=` kwarg is NOT independently verified to
# bound a hang (confirmed live: m1_paper wedged at near-zero CPU inside a
# feed fetch, never returning). A thread + future.result(timeout=) is the
# stdlib way to hard-cap ANY call regardless of what it blocks on internally.
# Ceiling = declared timeout + 5s grace (let the library's own timeout fire
# first if it works; force-abandon it if it doesn't). The stray thread is
# daemonized and leaked on timeout -- Python cannot kill a thread -- but that
# is far cheaper than wedging the whole research loop forever.
_WATCHDOG_GRACE_SEC = 5.0
_watchdog_pool = concurrent.futures.ThreadPoolExecutor(
    max_workers=4, thread_name_prefix="odds-watchdog")


def _bounded_call(fn: Callable[..., Any], url: str, timeout: float) -> Any:
    """Call fn(url, timeout) but never block longer than timeout+grace."""
    fut = _watchdog_pool.submit(fn, url, timeout)
    try:
        return fut.result(timeout=timeout + _WATCHDOG_GRACE_SEC)
    except concurrent.futures.TimeoutError as exc:
        raise TimeoutError(
            f"transport watchdog: {getattr(fn, '__name__', fn)} exceeded "
            f"{timeout + _WATCHDOG_GRACE_SEC}s for {url}") from exc

_REPO = Path(__file__).resolve().parents[3]
_DEFAULT_PREFS_PATH = _REPO / "data" / "cache" / "odds_transport" / "transport_prefs.json"

# Entries older than this are treated as expired -- plain is re-probed first
# again so we return to the polite path once a wall lifts.
DEFAULT_STEALTH_TTL_SEC = 21600.0  # 6h

_BLOCKED_HTTP_CODES = (401, 403, 406, 409, 429, 451, 503)


def _kill_switch_on() -> bool:
    return os.environ.get("CV_STEALTH_FALLBACK", "1").strip().lower() in ("0", "false", "no")


def _browser_fallback_on() -> bool:
    """Tier 3 is opt-IN (opposite polarity of the tier-2 kill switch): default
    OFF, only tried when a human/reviewed-wake process sets this explicitly."""
    return os.environ.get("CV_BROWSER_FALLBACK", "0").strip().lower() in ("1", "true", "yes")


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
    tier: str = "stealth",
    prefs_path: Optional[Path] = None,
    now: Callable[[], float] = time.time,
) -> None:
    """Record that *host* should be tried via *tier* FIRST going forward.

    *tier* is "stealth" (default, back-compat) or "browser" (tier 3). Idempotent;
    refreshes ``since``/``last_used``/``tier`` on every call. Never raises.
    """
    prefs = _load_prefs(prefs_path)
    ts = float(now())
    entry = prefs.get(host)
    since = ts if not isinstance(entry, dict) else float(entry.get("since", ts))
    prefs[host] = {"since": since, "last_used": ts, "tier": tier}
    _save_prefs(prefs, prefs_path)


def _preferred_tier(host: str, *, prefs_path: Optional[Path], now: Callable[[], float]) -> Optional[str]:
    """Return the fresh (non-expired) preferred tier for *host*, or None if no
    mark exists or it has expired past the shared TTL. Legacy entries (written
    before the "tier" field existed) default to "stealth" -- unchanged behavior."""
    prefs = _load_prefs(prefs_path)
    entry = prefs.get(host)
    if not isinstance(entry, dict):
        return None
    try:
        since = float(entry.get("since", 0.0))
    except (TypeError, ValueError):
        return None
    if (float(now()) - since) >= _stealth_ttl_sec():
        return None
    return str(entry.get("tier", "stealth"))


def _is_stealth_first(host: str, *, prefs_path: Optional[Path], now: Callable[[], float]) -> bool:
    return _preferred_tier(host, prefs_path=prefs_path, now=now) == "stealth"


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
    browser_get: Callable[..., Any] = browser_get_json,
    prefs_path: Optional[Path] = None,
    now: Callable[[], float] = time.time,
) -> Any:
    """Fetch *url* as JSON, escalating plain -> stealth -> browser only when blocked.

    Order:
      1. Kill switch (CV_STEALTH_FALLBACK=0) -> plain_get only, exact legacy path
         (tier 3 is also skipped -- the kill switch restores full legacy behavior).
      2. Host has a fresh preferred-tier mark (stealth or browser) -> try that
         tier first, fall back to plain on ANY failure of it (never lose a feed
         to a tier-specific bug).
      3. Otherwise plain first; on a BLOCKED-SHAPED failure, try stealth.
      4. If stealth ALSO fails blocked-shaped AND env CV_BROWSER_FALLBACK=1,
         try browser (tier 3) as the last resort. DEFAULT OFF -- see
         _browser_fallback_on(); this is a transport config knob, not a model
         flag, so a daemon's behavior never changes unless a human/reviewed
         wake sets the env for a specific run.
      5. Whichever tier succeeds marks the host preferred-tier for next time.
      6. If every attempted tier fails, the ORIGINAL plain error is re-raised
         (never a stealth/browser error) -- honest degrade, provider goes
         UNAVAILABLE as today.
      7. A non-blocked-shaped plain failure re-raises immediately -- never masks
         a real outage with a stealth/browser retry.
    """
    if _kill_switch_on():
        return plain_get(url, timeout)

    host = _host(url)
    browser_on = _browser_fallback_on()

    preferred = _preferred_tier(host, prefs_path=prefs_path, now=now)
    if preferred == "stealth":
        try:
            result = _bounded_call(stealth_get, url, timeout)
            mark_stealth_first(host, tier="stealth", prefs_path=prefs_path, now=now)
            return result
        except Exception as exc:  # noqa: BLE001 -- preferred-tier hosts still fall back
            logger.debug("stealth-first fetch failed for %s, falling back to plain: %s",
                        host, exc)
            return plain_get(url, timeout)
    if preferred == "browser" and browser_on:
        try:
            result = _bounded_call(browser_get, url, timeout)
            mark_stealth_first(host, tier="browser", prefs_path=prefs_path, now=now)
            return result
        except Exception as exc:  # noqa: BLE001 -- preferred-tier hosts still fall back
            logger.debug("browser-first fetch failed for %s, falling back to plain: %s",
                        host, exc)
            return plain_get(url, timeout)

    try:
        return plain_get(url, timeout)
    except Exception as plain_exc:  # noqa: BLE001 -- classify before escalating
        if not _is_blocked_shaped(plain_exc):
            raise
        try:
            result = _bounded_call(stealth_get, url, timeout)
        except Exception as stealth_exc:  # noqa: BLE001 -- honest degrade / maybe tier 3
            logger.debug("stealth fallback also failed for %s: %s", host, stealth_exc)
            if browser_on and _is_blocked_shaped(stealth_exc):
                try:
                    result = _bounded_call(browser_get, url, timeout)
                except Exception as browser_exc:  # noqa: BLE001 -- honest degrade
                    logger.debug("browser fallback also failed for %s: %s",
                                host, browser_exc)
                    raise plain_exc
                mark_stealth_first(host, tier="browser", prefs_path=prefs_path, now=now)
                return result
            raise plain_exc
        mark_stealth_first(host, tier="stealth", prefs_path=prefs_path, now=now)
        return result


__all__ = [
    "resilient_get_json",
    "mark_stealth_first",
    "DEFAULT_STEALTH_TTL_SEC",
]
