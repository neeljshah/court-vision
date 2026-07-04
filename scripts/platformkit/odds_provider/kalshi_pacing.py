"""scripts.platformkit.odds_provider.kalshi_pacing -- request pacing + 429 detection.

Split out of inplay_kalshi.py (which is near the 300 LOC cap) so the LANE 1
(wave-16) pacing/429-observability fix has its own small, testable home.

THE PROBLEM (wave-16 evidence): the 6-sport widened in-play capture loop fires up
to 4 Kalshi series requests per sport per tick (kalshi_series_spec.SERIES_SPEC),
17 total across the 6 DEFAULT_SPORTS, back-to-back with zero inter-request gap,
every LIVE_INTERVAL_SEC=20s while any game is live. A shared-venue 429 wall (Kalshi
throttling the whole client, not per-series) then hits every remaining series in
the SAME burst; http_cache's own retry (3 attempts, 0.5-4s backoff) plus
transport's stealth escalation can together cost tens of seconds per throttled
series, occasionally exceeding the loop's own 20s cadence -- producing the observed
n_live=0 / all-games no_live_state heartbeat cycles. A 429 was indistinguishable
from a dead feed (inplay_kalshi._fetch_one_series caught it and returned [],
uncounted) so the SLA had no signal to page on.

This module supplies:
  * is_429(exc)            -- True iff exc is (or is shaped like) an HTTP 429.
  * retry_after_sec(exc)    -- Retry-After header value in seconds, if present.
  * stagger_sleep(sleep_fn, stagger_sec, is_first) -- the inter-request pacing
    call (a no-op before the first request in a batch).
  * cooldown_after_429(exc, sleep_fn, max_cooldown_sec) -- a short, capped pause
    (honoring Retry-After when the venue sends one) so the NEXT series request
    isn't fired immediately into the same throttle wall.
  * record_request(stats) / record_429(stats) -- in-place counters on an optional
    caller-owned dict, additive and None-safe (a caller that does not pass stats
    sees no behavior change at all).

Everything here is a pure/near-pure helper -- no network, no I/O, no imports of
inplay_kalshi (this module is imported BY inplay_kalshi, never the reverse).

INVARIANTS: build only under scripts/platformkit/; <=300 LOC; ASCII only; stdlib
only. Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/odds_provider/test_kalshi_pacing.py -q
"""
from __future__ import annotations

import logging
import time
import urllib.error
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger(__name__)

SleepFn = Callable[[float], None]

# Inter-series pacing: a small stagger between the up-to-4 series requests one
# fetch_inplay(sport) call fires, so a 6-sport cycle drips 17 requests instead of
# bursting them. At 0.3s x 17 = ~5.1s added worst-case per full cycle (well under
# the 20s LIVE_INTERVAL_SEC).
REQUEST_STAGGER_SEC = 0.3

# 429-specific short cool-down: distinct from http_cache's own transient retry
# (which already backs off 0.5-4s per call before reraising) -- this is an
# ADDITIONAL small pause taken between a 429'd series and the next one, so a
# shared-venue throttle gets a moment to clear before we hit it again, rather
# than hammering the next series immediately. Honors Retry-After (seconds form)
# when the venue sends one, capped PER SERIES at MAX_429_COOLDOWN_SEC. This caps
# the cost of any ONE throttled series, but a sustained storm hitting many/all 17
# series in one cycle is NOT bounded below the loop's cadence (worst case 17 x
# 2.0s = 34s > LIVE_INTERVAL_SEC=20s) -- now visible via cycle_duration_sec/
# n_429_total instead of silent; a per-cycle cooldown BUDGET cap is future work.
MAX_429_COOLDOWN_SEC = 2.0


def is_429(exc: BaseException) -> bool:
    """True iff *exc* is an HTTP 429 (urllib.error.HTTPError with code 429).

    http_cache's fallback retry re-raises the ORIGINAL exception on exhaustion,
    so a persistent 429 still surfaces here as an HTTPError -- nothing further
    to unwrap. A non-HTTPError (timeout, DNS, JSON parse) is never a 429.
    """
    return isinstance(exc, urllib.error.HTTPError) and exc.code == 429


def retry_after_sec(exc: BaseException) -> Optional[float]:
    """Retry-After header value in seconds, if the venue sent one. None-safe."""
    try:
        hdrs = getattr(exc, "headers", None)
        raw = hdrs.get("Retry-After") if hdrs is not None else None
        return float(raw) if raw is not None else None
    except (TypeError, ValueError):
        return None


def record_request(stats: Optional[Dict[str, Any]]) -> None:
    """Increment stats['n_requests'] in place. No-op if stats is None."""
    if stats is not None:
        stats["n_requests"] = stats.get("n_requests", 0) + 1


def record_429(stats: Optional[Dict[str, Any]]) -> None:
    """Increment stats['n_429'] in place. No-op if stats is None."""
    if stats is not None:
        stats["n_429"] = stats.get("n_429", 0) + 1


def stagger_sleep(sleep_fn: SleepFn, stagger_sec: float, *, is_first: bool) -> None:
    """Pace BETWEEN requests: sleeps *stagger_sec* via *sleep_fn*, skipped before
    the first request in a batch (is_first=True) and skipped entirely if
    stagger_sec<=0. Never raises -- a broken clock never sinks the caller."""
    if is_first or stagger_sec <= 0:
        return
    try:
        sleep_fn(stagger_sec)
    except Exception as exc:  # noqa: BLE001 -- a clock error never sinks the fetch
        logger.debug("kalshi inter-request stagger sleep failed: %s", exc)


def cooldown_after_429(exc: BaseException, sleep_fn: SleepFn,
                       max_cooldown_sec: float = MAX_429_COOLDOWN_SEC) -> None:
    """Short, capped pause after a detected 429 (honors Retry-After if given).

    Gives a shared-venue throttle wall a moment to clear before the caller's
    NEXT request goes out. Never raises -- a broken clock never sinks the fetch.
    """
    cooldown = retry_after_sec(exc)
    cooldown = max_cooldown_sec if cooldown is None else min(cooldown, max_cooldown_sec)
    try:
        sleep_fn(cooldown)
    except Exception as sleep_exc:  # noqa: BLE001 -- a clock error never sinks the fetch
        logger.debug("kalshi 429 cooldown sleep failed: %s", sleep_exc)


__all__ = [
    "REQUEST_STAGGER_SEC",
    "MAX_429_COOLDOWN_SEC",
    "is_429",
    "retry_after_sec",
    "record_request",
    "record_429",
    "stagger_sleep",
    "cooldown_after_429",
]
