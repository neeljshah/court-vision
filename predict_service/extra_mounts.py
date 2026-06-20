"""predict_service.extra_mounts -- register the Phase-1 + W2 backend routers.

Keeps predict_service.app focused (and under the LOC budget) by factoring the
guarded include_router blocks for the new Phase-1 endpoints into one place:

  * BE-P0-04  GET /api/produce/status + POST /api/produce/refresh
  * BE-P1-01  GET /api/lines/{sport}              (all-books board)
  * BE-P0-05  GET /api/lines/{sport}/{game_id}/history
  * BE-P1-06  GET /api/gate/status
  * BE-P0-09  GET /api/results/{sport}
  * W2        GET /api/predict/props/{sport}
              GET /api/predict/props/{sport}/{game_id}

Each router is mounted GUARDED: an import/boot failure is caught + logged and a
503 'unavailable' sentinel route is registered in its place, so a single bad
module can never sink the rest of the API. register(app) is called once from
predict_service.app.

HONESTY: no $ field; every fallback carries edge_claimed=False and a stale/absent
producer reads ok=False (stale-never-green). Read-only / guarded.

INVARIANTS: build only under predict_service/; <=300 LOC; ASCII only; no secrets.
"""
from __future__ import annotations

import logging

from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


def _mount_produce(app) -> None:  # noqa: ANN001
    try:
        from predict_service.produce_status import router  # noqa: PLC0415
        app.include_router(router)
        logger.info("extra_mounts: produce_status mounted at /api/produce/*")
    except Exception as exc:  # noqa: BLE001
        logger.warning("extra_mounts: produce_status not mounted (%s: %s)",
                       type(exc).__name__, exc)

        @app.get("/api/produce/status")
        def _produce_status_unavailable() -> JSONResponse:  # noqa: ANN202
            return JSONResponse(
                {"status": "unavailable",
                 "reason": "produce_status failed to load",
                 "sports": [], "n_sports": 0, "any_fresh": False,
                 "edge_claimed": False},
                status_code=503)


def _mount_lines(app) -> None:  # noqa: ANN001
    try:
        from frontend.lines_routes import router  # noqa: PLC0415
        app.include_router(router)
        logger.info("extra_mounts: lines_routes mounted at /api/lines/*")
    except Exception as exc:  # noqa: BLE001
        logger.warning("extra_mounts: lines_routes not mounted (%s: %s)",
                       type(exc).__name__, exc)

        @app.get("/api/lines/{sport}")
        def _lines_unavailable(sport: str) -> JSONResponse:  # noqa: ANN202
            return JSONResponse(
                {"status": "unavailable", "sport": sport,
                 "reason": "lines_routes failed to load",
                 "lines": [], "count": 0, "edge_claimed": False},
                status_code=503)


def _mount_gate(app) -> None:  # noqa: ANN001
    try:
        from frontend.gate_routes import router  # noqa: PLC0415
        app.include_router(router)
        logger.info("extra_mounts: gate_routes mounted at /api/gate/status")
    except Exception as exc:  # noqa: BLE001
        logger.warning("extra_mounts: gate_routes not mounted (%s: %s)",
                       type(exc).__name__, exc)

        @app.get("/api/gate/status")
        def _gate_unavailable() -> JSONResponse:  # noqa: ANN202
            return JSONResponse(
                {"status": "ok", "paper_only": True, "real_money_enabled": False,
                 "eligible": False, "n_settled_true_close": None,
                 "threshold": None,
                 "reasons": ["gate_routes failed to load -- default-DENY"],
                 "edge_claimed": False},
                status_code=503)


def _mount_results(app) -> None:  # noqa: ANN001
    try:
        from frontend.results_routes import router  # noqa: PLC0415
        app.include_router(router)
        logger.info("extra_mounts: results_routes mounted at /api/results/*")
    except Exception as exc:  # noqa: BLE001
        logger.warning("extra_mounts: results_routes not mounted (%s: %s)",
                       type(exc).__name__, exc)

        @app.get("/api/results/{sport}")
        def _results_unavailable(sport: str) -> JSONResponse:  # noqa: ANN202
            return JSONResponse(
                {"status": "unavailable", "sport": sport,
                 "reason": "results_routes failed to load",
                 "results": [], "count": 0, "edge_claimed": False},
                status_code=503)


