"""scripts.platformkit.odds_provider.browser_fetch -- headless-browser-render GET.

THE GAP (tier 3): a small number of sources bot-wall BOTH the plain urllib client
(http_cache) AND the browser-TLS-impersonated stealth tier (stealth_fetch) --
e.g. a JS-challenge wall that only clears once real JavaScript executes in a
real rendering engine (no TLS-fingerprint spoof substitutes for that). This
module drives an actual headless browser page load via scrapling's
`DynamicFetcher` (Playwright/Chromium-backed) as the LAST-RESORT tier. It is
used only as a fallback of a fallback (see transport.py's tier-3 branch),
never the default path, and never wired into any capture loop in this change.

ENVIRONMENT FINDING (2026-07-04, this box, scrapling 0.4.9): scrapling ships
TWO browser-backed fetchers. `StealthyFetcher` needs the `camoufox` package
(a separate Firefox-based stealth browser) which is NOT installed here --
`import camoufox` fails with ModuleNotFoundError. `DynamicFetcher` needs only
`playwright` (already installed + Chromium already provisioned in this env)
and WORKS: a live headless fetch of https://example.com returned a real 200
with parseable body. This module therefore standardizes on `DynamicFetcher`.
To add the camoufox-backed tier later: `pip install camoufox[geoip]` then
`python -m camoufox fetch` (run in a restart window, never mid-daemon-run --
see the no-pip-install-while-daemons-run invariant).

KNOWN LIMITATION (verified live on this box): scrapling's `DynamicFetcher`
calls Playwright's `page.goto(url, referer=...)` with the default
`wait_until="load"`. Chromium's `load` navigation lifecycle treats certain
non-2xx responses as a hard navigation failure (`net::ERR_HTTP_RESPONSE_CODE_
FAILURE`) BEFORE a Response object is ever constructed -- confirmed against
raw Playwright (which returns `resp.status` cleanly for the same URL) that
this is a scrapling-wrapper behavior, not a Playwright limitation, and it is
out of scope to patch a third-party package here. Practically: a real 4xx/5xx
from a tier-3 target surfaces as `BrowserBlockedShape` (status unknown) rather
than an `HTTPError` carrying the real numeric code. A 2xx response (including
the Akamai-style 200-trap: HTML/challenge body served with a 200 where JSON
was expected) is unaffected and surfaces exactly like the other tiers --
`.status`/`.body`, JSON-parse failure propagates as ValueError.

Honesty: still a read-only GET of a public endpoint (same contract as
http_cache.http_get_json / stealth_fetch.stealth_get_json) -- no auth bypass,
no login, no fabricated data. Headless only; never opens a visible window.
One page-load per call, no session/context reuse in v1 (simple + honest --
reuse is a possible v2 if a caller needs many requests to the same host).

Everything is injectable for offline tests: pass a fake `fetcher(url, **kwargs)`
that returns an object exposing `.status` (int) and `.body` (str/bytes) and
neither scrapling nor the network is ever touched.
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

# Substring Chromium raises for a non-2xx response BEFORE a Response object
# exists (see KNOWN LIMITATION above). Matched loosely (not a hard equality)
# since scrapling formats the full navigation error message around it.
_NAV_BLOCKED_MARKER = "ERR_HTTP_RESPONSE_CODE_FAILURE"


class BrowserUnavailable(RuntimeError):
    """Raised when scrapling's DynamicFetcher (Playwright-backed) is not usable
    in this environment (package missing, or its browser binary not provisioned)."""


class BrowserBlockedShape(RuntimeError):
    """Raised when the browser navigation itself failed in a way that looks like
    a bot-wall (non-2xx before a Response was constructed) -- see the KNOWN
    LIMITATION docstring: the real numeric status code is not recoverable from
    scrapling's DynamicFetcher in that failure path, so this carries no `.code`
    (unlike urllib.error.HTTPError from the other two tiers)."""


def _silence_scrapling_logger() -> None:
    """scrapling prints INFO-level fetch lines to stdout by default; keep it quiet
    (WARNING+) so a browser fallback does not spam the console on every fetch."""
    logging.getLogger("scrapling").setLevel(logging.WARNING)


def browser_available() -> bool:
    """True iff scrapling's DynamicFetcher (Playwright-backed) is importable AND
    its browser binary is actually launchable in this environment.

    Lazy + cached: the check is attempted at most once per process. A cheap,
    real (network-free) local launch+close is used to confirm the Chromium
    binary is provisioned, not just that the Python package imports -- an
    import-only check would false-positive if playwright is installed but
    `playwright install` was never run.
    """
    global _available_cache
    if _available_cache is not None:
        return _available_cache
    try:
        from scrapling.fetchers import DynamicFetcher  # noqa: F401
        from playwright.sync_api import sync_playwright
        _silence_scrapling_logger()
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            browser.close()
        _available_cache = True
    except Exception as exc:  # noqa: BLE001 -- any failure means unavailable
        logger.debug("browser tier unavailable: %s", exc)
        _available_cache = False
    return _available_cache


def _real_fetcher(url: str, *, timeout: float) -> Any:
    """The real scrapling call. Only imported/invoked when actually used."""
    from scrapling.fetchers import DynamicFetcher
    _silence_scrapling_logger()
    return DynamicFetcher.fetch(
        url, headless=True, disable_resources=True,
        timeout=timeout * 1000.0, extra_headers=dict(_UA_ACCEPT))


def browser_get_json(
    url: str,
    timeout: float = 30.0,
    *,
    fetcher: Optional[Callable[..., Any]] = None,
) -> Any:
    """GET *url* via a real headless-browser page load and parse the JSON body.

    Raises BrowserUnavailable if the browser tier is not usable (unless
    *fetcher* is injected, in which case the availability check is skipped --
    tests never need the real package/binary). Raises urllib.error.HTTPError
    (built with the REAL status code) on a non-2xx response that still
    produced a Response object, so callers' existing transient/blocked
    classification composes unchanged. Raises BrowserBlockedShape (no real
    status recoverable -- see KNOWN LIMITATION) when the navigation itself
    failed in a blocked-looking way. A JSON parse failure on a 2xx response
    (the 200-trap case) propagates as the normal json.JSONDecodeError/
    ValueError, matching the other tiers.
    """
    if fetcher is None:
        if not browser_available():
            raise BrowserUnavailable(
                "browser tier unavailable: scrapling's DynamicFetcher needs "
                "playwright with a provisioned Chromium binary. If playwright "
                "is missing: pip install playwright && playwright install "
                "chromium (run in a restart window, never mid-daemon-run).")
        _silence_scrapling_logger()
        try:
            response = _real_fetcher(url, timeout=timeout)
        except BaseException as exc:  # noqa: BLE001 -- classify nav failure
            if _NAV_BLOCKED_MARKER in str(exc):
                raise BrowserBlockedShape(
                    f"browser navigation blocked-shaped for {url}: {exc}") from exc
            raise
    else:
        response = fetcher(url, timeout=timeout)

    status = int(getattr(response, "status", 200))
    if status >= 400:
        raise urllib.error.HTTPError(url, status, "browser fetch failed", None, None)

    body = getattr(response, "body", None)
    if body is None:
        body = getattr(response, "text", None)
    if isinstance(body, bytes):
        body = body.decode("utf-8", errors="replace")
    return json.loads(body)


__all__ = [
    "browser_available",
    "browser_get_json",
    "BrowserUnavailable",
    "BrowserBlockedShape",
]
