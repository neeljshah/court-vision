"""predict_service.frontend._guarded_mounts -- overflow mount helpers for core_mounts.

Factored out from predict_service.core_mounts to keep that file under the <=300
LOC cap. Contains two guarded router-include helpers that are called by
core_mounts.register(app); not intended for direct external use.

HONESTY: no $ field; every fallback carries edge_claimed=False; a degraded mount
returns an explicit 503 'unavailable' sentinel (never a silent 404, never green).
INVARIANTS: <=300 LOC; ASCII only; no secrets; no $-edge fabrication.
"""
from __future__ import annotations

import logging

from fastapi.responses import JSONResponse

from predict_service.contracts import HONEST_NOTE

logger = logging.getLogger(__name__)


def _mount_funnel(app) -> None:  # noqa: ANN001
    """Gate-verdict ledger + improvement backlog: /api/funnel/ledger,
    /api/meta/backlog. Read-only over on-disk honest artifacts; no $ field."""
    try:
        from frontend.funnel_routes import router as _funnel_router  # noqa: PLC0415
        app.include_router(_funnel_router)
        logger.info("core_mounts: funnel_routes mounted at "
                    "/api/funnel/ledger,/api/meta/backlog")
    except Exception as exc:  # noqa: BLE001
        logger.warning("core_mounts: funnel_routes not mounted (%s: %s)",
                       type(exc).__name__, exc)

        @app.get("/api/funnel/ledger")
        def _funnel_ledger_unavailable() -> JSONResponse:  # noqa: ANN202
            return JSONResponse(
                {"status": "unavailable",
                 "reason": "funnel_routes failed to load",
                 "rows": [], "n": 0, "counts": {}, "edge_claimed": False},
                status_code=503)

        @app.get("/api/meta/backlog")
        def _meta_backlog_unavailable() -> JSONResponse:  # noqa: ANN202
            return JSONResponse(
                {"status": "unavailable",
                 "reason": "funnel_routes failed to load",
                 "candidates": [], "n": 0, "categories": [],
                 "edge_claimed": False},
                status_code=503)


def _mount_lines_matrix(app) -> None:  # noqa: ANN001
    """Multi-book line shopping matrix + NBA-aware prop board.

    W1 (api-lines): GET /api/lines/{sport}/{game_id} (per-market book matrix +
    best-line per market with PM separation) and GET /api/props/{sport} (cross-
    source prop best-line board; degrades to UNAVAILABLE for NBA in offseason).
    No $ field; stale-never-green; edge_claimed=False.
    """
    try:
        from predict_service.frontend.lines_matrix_routes import (  # noqa: PLC0415
            router as _lines_matrix_router,
        )
        app.include_router(_lines_matrix_router)
        logger.info("core_mounts: lines_matrix_routes mounted at "
                    "/api/lines/{sport}/{game_id} + /api/props/{sport}")
    except Exception as exc:  # noqa: BLE001
        logger.warning("core_mounts: lines_matrix_routes not mounted (%s: %s)",
                       type(exc).__name__, exc)

        @app.get("/api/lines/{sport}/{game_id}")
        def _lines_matrix_unavailable(sport: str,
                                      game_id: str) -> JSONResponse:  # noqa: ANN202
            return JSONResponse(
                {"status": "UNAVAILABLE", "sport": sport, "game_id": game_id,
                 "reason": "lines_matrix_routes failed to load",
                 "markets": {}, "best": {}, "edge_claimed": False},
                status_code=503)

        @app.get("/api/props/{sport}")
        def _props_board_unavailable(sport: str) -> JSONResponse:  # noqa: ANN202
            return JSONResponse(
                {"status": "UNAVAILABLE", "sport": sport,
                 "reason": "lines_matrix_routes failed to load",
                 "props": [], "count": 0, "edge_claimed": False},
                status_code=503)


__all__ = ["_mount_funnel", "_mount_lines_matrix"]
