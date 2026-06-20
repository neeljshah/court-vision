"""predict_service.honest_route -- the SHARED honest-envelope route decorator.

W3 ROBUSTNESS (BACKEND lane). The mount-level guards in core_mounts/extra_mounts
already catch a router's IMPORT-time failure. This closes the remaining coverage
GAP: a router that imports cleanly but RAISES INSIDE A HANDLER at request time
would otherwise leak a 500 + Python stack traceback to the browser. That is a
crash, not an honest degradation.

@honest_route wraps a FastAPI handler so that ANY exception it raises is converted
into an honest, units-only {status:"unavailable", reason, edge_claimed:False}
envelope served with a chosen status code (default 503) -- NEVER a stack, NEVER a
fabricated value, NEVER a fabricated green. The reason carries only the EXCEPTION
TYPE NAME (e.g. "ValueError"), never the message/args/traceback, so no internal
detail or accidental secret leaks to the client. A handler that returns normally
is passed through untouched (zero behavior change on the happy path).

This does NOT weaken any existing honest behavior: a handler that already returns
an explicit unavailable sentinel keeps doing so; the decorator only intercepts the
UNHANDLED-exception path that previously produced a 500 stack.

Both sync and async handlers are supported. The decorator preserves the wrapped
function's signature (via functools.wraps) so FastAPI's dependency-injection and
path/query parameter binding are unaffected.

INVARIANTS: build only under predict_service/; <=300 LOC; ASCII only; no secrets;
no $ field; reuse JSONResponse; never re-raises to the framework.
"""
from __future__ import annotations

import functools
import inspect
import logging
from typing import Any, Callable, Optional

try:
    from fastapi.responses import JSONResponse
except Exception as exc:  # pragma: no cover -- fastapi required at runtime
    raise ImportError("predict_service.honest_route requires fastapi.") from exc

logger = logging.getLogger(__name__)

# The default HTTP code for an honest degradation. 503 == "the service is up but
# this surface is temporarily unavailable" -- the correct semantics for a feed/
# router that could not produce a real answer. NEVER 500 (which reads as a crash).
DEFAULT_STATUS_CODE = 503


def honest_envelope(
    reason: str,
    *,
    where: str = "",
    extra: Optional[dict] = None,
) -> dict:
    """Build the canonical honest-degradation body. Units only; no $; no stack.

    The body always carries status='unavailable' and edge_claimed=False. *extra*
    lets a caller seed shape-stable empty fields (e.g. rows=[], count=0) so the UI
    degrades on a familiar shape rather than a bare sentinel. A forbidden $/edge
    key in *extra* is dropped defensively (the units-only rail is never widened
    by a degradation body).
    """
    body: dict = {
        "status": "unavailable",
        "reason": reason,
        "edge_claimed": False,
    }
    if where:
        body["where"] = where
    if extra:
        for k, v in extra.items():
            kl = str(k).lower()
            # Never let a degradation body smuggle a $/edge key past the rail.
            if kl in body:
                continue
            words = set(kl.replace("-", "_").split("_"))
            if words & _FORBIDDEN_MONEY_TOKENS:
                continue
            body[k] = v
    return body


# A degradation body must never introduce a money/edge key (belt + braces with
# honesty_mw, which would otherwise fail-closed on it -- but we never want a
# degradation to itself trip the linter).
_FORBIDDEN_MONEY_TOKENS = frozenset({
    "pnl", "roi", "bankroll", "profit", "dollar", "dollars", "usd", "stake",
})


def _build_failure_response(
    exc: BaseException,
    *,
    name: str,
    status_code: int,
    extra: Optional[dict],
) -> JSONResponse:
    """Turn a caught exception into the honest 503 envelope (type name only)."""
    # CRITICAL: surface ONLY the exception TYPE NAME, never str(exc) -- the message
    # may contain a path, a query, or an accidental secret. No traceback is served.
    reason = "%s raised (%s)" % (name or "handler", type(exc).__name__)
    body = honest_envelope(reason, where=name, extra=extra)
    return JSONResponse(body, status_code=status_code)


def honest_route(
    _fn: Optional[Callable] = None,
    *,
    status_code: int = DEFAULT_STATUS_CODE,
    extra: Optional[dict] = None,
) -> Callable:
    """Decorate a FastAPI handler so an UNHANDLED exception -> honest 503 envelope.

    Usage (both forms supported)::

        @router.get("/api/x")
        @honest_route
        def x(): ...

        @router.get("/api/y")
        @honest_route(status_code=503, extra={"rows": [], "count": 0})
        def y(): ...

    On the happy path the wrapped handler's return value is passed through
    UNCHANGED. On an exception, a {status:'unavailable', reason} body is returned
    (the reason is the exception TYPE NAME only). The wrapper NEVER re-raises, so a
    500 stack can never reach the browser. Supports sync and async handlers.
    """

    def _decorate(fn: Callable) -> Callable:
        name = getattr(fn, "__name__", "handler")

        if inspect.iscoroutinefunction(fn):

            @functools.wraps(fn)
            async def _async_wrapper(*args: Any, **kwargs: Any):
                try:
                    return await fn(*args, **kwargs)
                except Exception as exc:  # noqa: BLE001 -- the WHOLE POINT: no leak
                    logger.warning(
                        "honest_route: handler %s raised %s -> honest 503",
                        name, type(exc).__name__)
                    return _build_failure_response(
                        exc, name=name, status_code=status_code, extra=extra)

            return _async_wrapper

        @functools.wraps(fn)
        def _sync_wrapper(*args: Any, **kwargs: Any):
            try:
                return fn(*args, **kwargs)
            except Exception as exc:  # noqa: BLE001 -- the WHOLE POINT: no leak
                logger.warning(
                    "honest_route: handler %s raised %s -> honest 503",
                    name, type(exc).__name__)
                return _build_failure_response(
                    exc, name=name, status_code=status_code, extra=extra)

        return _sync_wrapper

    # Support both @honest_route and @honest_route(...).
    if _fn is not None and callable(_fn):
        return _decorate(_fn)
    return _decorate


__all__ = ["honest_route", "honest_envelope", "DEFAULT_STATUS_CODE"]
