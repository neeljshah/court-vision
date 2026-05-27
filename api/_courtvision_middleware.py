"""_courtvision_middleware.py — slowapi rate limit + CSP middleware.

Imported by api.courtvision_router and attached to the FastAPI app by
api.main via courtvision_router.register_with_app(app).
"""
from __future__ import annotations

import os

_CSP = (
    "default-src 'self'; "
    "script-src 'self' https://cdn.tailwindcss.com https://unpkg.com 'unsafe-inline'; "
    "style-src 'self' https://cdn.tailwindcss.com 'unsafe-inline'; "
    "img-src 'self' data:; "
    "connect-src 'self'; "
    "frame-ancestors 'none'; "
    "base-uri 'self'"
)

_PUBLIC_PREFIXES = (b"/tonight", b"/parlays", b"/share", b"/plus_ev")

_HEADERS_TO_ADD = (
    (b"content-security-policy", _CSP.encode()),
    (b"referrer-policy", b"strict-origin-when-cross-origin"),
    (b"x-content-type-options", b"nosniff"),
    (b"permissions-policy",
     b"interest-cohort=(), geolocation=(), microphone=()"),
)


def _csp_middleware_class():
    """Pure-ASGI middleware that appends CSP/security headers on public HTML routes.

    Avoids BaseHTTPMiddleware (which buffers the full response body — fatal for
    streaming endpoints like SSE).
    """
    class _CSPMiddleware:
        def __init__(self, app):
            self.app = app

        async def __call__(self, scope, receive, send):
            if scope.get("type") != "http":
                return await self.app(scope, receive, send)
            path = scope.get("path", "").encode()
            if not any(path.startswith(p) for p in _PUBLIC_PREFIXES):
                return await self.app(scope, receive, send)

            async def send_wrapper(message):
                if message["type"] == "http.response.start":
                    headers = list(message.get("headers", []))
                    existing = {h[0].lower() for h in headers}
                    for k, v in _HEADERS_TO_ADD:
                        if k not in existing:
                            headers.append((k, v))
                    message["headers"] = headers
                await send(message)

            return await self.app(scope, receive, send_wrapper)

    return _CSPMiddleware


def install(app, limiter) -> None:
    """Attach slowapi limiter + CSP middleware. No-op when disabled by env var."""
    if os.environ.get("COURTVISION_DISABLE_RATELIMIT") == "1":
        return
    if limiter is not None:
        try:
            from slowapi.errors import RateLimitExceeded
            from slowapi import _rate_limit_exceeded_handler
            app.state.limiter = limiter
            app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
        except Exception:
            pass
    app.add_middleware(_csp_middleware_class())
