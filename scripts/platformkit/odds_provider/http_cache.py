"""scripts.platformkit.odds_provider.http_cache -- injectable HTTP + TTL disk cache.

`http_get_json` is the default network fetcher; every provider takes an injectable
`http_get` so tests run with ZERO network on canned payloads. `disk_cache_get`
wraps any fetcher with a TTL JSON file cache so we do not hammer free public
sources (Kalshi ~30 rps, ESPN/Polymarket unmetered but be polite).

No secrets here; tokens (if any) are read from ENV inside each provider.

STALE-NEVER-GREEN (LA-P0-a): a cache entry records the TRUE wall-clock time the
BODY was fetched from the network (``_fetched_at``). On a cache HIT we return that
ORIGINAL fetch time -- NEVER now() -- so a body served from a cached (or, after a
fetch failure, dead) feed can never re-stamp itself fresh inside the TTL. Callers
use ``disk_cache_get_meta`` to learn the true fetched-at and whether the read was a
cache hit, and stamp their ``as_of`` / ``captured_at`` with that true time.

RETRY/BACKOFF (LA-P0-c / EX-P0-01): the network fetch is wrapped in an exponential
backoff + jitter + cap retry (tenacity when installed; an equivalent stdlib
fallback otherwise) so one transient 503 does not drop an entire sport's lines.

STEALTH FALLBACK: when a caller leaves ``http_get`` at its default
(``http_get_json``), ``disk_cache_get_meta`` routes the live fetch through
``transport.resilient_get_json``, which escalates a BLOCKED-SHAPED failure
(401/403/406/429/451/503, or an HTML wall parsed as JSON) to a browser-TLS-
impersonated fetch before giving up. Kill switch: env CV_STEALTH_FALLBACK=0
restores exact legacy (plain-only) behavior. A caller that injects its own
``http_get`` is UNCHANGED -- escalation only applies to the shared default path.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable, Optional, Tuple

logger = logging.getLogger(__name__)

DEFAULT_TTL_SECONDS = 60.0  # live odds move fast; a short TTL is plenty.
_CACHE_DIR = Path(os.environ.get("ODDS_PROVIDER_CACHE_DIR",
                                 str(Path.home() / ".cache" / "courtvision_odds")))
_UA = "Mozilla/5.0 (CourtVision odds_provider; honest public-API client)"

# Retry tuning: a few attempts with exponential backoff + jitter, capped so a flaky
# venue recovers from a transient blip without hammering the source or stalling the
# whole slate. Kept small (seconds) -- a feed that is truly down should degrade to
# UNAVAILABLE promptly, not block every other sport.
RETRY_ATTEMPTS = 3
RETRY_BASE_SEC = 0.5
RETRY_MAX_SEC = 4.0

# Exceptions worth retrying: transient network / 5xx / timeouts. A 4xx (client)
# error is NOT retried (it will not self-heal); we let it surface so the provider
# degrades to UNAVAILABLE.
_TRANSIENT = (urllib.error.URLError, TimeoutError, ConnectionError, OSError)


def _is_transient(exc: BaseException) -> bool:
    """True iff *exc* is a transient/retryable network error (not a 4xx)."""
    if isinstance(exc, urllib.error.HTTPError):
        # Retry only server-side / rate-limit codes; client 4xx will not self-heal.
        return exc.code in (429, 500, 502, 503, 504)
    return isinstance(exc, _TRANSIENT)


def _retrying(fn: Callable[..., Any]) -> Callable[..., Any]:
    """Wrap *fn* in exponential-backoff + jitter + cap retry on transient errors.

    Uses tenacity (pinned in requirements) when importable; otherwise an equivalent
    stdlib fallback with the SAME policy (RETRY_ATTEMPTS tries, exp backoff base
    RETRY_BASE_SEC, full jitter, capped at RETRY_MAX_SEC). A non-transient error is
    raised immediately. Time is taken from ``time.sleep`` (monkeypatchable in tests).
    """
    try:
        from tenacity import (retry, retry_if_exception, stop_after_attempt,
                              wait_exponential_jitter)
        return retry(
            reraise=True,
            stop=stop_after_attempt(RETRY_ATTEMPTS),
            wait=wait_exponential_jitter(initial=RETRY_BASE_SEC, max=RETRY_MAX_SEC),
            retry=retry_if_exception(_is_transient),
        )(fn)
    except Exception:  # noqa: BLE001 -- tenacity absent: use the stdlib fallback.
        return _fallback_retry(fn)


def _fallback_retry(fn: Callable[..., Any]) -> Callable[..., Any]:
    """Stdlib retry wrapper mirroring the tenacity policy (no extra dependency)."""
    import functools
    import random

    @functools.wraps(fn)
    def _wrapped(*args: Any, **kwargs: Any) -> Any:
        last: Optional[BaseException] = None
        for attempt in range(1, RETRY_ATTEMPTS + 1):
            try:
                return fn(*args, **kwargs)
            except Exception as exc:  # noqa: BLE001 -- decide retry vs reraise below
                last = exc
                if attempt >= RETRY_ATTEMPTS or not _is_transient(exc):
                    raise
                backoff = min(RETRY_MAX_SEC, RETRY_BASE_SEC * (2 ** (attempt - 1)))
                delay = random.uniform(0.0, backoff)  # full jitter
                logger.debug("retrying after transient error (attempt %d): %s",
                             attempt, exc)
                time.sleep(delay)
        if last is not None:  # pragma: no cover -- loop always returns or raises
            raise last
    return _wrapped


@_retrying
def http_get_json(url: str, timeout: float = 20.0) -> Any:
    """GET *url* and parse JSON. HTTPS only; sends a polite UA + Accept header.

    Retried with exponential backoff + jitter on a transient (5xx/429/timeout)
    error so one blip does not drop a whole sport's slate; a 4xx surfaces at once.
    """
    req = urllib.request.Request(
        url, headers={"Accept": "application/json", "User-Agent": _UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310 (https only)
        return json.loads(r.read().decode("utf-8", errors="replace"))


def _cache_path(url: str) -> Path:
    h = hashlib.sha256(url.encode("utf-8")).hexdigest()[:24]
    return _CACHE_DIR / f"{h}.json"


def _tmp_write_path(path: Path) -> Tuple[int, str]:
    """Open a fresh, atomically-unique tmp file next to *path* (open fd + name).

    Was ``path.with_suffix(path.suffix + ".tmp")`` -- ONE shared tmp name per
    URL, so two concurrent same-URL writers could alias the same tmp inode
    (torn JSON possible). ``tempfile.mkstemp`` guarantees OS-level unique
    creation, so distinct writers never collide even within one process.
    """
    return tempfile.mkstemp(dir=str(path.parent), prefix=path.name + ".", suffix=".tmp")


def disk_cache_get_meta(
    url: str,
    *,
    http_get: Callable[[str], Any] = http_get_json,
    ttl: float = DEFAULT_TTL_SECONDS,
    now: Callable[[], float] = time.time,
) -> Tuple[Any, str, bool]:
    """Return (body, fetched_at_iso, cache_hit) for *url*.

    A fresh cache entry (younger than *ttl*) is returned WITH ITS ORIGINAL
    ``fetched_at`` -- the true wall-clock time the body was last pulled from the
    network -- and cache_hit=True. This is the stale-never-green guard: a cached or
    dead feed carries its real fetch time, so a caller stamping ``as_of`` from it
    cannot read fresh once that time ages past the freshness TTL.

    On a cache miss / expiry we fetch live, stamp ``fetched_at = now()``, persist the
    body wrapped with that time, and return cache_hit=False. A cache read/write
    failure is non-fatal -- we fall back to a live fetch (or skip caching). The
    fetch itself is retried (see http_get_json); if it still fails the error
    propagates so the provider can degrade to UNAVAILABLE (never a stale-green body).
    """
    path = _cache_path(url)
    try:
        if path.is_file():
            with path.open("r", encoding="utf-8") as fh:
                stored = json.load(fh)
            body, fetched_at, fetched_epoch = _unwrap(stored, path)
            # Age is measured against the entry's OWN stored fetch epoch (consistent
            # with the injectable *now*), falling back to file mtime for legacy
            # entries. A cache hit therefore expires on the same clock the caller
            # uses -- never a now()/mtime mismatch that hides a stale entry.
            if now() - fetched_epoch < ttl:
                return body, fetched_at, True
    except Exception as exc:  # noqa: BLE001 -- cache read must never sink a fetch
        logger.debug("odds cache read miss for %s: %s", url, exc)
    if http_get is http_get_json:
        # Caller left http_get at its default -> route through the escalating
        # transport (plain first, stealth fallback on a blocked-shaped failure).
        # Imported here (not at module top) to avoid a transport<->http_cache cycle.
        from .transport import resilient_get_json
        body = resilient_get_json(url)
    else:
        body = http_get(url)
    fetched_epoch = float(now())
    fetched_at = _epoch_to_iso(fetched_epoch)
    try:
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        # Atomic tmp + os.replace (mirrors transport._save_prefs in this same
        # tree): a reader of this cache entry must never see a half-written
        # (torn) JSON file from a concurrent writer/crash. The tmp name itself
        # is per-writer-unique (see _tmp_write_path) so two concurrent
        # same-URL writers never alias one tmp inode.
        fd, tmp_name = _tmp_write_path(path)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump({"_fetched_at": fetched_at, "_fetched_epoch": fetched_epoch,
                           "_body": body}, fh)
            os.replace(tmp_name, str(path))
        except Exception:
            try:
                os.remove(tmp_name)
            except OSError:
                pass
            raise
    except Exception as exc:  # noqa: BLE001 -- cache write must never sink a fetch
        logger.debug("odds cache write skipped for %s: %s", url, exc)
    return body, fetched_at, False


def _epoch_to_iso(epoch: float) -> str:
    from datetime import datetime, timezone
    return datetime.fromtimestamp(epoch, tz=timezone.utc).isoformat(timespec="seconds")


def _unwrap(stored: Any, path: Path) -> Tuple[Any, str, float]:
    """Pull (body, fetched_at_iso, fetched_epoch) out of a stored cache entry.

    New entries are wrapped {"_fetched_at", "_fetched_epoch", "_body"}. A LEGACY
    entry (raw body, pre-LA-P0-a) has no wrapper -- we degrade its fetched time to
    the file mtime so even a legacy cached body carries a TRUE (never-now) time.
    """
    if isinstance(stored, dict) and "_body" in stored and "_fetched_at" in stored:
        epoch = stored.get("_fetched_epoch")
        if not isinstance(epoch, (int, float)):
            epoch = path.stat().st_mtime  # legacy wrapper without an epoch
        return stored["_body"], str(stored["_fetched_at"]), float(epoch)
    mtime = path.stat().st_mtime
    return stored, _epoch_to_iso(mtime), float(mtime)


def disk_cache_get(
    url: str,
    *,
    http_get: Callable[[str], Any] = http_get_json,
    ttl: float = DEFAULT_TTL_SECONDS,
    now: Callable[[], float] = time.time,
) -> Any:
    """Return cached JSON for *url* if fresher than *ttl*, else fetch + cache it.

    Back-compat shim over disk_cache_get_meta: returns ONLY the body (so legacy
    callers are unchanged). Callers that need the true fetched-at time (to avoid
    re-stamping a cached body as now()) should use disk_cache_get_meta instead.
    """
    body, _fetched_at, _hit = disk_cache_get_meta(
        url, http_get=http_get, ttl=ttl, now=now)
    return body


__all__ = [
    "http_get_json",
    "disk_cache_get",
    "disk_cache_get_meta",
    "DEFAULT_TTL_SECONDS",
    "RETRY_ATTEMPTS",
]
