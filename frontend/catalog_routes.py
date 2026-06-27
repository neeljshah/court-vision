"""frontend.catalog_routes -- the unified-gateway CATALOG + single honesty bit.

WAVE 4. Two read-only endpoints over the gateway FACES registry (no number):

  GET /api/catalog
      Lists the contracted faces (prediction / execution / lines / intelligence)
      with their version, capabilities, route prefixes, and honest_note, plus the
      product-wide rails (units only, edge_claimed=False, real_money_enabled=False).

  GET /api/status.all_honest
      THE single boolean. ok=True ONLY if NO face is serving a $ field, a
      fabricated edge, a stale-green, or real-money-enabled -- and flips False the
      INSTANT any does. The verdict scans the DECLARED FaceSpec rails always, and
      (when the gateway can cheaply probe the live faces) the live bodies too. A
      ?inject= test hook lets a caller assert the bit flips False under a violation
      WITHOUT mutating the real registry (the injected probe body is scanned only).

Both endpoints pass through a keyless rate guard. Units only; no $; no secrets.

INVARIANTS: build only under frontend/; <=300 LOC; ASCII only; no $ key; no secrets.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

try:
    from fastapi import APIRouter, Depends, Query
    from fastapi.responses import JSONResponse
except Exception as exc:  # pragma: no cover -- fastapi required at runtime
    raise ImportError("frontend.catalog_routes requires fastapi.") from exc

from scripts.platformkit.gateway.catalog import all_honest, catalog
from frontend.rate_limit import get_default_limiter, rate_limit_dependency
from predict_service.honest_route import honest_route

router = APIRouter()

_guard = rate_limit_dependency(get_default_limiter())


@router.get("/api/catalog", dependencies=[Depends(_guard)])
@honest_route(extra={"faces": [], "count": 0, "real_money_enabled": False})
def get_catalog() -> JSONResponse:
    """List the contracted gateway faces + the standing rails. Never raises."""
    try:
        body = catalog()
    except Exception as exc:  # noqa: BLE001 -- catalog is pure; belt + braces
        logger.warning("catalog_routes /api/catalog failed: %s", exc)
        body = {"status": "error", "faces": [], "count": 0,
                "edge_claimed": False, "real_money_enabled": False,
                "reason": "catalog unavailable (%s)" % type(exc).__name__}
    return JSONResponse(body)


def _parse_inject(inject: Optional[str]) -> List[Any]:
    """Parse the ?inject= test hook (a JSON object or array) into a probe list."""
    if not inject:
        return []
    try:
        obj = json.loads(inject)
    except Exception:  # noqa: BLE001 -- a bad inject is ignored, never fatal
        logger.debug("catalog_routes: ignoring unparseable inject=%r", inject)
        return []
    if isinstance(obj, list):
        return obj
    return [obj]


@router.get("/api/status.all_honest", dependencies=[Depends(_guard)])
@honest_route(extra={"ok": False, "violations": [
    {"face": "_internal", "reason": "honesty verdict route raised"}], "n_faces": 0})
def get_all_honest(
    inject: Optional[str] = Query(
        default=None,
        description="TEST HOOK: a JSON face-body (or array) probed for a "
                    "violation. The real registry is never mutated."),
) -> JSONResponse:
    """The single honesty bit. True iff NO face violates a rail. Never raises.

    Scans the DECLARED FaceSpec rails always. When ?inject= carries a JSON body,
    that body is probed as a LIVE face response -- so a caller can prove the bit
    flips False under an injected $/stale/real-money/edge violation. Without inject
    the bit reflects the registry's declared honesty.
    """
    probe = _parse_inject(inject)
    try:
        verdict = all_honest(probe=probe)
    except Exception as exc:  # noqa: BLE001 -- ambiguity reads DISHONEST, never green
        logger.warning("catalog_routes /api/status.all_honest failed: %s", exc)
        verdict = {"ok": False, "violations": [
            {"face": "_internal", "reason": "verdict computation failed (%s)"
             % type(exc).__name__}], "n_faces": 0}
    return JSONResponse(verdict)


__all__ = ["router"]