def _mount_progress(app) -> None:  # noqa: ANN001
    try:
        from predict_service.progress_router import router  # noqa: PLC0415
        app.include_router(router)
        logger.info("extra_mounts: progress_router mounted at /progress/*")
    except Exception as exc:  # noqa: BLE001
        logger.warning("extra_mounts: progress_router not mounted (%s: %s)",
                       type(exc).__name__, exc)

        @app.get("/progress/summary")
        def _progress_unavailable() -> JSONResponse:  # noqa: ANN202
            # Stale-never-green: a failed mount reads stale, never a fabricated green.
            return JSONResponse(
                {"status": "stale",
                 "reason": "progress_router failed to load",
                 "as_of": None, "latest": None, "history": [],
                 "model_static": True, "engine_enabled": False,
                 "edge_claimed": False},
                status_code=503)


def _mount_props(app) -> None:  # noqa: ANN001
    """W2 (api-props): player-prop prediction endpoints.

    GET /api/predict/props/{sport}            -- all props for sport
    GET /api/predict/props/{sport}/{game_id}  -- single-game props
    Degrades to UNAVAILABLE when no prop lines exist (NBA offseason, etc.).
    No $ field; clv_is_proxy=True; real-money default-DENY.
    """
    try:
        from predict_service.frontend.props_routes import router  # noqa: PLC0415
        app.include_router(router)
        logger.info("extra_mounts: props_routes mounted at /api/predict/props/*")
    except Exception as exc:  # noqa: BLE001
        logger.warning("extra_mounts: props_routes not mounted (%s: %s)",
                       type(exc).__name__, exc)

        @app.get("/api/predict/props/{sport}")
        def _props_unavailable(sport: str) -> JSONResponse:  # noqa: ANN202
            return JSONResponse(
                {"status": "UNAVAILABLE", "sport": sport,
                 "reason": "props_routes failed to load",
                 "rows": [], "count": 0,
                 "edge_claimed": False, "clv_is_proxy": True},
                status_code=503)

        @app.get("/api/predict/props/{sport}/{game_id}")
        def _props_game_unavailable(sport: str,
                                    game_id: str) -> JSONResponse:  # noqa: ANN202
            return JSONResponse(
                {"status": "UNAVAILABLE", "sport": sport, "game_id": game_id,
                 "reason": "props_routes failed to load",
                 "rows": [], "count": 0,
                 "edge_claimed": False, "clv_is_proxy": True},
                status_code=503)


def _mount_supervisor_status(app) -> None:  # noqa: ANN001
    """W-sup-route: GET /api/ops/supervisor -- real daemon state from disk.

    Reads data/frontend/ops/supervisor_status.json and returns the
    SupervisorStatus shape {live, any_degraded, reason, procs, updated_at ...}
    the FE LiveIndicator (p5api.getSupervisorStatus) expects.
    live=True ONLY when file is fresh AND all_ready AND no proc degraded.
    Missing/stale file -> status=unavailable, live=False, 503. Never green on
    missing/stale. No $ field. Stale-never-green.
    """
    try:
        from predict_service.frontend.supervisor_status_route import (  # noqa: PLC0415
            router as _sup_router,
        )
        app.include_router(_sup_router)
        logger.info(
            "extra_mounts: supervisor_status_route mounted at /api/ops/supervisor"
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "extra_mounts: supervisor_status_route not mounted (%s: %s)",
            type(exc).__name__, exc,
        )

        @app.get("/api/ops/supervisor")
        def _supervisor_status_unavailable() -> JSONResponse:  # noqa: ANN202
            return JSONResponse(
                {
                    "status": "unavailable",
                    "live": False,
                    "overall": "down",
                    "reason": "supervisor_status_route failed to load",
                    "all_ready": False,
                    "any_degraded": True,
                    "procs": [],
                    "restarts_total": 0,
                    "uptime_sec": None,
                    "age_sec": None,
                    "edge_claimed": False,
                },
                status_code=503,
            )


def register(app) -> None:  # noqa: ANN001
    """Mount all Phase-1 + W2 backend routers onto *app* (each guarded)."""
    _mount_produce(app)
    _mount_lines(app)
    _mount_gate(app)
    _mount_results(app)
    _mount_progress(app)
    _mount_props(app)
    _mount_supervisor_status(app)


__all__ = ["register"]
