"""scripts.platformkit.odds_provider.stealth_fetch -- browser-TLS-impersonated GET.

THE GAP: some odds sources bot-wall a plain urllib client (401/403, or an HTML
challenge page served where JSON was expected) even though the same endpoint is
publicly reachable from an ordinary browser. The `scrapling` package (installed
with the [fetchers] extra) drives a real browser-TLS fingerprint (impersonate=
'chrome') that clears these walls without any credential or scraping-behind-
login. This module is the STEALTH TIER -- used only as a fallback (see
transport.py), never the default path.

Honesty: this is still a read-only GET of a public endpoint (same contract as
http_cache.http_get_json) -- no auth bypass, no login, no fabricated data. A
non-2xx response raises urllib.error.HTTPError with the REAL status code so the
caller's existing transient/blocked classification logic composes unchanged.

Everything is injectable for offline tests: pass a fake `fetcher(url, **kwargs)`
that returns an object exposing `.status` (int) and `.body` (str) and neither
scrapling nor the network is ever touched.

Install: pip install "scrapling[fetchers]"  (already installed in this env,
version >=0.4.9; NOT required for the rest of odds_provider to import/run --
its absence just means the stealth tier is unavailable and transport.py falls
back to the plain path only).
"""
from __future__ import annotations

import json
import logging
import urllib.error
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

_UA_ACCEPT = {"Accept": "application/json"}

# Cached availability check result (None = not yet checked).
_available_cache: Optional[bool] = None


class StealthUnavailable(RuntimeError):
    """Raised when the scrapling package is not importable in this environment."""


def _silence_scrapling_logger() -> None:
    """scrapling prints INFO-level fetch lines to stdout by default; keep it quiet
    (WARNING+) so a stealth fallback does not spam the console on every fetch."""
    logging.getLogger("scrapling").setLevel(logging.WARNING)


def stealth_available() -> bool:
    """True iff the scrapling package (with its [fetchers] extra) is importable.

    Lazy + cached: the import is attempted at most once per process.
    """
    global _available_cache
    if _available_cache is not None:
        return _available_cache
    try:
        from scrapling.fetchers import Fetcher  # noqa: F401
        _available_cache = True
    except Exception:  # noqa: BLE001 -- any import failure means unavailable
        _available_cache = False
    return _available_cache


def _real_fetcher(url: str, *, timeout: float) -> Any:
    """The real scrapling call. Only imported/invoked when actually used."""
    from scrapling.fetchers import Fetcher
    _silence_scrapling_logger()
    return Fetcher.get(url, impersonate="chrome", timeout=timeout,
                       headers=dict(_UA_ACCEPT))


def stealth_get_json(
    url: str,
    timeout: float = 20.0,
    *,
    fetcher: Optional[Callable[..., Any]] = None,
) -> Any:
    """GET *url* via a browser-TLS-impersonated fetch and parse the JSON body.

    Raises StealthUnavailable if scrapling is not importable (unless *fetcher* is
    injected, in which case the availability check is skipped -- tests never need
    the real package). Raises urllib.error.HTTPError (built with the response's
    REAL status code) on any non-2xx response so callers' existing transient /
    blocked-shaped classification composes unchanged. A JSON parse failure
    propagates as the normal json.JSONDecodeError / ValueError.
    """
    if fetcher is None:
        if not stealth_available():
            raise StealthUnavailable(
                "scrapling is not importable; install with: "
                'pip install "scrapling[fetchers]"')
        _silence_scrapling_logger()
        response = _real_fetcher(url, timeout=timeout)
    else:
        response = fetcher(url, timeout=timeout)

    status = int(getattr(response, "status", 200))
    if status >= 400:
        raise urllib.error.HTTPError(url, status, "stealth fetch failed", None, None)

    body = getattr(response, "body", None)
    if body is None:
        body = getattr(response, "text", None)
    if isinstance(body, bytes):
        body = body.decode("utf-8", errors="replace")
    return json.loads(body)


__all__ = ["stealth_available", "stealth_get_json", "StealthUnavailable"]
