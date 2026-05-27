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

_PUBLIC_PREFIXES = ("/tonight", "/parlays", "/share", "/plus_ev")


def _csp_middleware_class():
    from starlette.middleware.base import BaseHTTPMiddleware

    class _CSPMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request, call_next):
            response = await call_next(request)
            if request.url.path.startswith(_PUBLIC_PREFIXES):
                h = response.headers
                h.setdefault("Content-Security-Policy", _CSP)
                h.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
                h.setdefault("X-Content-Type-Options", "nosniff")
                h.setdefault("Permissions-Policy",
                             "interest-cohort=(), geolocation=(), microphone=()")
            return response

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
