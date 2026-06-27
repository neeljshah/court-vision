"""frontend.rate_limit -- a simple keyless in-process rate guard for the gateway.

WAVE 4. The unified gateway is keyless (no auth, no $ tier). A single shared,
fixed-window counter per client keeps an abusive caller from starving the others
without requiring an API key. This is intentionally minimal: in-process, no
external store, time-injectable for tests, and total (a guard failure NEVER blocks
a legitimate request -- it fails OPEN, since the product is read-only and honest).

Public API
----------
RateLimiter(limit, window_sec)
    .check(client_id, *, now=None) -> (allowed: bool, retry_after_sec: float)
        Fixed-window: at most `limit` calls per `window_sec` per client_id. When
        the window rolls over the count resets. allowed=False returns the seconds
        until the window resets so the caller can surface a 429 honestly.
    .reset() -> None   (test convenience)

rate_limit_dependency(limiter)
    A FastAPI dependency factory: returns a callable that raises HTTPException 429
    when a client is over the limit. client_id is the request client host (keyless).

INVARIANTS: build only under frontend/; <=300 LOC; ASCII only; no secrets; no $.
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Callable, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

# Imported at module scope so a FastAPI dependency's `request: Request` annotation
# resolves via get_type_hints (which evaluates against module globals, not the
# closure). Guarded: absent fastapi/starlette degrades the dependency to a no-op.
try:  # pragma: no cover -- starlette ships with fastapi
    from starlette.requests import Request as _Request
except Exception:  # noqa: BLE001
    _Request = None  # type: ignore

DEFAULT_LIMIT = 120          # requests per window per client
DEFAULT_WINDOW_SEC = 60.0    # 1-minute fixed window


class RateLimiter:
    """A thread-safe fixed-window keyless rate limiter (in-process, no store)."""

    def __init__(self, limit: int = DEFAULT_LIMIT,
                 window_sec: float = DEFAULT_WINDOW_SEC) -> None:
        self.limit = int(limit)
        self.window_sec = float(window_sec)
        # client_id -> (window_start_epoch, count_in_window)
        self._buckets: Dict[str, Tuple[float, int]] = {}
        self._lock = threading.Lock()

    def _now(self, now: Optional[float]) -> float:
        return float(now) if now is not None else time.time()

    def check(self, client_id: str,
              *, now: Optional[float] = None) -> Tuple[bool, float]:
        """Return (allowed, retry_after_sec) for *client_id* under the window.

        Allowed when the client has made fewer than `limit` calls in the current
        window. On the call that crosses the limit, allowed=False and retry_after
        is the seconds remaining until the window resets. Total: any internal
        failure fails OPEN (allowed=True) -- a read-only honest API must not 500 a
        legitimate caller over its own rate bookkeeping.
        """
        try:
            cid = str(client_id or "anon")
            t = self._now(now)
            with self._lock:
                start, count = self._buckets.get(cid, (t, 0))
                if t - start >= self.window_sec:
                    start, count = t, 0  # window rolled over -> reset
                if count >= self.limit:
                    retry = max(0.0, self.window_sec - (t - start))
                    self._buckets[cid] = (start, count)
                    return False, retry
                self._buckets[cid] = (start, count + 1)
                return True, 0.0
        except Exception as exc:  # noqa: BLE001 -- fail OPEN, never block on our bug
            logger.warning("rate_limit.check failed (fail-open): %s", exc)
            return True, 0.0

    def reset(self) -> None:
        """Clear all buckets (test convenience)."""
        with self._lock:
            self._buckets.clear()


# A module-level default limiter shared by the gateway routes (keyless).
_DEFAULT_LIMITER = RateLimiter()


def get_default_limiter() -> RateLimiter:
    """Return the shared module-level limiter."""
    return _DEFAULT_LIMITER


def rate_limit_dependency(limiter: Optional[RateLimiter] = None) -> Callable:
    """Build a FastAPI dependency that 429s an over-limit keyless client.

    The dependency derives a keyless client_id from request.client.host and calls
    limiter.check(). Over the limit -> HTTPException(429) with a Retry-After hint.
    A FastAPI/Starlette import failure degrades to a no-op dependency (fail-open).
    """
    lim = limiter or _DEFAULT_LIMITER
    if _Request is None:  # without fastapi/starlette this is a no-op guard
        def _noop() -> None:
            return None
        return _noop
    from fastapi import HTTPException

    def _dep(request: _Request) -> None:
        client = getattr(request, "client", None)
        cid = getattr(client, "host", None) or "anon"
        allowed, retry = lim.check(cid)
        if not allowed:
            raise HTTPException(
                status_code=429,
                detail="rate limit exceeded (keyless gateway)",
                headers={"Retry-After": str(int(retry) + 1)},
            )
        return None

    return _dep


__all__ = ["RateLimiter", "rate_limit_dependency", "get_default_limiter",
           "DEFAULT_LIMIT", "DEFAULT_WINDOW_SEC"]
