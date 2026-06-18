"""scripts.platformkit.odds_provider.http_cache -- injectable HTTP + TTL disk cache.

`http_get_json` is the default network fetcher; every provider takes an injectable
`http_get` so tests run with ZERO network on canned payloads. `disk_cache_get`
wraps any fetcher with a TTL JSON file cache so we do not hammer free public
sources (Kalshi ~30 rps, ESPN/Polymarket unmetered but be polite).

No secrets here; tokens (if any) are read from ENV inside each provider.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import time
import urllib.request
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)

DEFAULT_TTL_SECONDS = 60.0  # live odds move fast; a short TTL is plenty.
_CACHE_DIR = Path(os.environ.get("ODDS_PROVIDER_CACHE_DIR",
                                 str(Path.home() / ".cache" / "courtvision_odds")))
_UA = "Mozilla/5.0 (CourtVision odds_provider; honest public-API client)"


def http_get_json(url: str, timeout: float = 20.0) -> Any:
    """GET *url* and parse JSON. HTTPS only; sends a polite UA + Accept header."""
    req = urllib.request.Request(
        url, headers={"Accept": "application/json", "User-Agent": _UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310 (https only)
        return json.loads(r.read().decode("utf-8", errors="replace"))


def _cache_path(url: str) -> Path:
    h = hashlib.sha256(url.encode("utf-8")).hexdigest()[:24]
    return _CACHE_DIR / f"{h}.json"


def disk_cache_get(
    url: str,
    *,
    http_get: Callable[[str], Any] = http_get_json,
    ttl: float = DEFAULT_TTL_SECONDS,
    now: Callable[[], float] = time.time,
) -> Any:
    """Return cached JSON for *url* if fresher than *ttl*, else fetch + cache it.

    A cache read/write failure is non-fatal -- we just fall back to a live fetch
    (or skip caching). *http_get* and *now* are injectable for tests.
    """
    path = _cache_path(url)
    try:
        if path.is_file():
            age = now() - path.stat().st_mtime
            if age < ttl:
                with path.open("r", encoding="utf-8") as fh:
                    return json.load(fh)
    except Exception as exc:  # noqa: BLE001 -- cache read must never sink a fetch
        logger.debug("odds cache read miss for %s: %s", url, exc)
    body = http_get(url)
    try:
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as fh:
            json.dump(body, fh)
    except Exception as exc:  # noqa: BLE001 -- cache write must never sink a fetch
        logger.debug("odds cache write skipped for %s: %s", url, exc)
    return body


__all__ = ["http_get_json", "disk_cache_get", "DEFAULT_TTL_SECONDS"]
